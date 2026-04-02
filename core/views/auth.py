import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core import models
from core.services import email_service, sms_service

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# POST /api/waitlist
# ------------------------------------------------------------------

@csrf_exempt
@require_POST
def waitlist(request):
    data = _parse_body(request)
    addr = data.get('email', '').strip()

    if not addr or '@' not in addr:
        return JsonResponse({'error': 'Invalid email address.'}, status=400)

    try:
        models.Waitlist.objects.create(email=addr.lower())
    except IntegrityError:
        pass  # duplicate — return ok silently so we don't leak existence
    except Exception as e:
        logger.error('[Waitlist] DB error: %s', e)
        return JsonResponse({'error': 'Could not save your email. Please try again.'}, status=500)

    logger.info('[Waitlist] New signup: %s', addr.lower())
    return JsonResponse({'ok': True})


# ------------------------------------------------------------------
# POST /api/auth/login
# Always returns 200 — never reveals whether the account exists.
# ------------------------------------------------------------------

@csrf_exempt
@require_POST
def login(request):
    data = _parse_body(request)
    addr = data.get('email', '').strip()
    phone = data.get('phone', '').strip()

    if not addr and not phone:
        return JsonResponse({'error': 'Provide an email or phone number.'}, status=400)

    method = 'email' if addr else 'phone'
    response = JsonResponse({'ok': True})
    response['X-Auth-Method'] = method

    try:
        if method == 'email':
            _handle_email_login(addr.lower())
        else:
            _handle_phone_login(phone)
    except Exception as e:
        logger.error('[Auth] Login error (%s): %s', method, e)

    return response


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _handle_email_login(addr):
    try:
        team = models.Team.objects.get(admin_email=addr, setup_complete=True)
    except models.Team.DoesNotExist:
        logger.info('[Auth] Email login — no team found for: %s', addr)
        return

    token = _create_magic_token(team)
    url = f'{settings.BASE_URL}/dashboard?token={token.token}'
    email_service.send_magic_link(to=addr, team_name=team.name, url=url)
    logger.info('[Auth] Magic link emailed to %s for team "%s"', addr, team.name)


def _handle_phone_login(phone_raw):
    digits = re.sub(r'\D', '', phone_raw)
    if digits.startswith('1') and len(digits) == 11:
        phone = f'+{digits}'
    elif len(digits) == 10:
        phone = f'+1{digits}'
    else:
        phone = phone_raw

    try:
        team = models.Team.objects.get(admin_phone=phone, setup_complete=True)
    except models.Team.DoesNotExist:
        logger.info('[Auth] Phone login — no team found for: %s', phone)
        return

    token = _create_magic_token(team)
    url = f'{settings.BASE_URL}/dashboard?token={token.token}'
    sms_service.send(
        to=phone,
        body=f'Your {team.name} dashboard link (expires 24h):\n{url}',
        team_id=str(team.id),
    )
    logger.info('[Auth] Magic link texted to %s for team "%s"', phone, team.name)


def _create_magic_token(team):
    return models.MagicToken.objects.create(
        team=team,
        token=secrets.token_hex(32),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )


def _parse_body(request):
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return request.POST
