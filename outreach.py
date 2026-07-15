"""Draft the WhatsApp outreach message + a click-to-chat link.

For the vertical slice we DRAFT and store the message (and a wa.me link)
so you can review/send. Full WhatsApp Business API auto-send is wired in
after the slice is validated -- that keeps the sender number safe from
spam bans while we confirm quality.
"""
import re
import urllib.parse


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def draft_message(lead: dict, live_url: str) -> str:
    name = lead.get("name", "there")
    return (
        f"Hi {name}! 👋 I noticed your business doesn't have a website yet, "
        f"so I built one for you as a free preview:\n\n{live_url}\n\n"
        f"It's mobile-friendly with your photos, services, and contact info. "
        f"If you'd like it live on your own domain with any changes, I can "
        f"set that up for ₹1000. Want me to go ahead? 😊"
    )


def wa_link(lead: dict, message: str) -> str:
    """wa.me click-to-chat link -- opens WhatsApp with the message prefilled."""
    num = _digits(lead.get("phone", ""))
    text = urllib.parse.quote(message)
    if num:
        return f"https://wa.me/{num}?text={text}"
    return f"https://wa.me/?text={text}"


import requests
import config

def send_whatsapp_message(to_phone: str, text: str) -> dict:
    """Send a text message directly using the Meta WhatsApp Business Cloud API.
    Returns the response JSON dict or simulated response if credentials are unset."""
    if not config.WHATSAPP_ACCESS_TOKEN or not config.WHATSAPP_PHONE_NUMBER_ID:
        print(f"[WhatsApp Mock Send] to {to_phone}: {text}")
        return {"mock": True, "status": "simulated"}

    # Clean phone: only digits (Meta API requires digits without + or spaces)
    clean_phone = _digits(to_phone)
    
    url = f"https://graph.facebook.com/v20.0/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_phone,
        "type": "text",
        "text": {
            "body": text
        }
    }
    
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()
