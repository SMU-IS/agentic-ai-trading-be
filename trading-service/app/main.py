from dotenv import load_dotenv
load_dotenv()


from fastapi import FastAPI
from .config import settings
from .api.routes import brokerage

app = FastAPI(
    title="Alpaca Broker Service", 
    version="1.0.0",
    root_path="/api/v1/trading",
    )

app.include_router(brokerage.router, prefix="", tags=["brokerage"])
# app.include_router(account.router, prefix="", tags=["account"])
# app.include_router(positions.router, prefix="", tags=["positions"])
# app.include_router(orders.router, prefix="", tags=["orders"])
# app.include_router(data.router, prefix="/data", tags=["data"])