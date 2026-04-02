"""
Team setup flow via SMS.

State machine (stored in Django cache, keyed by phone number):
  1. Someone texts "setup"
  2. Bot asks: "What's your team name?"
  3. They reply → session updated
  4. Bot asks: "What's your name?"
  5. They reply → session updated
  6. Bot asks: "What's your email?"
  7. They reply → Team + User created, setup_complete=True

Invite flow (admin only):
  "invite +15551234567 as Sarah" → PendingInvite created, welcome SMS sent

New member joins:
  They receive a welcome SMS and reply → User created from PendingInvite
"""
import logging
import re

from django.core.cache import cache

from core.models import PendingInvite, Team, User

logger = logging.getLogger(__name__)

_SESSION_TTL = 30 * 60  # 30 minutes


def _session_key(phone):
    return f'setup_session:{phone}'


def _get_session(phone):
    return cache.get(_session_key(phone))


def _set_session(phone, session):
    cache.set(_session_key(phone), session, _SESSION_TTL)


def _delete_session(phone):
    cache.delete(_session_key(phone))


# ------------------------------------------------------------------
# Main entry
# ------------------------------------------------------------------

def handle_setup_message(from_phone, body, to_number):
    text = body.strip().lower()

    # Is the Twilio number already claimed by a complete team?
    try:
        team = Team.objects.get(phone_number=to_number)
    except Team.DoesNotExist:
        team = None

    if team and team.setup_complete:
        try:
            invite = PendingInvite.objects.get(team=team, phone_number=from_phone)
            return _handle_new_member_join(from_phone, body, team, invite)
        except PendingInvite.DoesNotExist:
            pass
        return (
            f'Hi! This number is used by {team.name}. '
            f"If you're a team member, ask your admin to add you."
        )

    session = _get_session(from_phone)

    if not session:
        if text in ('setup', 'start'):
            _set_session(from_phone, {'step': 'awaiting_team_name', 'twilio_number': to_number})
            return "Welcome to TextApp! What's your team name?"
        return 'Text "setup" to create a new team, or ask your admin to add you.'

    return _continue_setup(from_phone, body, session)


# ------------------------------------------------------------------
# Setup steps
# ------------------------------------------------------------------

def _continue_setup(from_phone, body, session):
    text = body.strip()

    if session['step'] == 'awaiting_team_name':
        if len(text) < 2:
            return "What's your team name?"
        session['team_name'] = text
        session['step'] = 'awaiting_admin_name'
        _set_session(from_phone, session)
        return f'Great \u2014 "{text}"! And what\'s your name?'

    if session['step'] == 'awaiting_admin_name':
        if len(text) < 2:
            return "What's your name?"
        session['admin_name'] = text
        session['step'] = 'awaiting_email'
        _set_session(from_phone, session)
        return "What's your email? (We'll use it to send you a dashboard link.)"

    if session['step'] == 'awaiting_email':
        email = text.lower()
        if '@' not in email:
            return "That doesn't look like an email. Try again."
        try:
            team = Team.objects.create(
                name=session['team_name'],
                phone_number=session['twilio_number'],
                admin_phone=from_phone,
                admin_email=email,
                setup_complete=True,
            )
            User.objects.create(team=team, name=session['admin_name'], phone_number=from_phone)
            _delete_session(from_phone)
            return (
                f"You're all set, {session['admin_name']}! \U0001f389\n\n"
                f"Team: {session['team_name']}\n\n"
                f'To add teammates:\n"invite +15551234567 as Sarah"\n\n'
                f'To create a task:\n"Add homepage copy for Sarah, due Friday"\n\n'
                f'Your dashboard link will arrive by email.'
            )
        except Exception as e:
            logger.error('Setup error: %s', e)
            return 'Something went wrong. Please try again.'

    return 'Text "setup" to start over.'


# ------------------------------------------------------------------
# Invite (admin command)
# ------------------------------------------------------------------

def handle_invite(body, team, admin_user):
    match = re.match(r'invite\s+(\+?[\d\s\-().]+)\s+as\s+(.+)', body, re.IGNORECASE)
    if not match:
        return 'Format: "invite +15551234567 as Sarah"'

    raw_phone = re.sub(r'[\s\-().]', '', match.group(1))
    phone = raw_phone if raw_phone.startswith('+') else f'+1{raw_phone}'
    name = match.group(2).strip()

    if User.objects.filter(team=team, phone_number=phone).exists():
        existing = User.objects.get(team=team, phone_number=phone)
        return f'{existing.name} is already on the team.'

    PendingInvite.objects.update_or_create(
        team=team, phone_number=phone,
        defaults={'name': name},
    )

    try:
        from core.services import sms_service
        sms_service.send(
            to=phone,
            body=(
                f'Hi {name}! {admin_user.name} added you to {team.name} on TextApp.\n\n'
                f'Reply to this number to manage tasks by text. Text anything to get started.'
            ),
            team_id=str(team.id),
        )
    except Exception as e:
        logger.error('Failed to send invite SMS: %s', e)
        return f"Added {name}, but couldn't send them a text (bad number?)."

    return f'Invited! Welcome SMS sent to {name}.'


# ------------------------------------------------------------------
# New member joins after receiving invite
# ------------------------------------------------------------------

def _handle_new_member_join(phone, body, team, invite):
    name = invite.name or body.strip() or 'New Member'
    User.objects.create(team=team, name=name, phone_number=phone)
    invite.delete()
    return (
        f'Welcome to {team.name}, {name}! \U0001f44b\n\n'
        f"Here's what you can do:\n"
        f'\u2022 "Add task: write Q1 report" \u2014 create a task\n'
        f'\u2022 "My tasks" \u2014 see your open tasks\n'
        f'\u2022 "Mark Q1 report done" \u2014 update a task\n'
        f'\u2022 "Assign Q1 report to Sarah" \u2014 reassign'
    )
