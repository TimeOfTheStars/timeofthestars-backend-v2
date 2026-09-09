from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change-this-secret-key-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Приложение ---
    ENV: str = "dev"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8002
    SECRET_KEY: str = DEFAULT_SECRET_KEY
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
    # 25 МБ: снимок с зеркалки — это 10-15 МБ, прежние 10 их отсекали.
    # Менять вместе с request_body max_size в Caddy (там должен быть запас).
    MAX_UPLOAD_MB: int = 25

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def is_prod(self) -> bool:
        return self.ENV.strip().lower() in {"prod", "production"}

    @model_validator(mode="after")
    def _no_unsafe_defaults_in_prod(self) -> "Settings":
        """В проде отказываемся стартовать с дефолтами из публичного репозитория."""
        if not self.is_prod:
            return self

        problems: list[str] = []
        if self.SECRET_KEY == DEFAULT_SECRET_KEY:
            problems.append("SECRET_KEY остался дефолтным (openssl rand -hex 32)")
        if self.CORS_ORIGINS == "*":
            problems.append(
                "CORS_ORIGINS='*' недопустим: вместе с cookie-сессиями это разрешает "
                "credentialed-запросы с любого сайта. Укажите точные origin'ы"
            )
        if not self.DATABASE_URL and self.DB_PASSWORD == "postgres":
            problems.append("DB_PASSWORD остался дефолтным")
        if problems:
            raise ValueError("ENV=prod, но конфигурация небезопасна: " + "; ".join(problems))
        return self

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


settings = Settings()
