"""Cloudflare Turnstile verification for public deployments.

When `TURNSTILE_SECRET_KEY` is set, each question must carry a Turnstile token from the chat
page, and ROSIE checks it with Cloudflare before doing any work. Tokens are single-use and
expire after 300 seconds. With no secret configured, verification is off.
"""
import logging

import httpx

from rosie.config import settings

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

logger = logging.getLogger(__name__)


class TurnstileUnavailable(Exception):
    """Cloudflare could not be reached, or returned something unusable."""


def enabled() -> bool:
    return bool(settings.turnstile_secret_key)


def verify(token: str | None, remote_ip: str | None = None) -> bool:
    """Return True if Cloudflare accepts the token. Raise TurnstileUnavailable if it can't be asked."""
    if not token:
        return False
    data = {"secret": settings.turnstile_secret_key, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        response = httpx.post(SITEVERIFY_URL, data=data, timeout=settings.turnstile_timeout_seconds)
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise TurnstileUnavailable(str(error)) from error
    if result.get("success") is True:
        return True
    # Cloudflare's error codes say why, for example "timeout-or-duplicate" for a reused or
    # expired token, or "invalid-input-response" for a token from a different widget.
    logger.warning(
        "Cloudflare Turnstile rejected a token: %s",
        ", ".join(result.get("error-codes") or ["no error code given"]),
    )
    return False
