import json
import logging
from datetime import date

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a project management assistant that parses SMS messages.
Extract the user's intent and return ONLY a JSON object. No explanation.

Intents:
- create: user wants to add a task
- update: user wants to change a task's status or due date
- assign: user wants to reassign a task to someone else
- query: user wants to see tasks (their own or someone else's)
- unknown: can't determine intent

JSON format:
{{
  "intent": "create|update|assign|query|unknown",
  "confidence": "high|low",
  "task_title": "string or null",
  "owner_name": "string or null (first name only)",
  "due_date": "YYYY-MM-DD or null",
  "new_status": "open|done|blocked or null",
  "query_target": "me|user_name|all or null",
  "clarification_needed": "string or null"
}}

Rules:
- If message says "done", "finished", "completed" it's likely an update with new_status=done
- If message says "blocked", "stuck", "can't proceed" → new_status=blocked
- Relative dates: "today"=today, "tomorrow"=tomorrow, "friday"=next friday
- Today's date: {today}
- If confidence is low, set clarification_needed to a short question to ask the user
- Never guess a task title if the message is ambiguous\
"""


def parse_message(message, history=None, team_id=None, user_id=None):
    """
    Parse an inbound SMS using Claude Haiku and return a structured intent dict.
    Logs token usage to the llm_logs table.
    """
    today = date.today().isoformat()
    system_prompt = SYSTEM_PROMPT.format(today=today)

    history_text = ''
    if history:
        lines = [
            f"{'User' if m['direction'] == 'in' else 'Bot'}: {m['body']}"
            for m in history
        ]
        history_text = '\n\nRecent conversation:\n' + '\n'.join(lines)

    user_content = f'{history_text}\n\nNew message: {message}'

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=256,
            system=system_prompt,
            messages=[{'role': 'user', 'content': user_content}],
        )
    except Exception as e:
        logger.error('Haiku API error: %s', e)
        return {'intent': 'unknown', 'confidence': 'low', 'clarification_needed': None}

    input_tokens = response.usage.input_tokens if response.usage else 0
    output_tokens = response.usage.output_tokens if response.usage else 0

    raw = response.content[0].text if response.content else '{}'
    try:
        clean = raw.replace('```json', '').replace('```', '').strip()
        parsed = json.loads(clean)
    except Exception:
        logger.error('Failed to parse Haiku JSON: %s', raw)
        parsed = {'intent': 'unknown', 'confidence': 'low', 'clarification_needed': None}

    _log_llm_call(team_id, user_id, input_tokens, output_tokens, parsed.get('intent', 'unknown'))
    logger.info('[LLM] intent=%s tokens=%d+%d', parsed.get('intent'), input_tokens, output_tokens)
    return parsed


def _log_llm_call(team_id, user_id, input_tokens, output_tokens, intent):
    from core.models import LLMLog, Team, User
    try:
        team = Team.objects.get(id=team_id) if team_id else None
        user = User.objects.get(id=user_id) if user_id else None
        LLMLog.objects.create(
            team=team, user=user,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            intent=intent,
        )
    except Exception as e:
        logger.error('Failed to log LLM call: %s', e)
