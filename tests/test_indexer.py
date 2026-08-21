import pytest

import indexer


# --- clean_frontmatter ---

def test_clean_frontmatter_strips_wikilinks():
    result = indexer.clean_frontmatter({"pack": "[[Bone Gnawers]]"}, "/x.md")
    assert result["pack"] == "Bone Gnawers"


def test_clean_frontmatter_joins_lists():
    result = indexer.clean_frontmatter({"allies": ["[[Bob]]", "[[Alice]]"]}, "/x.md")
    assert result["allies"] == "Bob, Alice"


def test_clean_frontmatter_excludes_text_and_adds_path():
    result = indexer.clean_frontmatter({"text": "the body", "rank": 3}, "/vault/Bob.md")
    assert "text" not in result
    assert result["rank"] == "3"
    assert result["file_path"] == "/vault/Bob.md"


# --- split_note ---

def test_split_note_separates_frontmatter_from_body(write_note):
    path = write_note("note.md", frontmatter="text: hello", body="Body text here.")
    frontmatter, body = indexer.split_note(path)
    assert frontmatter == {"text": "hello"}
    assert body == "Body text here."


def test_split_note_handles_missing_frontmatter(write_note):
    path = write_note("note.md", body="Just prose.")
    frontmatter, body = indexer.split_note(path)
    assert frontmatter == {}
    assert body == "Just prose."


# --- extract_note_subtype ---

@pytest.mark.parametrize("path,expected", [
    ("/vault/data/notes/person/Bob.md", "person"),
    ("/vault/data/notes/quote/Q1.md", "quote"),
    ("/vault/data/notes/person/npcs/Bob.md", "person"),  # nested still resolves to the top folder
    ("/vault/data/notes/Loose.md", "root"),              # the guard for loose files
])
def test_extract_note_subtype(path, expected):
    assert indexer.extract_note_subtype(path) == expected


# --- parsers: the priority hierarchy ---

def test_structured_note_gets_top_priority(collection):
    indexer.parse_structured_note({"text": "Bob is a Ragabash."}, "/x.md", collection, "werewolf", "person")
    meta = collection.last["metadata"]
    assert meta["priority_score"] == 1
    assert meta["sub_type"] == "person"
    assert meta["chronicle_layer"] == "chronicle_setting"
    assert collection.last["document"] == "Bob is a Ragabash."


def test_priority_ordering_across_layers(collection):
    indexer.parse_structured_note({"text": "a"}, "/a.md", collection, "werewolf", "person")
    indexer.parse_mechanics_note({}, "/b.md", collection, "werewolf", "rules")
    indexer.parse_lore_note({}, "/c.md", collection, "werewolf", "history")
    scores = [u["metadata"]["priority_score"] for u in collection.upserts]
    assert scores == [1, 2, 3]  # live notes beat mechanics beat lore


def test_empty_mechanics_note_falls_back_to_filename(collection):
    """Regression test: splitext returns a tuple, so this once produced "('Rage', '.md')"."""
    indexer.parse_mechanics_note({}, "/vault/Rage.md", collection, "werewolf", "")
    assert collection.last["document"] == "Mechanics rule: Rage"


# --- route_project_file: the routing table ---

@pytest.mark.parametrize("rel_path,expected_category", [
    ("data/notes/person/Bob.md", "structured_note"),
    ("data/notes/location/Caern.md", "structured_note"),
    ("data/mechanics/Rage.md", "mechanics"),
    ("data/lore/Impergium.md", "lore"),
    ("Session Prep.md", "general_project"),  # falls through to generic
])
def test_route_project_file_picks_the_right_parser(write_note, collection, rel_path, expected_category):
    path = write_note(rel_path, frontmatter="text: content", body="Body.")
    indexer.route_project_file(path, collection, "werewolf")
    assert collection.last["metadata"]["data_category"] == expected_category


def test_route_uses_file_path_as_id(write_note, collection):
    path = write_note("data/notes/person/Bob.md", frontmatter="text: Bob")
    indexer.route_project_file(path, collection, "werewolf")
    assert collection.last["id"] == path


# --- safe_index ---

def test_safe_index_skips_non_markdown(collection):
    indexer.safe_index(indexer.route_project_file, "/vault/image.png", collection, "werewolf")
    assert collection.upserts == []


def test_safe_index_survives_a_bad_file(collection, capsys):
    indexer.safe_index(indexer.route_project_file, "/does/not/exist.md", collection, "werewolf")
    assert collection.upserts == []
    assert "[INDEX ERROR]" in capsys.readouterr().out


# --- reconcile_collection ---

def test_reconcile_removes_ghosts_but_keeps_live_files(write_note, tmp_path):
    from tests.conftest import FakeCollection

    live = write_note("Alive.md", body="still here")
    ghost = str(tmp_path / "Deleted.md")

    collection = FakeCollection(ids=[live, ghost])
    indexer.reconcile_collection(collection, str(tmp_path))

    assert collection.deleted == [ghost]