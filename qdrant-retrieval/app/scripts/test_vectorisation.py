import asyncio

from app.core.logger import logger
from app.data import MOCK_REDDIT_PAYLOAD
from app.schemas.raw_news_payload import SourcePayload
from app.services.vectorisation import VectorisationService


async def run_test():
    logger.info("🚀 Vectorising...")
    try:
        payload = SourcePayload(**MOCK_REDDIT_PAYLOAD)
        logger.info("✅ Payload Validated")
    except Exception as e:
        logger.info(f"❌ Payload Validation Failed: {e}")
        return

    try:
        service = VectorisationService()
        await service.ensure_indexes()
    except Exception as e:
        logger.error(f"Error: {e}")
        return

    try:
        result = await service.get_sanitised_news_payload(payload)  # type: ignore
        logger.info("\n🎉 Test Success!")
        logger.info(f"Response: {result}")
    except RuntimeError as e:
        logger.error(f"\n❌ Test Failed during ingestion: {e}")


if __name__ == "__main__":
    asyncio.run(run_test())
