/**
 * Auth routes
 *
 * POST /api/waitlist        — save an email for early-access notifications
 * POST /api/auth/login      — send magic link via email or SMS
 */

const express = require('express');
const { supabase, getTeamByPhoneNumber, createMagicToken } = require('../db');
const email = require('../services/email');
const sms = require('../services/sms');

const router = express.Router();

// ------------------------------------------------------------------
// POST /api/waitlist
// Body: { email: string }
// ------------------------------------------------------------------
router.post('/api/waitlist', async (req, res) => {
  const { email: addr } = req.body;

  if (!addr || !addr.includes('@')) {
    return res.status(400).json({ error: 'Invalid email address.' });
  }

  const normalised = addr.trim().toLowerCase();

  const { error } = await supabase
    .from('waitlist')
    .insert({ email: normalised });

  if (error) {
    // Duplicate entry is fine — just return ok so we don't leak existence
    if (error.code === '23505') {
      return res.json({ ok: true });
    }
    console.error('[Waitlist] DB error:', error.message);
    return res.status(500).json({ error: 'Could not save your email. Please try again.' });
  }

  console.log(`[Waitlist] New signup: ${normalised}`);
  res.json({ ok: true });
});

// ------------------------------------------------------------------
// POST /api/auth/login
// Body: { email?: string, phone?: string }
// Always returns 200 — never reveals whether the account exists.
// Sets X-Auth-Method header so the client can show the right message.
// ------------------------------------------------------------------
router.post('/api/auth/login', async (req, res) => {
  const { email: addr, phone } = req.body;

  // Validate we got something
  if (!addr && !phone) {
    return res.status(400).json({ error: 'Provide an email or phone number.' });
  }

  const method = addr ? 'email' : 'phone';
  res.set('X-Auth-Method', method);

  try {
    if (method === 'email') {
      await handleEmailLogin(addr.trim().toLowerCase());
    } else {
      await handlePhoneLogin(phone.trim());
    }
  } catch (err) {
    // Log internally but always return 200 to client
    console.error(`[Auth] Login error (${method}):`, err.message);
  }

  // Always respond OK — never leak account existence
  res.json({ ok: true });
});

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

async function handleEmailLogin(addr) {
  // Find team by admin email
  const { data: team } = await supabase
    .from('teams')
    .select('*')
    .eq('admin_email', addr)
    .eq('setup_complete', true)
    .single();

  if (!team) {
    console.log(`[Auth] Email login attempt — no team found for: ${addr}`);
    return; // Silently succeed
  }

  const token = await createMagicToken(team.id);
  const url = `${process.env.BASE_URL}/dashboard?token=${token.token}`;

  await email.sendMagicLink({ to: addr, teamName: team.name, url });
  console.log(`[Auth] Magic link emailed to ${addr} for team "${team.name}"`);
}

async function handlePhoneLogin(phoneRaw) {
  // Normalise to E.164
  const digits = phoneRaw.replace(/\D/g, '');
  const phone = digits.startsWith('1') && digits.length === 11
    ? `+${digits}`
    : digits.length === 10
      ? `+1${digits}`
      : phoneRaw;

  // Find team by admin phone
  const { data: team } = await supabase
    .from('teams')
    .select('*')
    .eq('admin_phone', phone)
    .eq('setup_complete', true)
    .single();

  if (!team) {
    console.log(`[Auth] Phone login attempt — no team found for: ${phone}`);
    return;
  }

  const token = await createMagicToken(team.id);
  const url = `${process.env.BASE_URL}/dashboard?token=${token.token}`;

  await sms.send({
    to: phone,
    body: `Your ${team.name} dashboard link (expires 24h):\n${url}`,
    teamId: team.id,
  });

  console.log(`[Auth] Magic link texted to ${phone} for team "${team.name}"`);
}

module.exports = router;
