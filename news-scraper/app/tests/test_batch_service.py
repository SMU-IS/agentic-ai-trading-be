from datetime import datetime, timezone, timedelta
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
        """[HAPPY] scraped_timestamp is set; vectorised_timestamp starts empty."""
        post = _make_post(post_id="ts_test")
        subreddit_mock = MagicMock()
        subreddit_mock.new.return_value = [post]
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["test"], days=5, batch_size=50)

        key = "post_timestamps:reddit:ts_test"
        assert self.redis.hget(key, "scraped_timestamp") is not None
        assert self.redis.hget(key, "vectorised_timestamp") == b""

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
    def test_sad_single_post_exception_does_not_stop_processing(self, _sleep):
        """[SAD] Exception on one post is swallowed; remaining posts still saved."""
        good_post = _make_post(post_id="good")
        bad_mock = MagicMock()
        bad_mock.id = "bad"
        type(bad_mock).created_utc = PropertyMock(side_effect=Exception("boom"))
        subreddit_mock = MagicMock()
        subreddit_mock.new.return_value = [bad_mock, good_post]
        self.reddit.subreddit.return_value = subreddit_mock

        self.service.run(["test"], days=5, batch_size=50)
        self.storage.save_batch.assert_called_once()

# """
# Pytest unit tests for:
#   - EntityWatcherService
#   - RedditBatchService
#   - RedditStreamService
#   - ScraperController
#   - RedisStreamStorage

# Strategy:
#   - fakeredis.FakeRedis for all Redis interactions
#   - unittest.mock.MagicMock / patch for Reddit client (praw) and storage
#   - time.sleep patched throughout to keep tests fast
# """

# import json
# import time
# import threading
# import asyncio
# from datetime import datetime, timezone, timedelta
# from unittest.mock import MagicMock, patch, PropertyMock
# import pytest
# import fakeredis
# import prawcore

# # ---------------------------------------------------------------------------
# # Shared fixtures
# # ---------------------------------------------------------------------------

# @pytest.fixture
# def fake_redis():
#     return fakeredis.FakeRedis()


# @pytest.fixture
# def mock_storage():
#     s = MagicMock()
#     s.save = MagicMock()
#     s.save_batch = MagicMock()
#     return s


# def _make_post(
#     post_id="abc123",
#     title="Test Title",
#     body="Test body",
#     author="user1",
#     url="https://reddit.com/r/test",
#     subreddit="test",
#     created_utc=None,
#     num_comments=5,
#     score=100,
#     upvote_ratio=0.95,
# ):
#     """Build a minimal mock Reddit submission."""
#     post = MagicMock()
#     post.id = post_id
#     post.title = title
#     post.selftext = body
#     post.author = author
#     post.url = url
#     post.subreddit.display_name = subreddit
#     post.num_comments = num_comments
#     post.score = score
#     post.upvote_ratio = upvote_ratio
#     post.created_utc = (
#         created_utc
#         if created_utc is not None
#         else datetime.now(timezone.utc).timestamp()
#     )
#     return post


# # ===========================================================================
# # EntityWatcherService
# # ===========================================================================

# # class TestEntityWatcherService:
# #     @pytest.fixture(autouse=True)
# #     def _setup(self, fake_redis):
# #         from app.services.entity_watcher import EntityWatcherService
# #         self.redis = fake_redis
# #         self.service = EntityWatcherService(fake_redis, "all_identified_tickers")

# #     # --- happy path ----------------------------------------------------------

# #     @patch("time.sleep", return_value=None)
# #     def test_new_entity_pushed_to_queue(self, _sleep):
# #         """Ticker found in hash but not in processed_set is queued."""
# #         self.redis.hset("all_identified_tickers", "AAPL", "data")

