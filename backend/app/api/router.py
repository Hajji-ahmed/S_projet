from fastapi import APIRouter

from app.api import health

# Tous les endpoints sont sous /api. Ajouter ici le routeur de chaque nouveau module.
api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
