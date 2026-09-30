from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Paramètres lus depuis les variables d'environnement (voir `.env.example`)."""

    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://simtis:simtis_dev_password@db:5432/simtis"
    # Origines autorisées à appeler l'API depuis le navigateur, séparées par des virgules
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
