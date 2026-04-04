"""
Full Pipeline Integration Test
================================
Verifies end-to-end flow: news stream → preprocessing → ticker → event → sentiment → vectorisation → aggregator stream.

Requirements:
- Cloud Redis, Qdrant, and LLM APIs accessible from local machine
- ENV_FILE=.env.test set when running

Env test variables required:
Preproc:
NEWS_STREAM=test:news_stream
PREPROC_STREAM=test:preproc_stream
POST_TIMESTAMP_KEY=test:post_timestamps

Ticker:
PREPROC_STREAM=test:preproc_stream
TICKER_STREAM=test:ticker_stream
POST_TIMESTAMP_KEY=test:post_timestamps

Event:
TICKER_STREAM=test:ticker_stream
EVENT_STREAM=test:event_stream
POST_TIMESTAMP_KEY=test:post_timestamps

Sentiment:
EVENT_STREAM=test:event_stream
SENTIMENT_STREAM=test:sentiment_stream
POST_TIMESTAMP_KEY=test:post_timestamps

Qdrant:
SENTIMENT_STREAM=test:sentiment_stream
AGGREGATOR_STREAM=test:aggregator_stream
POST_TIMESTAMP_KEY=test:post_timestamps
POSTGRES_HOST=localhost
POSTGRES_USER=test
POSTGRES_PASSWORD=test
POSTGRES_PORT=5432
POSTGRES_DB=test
POSTGRES_SSL_MODE=require

Run:
    cd qdrant-retrieval
    ENV_FILE=.env.test pytest app/tests/test_pipeline_integration.py -v -s -m integration
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from qdrant_client import QdrantClient
from qdrant_client.models import PointIdsList

from app.core.config import env_config

QDRANT_COLLECTION = "news_analysis_compiled"

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]  # .../31-mar/

SERVICE_DIRS = {
    "preprocessing":   (REPO_ROOT / "preprocessing-service",  "app.services.preprocessing_worker"),
    "ticker":          (REPO_ROOT / "ticker-identification-service", "app.services.ticker_identification_worker"),
    "event":           (REPO_ROOT / "event-identification-service", "app.services.event_identification_worker"),
    "sentiment":       (REPO_ROOT / "sentiment-analysis-service", "app.services.sentiment_analysis_worker"),
    "vectorisation":   (REPO_ROOT / "qdrant-retrieval", "app.services.qdrant_vectorisation_worker"),
}

NEWS_STREAM      = os.environ.get("NEWS_STREAM", "test:news_stream")
AGGREGATOR_STREAM = env_config.redis_aggregator_stream

POLL_INTERVAL_S  = 3
MAX_WAIT_S       = 120
SERVICE_BOOT_S   = 60   # max time to wait for all services to be alive


# ── Service startup fixture ───────────────────────────────────────────────────
@pytest.fixture(scope="session")
def pipeline_services():
    """Start all 5 pipeline services as subprocesses with ENV_FILE=.env.test."""
    env = {**os.environ, "ENV_FILE": ".env.test"}
    processes = []

    for name, (service_dir, module) in SERVICE_DIRS.items():
        proc = subprocess.Popen(
            [sys.executable, "-m", module],
            cwd=str(service_dir),
            env=env,
            stdout=None,
            stderr=None,
        )
        processes.append((name, proc))
        print(f"🚀 Started {name} (pid {proc.pid})")

    # Give services time to boot, then check none crashed
    time.sleep(SERVICE_BOOT_S)
    crashed = [name for name, proc in processes if proc.poll() is not None]
    if crashed:
        for name, proc in processes:
            proc.terminate()
        pytest.fail(f"Services crashed on startup: {crashed}")

    print("✅ All services running")
    yield

    # Teardown — stop all services
    for name, proc in processes:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        print(f"🛑 Stopped {name}")


# ── Redis fixture ─────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def r():
    client = aioredis.Redis(
        host=env_config.redis_host,
        port=env_config.redis_port,
        password=env_config.redis_password,
        decode_responses=True,
    )
    yield client
    await client.aclose()


# ── Test ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_pipeline(pipeline_services, r: aioredis.Redis):
    # ── 1. Build a unique test post ───────────────────────────
    run_id  = uuid.uuid4().hex[:8]
    post_id = f"reddit:integration_{run_id}"

    raw_post = {
        "id": post_id,
        "content_type": "post",
        "native_id": f"integration_{run_id}",
        "source": "reddit_batch",
        "author": "integration_test",
        "url": "https://www.reddit.com/r/stocks/comments/integration_test",
        "timestamps": "2026-03-31T10:00:00+00:00",
        "scraped_timestamp": "2026-03-31T10:00:00+08:00",
        "posted_timestamp": "2026-03-31T09:55:00+08:00",
        "content": {
            "title": "AAPL reports record Q1 earnings, beats estimates by 15%",
            "body": (
                "Apple just reported massive Q1 earnings. EPS came in at $2.40 vs $2.09 expected. "
                "Revenue up 12% YoY. iPhone sales strong. Stock up 5% after hours. "
                "This is a major earnings beat driven by strong iPhone and services revenue."
            ),
            "clean_title": "AAPL reports record Q1 earnings, beats estimates by 15%",
            "clean_body": (
                "Apple just reported massive Q1 earnings. EPS came in at $2.40 vs $2.09 expected. "
                "Revenue up 12% YoY. iPhone sales strong. Stock up 5% after hours. "
                "This is a major earnings beat driven by strong iPhone and services revenue."
            ),
            "clean_combined_withurl": (
                "AAPL reports record Q1 earnings, beats estimates by 15%. "
                "Apple just reported massive Q1 earnings. EPS came in at $2.40 vs $2.09 expected. "
                "Revenue up 12% YoY. iPhone sales strong. Stock up 5% after hours."
            ),
            "clean_combined_withouturl": (
                "AAPL reports record Q1 earnings, beats estimates by 15%. "
                "Apple just reported massive Q1 earnings. EPS came in at $2.40 vs $2.09 expected. "
                "Revenue up 12% YoY. iPhone sales strong. Stock up 5% after hours."
            ),
        },
        "engagement": {"total_comments": 50, "score": 200, "upvote_ratio": 0.95},
        "metadata": {"subreddit": "stocks", "category": None},
        "images": [],
        "links": [],
    }

    # ── 2. Inject into test news stream ───────────────────────
    msg_id = await r.xadd(NEWS_STREAM, {"data": json.dumps(raw_post)})
    print(f"\n✅ Injected post {post_id} → stream msg {msg_id}")

    # ── 3. Poll aggregator stream ─────────────────────────────
    found          = None
    found_entry_id = None

    for attempt in range(MAX_WAIT_S // POLL_INTERVAL_S):
        await asyncio.sleep(POLL_INTERVAL_S)
        elapsed = (attempt + 1) * POLL_INTERVAL_S
        print(f"⏳ Waiting... {elapsed}s elapsed")

        entries = await r.xrange(AGGREGATOR_STREAM, "-", "+")
        for entry_id, fields in entries:
            entry_data = {}
            for k, v in fields.items():
                try:
                    entry_data[k] = json.loads(v)
                except Exception:
                    entry_data[k] = v

            if post_id in str(entry_data.get("id", "")).strip('"'):
                found          = entry_data
                found_entry_id = entry_id
                print(f"✅ Found in aggregator stream after {elapsed}s")
                break

        if found:
            break

    # ── 4. Assertions ─────────────────────────────────────────
    assert found is not None, (
        f"Post {post_id} did not reach aggregator stream within {MAX_WAIT_S}s. "
        "Check service logs for which stage failed."
    )
    assert found.get("id"), "Missing id in final output"

    ticker_metadata = found.get("ticker_metadata", {})
    assert ticker_metadata, "Missing ticker_metadata — ticker or event stage may have failed"

    for ticker, info in ticker_metadata.items():
        assert info.get("event_type")        is not None, f"Missing event_type for {ticker}"
        assert info.get("sentiment_score")   is not None, f"Missing sentiment_score for {ticker}"
        assert info.get("sentiment_label")   is not None, f"Missing sentiment_label for {ticker}"

    print(f"✅ Tickers identified: {list(ticker_metadata.keys())}")

    # ── Verify post_timestamp entries for all stages ───────────
    ts_key = f"test:post_timestamps:{post_id}"
    timestamps = await r.hgetall(ts_key)

    expected_timestamp_fields = [
        "preproc_timestamp_start",
        "preproc_timestamp",
        "ticker_timestamp_start",
        "ticker_timestamp",
        "event_timestamp_start",
        "event_timestamp",
        "sentiment_timestamp_start",
        "sentiment_timestamp",
        "qdrant_timestamp_start",
        "qdrant_timestamp",
    ]
    missing_ts = [f for f in expected_timestamp_fields if f not in timestamps]
    assert not missing_ts, f"Missing timestamp fields — stages may have failed: {missing_ts}"
    print("✅ All stage timestamps present")

    print(f"✅ Pipeline passed for post {post_id}")

    # ── 5. Cleanup ────────────────────────────────────────────
    if found_entry_id:
        await r.xdel(AGGREGATOR_STREAM, found_entry_id)

    dedup_keys = [
        f"preproc_dedup:{post_id}",
        f"ticker_dedup:{post_id}",
        f"event_dedup:{post_id}",
        f"sentiment_dedup:{post_id}",
        f"qdrant_dedup:{post_id}",
        f"test:post_timestamps:{post_id}",
    ]
    for key in dedup_keys:
        await r.expire(key, 60)

    # Delete test vector from Qdrant
    try:
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, post_id))
        qdrant = QdrantClient(
            url=env_config.qdrant_url,
            api_key=env_config.qdrant_api_key,
        )
        qdrant.delete(
            collection_name=QDRANT_COLLECTION,
            points_selector=PointIdsList(points=[point_id]),
        )
        print(f"✅ Deleted test vector {point_id} from Qdrant")
    except Exception as e:
        print(f"⚠️ Qdrant cleanup failed (manual deletion may be needed): {e}")

    print("✅ Cleanup done — dedup keys expire in 60s")
