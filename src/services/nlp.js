const Anthropic = require('@anthropic-ai/sdk');
const db = require('../db');

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

// Keep this TIGHT — under 500 tokens
const SYSTEM_PROMPT = `You are a project management assistant that parses SMS messages.
Extract the user's intent and return ONLY a JSON object. No explanation.

Intents:
- create: user wants to add a task
- update: user wants to change a task's status or due date
- assign: user wants to reassign a task to someone else
- query: user wants to see tasks (their own or someone else's)
- unknown: can't determine intent

JSON format:
{
  "intent": "create|update|assign|query|unknown",
  "confidence": "high|low",
  "task_title": "string or null",
  "owner_name": "string or null (first name only)",
  "due_date": "YYYY-MM-DD or null",
  "new_status": "open|done|blocked or null",
  "query_target": "me|user_name|all or null",
  "clarification_needed": "string or null"
}

Rules:
- If message says "done", "finished", "completed" it's likely an update with new_status=done
- If message says "blocked", "stuck", "can't proceed" → new_status=blocked
- Relative dates: "today"=today, "tomorrow"=tomorrow, "friday"=next friday
- Today's date: REPLACE_DATE
- If confidence is low, set clarification_needed to a short question to ask the user
- Never guess a task title if the message is ambiguous`;

/**
 * Parse a user's SMS message using Claude Haiku.
 *
 * @param {string} message - The inbound SMS text
 * @param {Array}  history - Last N messages [{direction, body}]
 * @param {Object} context - { teamId, userId } for logging
 * @returns {Object} Parsed intent object
 */
async function parseMessage(message, history = [], context = {}) {
  const today = new Date().toISOString().split('T')[0];
  const systemPrompt = SYSTEM_PROMPT.replace('REPLACE_DATE', today);

  // Format history as a short context block
  const historyText = history.length
    ? '\n\nRecent conversation:\n' +
      history.map(m => `${m.direction === 'in' ? 'User' : 'Bot'}: ${m.body}`).join('\n')
    : '';

  const userContent = `${historyText}\n\nNew message: ${message}`;

  let response;
  try {
    response = await anthropic.messages.create({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 256,
      system: systemPrompt,
      messages: [{ role: 'user', content: userContent }],
    });
  } catch (err) {
    console.error('Haiku API error:', err.message);
    return { intent: 'unknown', confidence: 'low', clarification_needed: null };
  }

  const inputTokens = response.usage?.input_tokens || 0;
  const outputTokens = response.usage?.output_tokens || 0;

  // Log cost data
  const raw = response.content[0]?.text || '{}';
  let parsed;
  try {
    // Strip any markdown code fences Haiku might add
    const clean = raw.replace(/```json?\n?/g, '').replace(/```/g, '').trim();
    parsed = JSON.parse(clean);
  } catch {
    console.error('Failed to parse Haiku JSON:', raw);
    parsed = { intent: 'unknown', confidence: 'low', clarification_needed: null };
  }

  await db.logLLMCall({
    teamId: context.teamId || null,
    userId: context.userId || null,
    inputTokens,
    outputTokens,
    intent: parsed.intent || 'unknown',
  });

  console.log(`[LLM] intent=${parsed.intent} tokens=${inputTokens}+${outputTokens}`);
  return parsed;
}

module.exports = { parseMessage };
