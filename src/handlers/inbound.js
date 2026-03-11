/**
 * Core inbound SMS handler.
 * Called by the Twilio webhook with the raw POST body already parsed.
 *
 * Flow:
 *  1. Identify team (by To number) and user (by From number)
 *  2. If no team or setup not complete → hand off to setup handler
 *  3. Log inbound message
 *  4. Pull recent history for context
 *  5. Parse with Haiku
 *  6. Route to action handler
 *  7. Reply via TwiML
 */

const db = require('../db');
const nlp = require('../services/nlp');
const sms = require('../services/sms');
const actions = require('./actions');
const setup = require('./setup');

async function handleInbound(req, res) {
  const from = req.body.From;      // sender's phone e.g. +15551234567
  const to = req.body.To;          // our Twilio number
  const body = (req.body.Body || '').trim();

  if (!from || !body) {
    return res.status(200).send('<Response></Response>');
  }

  console.log(`[SMS IN] ${from} → ${to}: ${body}`);

  // --- Identify team ---
  const team = await db.getTeamByPhoneNumber(to);

  if (!team || !team.setup_complete) {
    const reply = await setup.handleSetupMessage(from, body, to);
    return sendTwimlReply(res, reply);
  }

  // --- Identify user ---
  let user = await db.getUserByPhone(team.id, from);

  // Unknown sender for a complete team — check pending invite
  if (!user) {
    const reply = await setup.handleSetupMessage(from, body, to);
    return sendTwimlReply(res, reply);
  }

  // --- Log inbound ---
  await db.logMessage({ teamId: team.id, userId: user.id, direction: 'in', body });

  // --- Check for special commands (no LLM needed) ---
  const lower = body.toLowerCase();

  // Invite command (admin only)
  if (lower.startsWith('invite ') && from === team.admin_phone) {
    const reply = await setup.handleInvite(body, team, user);
    return sendTwimlReply(res, reply);
  }

  // Help
  if (lower === 'help' || lower === '?') {
    const reply =
      `TextApp commands:\n` +
      `• "Add task: title" — create task\n` +
      `• "My tasks" — see your tasks\n` +
      `• "Team tasks" — see all tasks\n` +
      `• "Mark [task] done" — complete task\n` +
      `• "Mark [task] blocked" — flag as blocked\n` +
      `• "Assign [task] to [name]" — reassign\n` +
      `• "invite +1... as Name" — add teammate (admin)\n` +
      `• "dashboard" — get your dashboard link`;
    return sendTwimlReply(res, reply);
  }

  // Dashboard link request
  if (lower === 'dashboard' || lower === 'link') {
    const token = await db.createMagicToken(team.id);
    const url = `${process.env.BASE_URL}/dashboard?token=${token.token}`;
    return sendTwimlReply(res, `Your dashboard link (expires 24h):\n${url}`);
  }

  // --- Get recent history (max 5 messages) ---
  const history = await db.getRecentMessages(team.id, user.id, 5);

  // --- NLP parse ---
  const parsed = await nlp.parseMessage(body, history, { teamId: team.id, userId: user.id });

  // --- Route by intent ---
  let reply;

  if (parsed.confidence === 'low' && parsed.clarification_needed) {
    reply = parsed.clarification_needed;
  } else {
    switch (parsed.intent) {
      case 'create':
        reply = await actions.handleCreate(parsed, team, user);
        break;
      case 'update':
        reply = await actions.handleUpdate(parsed, team, user);
        break;
      case 'assign':
        reply = await actions.handleAssign(parsed, team, user);
        break;
      case 'query':
        reply = await actions.handleQuery(parsed, team, user);
        break;
      default:
        reply =
          "I didn't understand that. Try:\n" +
          "• \"Add task: homepage redesign\"\n" +
          "• \"My tasks\"\n" +
          "• \"Mark homepage done\"\n" +
          "Or text \"help\" for all commands.";
    }
  }

  // --- Log outbound + reply ---
  await db.logMessage({ teamId: team.id, userId: user.id, direction: 'out', body: reply });
  return sendTwimlReply(res, reply);
}

function sendTwimlReply(res, body) {
  res.set('Content-Type', 'text/xml');
  res.status(200).send(sms.twimlReply(body));
}

module.exports = { handleInbound };
