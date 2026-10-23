"""Typed access to the configuration and collections of the app."""

from typing import Any

from foca import get_collection as get_foca_collection
from foca import get_config
from pymongo.collection import Collection

from trs_filer.custom_config import CustomConfig

# Name of the app's database, as configured (`db.dbs` in `config.yaml`); with
# environment variable `MONGO_DBNAME` set, FOCA uses that name in MongoDB
DB = "trsStore"


def get_custom_config() -> CustomConfig:
    """Get the custom configuration of the current app.

    Returns:
        Custom configuration.

    Raises:
        RuntimeError: The app has no custom configuration.
    """
    # FOCA keeps the custom configuration as an untyped extra field; it is an
    # instance of `CustomConfig` only if the app loads the model by its full
    # path (`trs_filer.custom_config.CustomConfig`)
    custom = (get_config().model_extra or {}).get("custom")
    if not isinstance(custom, CustomConfig):
        raise RuntimeError(
            f"No custom configuration of type {CustomConfig}; check that "
            "`custom_config_model` is its full module path"
        )
    return custom


def get_collection(name: str) -> Collection[dict[str, Any]]:
    """Get a collection of the app's database.

    Args:
        name: Name of the collection, as configured.

    Returns:
        MongoDB collection.
    """
    return get_foca_collection(db=DB, collection=name)
