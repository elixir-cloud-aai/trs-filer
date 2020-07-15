import os

from foca.config.config_parser import ConfigParser

# Source the TRS config for defaults
# flask_config = parse_app_config(config_var='DRS_CONFIG')

# # Gunicorn number of workers and threads
workers = int(os.environ.get('GUNICORN_PROCESSES', '1'))
threads = int(os.environ.get('GUNICORN_THREADS', '1'))

forwarded_allow_ips = '*'

# For configuration handling. TODO: Need to introduce a null check here
flask_config = ConfigParser("app_config.yaml").config

# Gunicorn bind address
bind = '{address}:{port}'.format(
    address=flask_config.server.host,
    port=flask_config.server.port
)

# Source the environment variables for the Gunicorn workers
raw_env = [
    "TRS_CONFIG=%s" % os.environ.get('TRS_CONFIG', ''),
    "MONGO_HOST=%s" % os.environ.get(
        'MONGO_HOST', flask_config.database.host),
    "MONGO_PORT=%s" % os.environ.get(
        'MONGO_PORT', flask_config.database.port),
    "MONGO_DBNAME=%s" % os.environ.get(
        'MONGO_DBNAME', flask_config.database.name),
    "MONGO_USERNAME=%s" % os.environ.get('MONGO_USERNAME', ''),
    "MONGO_PASSWORD=%s" % os.environ.get('MONGO_PASSWORD', '')
]
