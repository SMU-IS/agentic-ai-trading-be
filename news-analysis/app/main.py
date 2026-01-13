from fastapi import FastAPI

app = FastAPI(
    title="Agentic AI Trading Portfolio Backend",
    description="",
    contact={
        "name": "SMU IS484 - Mvidia",
        "url": "https://github.com/SMU-IS/agentic-ai-trading-be",
    },
    root_path="/api/v1/analysis",
)


@app.get("/")
async def root():
    return {"message": "Hello World"}
