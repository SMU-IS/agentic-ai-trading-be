import asyncio

from fastapi import FastAPI

from app.router.metrics import router as metrics_router
from app.services.pipeline_metrics import run_aggregator

app = FastAPI(
    title="Metrics Tracker",
    description="Pipeline metrics aggregator and API",
)

app.include_router(metrics_router)


@app.on_event("startup")
async def start_aggregator():
    app.state.tasks = []
    task = asyncio.create_task(run_aggregator())
    app.state.tasks.append(task)


@app.on_event("shutdown")
async def stop_aggregator():
    for task in app.state.tasks:
        task.cancel()
    await asyncio.gather(*app.state.tasks, return_exceptions=True)


@app.get("/", tags=["Health Check"])
def healthcheck():
    return {"status": "Metrics tracker is healthy"}
