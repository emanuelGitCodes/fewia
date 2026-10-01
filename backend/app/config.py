"""Application settings read from the environment."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Each field reads its uppercase environment variable."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = "postgresql+psycopg://fewia:fewia@localhost:5432/fewia"


settings = Settings()
