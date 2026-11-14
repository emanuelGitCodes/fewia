"""Application settings read from the environment."""

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.cloud_database_settings import cloud_database_url
from app.local_database_settings import DEFAULT_DATABASE_URL, local_database_url


class Settings(BaseSettings):
    """Runtime settings. Each field reads its uppercase environment variable."""

    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    database_url: str = Field(
        default=DEFAULT_DATABASE_URL,
        repr=False,
        exclude=True,
    )


_local_url = local_database_url(
    admin=os.environ.get("FEWIA_LOCAL_BOOTSTRAP_DATABASE") == "1"
)
_cloud_url = _local_url or cloud_database_url()
settings = (
    Settings()
    if _cloud_url is None
    else Settings(database_url=_cloud_url.render_as_string(hide_password=False))
)
