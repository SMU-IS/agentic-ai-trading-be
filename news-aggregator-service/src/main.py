import asyncio

from dotenv import load_dotenv
load_dotenv()

import asyncio
from src.services.redis_service import RedisService
from src.workflows.main_workflow import setup_workflow

async def main():
    workflow = await setup_workflow()  # Initializes global services + app

    print("🚀 News Aggregator started...")
    
    redis_service = RedisService()  # Global instance
    await redis_service.connect()
    
    print("🚀 News Aggregator Live!")

    async for article in redis_service.listen_news_stream():
        result = await workflow.run({
            "articles": [article.to_dict()],
            "qdrant_context": [],
            "topics": [],
            "triggered_topics": [],
            "analyses": [],
            "signals": [],
        })
        
        if result["signals"]:
            print(f"📊 Processed batch: {len(result['signals'])} signals generated")

if __name__ == "__main__":
    asyncio.run(main())
