# Deprecated: use app.core.config.env_config instead.
# This file is kept only for backward compatibility with any legacy imports.
from app.core.config import env_config

REDIS_HOST = env_config.redis_host
REDIS_PORT = env_config.redis_port
REDIS_STREAM_NAME = env_config.redis_stream_name
