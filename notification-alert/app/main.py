import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.workers.stream_consumer import StreamConsumer
from app.workers.sentiment_to_notification import SentimentBridge
from app.services.notification_service import router as notification_router


app = FastAPI()

app.include_router(notification_router)

@app.on_event("startup")
async def start_consumers():
    """
    Start both Redis consumers when FastAPI starts.
    """
    # Sentiment -> Notification bridge
    sentiment_bridge = SentimentBridge()
    asyncio.create_task(sentiment_bridge.async_start())

    # Notification stream consumer
    stream_consumer = StreamConsumer()
    asyncio.create_task(stream_consumer.async_start())
