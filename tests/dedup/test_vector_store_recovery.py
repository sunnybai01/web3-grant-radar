"""Vector store handle recovery and clear semantics.

Regression guard for a live failure: `clear_all()` used to drop and recreate the
collection, which invalidated the cached collection handle held by every other
process. The next query from the chat-api process raised
"Collection [uuid] does not exist" and 40 items in one run were skipped.
"""
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.dedup.vector_store import VectorStore, VectorStoreError


class FakeCollection:
    """Minimal Chroma collection double."""

    def __init__(self, ids=None, broken=False, name="web3_events"):
        self.ids = list(ids or [])
        self.broken = broken
        self.name = name
        self.deleted = []

    def _check(self):
        if self.broken:
            raise RuntimeError(
                "Collection [4af102eb] does not exist."
            )

    def count(self):
        self._check()
        return len(self.ids)

    def get(self, include=None):
        self._check()
        return {"ids": list(self.ids)}

    def query(self, query_texts=None, n_results=5, where=None, include=None):
        self._check()
        return {"ids": [list(self.ids)], "distances": [[0.1] * len(self.ids)],
                "metadatas": [[{}] * len(self.ids)]}

    def upsert(self, ids=None, documents=None, metadatas=None):
        self._check()
        self.ids.extend(ids or [])

    def add(self, ids=None, documents=None, metadatas=None):
        self._check()
        self.ids.extend(ids or [])

    def delete(self, ids=None):
        self._check()
        self.deleted.extend(ids or [])
        self.ids = [i for i in self.ids if i not in set(ids or [])]


class FakeClient:
    def __init__(self, collections):
        self._collections = collections
        self.requested = []

    def get_or_create_collection(self, name, metadata=None):
        self.requested.append(name)
        return self._collections[name]


def _store(cached, fresh=None):
    store = VectorStore.__new__(VectorStore)  # bypass the HTTP client
    store._client = FakeClient({VectorStore.COLLECTION_NAME: fresh or cached})
    store._collection = cached
    return store


def test_stale_handle_is_re_resolved_by_name() -> None:
    stale = FakeCollection(ids=["event_1"], broken=True)
    fresh = FakeCollection(ids=["event_1", "event_2"])
    store = _store(stale, fresh)

    # A query through the dead handle must recover instead of propagating.
    results = store.search_similar("anything")

    assert len(results) == 2
    assert store._client.requested == [VectorStore.COLLECTION_NAME]


def test_count_recovers_from_a_dropped_collection() -> None:
    stale = FakeCollection(broken=True)
    fresh = FakeCollection(ids=["event_9"])
    store = _store(stale, fresh)

    assert store.count() == 1


def test_existing_ids_recovers_from_a_dropped_collection() -> None:
    stale = FakeCollection(broken=True)
    fresh = FakeCollection(ids=["event_3"])
    store = _store(stale, fresh)

    assert store.existing_ids() == {"event_3"}


def test_add_recovers_from_a_dropped_collection() -> None:
    stale = FakeCollection(broken=True)
    fresh = FakeCollection(ids=[])
    store = _store(stale, fresh)

    store.add("event_5", "text", {"event_type": "grant"})

    assert fresh.ids == ["event_5"]


def test_clear_all_empties_the_collection_without_dropping_it() -> None:
    collection = FakeCollection(ids=["event_1", "event_2"])
    store = _store(collection)

    store.clear_all()

    assert collection.ids == []
    assert collection.deleted == ["event_1", "event_2"]
    # The handle must stay the same object: other processes hold this reference.
    assert store._collection is collection


def test_clear_all_on_an_empty_collection_is_a_no_op() -> None:
    collection = FakeCollection(ids=[])
    store = _store(collection)

    store.clear_all()

    assert collection.deleted == []


def test_clear_all_surfaces_errors() -> None:
    store = _store(FakeCollection(broken=True), FakeCollection(broken=True))

    with pytest.raises(VectorStoreError):
        store.clear_all()
