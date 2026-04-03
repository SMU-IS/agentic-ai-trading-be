from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from .api.routes import brokerage, trading_db, telegram, yahoo


app = FastAPI(
    title="Alpaca Broker Service",
    version="1.0.0",
    root_path="/api/v1/trading",
)

# Initialize Prometheus Instrumentator
Instrumentator().instrument(app).expose(app)

app.include_router(brokerage.router, prefix="", tags=["brokerage"])
app.include_router(yahoo.router, prefix="/yahoo", tags=["yahoo"])
app.include_router(trading_db.router, prefix="/decisions", tags=["decisions"])
app.include_router(telegram.router, prefix="/telegram", tags=["telegram"])
