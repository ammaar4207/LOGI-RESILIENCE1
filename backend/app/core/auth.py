import httpx
import logging
from typing import List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger("logi-resilience")
settings = get_settings()

security = HTTPBearer(auto_error=False)

# Configuration settings (can be overridden in settings/env)
KEYCLOAK_URL = getattr(settings, "KEYCLOAK_URL", "http://keycloak:8080")
KEYCLOAK_REALM = getattr(settings, "KEYCLOAK_REALM", "logiresilience")
KEYCLOAK_CLIENT_ID = getattr(settings, "KEYCLOAK_CLIENT_ID", "logi-resilience-api")

JWKS_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"

class UserProfile(BaseModel):
    username: str
    roles: List[str] = Field(default_factory=list)
    email: Optional[str] = None

# Cache for JWKS keys to avoid requesting Keycloak on every request
_cached_jwks = None

async def fetch_jwks() -> Optional[dict]:
    global _cached_jwks
    if _cached_jwks:
        return _cached_jwks

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(JWKS_URL, timeout=3.0)
            if resp.status_code == 200:
                _cached_jwks = resp.json()
                logger.info("Successfully loaded JWKS from Keycloak.")
                return _cached_jwks
    except Exception as exc:
        logger.debug("Keycloak JWKS endpoint not reachable: %s. Using development fallback mode.", exc)
    return None

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserProfile:
    """
    FastAPI dependency that extracts and validates the Keycloak JWT token.
    In development environments, mock tokens are allowed for testing.
    In production, only valid Keycloak JWT tokens are accepted.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # 1. Developer Mock Token Fallback (DEVELOPMENT ONLY — never in production)
    is_dev = settings.ENVIRONMENT in ("development", "dev") or settings.DEBUG
    if is_dev and token == "mock-admin-token":
        logger.info("Mock admin token authenticated (development mode only).")
        return UserProfile(username="admin_mock", roles=["admin", "dispatcher"], email="admin@logiresilience.io")
    elif is_dev and token == "mock-dispatcher-token":
        return UserProfile(username="dispatcher_mock", roles=["dispatcher"], email="dispatcher@logiresilience.io")
    elif is_dev and token == "mock-viewer-token":
        return UserProfile(username="viewer_mock", roles=["viewer"], email="viewer@logiresilience.io")

    # 2. Keycloak Token Validation (required in all environments)
    jwks = await fetch_jwks()
    if not jwks:
        # Keycloak is unreachable — in development allow guest, in production DENY
        if is_dev:
            logger.warning("Keycloak offline and no mock token. Dev guest mode active.")
            return UserProfile(username="dev_guest", roles=["admin", "dispatcher"], email="dev@guest.io")
        
        # PRODUCTION: Fail secure — never allow bypass
        logger.error("CRITICAL SECURITY: Keycloak offline in production. Authentication rejected.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication server unavailable. Please try again later.",
        )

    try:
        # Extract kid from token header
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token headers: missing kid")

        # Find matching key in JWKS
        key = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key = k
                break

        if not key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No matching public key found in JWKS")

        # Decode and verify token
        issuer_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=KEYCLOAK_CLIENT_ID,
            issuer=issuer_url,
            options={"verify_aud": False}
        )

        username = payload.get("preferred_username") or payload.get("sub", "unknown")
        email = payload.get("email")

        # Extract roles from Realm Access and Resource/Client Access
        roles = []
        realm_access = payload.get("realm_access", {})
        roles.extend(realm_access.get("roles", []))

        resource_access = payload.get("resource_access", {})
        client_access = resource_access.get(KEYCLOAK_CLIENT_ID, {})
        roles.extend(client_access.get("roles", []))

        return UserProfile(username=username, roles=roles, email=email)

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token validation failed: {str(exc)}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Authentication check encountered an unexpected error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal authentication validation failed")

def require_roles(allowed_roles: List[str]):
    """
    Role guarding helper.
    Example usage: Depends(require_roles(["admin", "dispatcher"]))
    """
    def dependency(user: UserProfile = Depends(get_current_user)) -> UserProfile:
        if not any(role in user.roles for role in allowed_roles):
            logger.warning(
                "User '%s' lacks permissions. Required: %s, Found: %s",
                user.username, allowed_roles, user.roles
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Insufficient privileges"
            )
        return user
    return dependency
