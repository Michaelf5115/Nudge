import logging

from django.conf import settings
from django.http import HttpResponse
from twilio.request_validator import RequestValidator

logger = logging.getLogger(__name__)


def twilio_required(view_func):
    """
    Decorator that validates the X-Twilio-Signature header.
    Skipped when SKIP_TWILIO_VALIDATION=true (dev/test).
    """
    def wrapper(request, *args, **kwargs):
        if settings.SKIP_TWILIO_VALIDATION:
            return view_func(request, *args, **kwargs)

        signature = request.META.get('HTTP_X_TWILIO_SIGNATURE', '')

        # Reconstruct the full URL exactly as Twilio signed it
        host = request.META.get('HTTP_X_FORWARDED_HOST') or request.META.get('HTTP_HOST', '')
        proto = request.META.get('HTTP_X_FORWARDED_PROTO') or (
            'https' if request.is_secure() else 'http'
        )
        full_url = f'{proto}://{host}{request.get_full_path()}'

        # POST params as a plain dict (Twilio expects single-value mapping)
        params = {k: v for k, v in request.POST.items()}

        validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
        if not validator.validate(full_url, params, signature):
            logger.warning('[Security] Invalid Twilio signature from %s', request.META.get('REMOTE_ADDR'))
            return HttpResponse('Forbidden', status=403)

        return view_func(request, *args, **kwargs)

    wrapper.__name__ = view_func.__name__
    return wrapper
