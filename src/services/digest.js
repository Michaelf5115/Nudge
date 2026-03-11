/**
 * Morning digest service.
 * Sends each team member their open tasks at the team's configured hour.
 *
 * Run via node-cron every minute — checks if any team's digest should fire now.
 */

const cron = require('node-cron');
const db = require('../db');
const sms = require('./sms');
const { formatDueDate, isOverdue, isToday } = require('../utils/dates');

/**
 * Send the morning digest for a single team.
 */
async function sendTeamDigest(team) {
  const users = await db.getTeamUsers(team.id);

  for (const user of users) {
    const tasks = await db.getOpenTasksForUser(user.id);
    if (tasks.length === 0) continue;

    const overdueItems = tasks.filter(t => t.due_date && isOverdue(t.due_date));
    const todayItems = tasks.filter(t => t.due_date && isToday(t.due_date));
    const upcoming = tasks.filter(t => !t.due_date || (!isOverdue(t.due_date) && !isToday(t.due_date)));

    const lines = [];
    lines.push(`Good morning, ${user.name}! Here's your day:`);
    lines.push('');

    if (overdueItems.length) {
      lines.push('⚠ Overdue:');
      overdueItems.forEach(t => lines.push(`  • ${t.title} (${formatDueDate(t.due_date)})`));
      lines.push('');
    }

    if (todayItems.length) {
      lines.push('📌 Due today:');
      todayItems.forEach(t => lines.push(`  • ${t.title}`));
      lines.push('');
    }

    if (upcoming.length) {
      lines.push('Up next:');
      upcoming.slice(0, 5).forEach(t => {
        const due = t.due_date ? ` (${formatDueDate(t.due_date)})` : '';
        lines.push(`  • ${t.title}${due}`);
      });
    }

    const body = lines.join('\n');

    try {
      await sms.send({ to: user.phone_number, body, teamId: team.id, userId: user.id });
      console.log(`[Digest] Sent to ${user.name} (${user.phone_number})`);
    } catch (err) {
      console.error(`[Digest] Failed for ${user.name}:`, err.message);
    }
  }
}

/**
 * Check all teams and fire digest if it's their configured hour (local time).
 */
async function checkAndSendDigests() {
  const teams = await db.getAllTeams();
  const nowUTC = new Date();

  for (const team of teams) {
    if (!team.setup_complete) continue;

    // Convert UTC now to team's local hour
    const localHour = getLocalHour(nowUTC, team.timezone);

    if (localHour === team.digest_hour) {
      console.log(`[Digest] Sending for team ${team.name} (local hour: ${localHour})`);
      await sendTeamDigest(team);
    }
  }
}

/**
 * Get the current hour in a given IANA timezone.
 */
function getLocalHour(date, timezone) {
  try {
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      hour: 'numeric',
      hour12: false,
    });
    const parts = formatter.formatToParts(date);
    const hourPart = parts.find(p => p.type === 'hour');
    return parseInt(hourPart?.value || '0', 10);
  } catch {
    // Fallback to UTC
    return date.getUTCHours();
  }
}

/**
 * Start the cron job — runs once per minute.
 * Only sends if current minute is :00 (on the hour).
 */
function startDigestCron() {
  // Run at the top of every hour
  cron.schedule('0 * * * *', async () => {
    console.log('[Digest] Hourly check running...');
    try {
      await checkAndSendDigests();
    } catch (err) {
      console.error('[Digest] Error:', err.message);
    }
  });

  console.log('[Digest] Cron started — will check hourly for teams due a digest.');
}

module.exports = { startDigestCron, sendTeamDigest, checkAndSendDigests };