# #         entities = self.redis.hgetall("all_identified_tickers")
# #         processed_set = "entity_processed_set"
# #         for ticker in entities:
# #             ticker = ticker.decode() if isinstance(ticker, bytes) else ticker
# #             if self.redis.sismember(processed_set, ticker):
# #                 continue
# #             self.redis.lpush("batch_queue", ticker)
# #             self.redis.sadd(processed_set, ticker)
# #             self.redis.set("stream_version", time.time())

# #         assert self.redis.llen("batch_queue") == 1
# #         assert self.redis.brpop("batch_queue")[1] == b"AAPL"

# #     @patch("time.sleep", return_value=None)
# #     def test_already_processed_entity_not_requeued(self, _sleep):
# #         """Ticker already in processed_set must not be pushed again."""
# #         self.redis.hset("all_identified_tickers", "TSLA", "data")
# #         self.redis.sadd("entity_processed_set", "TSLA")

# #         entities = self.redis.hgetall("all_identified_tickers")
# #         processed_set = "entity_processed_set"
# #         for ticker in entities:
# #             ticker = ticker.decode() if isinstance(ticker, bytes) else ticker
# #             if self.redis.sismember(processed_set, ticker):
# #                 continue
# #             self.redis.lpush("batch_queue", ticker)

# #         assert self.redis.llen("batch_queue") == 0

# #     # --- boundary ------------------------------------------------------------

# #     @patch("time.sleep", return_value=None)
# #     def test_empty_hash_no_stream_version_update(self, _sleep):
# #         """Empty hash → stream_version must NOT be set."""
# #         entities = self.redis.hgetall("all_identified_tickers")
# #         updated = False
# #         for _ in entities:
# #             updated = True

# #         assert not updated
# #         assert self.redis.get("stream_version") is None

# #     @patch("time.sleep", return_value=None)
# #     def test_multiple_new_entities_all_queued(self, _sleep):
# #         for t in ["AAPL", "GOOG", "MSFT"]:
# #             self.redis.hset("all_identified_tickers", t, "data")

# #         processed_set = "entity_processed_set"
# #         for ticker in (k.decode() for k in self.redis.hgetall("all_identified_tickers")):
# #             if not self.redis.sismember(processed_set, ticker):
# #                 self.redis.lpush("batch_queue", ticker)
# #                 self.redis.sadd(processed_set, ticker)

# #         assert self.redis.llen("batch_queue") == 3

# #     # --- negative / context paths --------------------------------------------

# #     @patch("time.sleep", return_value=None)
# #     def test_bytes_ticker_decoded_correctly(self, _sleep):
# #         """Tickers stored as bytes in Redis are decoded before queuing."""
# #         self.redis.hset("all_identified_tickers", b"NVDA", b"data")
# #         processed_set = "entity_processed_set"
# #         for ticker in self.redis.hgetall("all_identified_tickers"):
# #             ticker = ticker.decode() if isinstance(ticker, bytes) else ticker
# #             if not self.redis.sismember(processed_set, ticker):
# #                 self.redis.lpush("batch_queue", ticker)
# #                 self.redis.sadd(processed_set, ticker)

# #         val = self.redis.brpop("batch_queue")[1]
# #         assert val == b"NVDA"


# # ===========================================================================
# # RedditBatchService
# # ===========================================================================

# class TestRedditBatchService:
#     @pytest.fixture(autouse=True)
#     def _setup(self, fake_redis, mock_storage):
#         from app.services.reddit_batch_ingestion import RedditBatchService
#         self.redis = fake_redis
#         self.storage = mock_storage
#         self.reddit = MagicMock()
#         self.service = RedditBatchService(self.reddit, mock_storage, fake_redis)

#     # --- resolve_subreddits_for_ticker ---------------------------------------

#     # def test_resolve_subreddits_missing_ticker(self):
#     #     """Returns empty list when ticker not in hash."""
#     #     assert self.service.resolve_subreddits_for_ticker("UNKNOWN") == []

