"""
Dépendances FastAPI — authentification et RBAC.

Ce service ne fait AUCUNE émission de token (pas de /login ici) : il se
contente de VÉRIFIER les tokens JWT émis par le backend principal au login,
en utilisant la même SECRET_KEY / ALGORITHM (voir .env.example). Le rôle de
l'utilisateur est relu depuis la table `utilisateurs` (modèle readonly),
exactement comme le fait apps/api/app/api/deps.py côté backend principal.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.readonly import Utilisateur

security_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


def get_current_user(
    request: Request,
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Utilisateur:
    """Extrait l'utilisateur courant : en-tête Authorization Bearer en priorité,
    sinon cookie 'access_token' (posé par le backend principal au login)."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Non authentifié",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if auth_header:
        token = auth_header.credentials
    else:
        token = request.cookies.get("access_token")

    if not token:
        raise credentials_exception

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception

    user_id: str = payload.get("sub")
    if not user_id:
        raise credentials_exception

    logger.warning(f"Recherche utilisateur avec id: {user_id}")
    user = (
        db.query(Utilisateur)
        .filter(Utilisateur.id == UUID(user_id), Utilisateur.active == True)  # noqa: E712
        .first()
    )
    if not user:
        raise credentials_exception

    return user


class RequireRole:
    """Dépendance RBAC — vérifie que l'utilisateur possède un des rôles autorisés."""

    def __init__(self, *roles: UserRole):
        self.roles = roles

    def __call__(self, current_user: Utilisateur = Depends(get_current_user)) -> Utilisateur:
        if current_user.role not in self.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès refusé. Rôle requis : {[r.value for r in self.roles]}",
            )
        return current_user


# Les endpoints /agent/* sont ouverts aux mêmes rôles que côté backend
# principal pour les fonctionnalités CX/agence : CX Manager, Agency Manager,
# Admin (voir apps/api/app/api/deps.py::get_cx_or_agency_manager).
require_agent_access = RequireRole(UserRole.CX_MANAGER, UserRole.AGENCY_MANAGER, UserRole.ADMIN)
