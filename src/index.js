require('dotenv').config();

const express = require('express');
const cookieParser = require('cookie-parser');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const path = require('path');

const { twilioValidation } = require('./middleware/twilioValidation');
const { handleInbound } = require('./handlers/inbound');
const dashboardRouter = require('./routes/dashboard');
const authRouter = require('./routes/auth');
const { startDigestCron } = require('./services/digest');

// ------------------------------------------------------------------
// Validate required env vars on startup
// ------------------------------------------------------------------
const REQUIRED_VARS = [
  'ANTHROPIC_API_KEY',
  'TWILIO_ACCOUNT_SID',
  'TWILIO_AUTH_TOKEN',
  'TWILIO_PHONE_NUMBER',
  'SUPABASE_URL',
  'SUPABASE_ANON_KEY',
];

const missing = REQUIRED_VARS.filter(v => !process.env[v]);
if (missing.length) {
  console.error('Missing required environment variables:', missing.join(', '));
  process.exit(1);
}

// ------------------------------------------------------------------
// Express setup
// ------------------------------------------------------------------
const app = express();

// Trust proxy headers from Railway/Render so rate limiting uses real IPs
app.set('trust proxy', 1);

// Security headers (helmet) — configured to allow static assets & inline styles on dashboard
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'"],   // landing page inline JS
      styleSrc: ["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com'],
      fontSrc: ["'self'", 'https://fonts.gstatic.com'],
      imgSrc: ["'self'", 'data:'],
      connectSrc: ["'self'"],
    },
  },
  crossOriginEmbedderPolicy: false, // allow font CDN
}));

// IMPORTANT: Twilio validation requires the raw URL-encoded body
app.use(express.urlencoded({ extended: false }));
app.use(express.json({ limit: '16kb' }));
app.use(cookieParser());

// Serve static files
app.use(express.static(path.join(__dirname, '../public')));

// ------------------------------------------------------------------
// Rate limiters
// ------------------------------------------------------------------

// Auth endpoints: 10 attempts per 15 min per IP
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 10,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many requests. Please try again later.' },
});

// Waitlist: 5 signups per hour per IP
const waitlistLimiter = rateLimit({
  windowMs: 60 * 60 * 1000,
  max: 5,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many signups from this address. Try again later.' },
});

// Dashboard API: 60 req/min per IP
const dashboardLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 60,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many requests.' },
});

// ------------------------------------------------------------------
// Health check
// ------------------------------------------------------------------
app.get('/health', (req, res) => {
  res.json({ status: 'ok', ts: new Date().toISOString() });
});

// ------------------------------------------------------------------
// Twilio webhook — POST /sms
// Twilio signature validation is the primary security layer here
// ------------------------------------------------------------------
app.post('/sms', twilioValidation, async (req, res) => {
  try {
    await handleInbound(req, res);
  } catch (err) {
    console.error('[SMS] Unhandled error:', err);
    res.set('Content-Type', 'text/xml');
    res.status(200).send(
      '<Response><Message>Something went wrong. Please try again.</Message></Response>'
    );
  }
});

// ------------------------------------------------------------------
// Auth routes (rate limited)
// ------------------------------------------------------------------
app.use('/api/auth', authLimiter);
app.use('/api/waitlist', waitlistLimiter);
app.use('/', authRouter);

// ------------------------------------------------------------------
// Dashboard routes (rate limited)
// ------------------------------------------------------------------
app.use('/api/tasks', dashboardLimiter);
app.use('/api/send-dashboard-link', authLimiter);
app.use('/', dashboardRouter);

// ------------------------------------------------------------------
// 404
// ------------------------------------------------------------------
app.use((req, res) => {
  res.status(404).json({ error: 'Not found' });
});

// ------------------------------------------------------------------
// Start
// ------------------------------------------------------------------
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`TextApp running on port ${PORT}`);
  console.log(`Twilio webhook → POST /sms`);
  console.log(`Dashboard      → GET  /dashboard?token=...`);

  startDigestCron();
});

module.exports = app;
