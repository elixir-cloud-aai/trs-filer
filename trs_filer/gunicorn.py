"""Gunicorn entry point."""

import os

from foca import get_config

from trs_filer.app import init_app
from trs_filer.utils import DB

# Source application configuration
init_app()
app_config = get_config()
# configured in `config.yaml`; checked for type checkers
assert app_config.db is not None, "no database configured"

# Set Gunicorn number of workers and threads
workers = int(os.environ.get("GUNICORN_PROCESSES", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "1"))

# Set allowed IPs
forwarded_allow_ips = "*"  # pylint: disable=invalid-name

# Set Gunicorn bind address
bind = f"{app_config.server.host}:{app_config.server.port}"

# Source the environment variables for the Gunicorn workers; the database
# name defaults to the configured one (`db.dbs` in `config.yaml`)
raw_env = [
    f"WES_CONFIG={os.environ.get('TRS_CONFIG', '')}",
    f"MONGO_HOST={os.environ.get('MONGO_HOST', app_config.db.host)}",
    f"MONGO_PORT={os.environ.get('MONGO_PORT', app_config.db.port)}",
    f"MONGO_DBNAME={os.environ.get('MONGO_DBNAME', DB)}",
    f"MONGO_USERNAME={os.environ.get('MONGO_USERNAME', '')}",
    f"MONGO_PASSWORD={os.environ.get('MONGO_PASSWORD', '')}",
]
