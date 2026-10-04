"""Application settings read from the environment."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.cloud_database_settings import cloud_database_url


class Settings(BaseSettings):
    """Runtime settings. Each field reads its uppercase environment variable."""

    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    database_url: str = Field(
        default="postgresql+psycopg://fewia:fewia@localhost:5432/fewia",
        repr=False,
        exclude=True,
    )


_cloud_url = cloud_database_url()
settings = (
    Settings()
    if _cloud_url is None
    else Settings(database_url=_cloud_url.render_as_string(hide_password=False))
)
