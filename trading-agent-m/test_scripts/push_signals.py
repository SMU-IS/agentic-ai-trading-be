import asyncio
import redis.asyncio as aioredis
from app.core.config import env_config

SIGNAL_IDS = [
    "69d7b66851acd9f87166eb24",
    "69d7a830c8798609be79861d",
    "69d7b2cdc8798609be798620",
    "69d7a830c8798609be79861d",
    "69d65d0fefcaf610b805ea3a",
    "69d65656673d2fc46b789253",
    "69d64c32673d2fc46b789251",
    "69d64b75673d2fc46b78924f",
]

async def main():
    redis_con = f"redis://:{env_config.redis_password}@{env_config.redis_host}:{env_config.redis_port}"
    r = await aioredis.from_url(redis_con)

    stream = env_config.redis_signal_stream
    print(f"📤 Pushing {len(SIGNAL_IDS)} signals to '{stream}'...")

    for signal_id in SIGNAL_IDS:
        msg_id = await r.xadd(stream, {"signal_id": signal_id})
        print(f"   ✅ {signal_id} → {msg_id}")

    await r.aclose()
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
