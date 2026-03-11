import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock
import pytest
import fakeredis
import prawcore


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis()

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
        """[HAPPY] scraped_timestamp set; vectorised_timestamp initialised empty."""
        self.service.handle_post(_make_post(post_id="stream1"))

        key = "post_timestamps:reddit:stream1"
        assert self.redis.hget(key, "scraped_timestamp") is not None
        assert self.redis.hget(key, "vectorised_timestamp") == b""

    @patch("time.sleep", return_value=None)
    def test_happy_handle_post_row_has_all_fields(self, _sleep):
        """[HAPPY] Saved row contains content, engagement and metadata sections."""
        self.service.handle_post(_make_post(post_id="s", title="Hello", body="World"))

        row = self.storage.save.call_args[0][0]
        assert row["content"]["title"] == "Hello"
        assert row["content"]["body"] == "World"
        assert "engagement" in row
        assert "metadata" in row

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
        """[SAD] PrawcoreException causes sleep+retry; stream does not crash."""
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