#     # def test_resolve_subreddits_happy(self):
#     #     entity = {"OfficialName": "Apple Inc", "Aliases": ["Apple", "AAPL Corp"]}
#     #     self.redis.hset("all_identified_tickers", "AAPL", json.dumps(entity))
#     #     subs = self.service.resolve_subreddits_for_ticker("AAPL")
#     #     assert "aapl" in subs
#     #     assert "appleinc" in subs
#     #     assert "apple" in subs
#     #     assert "aaplcorp" in subs

#     # def test_resolve_subreddits_no_aliases(self):
#     #     entity = {"OfficialName": "Tesla", "Aliases": []}
#     #     self.redis.hset("all_identified_tickers", "TSLA", json.dumps(entity))
#     #     subs = self.service.resolve_subreddits_for_ticker("TSLA")
#     #     assert "tsla" in subs and "tesla" in subs

#     # def test_resolve_subreddits_no_official_name(self):
#     #     entity = {"Aliases": ["GME Community"]}
#     #     self.redis.hset("all_identified_tickers", "GME", json.dumps(entity))
#     #     subs = self.service.resolve_subreddits_for_ticker("GME")
#     #     assert "gme" in subs and "gmecommunity" in subs

#     # --- normalise -----------------------------------------------------------

#     # def test_normalise_strips_spaces_and_special_chars(self):
#     #     assert self.service.normalise("Apple Inc.") == "appleinc"

#     # def test_normalise_empty_string(self):
#     #     assert self.service.normalise("") == ""

#     # def test_normalise_already_clean(self):
#     #     assert self.service.normalise("apple") == "apple"

#     # --- run (batch scraping) ------------------------------------------------

#     @patch("time.sleep", return_value=None)
#     def test_run_happy_path_posts_flushed(self, _sleep):
#         """Posts within cutoff window are buffered and saved."""
#         post = _make_post()
#         subreddit_mock = MagicMock()
#         subreddit_mock.new.return_value = [post]
#         self.reddit.subreddit.return_value = subreddit_mock

#         self.service.run(["test"], days=5, batch_size=50)

#         self.storage.save_batch.assert_called_once()
#         args = self.storage.save_batch.call_args[0][0]
#         assert len(args) == 1
#         assert args[0]["native_id"] == "abc123"

#     @patch("time.sleep", return_value=None)
#     def test_run_post_older_than_cutoff_skipped(self, _sleep):
#         """Posts older than `days` cutoff are not included."""
#         old_ts = (datetime.now(timezone.utc) - timedelta(days=200)).timestamp()
#         post = _make_post(created_utc=old_ts)
#         subreddit_mock = MagicMock()
#         subreddit_mock.new.return_value = [post]
#         self.reddit.subreddit.return_value = subreddit_mock

#         self.service.run(["test"], days=5, batch_size=50)
#         self.storage.save_batch.assert_not_called()

#     @patch("time.sleep", return_value=None)
#     def test_run_batch_flush_on_batch_size(self, _sleep):
#         """Buffer flushes when batch_size is reached mid-stream."""
#         posts = [_make_post(post_id=str(i)) for i in range(5)]
#         subreddit_mock = MagicMock()
#         subreddit_mock.new.return_value = posts
#         self.reddit.subreddit.return_value = subreddit_mock

#         # 5 posts, batch_size=3 → 1 mid-flush (3) + 1 final (2)
#         self.service.run(["test"], days=5, batch_size=3)
#         assert self.storage.save_batch.call_count == 2

#     @patch("time.sleep", return_value=None)
#     def test_run_saves_post_timestamps_in_redis(self, _sleep):
#         post = _make_post(post_id="ts_test")
#         subreddit_mock = MagicMock()
#         subreddit_mock.new.return_value = [post]
#         self.reddit.subreddit.return_value = subreddit_mock

#         self.service.run(["test"], days=5, batch_size=50)

#         key = "post_timestamps:reddit:ts_test"
#         assert self.redis.hget(key, "scraped_timestamp") is not None
#         assert self.redis.hget(key, "vectorised_timestamp") == b""

