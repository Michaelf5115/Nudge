import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.handlers.inbound import handle_inbound
from core.middleware import twilio_required
from core.services.sms_service import twiml_reply

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
@twilio_required
def sms_webhook(request):
    from_phone = request.POST.get('From', '')
    to_phone = request.POST.get('To', '')
    body = request.POST.get('Body', '').strip()

    if not from_phone or not body:
        return HttpResponse('<Response></Response>', content_type='text/xml')

    try:
        reply = handle_inbound(from_phone, to_phone, body)
        xml = twiml_reply(reply) if reply else '<Response></Response>'
    except Exception as e:
        logger.error('[SMS] Unhandled error: %s', e)
        xml = '<Response><Message>Something went wrong. Please try again.</Message></Response>'

    return HttpResponse(xml, content_type='text/xml')
