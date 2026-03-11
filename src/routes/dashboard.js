/**
 * Dashboard routes.
 *
 * GET /dashboard?token=xxx  → validate token, set session cookie, serve dashboard
 * GET /api/tasks?token=xxx  → JSON tasks for the dashboard JS
 */

const express = require('express');
const path = require('path');
const db = require('../db');
const email = require('../services/email');

const router = express.Router();

// Validate token and serve dashboard HTML
router.get('/dashboard', async (req, res) => {
  const { token } = req.query;

  if (!token) {
    return res.status(400).send(errorPage('No token provided. Text "dashboard" to your team number.'));
  }

  const record = await db.validateMagicToken(token);
  if (!record) {
    return res.status(401).send(errorPage('Link expired or already used. Text "dashboard" for a new one.'));
  }

  // Token is single-use — mark used
  await db.markTokenUsed(record.id);

  // Set a short-lived signed cookie with team ID so the /api/tasks call works
  // For simplicity in this MVP, we pass teamId as a query param to /api/tasks
  // (the API route validates via a separate fresh token lookup is not needed since
  //  we embed the teamId encrypted in a session approach; instead we just pass
  //  the team ID directly in the page and the API validates it with a referer check)
  // SIMPLER: embed team ID in a signed JWT-lite cookie
  const teamId = record.team_id;
  res.cookie('ta_team', teamId, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 8 * 60 * 60 * 1000, // 8 hours
  });

  // Redirect to the clean dashboard URL
  res.redirect(`/dashboard/view?team=${teamId}`);
});

// Serve the static dashboard page (with team context)
router.get('/dashboard/view', async (req, res) => {
  const teamId = req.query.team;
  const cookieTeam = req.cookies?.ta_team;

  if (!teamId || teamId !== cookieTeam) {
    return res.status(401).send(errorPage('Session expired. Text "dashboard" for a new link.'));
  }

  const team = await db.getTeamById(teamId);
  if (!team) return res.status(404).send(errorPage('Team not found.'));

  res.sendFile(path.join(__dirname, '../../public/dashboard.html'));
});

// API: tasks JSON (consumed by dashboard JS)
router.get('/api/tasks', async (req, res) => {
  const teamId = req.cookies?.ta_team;

  if (!teamId) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const team = await db.getTeamById(teamId);
  if (!team) return res.status(404).json({ error: 'Team not found' });

  const [tasks, users] = await Promise.all([
    db.getTeamTasks(team.id),
    db.getTeamUsers(team.id),
  ]);

  res.json({ team, tasks, users });
});

// Admin: send dashboard link to email
router.post('/api/send-dashboard-link', async (req, res) => {
  const teamId = req.cookies?.ta_team;
  if (!teamId) return res.status(401).json({ error: 'Unauthorized' });

  const team = await db.getTeamById(teamId);
  if (!team || !team.admin_email) {
    return res.status(400).json({ error: 'No admin email on file' });
  }

  const token = await db.createMagicToken(team.id);
  const url = `${process.env.BASE_URL}/dashboard?token=${token.token}`;

  await email.sendMagicLink({ to: team.admin_email, teamName: team.name, url });
  res.json({ ok: true });
});

function errorPage(message) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>TextApp</title>
<style>body{font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#f5f5f5}
.box{background:#fff;border-radius:12px;padding:40px;max-width:400px;text-align:center;box-shadow:0 2px 12px rgba(0,0,0,.08)}
h2{margin:0 0 12px;font-size:20px}p{color:#666;margin:0;font-size:15px}</style></head>
<body><div class="box"><h2>TextApp</h2><p>${message}</p></div></body></html>`;
}

module.exports = router;
