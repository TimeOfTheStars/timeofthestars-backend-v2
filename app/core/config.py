from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Приложение ---
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8002
    SECRET_KEY: str = "change-this-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    CORS_ORIGINS: str = "*"

    # --- База данных ---
    DATABASE_URL: str | None = None
    DB_NAME: str = Field(default="tots", validation_alias=AliasChoices("DB_NAME", "POSTGRESQL_DATABASE"))
    DB_USER: str = Field(default="postgres", validation_alias=AliasChoices("DB_USER", "POSTGRESQL_USERNAME"))
    DB_PASSWORD: str = Field(default="postgres", validation_alias=AliasChoices("DB_PASSWORD", "POSTGRESQL_PASSWORD"))
    DB_HOST: str = Field(default="localhost", validation_alias=AliasChoices("DB_HOST", "POSTGRESQL_HOST"))
    DB_PORT: str = Field(default="5432", validation_alias=AliasChoices("DB_PORT", "POSTGRESQL_PORT"))

    # --- Файлы ---
    MEDIA_DIR: str = "media"
    MAX_UPLOAD_MB: int = 10

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy URL (asyncpg)."""
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif url.startswith("sqlite://"):
                url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)
            return url
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def sync_database_url(self) -> str:
        """Sync URL for Alembic (psycopg/asyncpg-less)."""
        url = self.database_url
        return url.replace("+asyncpg", "").replace("+aiosqlite", "")


settings = Settings()
