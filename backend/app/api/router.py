from fastapi import APIRouter, Depends

from app.api import auth, banks, health
from app.api.deps import get_current_user

# Routes accessibles sans être connecté. Toute nouvelle route publique doit aussi être ajoutée à
# PUBLIC_ROUTES dans tests/test_permissions.py, sinon le test de protection par défaut échoue.
public_router = APIRouter()
public_router.include_router(health.router)
public_router.include_router(auth.public_router)

# Toutes les autres routes : un utilisateur connecté est OBLIGATOIRE (401 sinon). Chaque endpoint
# sensible ajoute en plus sa permission : `Depends(require_permission(PermissionCode.X))` (403 sinon).
# Ajouter ici le routeur de chaque nouveau module.
protected_router = APIRouter(dependencies=[Depends(get_current_user)])
protected_router.include_router(auth.protected_router)
protected_router.include_router(banks.router)

api_router = APIRouter(prefix="/api")
api_router.include_router(public_router)
api_router.include_router(protected_router)