#     @patch("time.sleep", return_value=None)
#     def test_run_reddit_api_error_continues_next_sub(self, _sleep):
#         """PrawcoreException for one sub doesn't abort the run."""
#         self.reddit.subreddit.side_effect = prawcore.exceptions.ResponseException(
#             MagicMock(status_code=503)
#         )
#         self.service.run(["bad_sub", "another_bad"], days=5, batch_size=50)
#         self.storage.save_batch.assert_not_called()

#     @patch("time.sleep", return_value=None)
#     def test_run_storage_failure_clears_buffer(self, _sleep):
#         """save_batch raising clears buffer and doesn't propagate."""
#         posts = [_make_post(post_id=str(i)) for i in range(4)]
#         subreddit_mock = MagicMock()
#         subreddit_mock.new.return_value = posts
#         self.reddit.subreddit.return_value = subreddit_mock
#         self.storage.save_batch.side_effect = [Exception("Redis down"), None]

#         self.service.run(["test"], days=5, batch_size=3)  # should not raise

#     @patch("time.sleep", return_value=None)
#     def test_run_post_processing_exception_continues(self, _sleep):
#         """Exception on one post is swallowed; rest continue processing."""
#         good_post = _make_post(post_id="good")
#         bad_mock = MagicMock()
#         bad_mock.id = "bad"
#         type(bad_mock).created_utc = PropertyMock(side_effect=Exception("boom"))

#         subreddit_mock = MagicMock()
#         subreddit_mock.new.return_value = [bad_mock, good_post]
#         self.reddit.subreddit.return_value = subreddit_mock

#         self.service.run(["test"], days=5, batch_size=50)
#         self.storage.save_batch.assert_called_once()

#     # --- run_worker ----------------------------------------------------------

#     # @patch("time.sleep", return_value=None)
#     # def test_run_worker_processes_queued_ticker(self, _sleep):
#     #     entity = {"OfficialName": "Apple Inc", "Aliases": []}
#     #     self.redis.hset("all_identified_tickers", "AAPL", json.dumps(entity))

#     #     stop_event = threading.Event()
#     #     call_count = [0]
#     #     original_brpop = self.redis.brpop

#     #     with patch.object(self.service, "run") as mock_run:
#     #         def _brpop(key, timeout=5):
#     #             call_count[0] += 1
#     #             if call_count[0] == 1:
#     #                 return (b"batch_queue", b"AAPL")
#     #             stop_event.set()
#     #             return None

#     #         with patch.object(self.redis, "brpop", side_effect=_brpop):
#     #             self.service.run_worker(stop_event)

#     #         mock_run.assert_called_once()

#     # @patch("time.sleep", return_value=None)
#     # def test_run_worker_skips_already_processed(self, _sleep):
#     #     self.redis.lpush("batch_queue", "TSLA")
#     #     self.redis.sadd("batch_processed_tickers", "TSLA")

#     #     stop_event = threading.Event()
#     #     call_count = [0]

#     #     with patch.object(self.service, "run") as mock_run:
#     #         def _brpop(key, timeout=5):
#     #             call_count[0] += 1
#     #             if call_count[0] == 1:
#     #                 return (b"batch_queue", b"TSLA")
#     #             stop_event.set()
#     #             return None

#     #         with patch.object(self.redis, "brpop", side_effect=_brpop):
#     #             self.service.run_worker(stop_event)

#     #         mock_run.assert_not_called()


# # ===========================================================================
# # RedditStreamService
# # ===========================================================================

# class TestRedditStreamService:
#     @pytest.fixture(autouse=True)
#     def _setup(self, fake_redis, mock_storage):
#         from app.services.reddit_stream_ingestion import RedditStreamService
#         self.redis = fake_redis
#         self.storage = mock_storage
#         self.reddit = MagicMock()
#         self.service = RedditStreamService(self.reddit, mock_storage, fake_redis)

