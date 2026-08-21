import pytest


class FakeCollection:
    """Stand-in for a Chroma collection: records calls instead of touching a database."""

    def __init__(self, ids=None):
        self.upserts = []
        self.deleted = []
        self._ids = list(ids or [])
        self._metadatas = {}  # id -> metadata, populated by upsert

    def upsert(self, documents, metadatas, ids):
        self.upserts.append({"document": documents[0], "metadata": metadatas[0], "id": ids[0]})
        self._metadatas[ids[0]] = metadatas[0]
        if ids[0] not in self._ids:
            self._ids.append(ids[0])

    def delete(self, ids):
        self.deleted.extend(ids)

    def get(self, include=None):
        return {"ids": list(self._ids), "metadatas": [self._metadatas.get(i, {}) for i in self._ids]}

    @property
    def last(self):
        """The most recent upsert, which is what most tests want to inspect."""
        return self.upserts[-1]


@pytest.fixture
def collection():
    return FakeCollection()


@pytest.fixture
def write_note(tmp_path):
    """Writes a markdown note into a temp folder and returns its path."""
    def _write(rel_path, frontmatter=None, body=""):
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        content = f"---\n{frontmatter.strip()}\n---\n" if frontmatter else ""
        path.write_text(content + body, encoding="utf-8")
        return str(path)
    return _write


class FakeQueryCollection:
    """Stand-in for a Chroma collection on the read side: canned query/get/count, records calls."""

    def __init__(self, query_result=None, get_result=None, count_result=0):
        self.query_result = query_result or {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        self.get_result = get_result if get_result is not None else {"ids": [], "documents": [], "metadatas": []}
        self.count_result = count_result
        self.last_query_kwargs = None
        self.last_get_ids = None

    def query(self, **kwargs):
        self.last_query_kwargs = kwargs
        return self.query_result

    def get(self, ids):
        self.last_get_ids = ids
        return self.get_result

    def count(self):
        return self.count_result


class FakeChromaClient:
    """Stand-in for a Chroma PersistentClient: hands out FakeQueryCollections by name."""

    def __init__(self, collections=None):
        self._collections = collections or {}

    def get_or_create_collection(self, name):
        return self._collections.setdefault(name, FakeQueryCollection())


@pytest.fixture
def fake_chroma_client(monkeypatch):
    """Points rag_server.get_client() at a FakeChromaClient instead of a real Chroma DB."""
    import rag_server

    client = FakeChromaClient()
    monkeypatch.setattr(rag_server, "_client", client)
    return client