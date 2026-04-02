import logging

import resend
from django.conf import settings

logger = logging.getLogger(__name__)

FROM_EMAIL = 'TextApp <noreply@textapp.co>'


def send_magic_link(to, team_name, url):
    """Send a magic-link email to the team admin for dashboard access."""
    resend.api_key = settings.RESEND_API_KEY

    html = f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 520px; margin: 40px auto; padding: 0 20px; color: #1a1a1a;">
  <h2 style="font-size: 22px; font-weight: 600; margin-bottom: 8px;">{team_name} Dashboard</h2>
  <p style="color: #555; margin-bottom: 28px;">Here's your read-only view of all open tasks.</p>
  <a href="{url}" style="display: inline-block; background: #1a1a1a; color: #fff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-size: 15px; font-weight: 500;">Open Dashboard →</a>
  <p style="color: #aaa; font-size: 13px; margin-top: 24px;">
    This link expires in 24 hours. Text "dashboard" to your team number for a new one.
  </p>
</body>
</html>"""

    params = {
        'from': FROM_EMAIL,
        'to': [to],
        'subject': f'{team_name} \u2014 your dashboard link',
        'html': html,
    }

    result = resend.Emails.send(params)
    if isinstance(result, dict) and 'error' in result:
        logger.error('Email send failed: %s', result['error'])
        raise Exception(result['error'])
    return result
