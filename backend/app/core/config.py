from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valeur de développement : volontairement reconnaissable pour être refusée en production
DEV_JWT_SECRET = "dev-only-secret-change-me-before-any-real-deployment"
MIN_PRODUCTION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Paramètres lus depuis les variables d'environnement (voir `.env.example`)."""

    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://simtis:simtis_dev_password@db:5432/simtis"
    # Origines autorisées à appeler l'API depuis le navigateur, séparées par des virgules
    cors_origins: str = "http://localhost:3000"

    # Authentification
    jwt_secret: str = DEV_JWT_SECRET
    access_token_minutes: int = 15
    session_hours: int = 12
    # Après N échecs consécutifs, le compte est verrouillé pendant `lockout_minutes`
    max_login_failures: int = 5
    lockout_minutes: int = 15

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _refuse_weak_secret_in_production(self) -> "Settings":
        if self.is_production and (
            self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < MIN_PRODUCTION_SECRET_LENGTH
        ):
            raise ValueError(
                "JWT_SECRET doit être défini en production, avec au moins "
                f"{MIN_PRODUCTION_SECRET_LENGTH} caractères (valeur de développement refusée)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
