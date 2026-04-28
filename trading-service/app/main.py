from fastapi import FastAPI

from .api.routes import brokerage, trading_db, telegram, yahoo, waitlist


app = FastAPI(
    title="Alpaca Broker Service",
    version="1.0.0",
    root_path="/api/v1/trading",
)

app.include_router(brokerage.router, prefix="", tags=["brokerage"])
app.include_router(yahoo.router, prefix="/yahoo", tags=["yahoo"])
app.include_router(trading_db.router, prefix="/decisions", tags=["decisions"])
app.include_router(telegram.router, prefix="/telegram", tags=["telegram"])
app.include_router(waitlist.router, prefix="/waitlist", tags=["waitlist"])
