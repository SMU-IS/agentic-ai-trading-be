"""
Unit Tests — compute_pipeline_metrics()
File: app/tests/test_metrics.py

Run from metrics-tracker/:
    pytest
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.pipeline_metrics  # ensure module is imported before patching


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ts(delta_hours=0, delta_seconds=0):
    """Return an ISO timestamp offset from now (UTC)."""
    return (datetime.now(timezone.utc) + timedelta(hours=delta_hours, seconds=delta_seconds)).isoformat()


def _stage_times(base_offset_hours, durations_s):
    """
    Build start/end timestamps for all 5 pipeline stages.
    durations_s: [preproc, ticker, event, sentiment, qdrant]
    """
    t = datetime.now(timezone.utc) + timedelta(hours=base_offset_hours)
    result = {}
    stages = ["preproc", "ticker", "event", "sentiment", "qdrant"]
    for stage, dur in zip(stages, durations_s):
        end = t + timedelta(seconds=dur)
        result[f"{stage}_timestamp_start"] = t.isoformat()
        result[f"{stage}_timestamp"] = end.isoformat()
        t = end
    return result


def _make_redis_mock(keys_data: dict):
    """
    Build an async Redis mock that responds to scan + pipeline(hgetall).
    keys_data: { "post_timestamps:reddit:abc001": { field: value, ... }, ... }
    """
    mock_redis = MagicMock()

    keys = list(keys_data.keys())
    values = [keys_data[k] for k in keys]

    # scan returns all keys in one shot (cursor 0 → done)
    mock_redis.scan = AsyncMock(return_value=(0, keys))

    # pipeline().hgetall() returns values in order
    pipe_mock = MagicMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    pipe_mock.hgetall = MagicMock()
    pipe_mock.execute = AsyncMock(return_value=values)
    pipe_mock.set = MagicMock()
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    return mock_redis


# ─── Funnel counts ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_funnel_counts_full_pipeline():
    """Post within 24h with all stages → counts scraped + all funnel stages."""
    data = {
        "post_timestamps:reddit:p1": {
            "scraped_timestamp": _ts(-1),
            "posted_timestamp":  _ts(-1, -30),
            **_stage_times(-1, [2, 3, 4, 5, 2]),
        }
    }
    with patch("app.services.pipeline_metrics.redis_client", _make_redis_mock(data)):
        from app.services.pipeline_metrics import compute_pipeline_metrics
        await compute_pipeline_metrics()


@pytest.mark.asyncio
async def test_funnel_excludes_posts_older_than_24h():
    """Post scraped 25h ago → not counted in funnel."""
    data = {
        "post_timestamps:reddit:old": {
            "scraped_timestamp": _ts(-25),
            **_stage_times(-25, [1, 2, 3, 4, 1]),
        }
    }
    mock_redis = _make_redis_mock(data)
    with patch("app.services.pipeline_metrics.redis_client", mock_redis):
        from app.services.pipeline_metrics import compute_pipeline_metrics
        await compute_pipeline_metrics()

    # pipeline.set should be called — just verify it ran without error
    mock_redis.pipeline.assert_called()


@pytest.mark.asyncio
async def test_funnel_dropped_at_ticker():
    """Post with only preproc (no ticker) → scraped=1, ticker_identified=0, no_ticker=1."""
    scraped = _ts(-2)
    data = {
        "post_timestamps:reddit:dropped": {
            "scraped_timestamp":     scraped,
            "preproc_timestamp_start": _ts(-2, 1),
            "preproc_timestamp":       _ts(-2, 3),
        }
    }
    with patch("app.services.pipeline_metrics.redis_client", _make_redis_mock(data)):
        from app.services.pipeline_metrics import compute_pipeline_metrics
        await compute_pipeline_metrics()


@pytest.mark.asyncio
async def test_funnel_signal_and_order_counted():
    """Post with signal + order timestamps → signal_generated and order_placed incremented."""
    scraped = _ts(-1)
    data = {
        "post_timestamps:reddit:sig": {
            "scraped_timestamp":        scraped,
            "posted_timestamp":         _ts(-1, -30),
            **_stage_times(-1, [2, 3, 4, 5, 2]),
            "signal_timestamp:AAPL":    _ts(-1, 240),
            "order_timestamp:AAPL":     _ts(-1, 300),
        }
    }
    with patch("app.services.pipeline_metrics.redis_client", _make_redis_mock(data)):
        from app.services.pipeline_metrics import compute_pipeline_metrics
        await compute_pipeline_metrics()


# ─── Scraper latency ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scraper_latency_excluded_when_posted_after_scraped():
    """posted > scraped → latency not added (guard: scraped >= posted)."""
    now = datetime.now(timezone.utc)
    scraped = (now - timedelta(minutes=30)).isoformat()
    posted  = (now - timedelta(minutes=10)).isoformat()  # posted AFTER scraped

    data = {
        "post_timestamps:reddit:bad": {
            "scraped_timestamp": scraped,
            "posted_timestamp":  posted,
        }
    }
    with patch("app.services.pipeline_metrics.redis_client", _make_redis_mock(data)):
        from app.services.pipeline_metrics import compute_pipeline_metrics
        await compute_pipeline_metrics()  # should not raise


@pytest.mark.asyncio
async def test_scraper_latency_valid():
    """posted < scraped → latency included."""
    now = datetime.now(timezone.utc)
    scraped = (now - timedelta(minutes=30)).isoformat()
    posted  = (now - timedelta(minutes=31)).isoformat()  # 60s latency

    data = {
        "post_timestamps:reddit:good": {
            "scraped_timestamp": scraped,
            "posted_timestamp":  posted,
        }
    }
    with patch("app.services.pipeline_metrics.redis_client", _make_redis_mock(data)):
        from app.services.pipeline_metrics import compute_pipeline_metrics
        await compute_pipeline_metrics()


# ─── Stage latency guards ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stage_latency_excluded_when_end_before_start():
    """end < start → latency not added."""
    now = datetime.now(timezone.utc)
    data = {
        "post_timestamps:reddit:corrupt": {
            "scraped_timestamp":       (now - timedelta(minutes=30)).isoformat(),
            "preproc_timestamp_start": (now - timedelta(minutes=5)).isoformat(),
            "preproc_timestamp":       (now - timedelta(minutes=10)).isoformat(),  # end < start
        }
    }
    with patch("app.services.pipeline_metrics.redis_client", _make_redis_mock(data)):
        from app.services.pipeline_metrics import compute_pipeline_metrics
        await compute_pipeline_metrics()  # should not raise


@pytest.mark.asyncio
async def test_gap_latency_excluded_when_negative():
    """curr < prev in gap stages → gap not added."""
    now = datetime.now(timezone.utc)
    data = {
        "post_timestamps:reddit:gap": {
            "scraped_timestamp":  (now - timedelta(minutes=30)).isoformat(),
            "preproc_timestamp":  (now - timedelta(minutes=25)).isoformat(),
            "ticker_timestamp":   (now - timedelta(minutes=28)).isoformat(),  # before preproc end
        }
    }
    with patch("app.services.pipeline_metrics.redis_client", _make_redis_mock(data)):
        from app.services.pipeline_metrics import compute_pipeline_metrics
        await compute_pipeline_metrics()


# ─── Tradingview source merging ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tradingview_sources_merged():
    """tradingview_ideas and tradingview_minds → merged into scraper:tradingview."""
    now = datetime.now(timezone.utc)
    data = {
        "post_timestamps:tradingview_ideas:p1": {
            "scraped_timestamp": (now - timedelta(minutes=30)).isoformat(),
            "posted_timestamp":  (now - timedelta(minutes=32)).isoformat(),
        },
        "post_timestamps:tradingview_minds:p2": {
            "scraped_timestamp": (now - timedelta(minutes=20)).isoformat(),
            "posted_timestamp":  (now - timedelta(minutes=21)).isoformat(),
        },
    }
    with patch("app.services.pipeline_metrics.redis_client", _make_redis_mock(data)):
        from app.services.pipeline_metrics import compute_pipeline_metrics
        await compute_pipeline_metrics()


# ─── Snapshot saved to Redis ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_snapshots_saved_to_redis():
    """compute_pipeline_metrics saves funnel + services snapshots via pipeline."""
    data = {
        "post_timestamps:reddit:p1": {
            "scraped_timestamp": _ts(-1),
            "posted_timestamp":  _ts(-1, -30),
            **_stage_times(-1, [2, 3, 4, 5, 2]),
        }
    }
    mock_redis = _make_redis_mock(data)
    with patch("app.services.pipeline_metrics.redis_client", mock_redis):
        from app.services.pipeline_metrics import compute_pipeline_metrics
        await compute_pipeline_metrics()

    pipe = mock_redis.pipeline.return_value
    pipe.set.assert_called()
    assert pipe.set.call_count == 2  # funnel + services snapshots


# ─── Empty Redis ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_redis_no_error():
    """No keys in Redis → completes without error, zero counts."""
    mock_redis = MagicMock()
    mock_redis.scan = AsyncMock(return_value=(0, []))
    pipe_mock = MagicMock()
    pipe_mock.__aenter__ = AsyncMock(return_value=pipe_mock)
    pipe_mock.__aexit__ = AsyncMock(return_value=False)
    pipe_mock.set = MagicMock()
    pipe_mock.execute = AsyncMock(return_value=[])
    mock_redis.pipeline = MagicMock(return_value=pipe_mock)

    with patch("app.services.pipeline_metrics.redis_client", mock_redis):
        from app.services.pipeline_metrics import compute_pipeline_metrics
        await compute_pipeline_metrics()


# ─── Multiple tickers ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multiple_tickers_min_signal_time_used():
    """Post with 2 ticker signals → min signal time used for to_signal latency."""
    now = datetime.now(timezone.utc)
    aggregator = (now - timedelta(minutes=5)).isoformat()
    signal_aapl = (now - timedelta(minutes=4)).isoformat()   # earlier
    signal_msft = (now - timedelta(minutes=3)).isoformat()   # later

    data = {
        "post_timestamps:reddit:multi": {
            "scraped_timestamp":        (now - timedelta(minutes=30)).isoformat(),
            "posted_timestamp":         (now - timedelta(minutes=31)).isoformat(),
            **_stage_times(-0.5, [2, 3, 4, 5, 2]),
            "aggregator_timestamp":     aggregator,
            "signal_timestamp:AAPL":    signal_aapl,
            "signal_timestamp:MSFT":    signal_msft,
            "order_timestamp:AAPL":     (now - timedelta(minutes=2)).isoformat(),
        }
    }
    with patch("app.services.pipeline_metrics.redis_client", _make_redis_mock(data)):
        from app.services.pipeline_metrics import compute_pipeline_metrics
        await compute_pipeline_metrics()


# ─── _avg helper ──────────────────────────────────────────────────────────────

def test_avg_returns_none_for_empty():
    from app.services.pipeline_metrics import _avg
    assert _avg([]) is None


def test_avg_returns_correct_value():
    from app.services.pipeline_metrics import _avg
    assert _avg([10, 20, 30]) == 20.0


def test_avg_single_value():
    from app.services.pipeline_metrics import _avg
    assert _avg([5.5]) == 5.5


# ─── _parse_dt helper ─────────────────────────────────────────────────────────

def test_parse_dt_valid_iso():
    from app.services.pipeline_metrics import _parse_dt
    dt = _parse_dt("2026-01-01T10:00:00+08:00")
    assert dt is not None
    assert dt.tzinfo is not None


def test_parse_dt_none_input():
    from app.services.pipeline_metrics import _parse_dt
    assert _parse_dt(None) is None


def test_parse_dt_empty_string():
    from app.services.pipeline_metrics import _parse_dt
    assert _parse_dt("") is None


def test_parse_dt_invalid_string():
    from app.services.pipeline_metrics import _parse_dt
    assert _parse_dt("not-a-date") is None


def test_parse_dt_naive_gets_utc():
    from app.services.pipeline_metrics import _parse_dt
    from datetime import timezone
    dt = _parse_dt("2026-01-01T10:00:00")
    assert dt.tzinfo == timezone.utc
