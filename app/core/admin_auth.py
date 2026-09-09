from fastapi import Header, HTTPException

from app.core.config import get_settings


def require_admin(
    x_admin_id: str = Header(..., alias="X-Admin-Id"),
    x_admin_secret: str = Header(..., alias="X-Admin-Secret"),
) -> None:
    settings = get_settings()
    if x_admin_id != settings.ADMIN_ID or x_admin_secret != settings.ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")