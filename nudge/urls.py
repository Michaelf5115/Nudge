from datetime import datetime, timezone

from django.http import JsonResponse
from django.urls import path

from core.views.auth import login, waitlist
from core.views.dashboard import api_tasks, dashboard_auth, dashboard_view, send_dashboard_link
from core.views.sms import sms_webhook


def health(request):
    return JsonResponse({'status': 'ok', 'ts': datetime.now(timezone.utc).isoformat()})


urlpatterns = [
    path('health', health),
    path('sms', sms_webhook),
    path('api/waitlist', waitlist),
    path('api/auth/login', login),
    path('dashboard', dashboard_auth),
    path('dashboard/view', dashboard_view),
    path('api/tasks', api_tasks),
    path('api/send-dashboard-link', send_dashboard_link),
]
