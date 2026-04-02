import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from core.utils import format_due_date, is_overdue, is_today

logger = logging.getLogger(__name__)


def send_team_digest(team):
    """Send each team member their morning task summary."""
    from core.models import User
    from core.services import sms_service

    for user in User.objects.filter(team=team):
        tasks = list(user.owned_tasks.filter(status='open').order_by('due_date'))
        if not tasks:
            continue

        due_strs = [str(t.due_date) if t.due_date else None for t in tasks]

        overdue = [t for t, d in zip(tasks, due_strs) if d and is_overdue(d)]
        today = [t for t, d in zip(tasks, due_strs) if d and is_today(d)]
        upcoming = [t for t, d in zip(tasks, due_strs) if not d or (not is_overdue(d) and not is_today(d))]

        lines = [f"Good morning, {user.name}! Here's your day:", '']

        if overdue:
            lines.append('\u26a0 Overdue:')
            for t in overdue:
                lines.append(f'  \u2022 {t.title} ({format_due_date(str(t.due_date))})')
            lines.append('')

        if today:
            lines.append('\U0001f4cc Due today:')
            for t in today:
                lines.append(f'  \u2022 {t.title}')
            lines.append('')

        if upcoming:
            lines.append('Up next:')
            for t in upcoming[:5]:
                due = f' ({format_due_date(str(t.due_date))})' if t.due_date else ''
                lines.append(f'  \u2022 {t.title}{due}')

        body = '\n'.join(lines)

        try:
            sms_service.send(to=user.phone_number, body=body, team_id=str(team.id), user_id=str(user.id))
            logger.info('[Digest] Sent to %s (%s)', user.name, user.phone_number)
        except Exception as e:
            logger.error('[Digest] Failed for %s: %s', user.name, e)


def check_and_send_digests():
    """Run at the top of each hour; fire digests for any team whose local hour matches."""
    from django.db import close_old_connections
    close_old_connections()

    from core.models import Team

    now_utc = datetime.now(timezone.utc)
    for team in Team.objects.filter(setup_complete=True):
        local_hour = _get_local_hour(now_utc, team.timezone)
        if local_hour == team.digest_hour:
            logger.info('[Digest] Sending for team %s (local hour: %d)', team.name, local_hour)
            try:
                send_team_digest(team)
            except Exception as e:
                logger.error('[Digest] Error for team %s: %s', team.name, e)


def _get_local_hour(dt, timezone_str):
    try:
        return dt.astimezone(ZoneInfo(timezone_str)).hour
    except Exception:
        return dt.utctimetuple().tm_hour


def start_digest_cron():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_and_send_digests, 'cron', minute=0)
    scheduler.start()
    logger.info('[Digest] APScheduler started \u2014 will check hourly for teams due a digest.')
