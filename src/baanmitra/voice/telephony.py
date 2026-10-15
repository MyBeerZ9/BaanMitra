"""Telephony on the Twilio FREE trial - calls, IVR, escalation, WhatsApp.

Trial-account realities (no card required):
  * you may only call numbers you have verified in the Twilio console
  * outbound messages are prefixed with "Twilio trial"
  * WhatsApp works through the free sandbox (join with a code on your phone)

Safety: `place_call` refuses any number that is not in CONSENTED_NUMBERS.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import settings

log = logging.getLogger("baanmitra.telephony")

_client = None


def client():
    global _client
    if _client is None:
        settings.require("twilio_account_sid", "twilio_auth_token", "twilio_number")
        from twilio.rest import Client
        _client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _client


def is_allowed(number: str) -> bool:
    """The agent may only dial explicitly consented, verified numbers."""
    return number in settings.consented_numbers


# --------------------------------------------------------------------------- #
# outbound IVR
# --------------------------------------------------------------------------- #
def place_call(to: str, audio_url: str, *, gather_action: str = "/twilio/gather",
               language: str = "en-IN") -> str:
    """Play `audio_url` (our TTS) then <Gather> the spoken reply."""
    if not is_allowed(to):
        raise PermissionError(
            f"{to} is not in CONSENTED_NUMBERS. Free-tier Twilio trial can only "
            "call verified numbers, and BaanMitra never dials without consent."
        )
    twiml = (
        f'<Response><Play>{audio_url}</Play>'
        f'<Gather input="speech" action="{gather_action}" method="POST" '
        f'language="{language}" speechTimeout="3" timeout="8">'
        f'<Say voice="Polly.Aditi" language="en-IN">Please speak after the tone.</Say>'
        f'</Gather>'
        f'<Redirect method="POST">{gather_action}?retry=1</Redirect></Response>'
    )
    call = client().calls.create(
        to=to, from_=settings.twilio_number, twiml=twiml,
        status_callback=f"{settings.public_base_url}/twilio/status",
        status_callback_event=["completed", "no-answer", "busy", "failed"],
        status_callback_method="POST",
    )
    log.info("placed call %s -> %s (%s)", call.sid, to, audio_url)
    return call.sid


def confirmation_twiml(reply_url: str) -> str:
    """Play a short confirmation and end the call."""
    return (f'<Response><Play>{reply_url}</Play>'
            f'<Say voice="Polly.Aditi" language="en-IN">Thank you. Stay safe.</Say>'
            f'<Hangup/></Response>')


# --------------------------------------------------------------------------- #
# escalation
# --------------------------------------------------------------------------- #
def send_sms(to: str, body: str) -> Optional[str]:
    if not is_allowed(to):
        log.warning("refusing SMS to non-consented number %s", to)
        return None
    msg = client().messages.create(
        to=to, from_=settings.twilio_number,
        body=("[BaanMitra] " if not settings.twilio_trial else "") + body,
    )
    log.info("escalation SMS %s -> %s", msg.sid, to)
    return msg.sid


def escalation_twiml() -> str:
    return ('<Response><Say voice="Polly.Aditi" language="en-IN">'
            'We could not reach you. Please move to higher ground and contact '
            'your village disaster management committee. '
            'Helpline 1079. Issued with ASDMA and CWC data.</Say>'
            '<Hangup/></Response>')


# --------------------------------------------------------------------------- #
# WhatsApp sandbox
# --------------------------------------------------------------------------- #
def send_whatsapp(to: str, body: str, media_url: Optional[str] = None) -> Optional[str]:
    if not is_allowed(to):
        log.warning("refusing WhatsApp message to non-consented number %s", to)
        return None
    kwargs = {"to": f"whatsapp:{to}", "from_": f"whatsapp:{settings.twilio_number}",
              "body": body}
    if media_url:
        kwargs["media_url"] = [media_url]
    msg = client().messages.create(**kwargs)
    log.info("whatsapp %s -> %s", msg.sid, to)
    return msg.sid
