const twilio = require('twilio');

/**
 * Validate that incoming requests are genuinely from Twilio.
 * Skipped in development when SKIP_TWILIO_VALIDATION=true.
 *
 * IMPORTANT: Express must be configured with raw body parsing for
 * this middleware to work correctly. We use express.urlencoded()
 * before mounting the Twilio route.
 */
function twilioValidation(req, res, next) {
  if (process.env.SKIP_TWILIO_VALIDATION === 'true') {
    return next();
  }

  const authToken = process.env.TWILIO_AUTH_TOKEN;
  const signature = req.headers['x-twilio-signature'];

  // Build the full URL Twilio signed (must match exactly what Twilio sees)
  const host = req.headers['x-forwarded-host'] || req.headers.host;
  const protocol = req.headers['x-forwarded-proto'] || req.protocol;
  const fullUrl = `${protocol}://${host}${req.originalUrl}`;

  const isValid = twilio.validateRequest(authToken, signature, fullUrl, req.body);

  if (!isValid) {
    console.warn('[Security] Invalid Twilio signature from', req.ip);
    return res.status(403).send('Forbidden');
  }

  next();
}

module.exports = { twilioValidation };
