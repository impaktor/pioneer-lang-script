"""Read environment variables and define constants."""

import os
from pathlib import Path
from typing import cast

from pydantic import SecretStr
from pydantic_settings import BaseSettings

# Configuration values are read from (most important first):
# - Environment variables
# - Values defined in the .env-file $CONFIG_FILE (or "config.env" if unset)
# - Default values defined in the Settings class of this file
CONFIG_FILE = os.environ.get("CONFIG_FILE", "config.env")


class Settings(BaseSettings):
    """Define configuration variables."""

    # TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL
    LOGLEVEL: str = "DEBUG"

    # Path relative home folder:
    PIONEER_PATH: Path = Path("/home/karlf/usr/src/pioneer/")

    OUTPUT_DIRECTORY: Path = Path(__file__).parents[2].absolute() / "output"

    API_TOKEN: SecretStr = cast(SecretStr, "")

    class Config:
        """Pydantic BaseSettings configuration."""

        # We're reading variable values from this file
        env_file = CONFIG_FILE


# Create an instance of the Settings-class, to be imported
settings = Settings()
