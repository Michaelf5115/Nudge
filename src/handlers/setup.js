/**
 * Team setup via SMS.
 *
 * State machine (stored in team.setup_state, a JSON column we'll treat as a field):
 *  1. Someone texts "setup" to the Twilio number
 *  2. Bot asks: "Welcome! What's your team name?"
 *  3. They reply with the name → team is created, they become admin
 *  4. Bot asks: "What's your name?"
 *  5. They reply → first user created
 *  6. Bot: "You're set! Add teammates: 'invite +15551234567 as Sarah'"
 *
 * Invite flow (for the admin):
 *  "invite +15551234567 as Sarah" → pending invite created, welcome SMS sent
 *
 * New member joins:
 *  They receive welcome SMS and text back → getPendingInvite → create user
 */

const db = require('../db');
const sms = require('../services/sms');

// Simple in-memory setup sessions (keyed by phone number)
// In production this could be in Redis or a setup_sessions table, but for MVP it's fine
const setupSessions = new Map();

/**
 * Main entry for unknown senders or setup keyword.
 * Returns a reply string.
 */
async function handleSetupMessage(from, body, toNumber) {
  const text = body.trim().toLowerCase();

  // Check for a pending invite first (they already got a welcome SMS)
  // toNumber is the Twilio number = team phone number
  // We need to find the team by the Twilio number they texted
  const team = await db.getTeamByPhoneNumber(toNumber);

  if (team && team.setup_complete) {
    // Check if they have a pending invite
    const invite = await db.getPendingInvite(team.id, from);
    if (invite) {
      return await handleNewMemberJoin(from, body, team, invite);
    }
    // Unknown number texting a set-up team
    return `Hi! This number is used by ${team.name}. If you're a team member, ask your admin to add you.`;
  }

  // No team yet — check setup session
  const session = setupSessions.get(from);

  if (!session) {
    if (text === 'setup' || text === 'start') {
      setupSessions.set(from, { step: 'awaiting_team_name', twilioNumber: toNumber });
      return "Welcome to TextApp! 👋 What's your team name?";
    }
    return "Text \"setup\" to create a new team, or ask your admin to add you.";
  }

  // Continue session
  return await continueSetup(from, body, session);
}

async function continueSetup(from, body, session) {
  const text = body.trim();

  if (session.step === 'awaiting_team_name') {
    if (!text || text.length < 2) return "What's your team name?";
    session.teamName = text;
    session.step = 'awaiting_admin_name';
    setupSessions.set(from, session);
    return `Great — "${text}"! And what's your name?`;
  }

  if (session.step === 'awaiting_admin_name') {
    if (!text || text.length < 2) return "What's your name?";
    session.adminName = text;
    session.step = 'awaiting_email';
    setupSessions.set(from, session);
    return "What's your email? (We'll use it to send you a dashboard link.)";
  }

  if (session.step === 'awaiting_email') {
    const email = text.toLowerCase();
    if (!email.includes('@')) return "That doesn't look like an email. Try again.";

    // Create team + admin user
    try {
      const team = await db.createTeam({
        name: session.teamName,
        phoneNumber: session.twilioNumber,
        adminPhone: from,
        timezone: 'America/New_York',
      });

      await db.updateTeam(team.id, { admin_email: email, setup_complete: true });

      const user = await db.createUser({
        teamId: team.id,
        name: session.adminName,
        phoneNumber: from,
      });

      setupSessions.delete(from);

      return (
        `You're all set, ${session.adminName}! 🎉\n\n` +
        `Team: ${session.teamName}\n\n` +
        `To add teammates:\n"invite +15551234567 as Sarah"\n\n` +
        `To create a task:\n"Add homepage copy for Sarah, due Friday"\n\n` +
        `Your dashboard link will arrive by email.`
      );
    } catch (err) {
      console.error('Setup error:', err.message);
      return 'Something went wrong. Please try again.';
    }
  }

  return "Text \"setup\" to start over.";
}

/**
 * Handle admin inviting a new member.
 * Message format: "invite +15551234567 as Sarah"
 */
async function handleInvite(body, team, admin) {
  // Parse "invite +1... as Name"
  const match = body.match(/invite\s+(\+?\d[\d\s\-().]+)\s+as\s+(.+)/i);
  if (!match) {
    return "Format: \"invite +15551234567 as Sarah\"";
  }

  const rawPhone = match[1].replace(/[\s\-().]/g, '');
  const phone = rawPhone.startsWith('+') ? rawPhone : `+1${rawPhone}`;
  const name = match[2].trim();

  // Check if already a member
  const existing = await db.getUserByPhone(team.id, phone);
  if (existing) return `${existing.name} is already on the team.`;

  await db.addPendingInvite(team.id, phone, name);

  // Send welcome SMS to the invitee
  try {
    await sms.send({
      to: phone,
      body:
        `Hi ${name}! ${admin.name} added you to ${team.name} on TextApp.\n\n` +
        `Reply to this number to manage tasks by text. Text anything to get started.`,
      teamId: team.id,
    });
  } catch (err) {
    console.error('Failed to send invite SMS:', err.message);
    return `Added ${name}, but couldn't send them a text (bad number?).`;
  }

  return `Invited! Welcome SMS sent to ${name}.`;
}

/**
 * New member texts back after receiving welcome invite.
 */
async function handleNewMemberJoin(phone, body, team, invite) {
  const name = invite.name || body.trim() || 'New Member';

  await db.createUser({ teamId: team.id, name, phoneNumber: phone });
  await db.deletePendingInvite(team.id, phone);

  return (
    `Welcome to ${team.name}, ${name}! 👋\n\n` +
    `Here's what you can do:\n` +
    `• "Add task: write Q1 report" — create a task\n` +
    `• "My tasks" — see your open tasks\n` +
    `• "Mark Q1 report done" — update a task\n` +
    `• "Assign Q1 report to Sarah" — reassign`
  );
}

module.exports = { handleSetupMessage, handleInvite };
