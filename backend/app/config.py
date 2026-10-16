from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ANKI_",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+asyncpg://anki:anki_db_2026_secure@localhost:5432/anki"
    DATABASE_URL_SYNC: str = "postgresql://anki:anki_db_2026_secure@localhost:5432/anki"

    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 1440
    JWT_REFRESH_EXPIRE_DAYS: int = 7
    TASK_DIR: str = "/var/lib/anki/tasks"
    UPLOAD_DIR: str = "/var/lib/anki/uploads"
    WORK_DIR: str = "/tmp/anki-v2"
    WORKER_MAX: int = 2

    CREDENTIAL_ENCRYPTION_KEY: str = "change-me-32-bytes-key-here!!!!!"

    SYNC_ENDPOINT: str = "http://127.0.0.1:8080"
    SYNC_USERNAME: str = "anki_user"
    SYNC_PASSWORD: str = "anki_sync_2024"
    SYNC_MEDIA_TIMEOUT_SECS: int = 300
    PUSH_MODE: str = "sync_client"

    AUTH_SERVICE_URL: str = "https://auth.3mudi.com"
    AUTH_SERVICE_TIMEOUT: int = 10

    COHERE_DEVICE: str = "cpu"

    FRONTEND_DIST: str = "/opt/anki-app/frontend/dist"


settings = Settings()
