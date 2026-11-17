import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> models.User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_token(creds.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user = db.get(models.User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or not found")
    return user


def require_roles(*roles: str):
    """Dependency factory: allow only the given roles."""

    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission for this action")
        return user

    return checker


def client_info(request: Request) -> tuple[str | None, str | None]:
    """Return the real client IP (Cloudflare/proxy aware) and user agent."""
    ip = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-real-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else None)
    )
    ua = request.headers.get("user-agent")
    return (ip[:45] if ip else None), (ua[:255] if ua else None)


def audit(
    db: Session,
    actor_id: int | None,
    action: str,
    entity: str,
    entity_id,
    detail: str | None = None,
    *,
    request: Request | None = None,
    username: str | None = None,
    ip_address: str | None = None,
):
    """Add an audit row. Pass request/username so IP and actor are recorded and
    the generic HTTP middleware does not add a duplicate entry for the action."""
    if request is not None:
        request.state.audit_recorded = True
        if ip_address is None:
            ip_address, _ = client_info(request)
    db.add(models.AuditLog(
        actor_id=actor_id, username=username[:50] if username else None,
        ip_address=ip_address[:45] if ip_address else None,
        action=action, entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail[:500] if detail else None,
    ))
