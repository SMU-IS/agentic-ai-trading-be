"""
Full Pipeline Integration Test
================================
Verifies end-to-end flow: news stream → preprocessing → ticker → event → sentiment → vectorisation → aggregator stream → news aggregator stream + news notif stream.

Requirements:
- Cloud Redis, Qdrant, and LLM APIs accessible from local machine
- ENV_FILE=.env.test set when running

Env test variables required:
Preproc:
NEWS_STREAM=test:raw_news_stream
PREPROC_STREAM=test:preproc_redis_stream
POST_TIMESTAMP_KEY=test:post_timestamps

Ticker:
PREPROC_STREAM=test:preproc_redis_stream
TICKER_STREAM=test:ticker_redis_stream
POST_TIMESTAMP_KEY=test:post_timestamps

Event:
EVENT_STREAM=test:event_redis_stream
TICKER_STREAM=test:ticker_redis_stream
POST_TIMESTAMP_KEY=test:post_timestamps

Sentiment:
EVENT_STREAM=test:event_redis_stream
SENTIMENT_STREAM=test:sentiment_redis_stream
POST_TIMESTAMP_KEY=test:post_timestamps

Qdrant:
SENTIMENT_STREAM=test:sentiment_redis_stream
AGGREGATOR_STREAM=test:aggregator_redis_stream
POST_TIMESTAMP_KEY=test:post_timestamps
POSTGRES_HOST=localhost
POSTGRES_USER=test
POSTGRES_PASSWORD=test
POSTGRES_PORT=5432
POSTGRES_DB=test
POSTGRES_SSL_MODE=require

notification-alert:
REDIS_NOTIFICATION_STREAM=test:news_notification_stream
REDIS_SENTIMENT_STREAM=test:aggregator_redis_stream
REDIS_ANALYSIS_STREAM=test:aggregator_analysis_stream
REDIS_AGGREGATOR_STREAM=test:news_aggregator_stream
REDIS_TRADE_STREAM=test:trade_notification_stream
POST_TIMESTAMP_KEY=test:post_timestamps
BASE_API=http://localhost:1234
JWT_TOKEN=test-token

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
import redis
import redis.asyncio as aioredis
from qdrant_client import QdrantClient
from qdrant_client.models import PointIdsList


QDRANT_COLLECTION = "news_analysis_compiled"

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]  

SERVICE_DIRS = {
    "preprocessing":            (REPO_ROOT / "preprocessing-service",  "app.services.preprocessing_worker"),
    "ticker":                   (REPO_ROOT / "ticker-identification-service", "app.services.ticker_identification_worker"),
    "event":                    (REPO_ROOT / "event-identification-service", "app.services.event_identification_worker"),
    "sentiment":                (REPO_ROOT / "sentiment-analysis-service", "app.services.sentiment_analysis_worker"),
    "vectorisation":            (REPO_ROOT / "qdrant-retrieval", "app.services.qdrant_vectorisation_worker"),
    "sentiment_to_aggregator":  (REPO_ROOT / "notification-alert", "app.workers.sentiment_to_aggregator"),
    "sentiment_to_notification":(REPO_ROOT / "notification-alert", "app.workers.sentiment_to_notification"),
}

NOTIF_AGGREGATOR_STREAM  = "test:news_aggregator_stream"
NOTIF_NOTIFICATION_STREAM = "test:news_notification_stream"
NEWS_STREAM = "test:raw_news_stream"

POLL_INTERVAL_S  = 3
MAX_WAIT_S       = 120
SERVICE_BOOT_S   = 60   # max time to wait for all services to be alive


# ── Safety guard ──────────────────────────────────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def _require_env_test():
    assert os.environ.get("ENV_FILE", "").strip() == ".env.test", \
        "Integration test requires ENV_FILE=.env.test to avoid writing to production streams"


# ── Service startup fixture ───────────────────────────────────────────────────
@pytest.fixture(scope="session")
def pipeline_services():
    """Start all 6 pipeline services as subprocesses with ENV_FILE=.env.test."""
    # Strip only conftest dummy values (localhost/test placeholders) so each
    # service's .env.test wins. Real CI secrets (from GitHub) are preserved.
    CONFTEST_DUMMIES = {
        "QDRANT_URL": "http://localhost:6333",
        "QDRANT_API_KEY": "test-qdrant-key",
        "STORAGE_PROVIDER": "qdrant_nomic",
        "LLM_PROVIDER": "nomic",
        "GEMINI_API_KEY": "test-gemini-key",
        "NOMIC_API_KEY": "test-nomic-key",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "REDIS_PASSWORD": "",
        "SENTIMENT_STREAM": "test_sentiment_stream",
        "AGGREGATOR_STREAM": "test_aggregator_stream",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "test",
        "TEXT_EMBEDDING_MODEL": "nomic-embed-text-v1.5",
    }
    base_env = {
        k: v for k, v in os.environ.items()
        if k not in CONFTEST_DUMMIES or v != CONFTEST_DUMMIES[k]
    }
    env = {**base_env, "ENV_FILE": ".env.test"}
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

    # Flush leftover test streams from previous runs to prevent stale messages
    # from being processed before the test post is injected
    _r = redis.Redis(
        host=_TEST_ENV["REDIS_HOST"],
        port=int(_TEST_ENV["REDIS_PORT"]),
        password=_TEST_ENV["REDIS_PASSWORD"],
        decode_responses=True,
    )
    test_streams = [
        "test:raw_news_stream",
        "test:preproc_redis_stream",
        "test:ticker_redis_stream",
        "test:event_redis_stream",
        "test:sentiment_redis_stream",
        "test:aggregator_redis_stream",
        "test:news_aggregator_stream",
        "test:news_notification_stream",
    ]
    for stream in test_streams:
        _r.delete(stream)
    _r.close()
    print("🧹 Flushed leftover test streams")

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
def _load_env_file(path: Path) -> dict:
    """Parse key=value pairs from an env file, ignoring comments."""
    result = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                result[k.strip()] = v.strip()
    return result

# Load .env (credentials) first, then .env.test (test stream overrides) on top
_qdrant_dir = REPO_ROOT / "qdrant-retrieval"
_TEST_ENV = {**_load_env_file(_qdrant_dir / ".env"), **_load_env_file(_qdrant_dir / ".env.test")}

AGGREGATOR_STREAM = _TEST_ENV.get("AGGREGATOR_STREAM", "test:aggregator_redis_stream")

@pytest_asyncio.fixture
async def r():
    client = aioredis.Redis(
        host=_TEST_ENV["REDIS_HOST"],
        port=int(_TEST_ENV["REDIS_PORT"]),
        password=_TEST_ENV["REDIS_PASSWORD"],
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
                print(f"✅ Found in test aggregator_redis_stream stream after {elapsed}s")
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

    # ── 4b. Poll news_aggregator_stream (sentiment_to_aggregator output) ──────
    found_aggregator = None
    for attempt in range(MAX_WAIT_S // POLL_INTERVAL_S):
        await asyncio.sleep(POLL_INTERVAL_S)
        elapsed = (attempt + 1) * POLL_INTERVAL_S
        entries = await r.xrange(NOTIF_AGGREGATOR_STREAM, "-", "+")
        for entry_id, fields in entries:
            if post_id in str(fields.get("id", "")):
                found_aggregator = fields
                print(f"✅ Found in test news_aggregator_stream after {elapsed}s")
                break
        if found_aggregator:
            break

    assert found_aggregator is not None, (
        f"Post {post_id} did not reach news_aggregator_stream within {MAX_WAIT_S}s. "
        "sentiment_to_aggregator worker may have failed."
    )
    assert found_aggregator.get("ticker"),                       "Missing ticker in news_aggregator_stream entry"
    assert found_aggregator.get("event_type") == "NEWS_UPDATE", "event_type should be NEWS_UPDATE"
    assert found_aggregator.get("event_type_meta"),              "Missing event_type_meta in news_aggregator_stream entry"
    assert found_aggregator.get("sentiment_score") is not None, "Missing sentiment_score in news_aggregator_stream entry"

    # ── 4c. Poll news_notification_stream (sentiment_to_notification output) ──
    found_notification = None
    for attempt in range(MAX_WAIT_S // POLL_INTERVAL_S):
        await asyncio.sleep(POLL_INTERVAL_S)
        elapsed = (attempt + 1) * POLL_INTERVAL_S
        entries = await r.xrange(NOTIF_NOTIFICATION_STREAM, "-", "+")
        for entry_id, fields in entries:
            if post_id in str(fields.get("id", "")):
                found_notification = fields
                print(f"✅ Found in test news_notification_stream after {elapsed}s")
                break
        if found_notification:
            break

    assert found_notification is not None, (
        f"Post {post_id} did not reach news_notification_stream within {MAX_WAIT_S}s. "
        "sentiment_to_notification worker may have failed."
    )
    assert found_notification.get("headline"), "Missing headline in news_notification_stream entry"
    assert found_notification.get("tickers"),  "Missing tickers in news_notification_stream entry"
    tickers_list = json.loads(found_notification["tickers"])
    assert len(tickers_list) > 0,               "Empty tickers list in news_notification_stream entry"
    assert tickers_list[0].get("symbol"),        "Missing symbol in tickers list"
    assert tickers_list[0].get("event_type"),    "Missing event_type in tickers list"
    assert tickers_list[0].get("sentiment_label"), "Missing sentiment_label in tickers list"

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
        "aggregator_timestamp",
    ]
    missing_ts = [f for f in expected_timestamp_fields if f not in timestamps]
    assert not missing_ts, f"Missing timestamp fields — stages may have failed: {missing_ts}"
    print("✅ All stage timestamps present")

    print(f"✅ Pipeline passed for post {post_id}")

    # ── 5. Cleanup ────────────────────────────────────────────
    if found_entry_id:
        await r.xdel(AGGREGATOR_STREAM, found_entry_id)

    # Clean up downstream stream entries
    agg_entries = await r.xrange(NOTIF_AGGREGATOR_STREAM, "-", "+")
    for entry_id, fields in agg_entries:
        if post_id in str(fields.get("id", "")):
            await r.xdel(NOTIF_AGGREGATOR_STREAM, entry_id)

    notif_entries = await r.xrange(NOTIF_NOTIFICATION_STREAM, "-", "+")
    for entry_id, fields in notif_entries:
        if post_id in str(fields.get("id", "")):
            await r.xdel(NOTIF_NOTIFICATION_STREAM, entry_id)

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
            url=_TEST_ENV["QDRANT_URL"],
            api_key=_TEST_ENV["QDRANT_API_KEY"],
        )
        qdrant.delete(
            collection_name=QDRANT_COLLECTION,
            points_selector=PointIdsList(points=[point_id]),
        )
        print(f"✅ Deleted test vector {point_id} from Qdrant")
    except Exception as e:
        print(f"⚠️ Qdrant cleanup failed (manual deletion may be needed): {e}")

    print("✅ Cleanup done — dedup keys expire in 60s")
 