#     # --- handle_post ---------------------------------------------------------

#     @patch("time.sleep", return_value=None)
#     def test_handle_post_saves_and_timestamps(self, _sleep):
#         post = _make_post(post_id="stream1")
#         self.service.handle_post(post)

#         self.storage.save.assert_called_once()
#         saved = self.storage.save.call_args[0][0]
#         assert saved["id"] == "reddit:stream1"
#         assert saved["source"] == "reddit_stream"

#         key = "post_timestamps:reddit:stream1"
#         assert self.redis.hget(key, "scraped_timestamp") is not None
#         assert self.redis.hget(key, "vectorised_timestamp") == b""

#     @patch("time.sleep", return_value=None)
#     def test_handle_post_exception_does_not_propagate(self, _sleep):
#         bad_post = MagicMock()
#         type(bad_post).created_utc = PropertyMock(side_effect=Exception("boom"))
#         bad_post.id = "bad1"
#         self.service.handle_post(bad_post)  # must not raise
#         self.storage.save.assert_not_called()

#     @patch("time.sleep", return_value=None)
#     def test_handle_post_row_structure(self, _sleep):
#         post = _make_post(post_id="struct_test", title="Hello", body="World")
#         self.service.handle_post(post)

#         row = self.storage.save.call_args[0][0]
#         assert row["content"]["title"] == "Hello"
#         assert row["content"]["body"] == "World"
#         assert "engagement" in row
#         assert "metadata" in row

#     # --- build_subreddit_list ------------------------------------------------

#     # def test_build_subreddit_list_merges_entities(self):
#     #     entity = {"OfficialName": "Palantir Technologies", "Aliases": ["PLTR Stock"]}
#     #     self.redis.hset("all_identified_tickers", "PLTR", json.dumps(entity))

#     #     result = self.service.build_subreddit_list(["wallstreetbets"])
#     #     assert "wallstreetbets" in result
#     #     assert "pltr" in result
#     #     assert "palantirtechnologies" in result
#     #     assert "pltrstock" in result

#     # def test_build_subreddit_list_empty_entities(self):
#     #     result = self.service.build_subreddit_list(["stocks"])
#     #     assert result == ["stocks"]

#     # def test_build_subreddit_list_deduplicates(self):
#     #     entity = {"OfficialName": "AAPL", "Aliases": []}
#     #     self.redis.hset("all_identified_tickers", "AAPL", json.dumps(entity))
#     #     result = self.service.build_subreddit_list(["aapl"])
#     #     assert result.count("aapl") == 1

#     # def test_build_subreddit_list_bytes_keys(self):
#     #     entity = {"OfficialName": "GameStop", "Aliases": []}
#     #     self.redis.hset("all_identified_tickers", b"GME", json.dumps(entity).encode())
#     #     result = self.service.build_subreddit_list([])
#     #     assert "gme" in result and "gamestop" in result

#     # --- run (streaming loop) ------------------------------------------------

#     @patch("time.sleep", return_value=None)
#     def test_run_stops_on_stop_event(self, _sleep):
#         stop_event = threading.Event()

#         def _gen(*args, **kwargs):
#             yield _make_post()
#             stop_event.set()
#             while True:
#                 yield _make_post()  # infinite; stop_event must exit

#         subreddit_mock = MagicMock()
#         subreddit_mock.stream.submissions.return_value = _gen()
#         self.reddit.subreddit.return_value = subreddit_mock

#         self.service.run(["stocks"], stop_event)
#         assert stop_event.is_set()

#     @patch("time.sleep", return_value=None)
#     def test_run_recovers_from_prawcore_exception(self, _sleep):
#         """PrawcoreException causes sleep+retry, not a crash."""
#         stop_event = threading.Event()
#         call_count = [0]

#         def _gen(*args, **kwargs):
#             call_count[0] += 1
#             if call_count[0] == 1:
#                 raise prawcore.exceptions.ResponseException(MagicMock(status_code=503))
#             stop_event.set()
#             return iter([])

