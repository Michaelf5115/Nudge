"""
Core inbound SMS handler.

Flow:
  1. Identify team (by To number) and user (by From number)
  2. If no team or setup not complete → hand off to setup handler
  3. Log inbound message
  4. Check for special keyword commands (no LLM needed)
  5. Pull recent message history for context
  6. Parse intent with Claude Haiku
  7. Route to action handler
  8. Log outbound reply
  9. Return reply string
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from django.conf import settings

from core import models
from core.handlers import actions, setup
from core.services import nlp, sms_service

logger = logging.getLogger(__name__)


def handle_inbound(from_phone, to_phone, body):
    """Return the reply string to send back to the user."""
    logger.info('[SMS IN] %s → %s: %s', from_phone, to_phone, body)

    # --- Identify team ---
    try:
        team = models.Team.objects.get(phone_number=to_phone)
    except models.Team.DoesNotExist:
        team = None

    if not team or not team.setup_complete:
        return setup.handle_setup_message(from_phone, body, to_phone)

    # --- Identify user ---
    try:
        user = models.User.objects.get(team=team, phone_number=from_phone)
    except models.User.DoesNotExist:
        user = None

    if not user:
        return setup.handle_setup_message(from_phone, body, to_phone)

    # --- Log inbound ---
    models.Message.objects.create(team=team, user=user, direction='in', body=body)

    # --- Special keyword commands ---
    lower = body.lower()

    if lower.startswith('invite ') and from_phone == team.admin_phone:
        reply = setup.handle_invite(body, team, user)
        models.Message.objects.create(team=team, user=user, direction='out', body=reply)
        return reply

    if lower in ('help', '?'):
        reply = (
            'TextApp commands:\n'
            '\u2022 "Add task: title" \u2014 create task\n'
            '\u2022 "My tasks" \u2014 see your tasks\n'
            '\u2022 "Team tasks" \u2014 see all tasks\n'
            '\u2022 "Mark [task] done" \u2014 complete task\n'
            '\u2022 "Mark [task] blocked" \u2014 flag as blocked\n'
            '\u2022 "Assign [task] to [name]" \u2014 reassign\n'
            '\u2022 "invite +1... as Name" \u2014 add teammate (admin)\n'
            '\u2022 "dashboard" \u2014 get your dashboard link'
        )
        models.Message.objects.create(team=team, user=user, direction='out', body=reply)
        return reply

    if lower in ('dashboard', 'link'):
        token_value = secrets.token_hex(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        token = models.MagicToken.objects.create(
            team=team, token=token_value, expires_at=expires_at
        )
        url = f'{settings.BASE_URL}/dashboard?token={token.token}'
        reply = f'Your dashboard link (expires 24h):\n{url}'
        models.Message.objects.create(team=team, user=user, direction='out', body=reply)
        return reply

    # --- Recent history (oldest-first, max 5) ---
    history = list(
        models.Message.objects.filter(team=team, user=user)
        .order_by('-created_at')
        .values('direction', 'body')[:5]
    )
    history = list(reversed(history))

    # --- NLP parse ---
    parsed = nlp.parse_message(body, history, team_id=str(team.id), user_id=str(user.id))

    # --- Route by intent ---
    if parsed.get('confidence') == 'low' and parsed.get('clarification_needed'):
        reply = parsed['clarification_needed']
    else:
        intent = parsed.get('intent', 'unknown')
        if intent == 'create':
            reply = actions.handle_create(parsed, team, user)
        elif intent == 'update':
            reply = actions.handle_update(parsed, team, user)
        elif intent == 'assign':
            reply = actions.handle_assign(parsed, team, user)
        elif intent == 'query':
            reply = actions.handle_query(parsed, team, user)
        else:
            reply = (
                "I didn't understand that. Try:\n"
                '\u2022 "Add task: homepage redesign"\n'
                '\u2022 "My tasks"\n'
                '\u2022 "Mark homepage done"\n'
                'Or text "help" for all commands.'
            )

    models.Message.objects.create(team=team, user=user, direction='out', body=reply)
    return reply
