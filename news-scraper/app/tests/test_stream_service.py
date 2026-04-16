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


class TestRedditStreamService:

    @pytest.fixture(autouse=True)
    def _setup(self, fake_redis, mock_storage):
        from app.services.reddit_stream_ingestion import RedditStreamService
        self.redis = fake_redis
        self.storage = mock_storage
        self.reddit = MagicMock()
        self.service = RedditStreamService(self.reddit, mock_storage, fake_redis)

    # HAPPY PATH ---------------------------------------------------------------

    @patch("time.sleep", return_value=None)
    def test_happy_handle_post_saves_row(self, _sleep):
        """[HAPPY] handle_post saves the correct row to storage."""
        post = _make_post(post_id="stream1")
        self.service.handle_post(post)

        self.storage.save.assert_called_once()
        saved = self.storage.save.call_args[0][0]
        assert saved["id"] == "reddit:stream1"
        assert saved["source"] == "reddit_stream"

    @patch("time.sleep", return_value=None)
    def test_happy_handle_post_writes_timestamp(self, _sleep):
        """[HAPPY] scraped_timestamp and posted_timestamp are set in Redis."""
        self.service.handle_post(_make_post(post_id="stream1"))

        key = "post_timestamps:reddit:stream1"
        assert self.redis.hget(key, "scraped_timestamp") is not None
        assert self.redis.hget(key, "posted_timestamp") is not None

    @patch("time.sleep", return_value=None)
    def test_happy_handle_post_row_has_all_fields(self, _sleep):
        """[HAPPY] Saved row contains content, engagement and metadata sections."""
        self.service.handle_post(_make_post(post_id="s", title="Hello", body="World"))

        row = self.storage.save.call_args[0][0]
        assert row["content"]["title"] == "Hello"
        assert row["content"]["body"] == "World"
        assert "engagement" in row
        assert "metadata" in row

    @patch("time.sleep", return_value=None)
    def test_happy_handle_post_sets_metrics_in_redis(self, _sleep):
        """[HAPPY] handle_post writes latency and post metrics to Redis."""
        self.service.handle_post(_make_post(post_id="metrics1"))

        assert self.redis.exists("newsscraper:metrics:posts_1d")
        assert self.redis.exists("newsscraper:metrics:latency_sum")
        assert self.redis.exists("newsscraper:metrics:latency_count")

    # BOUNDARY PATH ------------------------------------------------------------

    @patch("time.sleep", return_value=None)
    def test_boundary_run_stops_on_stop_event(self, _sleep):
        """[BOUNDARY] Stream exits as soon as stop_event is set mid-iteration."""
        stop_event = threading.Event()

        def _gen(*args, **kwargs):
            yield _make_post()
            stop_event.set()
            while True:
                yield _make_post()

        subreddit_mock = MagicMock()
        subreddit_mock.stream.submissions.return_value = _gen()
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["stocks"], stop_event)
        assert stop_event.is_set()

    @patch("time.sleep", return_value=None)
    def test_boundary_run_skips_old_post(self, _sleep):
        """[BOUNDARY] Posts older than max_delay_seconds (1h) are skipped."""
        stop_event = threading.Event()
        old_ts = datetime.now(timezone.utc).timestamp() - 7200  # 2 hours old
        old_post = _make_post(post_id="old_post", created_utc=old_ts)

        def _gen(*args, **kwargs):
            yield old_post
            stop_event.set()
            return iter([])

        subreddit_mock = MagicMock()
        subreddit_mock.stream.submissions.side_effect = _gen
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["stocks"], stop_event)
        self.storage.save.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_boundary_run_skips_existing_post(self, _sleep):
        """[BOUNDARY] Posts with an existing Redis key are skipped."""
        stop_event = threading.Event()
        post = _make_post(post_id="already_seen")
        self.redis.hset("post_timestamps:reddit:already_seen", mapping={"scraped_timestamp": "x"})

        def _gen(*args, **kwargs):
            yield post
            stop_event.set()
            return iter([])

        subreddit_mock = MagicMock()
        subreddit_mock.stream.submissions.side_effect = _gen
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["stocks"], stop_event)
        self.storage.save.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_boundary_run_skips_post_with_preproc_dedup_key(self, _sleep):
        """[BOUNDARY] Post with preproc_dedup key but no post_timestamps key is skipped."""
        stop_event = threading.Event()
        post = _make_post(post_id="preproc_seen")
        self.redis.set("preproc_dedup:preproc_seen", "1")

        def _gen(*args, **kwargs):
            yield post
            stop_event.set()
            return iter([])

        subreddit_mock = MagicMock()
        subreddit_mock.stream.submissions.side_effect = _gen
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["stocks"], stop_event)
        self.storage.save.assert_not_called()

    # SAD PATH -----------------------------------------------------------------

    @patch("time.sleep", return_value=None)
    def test_sad_handle_post_exception_does_not_propagate(self, _sleep):
        """[SAD] Exception inside handle_post is caught; storage never called."""
        bad_post = MagicMock()
        type(bad_post).created_utc = PropertyMock(side_effect=Exception("boom"))
        bad_post.id = "bad1"

        self.service.handle_post(bad_post)  # must not raise
        self.storage.save.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_sad_run_recovers_from_prawcore_exception(self, _sleep):
        """[SAD] PrawcoreException is caught; stream does not crash."""
        stop_event = threading.Event()
        call_count = [0]

        def _gen(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise prawcore.exceptions.ResponseException(MagicMock(status_code=503))
            stop_event.set()
            return iter([])

        subreddit_mock = MagicMock()
        subreddit_mock.stream.submissions.side_effect = _gen
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["stocks"], stop_event)
        assert call_count[0] >= 1

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

    # BUILD SUBREDDIT LIST tests -----------------------------------------------

    def test_build_subreddit_list_adds_entities(self):
        """[UNIT] Entities in Redis are appended to the base subreddit list."""
        entity = {"OfficialName": "Palantir", "Aliases": ["PLTR Stock"]}
        self.redis.hset("all_identified_tickers", "PLTR", json.dumps(entity))

        result = self.service.build_subreddit_list(["wallstreetbets"])
        assert "wallstreetbets" in result
        assert "pltr" in result
        assert "palantir" in result
        assert "pltrstock" in result

    def test_build_subreddit_list_empty_entities(self):
        """[UNIT] No entities → result is just the base list."""
        result = self.service.build_subreddit_list(["stocks"])
        assert result == ["stocks"]

    def test_build_subreddit_list_deduplicates(self):
        """[UNIT] Duplicate subreddit names appear only once."""
        entity = {"OfficialName": "AAPL", "Aliases": []}
        self.redis.hset("all_identified_tickers", "AAPL", json.dumps(entity))
        result = self.service.build_subreddit_list(["aapl"])
        assert result.count("aapl") == 1

    def test_build_subreddit_list_bytes_keys(self):
        """[UNIT] Bytes-encoded ticker keys in Redis are decoded correctly."""
        entity = {"OfficialName": "GameStop", "Aliases": []}
        self.redis.hset("all_identified_tickers", b"GME", json.dumps(entity).encode())
        result = self.service.build_subreddit_list([])
        assert "gme" in result
        assert "gamestop" in result

    def test_build_subreddit_list_no_official_name(self):
        """[UNIT] Entity with no OfficialName only contributes ticker + aliases."""
        entity = {"Aliases": ["WallStreetBets Community"]}
        self.redis.hset("all_identified_tickers", "WSB", json.dumps(entity))
        result = self.service.build_subreddit_list([])
        assert "wsb" in result
        assert "wallstreetbetscommunity" in result

    # NORMALISE tests ----------------------------------------------------------

    def test_normalise_strips_spaces_and_special_chars(self):
        """[UNIT] normalise lowercases and removes non-alphanumeric characters."""
        assert self.service.normalise("Apple Inc.") == "appleinc"

    def test_normalise_empty_string(self):
        """[UNIT] normalise on empty string returns empty string."""
        assert self.service.normalise("") == ""

    def test_normalise_already_clean(self):
        """[UNIT] Already clean string passes through unchanged."""
        assert self.service.normalise("apple") == "apple"
