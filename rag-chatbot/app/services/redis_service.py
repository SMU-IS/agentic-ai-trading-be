import redis

from app.core.config import env_config
from app.utils.logger import setup_logging

logger = setup_logging()


class RedisService:
    def __init__(self, client: redis.Redis | None = None):
        if client:
            self.client = client
        else:
            self.client = redis.Redis(
                host=env_config.redis_host,
                port=env_config.redis_port,
                password=env_config.redis_password,
                decode_responses=True,
                max_connections=20,
                socket_timeout=5,
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


# Global instance to be reused
_redis_service = None


def get_redis_service() -> RedisService:
    global _redis_service
    if _redis_service is None:
        _redis_service = RedisService()
    return _redis_service
