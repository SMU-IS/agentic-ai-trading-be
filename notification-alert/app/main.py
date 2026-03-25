import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.services.notification_service import router as notification_router
from app.workers.sentiment_to_aggregator import SentimentAggregator
from app.workers.sentiment_to_notification import SentimentBridge
from app.workers.stream_consumer import StreamConsumer

app = FastAPI()

app.include_router(notification_router)


@app.on_event("startup")
async def start_consumers():
    app.state.tasks = []

    # Sentiment -> Aggregator
    sentiment_bridge = SentimentAggregator()
    task1 = asyncio.create_task(sentiment_bridge.async_start())
    app.state.tasks.append(task1)

    # Sentiment -> Notification bridge
    sentiment_bridge = SentimentBridge()
    task2 = asyncio.create_task(sentiment_bridge.async_start())
    app.state.tasks.append(task2)

    # Notification stream consumer
    stream_consumer = StreamConsumer()
    task3 = asyncio.create_task(stream_consumer.async_start())
    app.state.tasks.append(task3)


@app.on_event("shutdown")
async def stop_consumers():
    for task in app.state.tasks:
        task.cancel()

    await asyncio.gather(*app.state.tasks, return_exceptions=True)


@app.get("/")
def health():
    return {"status": "Notification service is healthy"}
