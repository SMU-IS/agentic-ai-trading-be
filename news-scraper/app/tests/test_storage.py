import json
import pytest
import fakeredis


class TestRedisStreamStorage:

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.services.storage import RedisStreamStorage
        self.fake_r = fakeredis.FakeRedis(decode_responses=True)
        self.storage = RedisStreamStorage.__new__(RedisStreamStorage)
        self.storage.r = self.fake_r
        self.storage.stream_name = "test_stream"

    # HAPPY PATH ---------------------------------------------------------------

    def test_happy_save_single_item_to_stream(self):
        """[HAPPY] Single item is written to the configured stream."""
        self.storage.save({"id": "reddit:x1", "content_type": "post"})
        entries = self.fake_r.xrange("test_stream")
        assert len(entries) == 1
        assert json.loads(entries[0][1]["data"])["id"] == "reddit:x1"

    def test_happy_save_batch_all_items_present(self):
        """[HAPPY] All items in a batch are written to the stream."""
        self.storage.save_batch([{"id": f"reddit:{i}"} for i in range(10)])
        assert len(self.fake_r.xrange("test_stream")) == 10

    def test_happy_save_batch_order_preserved(self):
        """[HAPPY] Batch items appear in insertion order in the stream."""
        items = [{"id": f"reddit:{i}", "seq": i} for i in range(5)]
        self.storage.save_batch(items)
        for i, entry in enumerate(self.fake_r.xrange("test_stream")):
            assert json.loads(entry[1]["data"])["seq"] == i

    # BOUNDARY PATH ------------------------------------------------------------

    def test_boundary_save_batch_empty_list_no_entries(self):
        """[BOUNDARY] Empty batch writes nothing to the stream."""
        self.storage.save_batch([])
        assert len(self.fake_r.xrange("test_stream")) == 0

    def test_boundary_custom_stream_key_used(self):
        """[BOUNDARY] Changing stream_name directs writes to the new key only."""
        self.storage.stream_name = "custom_stream"
        self.storage.save({"id": "test"})
        assert self.fake_r.xlen("custom_stream") == 1
        assert self.fake_r.xlen("test_stream") == 0

    def test_boundary_save_batch_single_item(self):
        """[BOUNDARY] Batch of one item behaves identically to save()."""
        self.storage.save_batch([{"id": "reddit:single"}])
        entries = self.fake_r.xrange("test_stream")
        assert len(entries) == 1
        assert json.loads(entries[0][1]["data"])["id"] == "reddit:single"

    def test_boundary_large_batch(self):
        """[BOUNDARY] Large batch (1000 items) all written atomically via pipeline."""
        self.storage.save_batch([{"id": f"reddit:{i}"} for i in range(1000)])
        assert len(self.fake_r.xrange("test_stream", count=1001)) == 1000

    # CONTEXT PATH -------------------------------------------------------------

    def test_context_non_ascii_content_preserved(self):
        """[CONTEXT] Non-ASCII characters survive JSON serialisation round-trip."""
        self.storage.save({"id": "reddit:x2", "content": "日本語テスト"})
        entries = self.fake_r.xrange("test_stream")
        assert json.loads(entries[0][1]["data"])["content"] == "日本語テスト"

    def test_context_nested_dict_preserved(self):
        """[CONTEXT] Nested dict structure is preserved through serialisation."""
        item = {"id": "reddit:nested", "content": {"title": "Hello", "body": "World"}}
        self.storage.save(item)
        entries = self.fake_r.xrange("test_stream")
        saved = json.loads(entries[0][1]["data"])
        assert saved["content"]["title"] == "Hello"
        assert saved["content"]["body"] == "World"

    def test_context_multiple_saves_accumulate(self):
        """[CONTEXT] Multiple save() calls each append a new entry."""
        for i in range(3):
            self.storage.save({"id": f"reddit:{i}"})
        assert len(self.fake_r.xrange("test_stream")) == 3

    def test_context_save_and_save_batch_use_same_stream(self):
        """[CONTEXT] save() and save_batch() both write to the same stream key."""
        self.storage.save({"id": "reddit:a"})
        self.storage.save_batch([{"id": "reddit:b"}, {"id": "reddit:c"}])
        assert len(self.fake_r.xrange("test_stream")) == 3