#         subreddit_mock = MagicMock()
#         subreddit_mock.stream.submissions.side_effect = _gen
#         self.reddit.subreddit.return_value = subreddit_mock

#         self.service.run(["stocks"], stop_event)
#         assert call_count[0] >= 1


# # ===========================================================================
# # RedisStreamStorage
# # ===========================================================================

# class TestRedisStreamStorage:
#     @pytest.fixture(autouse=True)
#     def _setup(self):
#         from app.services.storage import RedisStreamStorage

#         self.fake_r = fakeredis.FakeRedis(decode_responses=True)
#         self.storage = RedisStreamStorage.__new__(RedisStreamStorage)
#         self.storage.r = self.fake_r
#         self.storage.stream_name = "test_stream"

#     def test_save_adds_to_stream(self):
#         self.storage.save({"id": "reddit:x1", "content_type": "post"})
#         entries = self.fake_r.xrange("test_stream")
#         assert len(entries) == 1
#         assert json.loads(entries[0][1]["data"])["id"] == "reddit:x1"

#     def test_save_non_ascii_content(self):
#         self.storage.save({"id": "reddit:x2", "content": "日本語テスト"})
#         entries = self.fake_r.xrange("test_stream")
#         assert json.loads(entries[0][1]["data"])["content"] == "日本語テスト"

#     def test_save_batch_all_items_present(self):
#         self.storage.save_batch([{"id": f"reddit:{i}"} for i in range(10)])
#         assert len(self.fake_r.xrange("test_stream")) == 10

#     def test_save_batch_empty_list(self):
#         self.storage.save_batch([])
#         assert len(self.fake_r.xrange("test_stream")) == 0

#     def test_save_batch_order_preserved(self):
#         items = [{"id": f"reddit:{i}", "seq": i} for i in range(5)]
#         self.storage.save_batch(items)
#         for i, entry in enumerate(self.fake_r.xrange("test_stream")):
#             assert json.loads(entry[1]["data"])["seq"] == i

#     def test_save_single_item_uses_configured_stream_key(self):
#         self.storage.stream_name = "custom_stream"
#         self.storage.save({"id": "test"})
#         assert self.fake_r.xlen("custom_stream") == 1


# # ===========================================================================
# # ScraperController
# # ===========================================================================

# class TestScraperController:
#     @pytest.fixture(autouse=True)
#     def _setup(self):
#         from app.services.scraper_controller import ScraperController
#         self.controller = ScraperController()

#     def test_start_returns_started_message(self):
#         app = MagicMock()
#         app.state.reddit = MagicMock()
#         app.state.storage = MagicMock()
#         app.state.redis_client = fakeredis.FakeRedis()
#         app.state.base_subreddits = ["stocks"]

#         with patch.object(self.controller, "_run_stream"), \
#              patch.object(self.controller, "_run_batch"):
#             result = asyncio.run(self.controller.start(app))

#         assert result["message"] == "Scraper started"
#         assert self.controller._running is True

#     def test_start_idempotent_when_already_running(self):
#         self.controller._running = True
#         result = asyncio.run(self.controller.start(MagicMock()))
#         assert "already running" in result["message"]

#     def test_stop_sets_stop_event_and_clears_state(self):
#         self.controller._running = True
#         self.controller._stop_event = threading.Event()
#         self.controller._threads = []
#         result = asyncio.run(self.controller.stop())
#         assert result["message"] == "Scraper stopped"
#         assert self.controller._running is False
#         assert self.controller._stop_event.is_set()

#     def test_stop_when_not_running(self):
#         result = asyncio.run(self.controller.stop())
#         assert "already stopped" in result["message"]

#     def test_status_reflects_running_flag(self):
#         assert self.controller.status() == {"running": False}
#         self.controller._running = True
#         assert self.controller.status() == {"running": True}