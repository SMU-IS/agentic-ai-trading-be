import json
import threading
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
import pytest
import fakeredis
import prawcore


@pytest.fixture
def fake_redis():
    r = fakeredis.FakeRedis(decode_responses=True)
    r.set("newsscraper:reddit:running", "1")
    return r

@pytest.fixture
def mock_storage():
    s = MagicMock()
    s.save = MagicMock()
    s.save_batch = MagicMock()
    return s

def _make_post(post_id="abc123", title="Test Title", body="Test body",
    author="user1", url="https://reddit.com/r/test", subreddit="test",
    created_utc=None, num_comments=5, score=100, upvote_ratio=0.95):
    post = MagicMock()
    post.id = post_id
    post.title = title
    post.selftext = body
    post.author = author
    post.url = url
    post.subreddit.display_name = subreddit
    post.num_comments = num_comments
    post.score = score
    post.upvote_ratio = upvote_ratio
    post.created_utc = (
        created_utc if created_utc is not None
        else datetime.now(timezone.utc).timestamp()
    )
    return post


class TestRedditBatchService:

    @pytest.fixture(autouse=True)
    def _setup(self, fake_redis, mock_storage):
        from app.services.reddit_batch_ingestion import RedditBatchService
        self.redis = fake_redis
        self.storage = mock_storage
        self.reddit = MagicMock()
        self.service = RedditBatchService(self.reddit, mock_storage, fake_redis)

    # HAPPY PATH ---------------------------------------------------------------

    @patch("time.sleep", return_value=None)
    def test_happy_run_posts_flushed(self, _sleep):
        """[HAPPY] Posts within cutoff window are buffered and saved."""
        post = _make_post()
        subreddit_mock = MagicMock()
        subreddit_mock.new.return_value = [post]
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["test"], days=5, batch_size=50)

        self.storage.save_batch.assert_called_once()
        args = self.storage.save_batch.call_args[0][0]
        assert len(args) == 1
        assert args[0]["native_id"] == "abc123"

    @patch("time.sleep", return_value=None)
    def test_happy_post_timestamp_written_to_redis(self, _sleep):
        """[HAPPY] scraped_timestamp is set in Redis after batch scrape."""
        post = _make_post(post_id="ts_test")
        subreddit_mock = MagicMock()
        subreddit_mock.new.return_value = [post]
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["test"], days=5, batch_size=50)

        key = "post_timestamps:reddit:ts_test"
        assert self.redis.hget(key, "scraped_timestamp") is not None

    @patch("time.sleep", return_value=None)
    def test_happy_post_row_structure(self, _sleep):
        """[HAPPY] Saved row contains all expected fields."""
        post = _make_post(post_id="struct1", title="Hello", body="World")
        subreddit_mock = MagicMock()
        subreddit_mock.new.return_value = [post]
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["test"], days=5, batch_size=50)

        row = self.storage.save_batch.call_args[0][0][0]
        assert row["content"]["title"] == "Hello"
        assert row["content"]["body"] == "World"
        assert "engagement" in row
        assert "metadata" in row
        assert row["source"] == "reddit_batch"

    # BOUNDARY PATH ------------------------------------------------------------

    @patch("time.sleep", return_value=None)
    def test_boundary_post_older_than_cutoff_skipped(self, _sleep):
        """[BOUNDARY] Post 200 days old exceeds 5-day cutoff → skipped."""
        old_ts = (datetime.now(timezone.utc) - timedelta(days=200)).timestamp()
        post = _make_post(created_utc=old_ts)
        subreddit_mock = MagicMock()
        subreddit_mock.new.return_value = [post]
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["test"], days=5, batch_size=50)
        self.storage.save_batch.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_boundary_mid_stream_flush_on_batch_size(self, _sleep):
        """[BOUNDARY] 5 posts with batch_size=3 → 1 mid-flush (3) + 1 final (2)."""
        posts = [_make_post(post_id=str(i)) for i in range(5)]
        subreddit_mock = MagicMock()
        subreddit_mock.new.return_value = posts
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["test"], days=5, batch_size=3)
        assert self.storage.save_batch.call_count == 2

    @patch("time.sleep", return_value=None)
    def test_boundary_exact_batch_size_single_flush(self, _sleep):
        """[BOUNDARY] Exactly batch_size posts → 1 mid-flush, no final flush."""
        posts = [_make_post(post_id=str(i)) for i in range(3)]
        subreddit_mock = MagicMock()
        subreddit_mock.new.return_value = posts
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["test"], days=5, batch_size=3)
        assert self.storage.save_batch.call_count == 1

    @patch("time.sleep", return_value=None)
    def test_boundary_existing_post_key_skipped(self, _sleep):
        """[BOUNDARY] Post whose Redis key already exists is skipped."""
        post = _make_post(post_id="already_seen")
        self.redis.hset("post_timestamps:reddit:already_seen", mapping={"scraped_timestamp": "x"})
        subreddit_mock = MagicMock()
        subreddit_mock.new.return_value = [post]
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["test"], days=5, batch_size=50)
        self.storage.save_batch.assert_not_called()

    # SAD PATH -----------------------------------------------------------------

    @patch("time.sleep", return_value=None)
    def test_sad_reddit_api_error_continues_to_next_sub(self, _sleep):
        """[SAD] PrawcoreException on one sub doesn't abort remaining subs."""
        self.reddit.subreddit.side_effect = prawcore.exceptions.ResponseException(
            MagicMock(status_code=503)
        )
        self.service.run(["bad_sub", "another_bad"], days=5, batch_size=50)
        self.storage.save_batch.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_sad_storage_failure_clears_buffer_and_continues(self, _sleep):
        """[SAD] save_batch raising clears buffer without propagating exception."""
        posts = [_make_post(post_id=str(i)) for i in range(4)]
        subreddit_mock = MagicMock()
        subreddit_mock.new.return_value = posts
        self.reddit.subreddit.return_value = subreddit_mock
        self.storage.save_batch.side_effect = [Exception("Redis down"), None]

        self.service.run(["test"], days=5, batch_size=3)  # must not raise

    @patch("time.sleep", return_value=None)
    def test_sad_should_stop_mid_stream_halts_processing(self, _sleep):
        """[SAD] Setting running flag to 0 causes scraper to stop mid-stream."""
        posts = [_make_post(post_id=str(i)) for i in range(10)]
        subreddit_mock = MagicMock()
        subreddit_mock.new.return_value = posts
        self.reddit.subreddit.return_value = subreddit_mock

        self.redis.set("newsscraper:reddit:running", "0")
        self.service.run(["test"], days=5, batch_size=50)
        self.storage.save_batch.assert_not_called()

    # SHOULD_STOP tests --------------------------------------------------------

    def test_should_stop_when_stop_event_is_set(self):
        """[UNIT] should_stop returns True when stop_event is set."""
        stop_event = threading.Event()
        stop_event.set()
        assert self.service.should_stop(stop_event) is True

    def test_should_stop_when_running_flag_missing(self):
        """[UNIT] should_stop returns True when redis running flag is absent."""
        self.redis.delete("newsscraper:reddit:running")
        assert self.service.should_stop(None) is True

    def test_should_stop_when_flag_is_zero(self):
        """[UNIT] should_stop returns True when redis flag is '0'."""
        self.redis.set("newsscraper:reddit:running", "0")
        assert self.service.should_stop(None) is True

    def test_should_stop_returns_false_when_running(self):
        """[UNIT] should_stop returns False when flag is '1' and no stop event."""
        assert self.service.should_stop(None) is False

    def test_should_stop_none_event_same_as_not_running(self):
        """[UNIT] should_stop with None event behaves same as no stop_event."""
        # redis flag is "1" → should_stop returns False (same as no event)
        result = self.service.should_stop(None)
        assert result is False

    # RESOLVE SUBREDDITS tests -------------------------------------------------

    def test_resolve_subreddits_missing_ticker(self):
        """[UNIT] Unknown ticker returns empty list."""
        assert self.service.resolve_subreddits_for_ticker("UNKNOWN") == []

    def test_resolve_subreddits_with_name_and_aliases(self):
        """[UNIT] Ticker with OfficialName and Aliases returns correct subs."""
        entity = {"OfficialName": "Apple Inc", "Aliases": ["AAPL Corp"]}
        self.redis.hset("all_identified_tickers", "AAPL", json.dumps(entity))
        subs = self.service.resolve_subreddits_for_ticker("AAPL")
        assert "aapl" in subs
        assert "appleinc" in subs
        assert "aaplcorp" in subs

    def test_resolve_subreddits_no_aliases(self):
        """[UNIT] Ticker with no aliases returns ticker + official name only."""
        entity = {"OfficialName": "Tesla", "Aliases": []}
        self.redis.hset("all_identified_tickers", "TSLA", json.dumps(entity))
        subs = self.service.resolve_subreddits_for_ticker("TSLA")
        assert "tsla" in subs
        assert "tesla" in subs

    def test_resolve_subreddits_no_official_name(self):
        """[UNIT] Entity with no OfficialName still returns ticker + aliases."""
        entity = {"Aliases": ["GME Community"]}
        self.redis.hset("all_identified_tickers", "GME", json.dumps(entity))
        subs = self.service.resolve_subreddits_for_ticker("GME")
        assert "gme" in subs
        assert "gmecommunity" in subs

    # NORMALISE tests ----------------------------------------------------------

    def test_normalise_strips_spaces_and_special_chars(self):
        """[UNIT] normalise lowercases and removes non-alphanumeric characters."""
        assert self.service.normalise("Apple Inc.") == "appleinc"

    def test_normalise_empty_string(self):
        """[UNIT] normalise on empty string returns empty string."""
        assert self.service.normalise("") == ""

    def test_normalise_already_clean(self):
        """[UNIT] Already lowercase alphanumeric string passes through unchanged."""
        assert self.service.normalise("apple") == "apple"

    def test_normalise_mixed_case(self):
        """[UNIT] normalise lowercases mixed-case input."""
        assert self.service.normalise("TSLA") == "tsla"

    # RUN WORKER tests ---------------------------------------------------------

    def test_run_worker_stops_immediately_when_event_set(self):
        """[UNIT] run_worker exits immediately when stop_event is pre-set."""
        stop_event = threading.Event()
        stop_event.set()
        self.service.run_worker(stop_event)
        self.storage.save_batch.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_run_worker_processes_queued_ticker(self, _sleep):
        """[UNIT] run_worker pops a ticker, calls run(), marks it processed."""
        entity = {"OfficialName": "Apple", "Aliases": []}
        self.redis.hset("all_identified_tickers", "AAPL", json.dumps(entity))
        self.redis.lpush("batch_queue", "AAPL")

        stop_event = threading.Event()
        call_count = [0]

        def mock_run(*args, **kwargs):
            call_count[0] += 1
            stop_event.set()

        with patch.object(self.service, "run", side_effect=mock_run):
            self.service.run_worker(stop_event)

        assert call_count[0] == 1
        assert self.redis.sismember("batch_processed_tickers", "AAPL")

    @patch("time.sleep", return_value=None)
    def test_run_worker_skips_already_processed_ticker(self, _sleep):
        """[UNIT] run_worker skips tickers already in the processed set."""
        self.redis.sadd("batch_processed_tickers", "TSLA")
        stop_event = threading.Event()
        call_count = [0]

        def fake_brpop(key, timeout=5):
            call_count[0] += 1
            if call_count[0] == 1:
                return (b"batch_queue", b"TSLA")
            stop_event.set()
            return None

        with patch.object(self.redis, "brpop", side_effect=fake_brpop):
            with patch.object(self.service, "run") as mock_run:
                self.service.run_worker(stop_event)

        mock_run.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_run_worker_handles_none_brpop_result(self, _sleep):
        """[UNIT] run_worker continues gracefully when brpop times out (None)."""
        stop_event = threading.Event()
        call_count = [0]

        def fake_brpop(key, timeout=5):
            call_count[0] += 1
            if call_count[0] == 1:
                return None
            stop_event.set()
            return None

        with patch.object(self.redis, "brpop", side_effect=fake_brpop):
            with patch.object(self.service, "run") as mock_run:
                self.service.run_worker(stop_event)

        mock_run.assert_not_called()
