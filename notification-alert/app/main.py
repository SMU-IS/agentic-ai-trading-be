import asyncio
from fastapi import FastAPI
from app.workers.sentiment_to_notification import SentimentBridge

app = FastAPI()

@app.on_event("startup")
async def start_consumers():
    """
    Start both Redis consumers when FastAPI starts.
    """
    # Sentiment -> Notification bridge
    sentiment_bridge = SentimentBridge()
    asyncio.create_task(sentiment_bridge.async_start())

    # Notification consumer 
