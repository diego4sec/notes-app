from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.config import settings

_bearer = HTTPBearer(auto_error=True)

# Authentication is not authorization. A valid token from a realm that hosts
# other applications is not by itself permission to use this one.
REQUIRED_ROLE = "notes-user"

# ponytail: one process-global JWKS client using PyJWT's own key cache. Reach for
# a shared cache only if key-rotation storms across many replicas show up.
_jwks = PyJWKClient(settings.oidc_jwks_url, cache_keys=True)


@dataclass(frozen=True)
class User:
    id: UUID
    email: str | None
    name: str | None
    roles: list[str]


def current_user(cred: HTTPAuthorizationCredentials = Depends(_bearer)) -> User:
    try:
        key = _jwks.get_signing_key_from_jwt(cred.credentials).key
        claims = jwt.decode(
            cred.credentials,
            key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError:
        # Deliberately vague: never tell a caller which check failed.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from None

    roles = claims.get("realm_access", {}).get("roles", [])
    check_role(roles)

    return User(
        id=UUID(claims["sub"]),
        email=claims.get("email"),
        name=claims.get("name"),
        roles=roles,
    )


def check_role(roles: list[str]) -> None:
    """403, not 404: the caller is authenticated, just not entitled. Split out
    so it is testable without minting a real token."""
    if REQUIRED_ROLE not in roles:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"missing required role: {REQUIRED_ROLE}"
        )
