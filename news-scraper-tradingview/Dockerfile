FROM python:3.12-slim

WORKDIR /code

# Install dependencies
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy application code
COPY ./app /code/app

# Default to batch mode; override with MODE=stream for real-time
ENV MODE=batch
ENV REDIS_HOST=redis-queue-news-analysis
ENV REDIS_PORT=6379
ENV REDIS_PASSWORD=
ENV REDIS_STREAM=tradingview_stream
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5013"]
