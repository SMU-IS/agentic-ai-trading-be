import redis

from app.core.config import env_config
from app.utils.logger import setup_logging

logger = setup_logging()


class RedisService:
    def __init__(self):
        self.client = redis.Redis(
            host=env_config.redis_host,
            port=env_config.redis_port,
            password=env_config.redis_password,
            decode_responses=True,
        )
        self._verify_connection()

    def _verify_connection(self):
        try:
            self.client.ping()
            logger.info("✅ Redis Cloud connection verified successfully.")
        except redis.exceptions.AuthenticationError:
            logger.error("❌ Redis Authentication failed.")
        except Exception as e:
            logger.error(f"❌ Redis Connection Error: {e}")

    def get_cached_prompt(self, key: str) -> str | None:
        try:
            return self.client.get(key)
        except Exception as e:
            logger.error(f"Redis GET error: {e}")
            return None

    def set_cached_prompt(self, key: str, value: str, expiry: int = 86400):
        try:
            self.client.setex(key, expiry, value)
        except Exception as e:
            logger.error(f"Redis SETEX error: {e}")
