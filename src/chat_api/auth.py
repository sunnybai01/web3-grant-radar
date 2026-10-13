import hmac
import os

from fastapi import Header, HTTPException

KEY_ENV = "CHAT_API_INTERNAL_KEY"
MIN_KEY_LENGTH = 16


def _configured_key() -> str:
    return os.getenv(KEY_ENV, "").strip()


def require_configured_key() -> None:
    """Refuse to serve without a usable key.

    An empty key used to switch auth off: the deployed chat-api had none, so
    delete, reset-dedup and manual scans answered anyone who could reach it.
    """
    if len(_configured_key()) < MIN_KEY_LENGTH:
        raise RuntimeError(
            f"{KEY_ENV} must be set to a random value of at least {MIN_KEY_LENGTH} "
            "characters, the same value as in apps/chat-web/.env"
        )


async def verify_internal_key(x_internal_key: str = Header(default="")) -> None:
    expected = _configured_key()
    if not expected:
        # Fail closed even if startup was bypassed.
        raise HTTPException(status_code=503, detail="internal key not configured")
    if not hmac.compare_digest(x_internal_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="invalid internal key")
