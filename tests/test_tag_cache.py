"""
Unit tests for qualitative/tag_cache.py -- the persistent, content-hashed
cache that gives per-record LLM classifications (NPS theme tags, protection
flags) stability across report regenerations on identical data.
Run: pytest tests/test_tag_cache.py -v
"""
from __future__ import annotations

import qualitative.tag_cache as tag_cache


class TestLoadSave:
    def test_load_missing_file_returns_empty_dict(self, tmp_path):
        assert tag_cache.load(tmp_path / "nonexistent.json") == {}

    def test_load_malformed_json_returns_empty_dict(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json", encoding="utf-8")
        assert tag_cache.load(path) == {}

    def test_save_then_load_round_trips(self, tmp_path):
        path = tmp_path / "cache.json"
        cache = {}
        tag_cache.put(cache, "theme", "row_0001", "some response text", ["product_value"])
        tag_cache.save(cache, path)
        reloaded = tag_cache.load(path)
        assert tag_cache.get(reloaded, "theme", "row_0001", "some response text") == ["product_value"]

    def test_save_creates_parent_directory(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "cache.json"
        tag_cache.save({}, path)
        assert path.exists()

    def test_default_path_is_monkeypatchable_via_module_attribute(self, tmp_path, monkeypatch):
        # load()/save() must resolve DEFAULT_CACHE_PATH fresh from the
        # module namespace on each call (not bind it as a stale default
        # argument value at function-definition time), otherwise
        # monkeypatching tag_cache.DEFAULT_CACHE_PATH in other tests would
        # silently do nothing.
        custom_path = tmp_path / "custom.json"
        monkeypatch.setattr(tag_cache, "DEFAULT_CACHE_PATH", custom_path)
        cache = {}
        tag_cache.put(cache, "theme", "row_0001", "text", ["x"])
        tag_cache.save(cache)
        assert custom_path.exists()
        assert tag_cache.load() == cache


class TestGetPut:
    def test_miss_returns_none(self):
        assert tag_cache.get({}, "theme", "row_0001", "some text") is None

    def test_put_then_get_returns_the_value(self):
        cache = {}
        tag_cache.put(cache, "theme", "row_0001", "some text", ["staff_service", "claims_process"])
        assert tag_cache.get(cache, "theme", "row_0001", "some text") == ["staff_service", "claims_process"]

    def test_different_text_is_a_cache_miss(self):
        # Content-hash-keyed: if the underlying response text for this id
        # ever changes, the old entry must never be served.
        cache = {}
        tag_cache.put(cache, "theme", "row_0001", "original text", ["product_value"])
        assert tag_cache.get(cache, "theme", "row_0001", "a corrected version of the text") is None

    def test_same_text_different_id_is_a_cache_miss(self):
        cache = {}
        tag_cache.put(cache, "theme", "row_0001", "shared text", ["product_value"])
        assert tag_cache.get(cache, "theme", "row_0002", "shared text") is None

    def test_kind_namespaces_the_key(self):
        # The same (id, text) is cached for two unrelated purposes (theme
        # tags AND, independently, protection-flag status) -- without a
        # kind prefix these would collide on the same key and silently
        # overwrite each other.
        cache = {}
        tag_cache.put(cache, "theme", "row_0001", "text", ["product_value"])
        tag_cache.put(cache, "flag", "row_0001", "text", {"flag_type": "staff_misconduct"})
        assert tag_cache.get(cache, "theme", "row_0001", "text") == ["product_value"]
        assert tag_cache.get(cache, "flag", "row_0001", "text") == {"flag_type": "staff_misconduct"}

    def test_empty_text_does_not_raise(self):
        cache = {}
        tag_cache.put(cache, "theme", "row_0001", "", ["x"])
        assert tag_cache.get(cache, "theme", "row_0001", "") == ["x"]

    def test_none_text_does_not_raise(self):
        cache = {}
        tag_cache.put(cache, "theme", "row_0001", None, ["x"])
        assert tag_cache.get(cache, "theme", "row_0001", None) == ["x"]
