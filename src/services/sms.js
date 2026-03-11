const twilio = require('twilio');
const db = require('../db');

// Lazy-initialize so the module loads even with placeholder credentials
let _client = null;
function getClient() {
  if (!_client) {
    _client = twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);
  }
  return _client;
}

const FROM = process.env.TWILIO_PHONE_NUMBER;

/**
 * Send an SMS and log it to the messages table.
 */
async function send({ to, body, teamId = null, userId = null }) {
  try {
    await getClient().messages.create({ from: FROM, to, body });
    await db.logMessage({ teamId, userId, direction: 'out', body });
  } catch (err) {
    console.error(`SMS send failed to ${to}:`, err.message);
    throw err;
  }
}

/**
 * Reply in TwiML format (used in webhook response when we want
 * Twilio to send the reply without a second API call).
 * Returns an XML string.
 */
function twimlReply(body) {
  const twiml = new twilio.twiml.MessagingResponse();
  twiml.message(body);
  return twiml.toString();
}

module.exports = { send, twimlReply };
