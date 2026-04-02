import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core import models
from core.services import email_service

logger = logging.getLogger(__name__)

_COOKIE = 'ta_team'
_COOKIE_MAX_AGE = 8 * 60 * 60  # 8 hours


def _error_page(message, status=401):
    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>TextApp</title>'
        '<style>body{font-family:system-ui,sans-serif;display:flex;align-items:center;'
        'justify-content:center;min-height:100vh;margin:0;background:#f5f5f5}'
        '.box{background:#fff;border-radius:12px;padding:40px;max-width:400px;'
        'text-align:center;box-shadow:0 2px 12px rgba(0,0,0,.08)}'
        'h2{margin:0 0 12px;font-size:20px}p{color:#666;margin:0;font-size:15px}</style>'
        f'</head><body><div class="box"><h2>TextApp</h2><p>{message}</p></div></body></html>'
    )
    return HttpResponse(html, status=status)


# ------------------------------------------------------------------
# GET /dashboard?token=xxx  → validate token, set cookie, redirect
# ------------------------------------------------------------------

@require_GET
def dashboard_auth(request):
    token_value = request.GET.get('token')
    if not token_value:
        return _error_page('No token provided. Text "dashboard" to your team number.')

    now = datetime.now(timezone.utc)
    try:
        record = models.MagicToken.objects.select_related('team').get(
            token=token_value,
            used=False,
            expires_at__gt=now,
        )
    except models.MagicToken.DoesNotExist:
        return _error_page('Link expired or already used. Text "dashboard" for a new one.')

    record.used = True
    record.save()

    team_id = str(record.team.id)
    response = redirect(f'/dashboard/view?team={team_id}')
    response.set_cookie(
        _COOKIE,
        team_id,
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax',
    )
    return response


# ------------------------------------------------------------------
# GET /dashboard/view?team=xxx  → serve dashboard HTML
# ------------------------------------------------------------------

@require_GET
def dashboard_view(request):
    team_id = request.GET.get('team')
    cookie_team = request.COOKIES.get(_COOKIE)

    if not team_id or team_id != cookie_team:
        return _error_page('Session expired. Text "dashboard" for a new link.')

    if not models.Team.objects.filter(id=team_id).exists():
        return _error_page('Team not found.', status=404)

    path = os.path.join(settings.BASE_DIR, 'public', 'dashboard.html')
    return FileResponse(open(path, 'rb'), content_type='text/html')


# ------------------------------------------------------------------
# GET /api/tasks  → JSON task data for the dashboard JS
# ------------------------------------------------------------------

@require_GET
def api_tasks(request):
    team_id = request.COOKIES.get(_COOKIE)
    if not team_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        team = models.Team.objects.get(id=team_id)
    except models.Team.DoesNotExist:
        return JsonResponse({'error': 'Team not found'}, status=404)

    tasks_qs = (
        models.Task.objects.filter(team=team)
        .select_related('owner', 'created_by')
        .order_by('due_date')
    )
    users_qs = models.User.objects.filter(team=team).order_by('joined_at')

    tasks = [
        {
            'id': str(t.id),
            'title': t.title,
            'status': t.status,
            'due_date': t.due_date.isoformat() if t.due_date else None,
            'created_at': t.created_at.isoformat(),
            'updated_at': t.updated_at.isoformat(),
            'owner': {'name': t.owner.name} if t.owner else None,
            'created_by': {'name': t.created_by.name} if t.created_by else None,
        }
        for t in tasks_qs
    ]
    users = [
        {
            'id': str(u.id),
            'name': u.name,
            'phone_number': u.phone_number,
            'joined_at': u.joined_at.isoformat(),
        }
        for u in users_qs
    ]
    team_data = {
        'id': str(team.id),
        'name': team.name,
        'phone_number': team.phone_number,
        'timezone': team.timezone,
        'digest_hour': team.digest_hour,
    }

    return JsonResponse({'team': team_data, 'tasks': tasks, 'users': users})


# ------------------------------------------------------------------
# POST /api/send-dashboard-link  → email a fresh link to the admin
# ------------------------------------------------------------------

@csrf_exempt
@require_POST
def send_dashboard_link(request):
    team_id = request.COOKIES.get(_COOKIE)
    if not team_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        team = models.Team.objects.get(id=team_id)
    except models.Team.DoesNotExist:
        return JsonResponse({'error': 'Team not found'}, status=404)

    if not team.admin_email:
        return JsonResponse({'error': 'No admin email on file'}, status=400)

    token = models.MagicToken.objects.create(
        team=team,
        token=secrets.token_hex(32),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    url = f'{settings.BASE_URL}/dashboard?token={token.token}'
    email_service.send_magic_link(to=team.admin_email, team_name=team.name, url=url)
    return JsonResponse({'ok': True})
