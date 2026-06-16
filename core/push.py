"""
Web Push: schickt Browser-native Push-Benachrichtigungen an die installierte
PWA — Alternative/Ergänzung zu Telegram, funktioniert auch wenn Telegram mal
nicht erreichbar ist oder der User komplett darauf verzichten will.
"""
import json
import logging
from pathlib import Path

import config
from core import db

log = logging.getLogger(__name__)

ALFRED_DIR = Path(__file__).resolve().parent.parent


def _private_key_pem() -> str:
    p = ALFRED_DIR / config.VAPID_PRIVATE_KEY_PATH
    return p.read_text()


def add_subscription(endpoint: str, p256dh: str, auth: str) -> None:
    db.execute(
        "INSERT INTO push_subscriptions (endpoint, p256dh, auth) VALUES (%s, %s, %s) "
        "ON CONFLICT (endpoint) DO NOTHING",
        (endpoint, p256dh, auth),
    )


def remove_subscription(endpoint: str) -> None:
    db.execute("DELETE FROM push_subscriptions WHERE endpoint = %s", (endpoint,))


def send_push(title: str, body: str, url: str = "/") -> int:
    """Schickt eine Push-Notification an alle registrierten Geräte.
    Gibt die Anzahl erfolgreich erreichter Geräte zurück. Synchron (für asyncio.to_thread)."""
    if not config.VAPID_PUBLIC_KEY:
        return 0
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        log.debug("pywebpush nicht installiert – Push übersprungen")
        return 0

    subs = db.query("SELECT endpoint, p256dh, auth FROM push_subscriptions")
    if not subs:
        return 0

    payload = json.dumps({"title": title, "body": body[:200], "url": url})
    sent = 0
    for s in subs:
        sub_info = {
            "endpoint": s["endpoint"],
            "keys": {"p256dh": s["p256dh"], "auth": s["auth"]},
        }
        try:
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=_private_key_pem(),
                vapid_claims={"sub": f"mailto:{config.VAPID_CLAIM_EMAIL}"},
            )
            sent += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                remove_subscription(s["endpoint"])
                log.info("Push-Subscription abgelaufen, entfernt")
            else:
                log.debug(f"Push fehlgeschlagen: {e}")
        except Exception as e:
            log.debug(f"Push fehlgeschlagen: {e}")
    return sent
