import logging

from django.conf import settings
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _client


def send(to, body, team_id=None, user_id=None):
    """Send an SMS via Twilio and log it to the messages table."""
    _get_client().messages.create(
        from_=settings.TWILIO_PHONE_NUMBER,
        to=to,
        body=body,
    )
    _log_outbound(team_id, user_id, body)


def _log_outbound(team_id, user_id, body):
    from core.models import Message, Team, User
    try:
        team = Team.objects.get(id=team_id) if team_id else None
        user = User.objects.get(id=user_id) if user_id else None
        Message.objects.create(team=team, user=user, direction='out', body=body)
    except Exception as e:
        logger.error('Failed to log outbound SMS: %s', e)


def twiml_reply(body):
    """Return a TwiML XML string that tells Twilio to send a reply SMS."""
    response = MessagingResponse()
    response.message(body)
    return str(response)
