import pytest

import rag_server
from config import FOLDERS, collection_name
from tests.conftest import FakeQueryCollection


# --- config wiring ---

def test_domains_derived_from_config():
    assert rag_server.DOMAINS == {name: collection_name(name) for name in FOLDERS}


def test_client_is_lazy(monkeypatch):
    monkeypatch.setattr(rag_server, "_client", None)
    assert rag_server._client is None


def test_get_client_caches_the_instance(monkeypatch):
    monkeypatch.setattr(rag_server, "_client", None)
    created = []
    monkeypatch.setattr(rag_server.chromadb, "PersistentClient",
                         lambda path: created.append(path) or "the-client")
    first = rag_server.get_client()
    second = rag_server.get_client()
    assert first is second == "the-client"
    assert len(created) == 1


# --- get_collection ---

def test_get_collection_rejects_unknown_domain(fake_chroma_client):
    with pytest.raises(ValueError, match="Unknown domain 'nope'"):
        rag_server.get_collection("nope")


def test_get_collection_resolves_known_domain(fake_chroma_client):
    collection = rag_server.get_collection("werewolf")
    assert fake_chroma_client._collections["vault_werewolf"] is collection


# --- format_hit / format_results ---

def test_format_hit_includes_tags_and_document():
    metadata = {"file_path": "/x.md", "data_category": "structured_note", "priority_score": 1}
    block = rag_server.format_hit("Bob is a Ragabash.", metadata, distance=0.1234)
    assert "/x.md" in block
    assert "data_category=structured_note" in block
    assert "priority_score=1" in block
    assert "distance=0.1234" in block
    assert "Bob is a Ragabash." in block


def test_format_hit_lists_extra_properties_separately():
    metadata = {"file_path": "/x.md", "pack": "Bone Gnawers"}
    block = rag_server.format_hit("text", metadata, distance=0.0)
    assert "Properties: pack: Bone Gnawers" in block


def test_format_results_empty():
    empty = {"documents": [[]], "metadatas": [[]], "distances": [[]]}
    assert rag_server.format_results(empty) == "No results found."


def test_format_results_includes_header_only_when_given():
    results = {"documents": [["body"]], "metadatas": [[{"file_path": "/x.md"}]], "distances": [[0.5]]}
    with_header = rag_server.format_results(results, "HEADER")
    without_header = rag_server.format_results(results)
    assert with_header.startswith("HEADER")
    assert not without_header.startswith("HEADER")


# --- tools ---

def test_list_domains_reports_counts(fake_chroma_client):
    fake_chroma_client._collections["vault_werewolf"] = FakeQueryCollection(count_result=42)
    output = rag_server.list_domains()
    assert "werewolf: 42 notes" in output


def test_search_notes_adds_priority_legend_for_werewolf_only(fake_chroma_client):
    hit = {"documents": [["a"]], "metadatas": [[{"file_path": "/a.md"}]], "distances": [[0.1]]}
    fake_chroma_client._collections["vault_werewolf"] = FakeQueryCollection(query_result=hit)
    fake_chroma_client._collections["vault_todo"] = FakeQueryCollection(query_result=hit)

    assert rag_server.PRIORITY_LEGEND in rag_server.search_notes("werewolf", "q")
    assert rag_server.PRIORITY_LEGEND not in rag_server.search_notes("todo", "q")


def test_search_werewolf_by_type_filters_on_sub_type(fake_chroma_client):
    collection = FakeQueryCollection()
    fake_chroma_client._collections["vault_werewolf"] = collection
    rag_server.search_werewolf_by_type("q", sub_type="person")
    assert collection.last_query_kwargs["where"] == {"sub_type": "person"}


def test_get_note_found(fake_chroma_client):
    fake_chroma_client._collections["vault_todo"] = FakeQueryCollection(
        get_result={"ids": ["/t.md"], "documents": ["do the thing"], "metadatas": [{"file_path": "/t.md"}]}
    )
    result = rag_server.get_note("todo", "/t.md")
    assert "do the thing" in result


def test_get_note_missing(fake_chroma_client):
    result = rag_server.get_note("todo", "/missing.md")
    assert "No indexed note found" in result
