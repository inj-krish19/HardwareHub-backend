import logging
import secrets

from fastapi import Header, HTTPException, Request

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _same(supplied: str, expected: str) -> bool:
    """Compare in constant time, so the time taken does not hint at how much matched."""
    return secrets.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


def require_admin(
    request: Request,
    x_admin_id: str = Header(..., alias="X-Admin-Id"),
    x_admin_secret: str = Header(..., alias="X-Admin-Secret"),
) -> None:
    settings = get_settings()
    # Both checks always run (no early exit), so a wrong id and a wrong secret look the same.
    id_ok = _same(x_admin_id, settings.ADMIN_ID)
    secret_ok = _same(x_admin_secret, settings.ADMIN_SECRET)
    if not (id_ok and secret_ok):
        # No credentials in the log, only that a login failed and from where.
        client = request.client.host if request.client else "unknown"
        logger.warning("admin login failed from %s", client)
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")