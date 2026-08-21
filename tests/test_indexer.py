import os
import time

import pytest

import indexer


# --- clean_frontmatter ---

def test_clean_frontmatter_strips_wikilinks(write_note):
    path = write_note("note.md")
    result = indexer.clean_frontmatter({"pack": "[[Bone Gnawers]]"}, path)
    assert result["pack"] == "Bone Gnawers"


def test_clean_frontmatter_joins_lists(write_note):
    path = write_note("note.md")
    result = indexer.clean_frontmatter({"allies": ["[[Bob]]", "[[Alice]]"]}, path)
    assert result["allies"] == "Bob, Alice"


def test_clean_frontmatter_excludes_text_and_adds_path(write_note):
    path = write_note("Bob.md")
    result = indexer.clean_frontmatter({"text": "the body", "rank": 3}, path)
    assert "text" not in result
    assert result["rank"] == "3"
    assert result["file_path"] == path


def test_clean_frontmatter_stamps_mtime(write_note):
    path = write_note("note.md")
    result = indexer.clean_frontmatter({}, path)
    assert result["mtime"] == int(os.path.getmtime(path))


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

def test_structured_note_gets_top_priority(write_note, collection):
    path = write_note("Bob.md")
    indexer.parse_structured_note({"text": "Bob is a Ragabash."}, path, collection, "werewolf", "person")
    meta = collection.last["metadata"]
    assert meta["priority_score"] == 1
    assert meta["sub_type"] == "person"
    assert meta["chronicle_layer"] == "chronicle_setting"
    assert collection.last["document"] == "Bob is a Ragabash."


def test_priority_ordering_across_layers(write_note, collection):
    a, b, c = write_note("a.md"), write_note("b.md"), write_note("c.md")
    indexer.parse_structured_note({"text": "a"}, a, collection, "werewolf", "person")
    indexer.parse_mechanics_note({}, b, collection, "werewolf", "rules")
    indexer.parse_lore_note({}, c, collection, "werewolf", "history")
    scores = [u["metadata"]["priority_score"] for u in collection.upserts]
    assert scores == [1, 2, 3]  # live notes beat mechanics beat lore


def test_empty_mechanics_note_falls_back_to_filename(write_note, collection):
    """Regression test: splitext returns a tuple, so this once produced "('Rage', '.md')"."""
    path = write_note("Rage.md")
    indexer.parse_mechanics_note({}, path, collection, "werewolf", "")
    assert collection.last["document"] == "Mechanics rule: Rage"


# --- route_werewolf_file: the routing table ---

@pytest.mark.parametrize("rel_path,expected_category", [
    ("data/notes/person/Bob.md", "structured_note"),
    ("data/notes/location/Caern.md", "structured_note"),
    ("data/mechanics/Rage.md", "mechanics"),
    ("data/lore/Impergium.md", "lore"),
    ("workspace/werewolf/reports/Session1.md", "quest_report"),
    ("Session Prep.md", "general_project"),  # falls through to generic
])
def test_route_werewolf_file_picks_the_right_parser(write_note, collection, rel_path, expected_category):
    path = write_note(rel_path, frontmatter="text: content", body="Body.")
    indexer.route_werewolf_file(path, collection, "werewolf")
    assert collection.last["metadata"]["data_category"] == expected_category


def test_route_uses_file_path_as_id(write_note, collection):
    path = write_note("data/notes/person/Bob.md", frontmatter="text: Bob")
    indexer.route_werewolf_file(path, collection, "werewolf")
    assert collection.last["id"] == path


# --- parse_report_note ---

def test_report_note_is_zero_trust_bottom_tier(write_note, collection):
    path = write_note("Session1.md")
    indexer.parse_report_note({}, path, collection, "werewolf", "Bob and Alice fought a wyrm-spawn.")
    meta = collection.last["metadata"]
    assert meta["priority_score"] == 4
    assert meta["data_category"] == "quest_report"
    assert meta["chronicle_layer"] == "derived_summary"
    assert collection.last["document"] == "Bob and Alice fought a wyrm-spawn."


def test_report_note_falls_back_to_filename_when_empty(write_note, collection):
    path = write_note("Session1.md")
    indexer.parse_report_note({}, path, collection, "werewolf", "")
    assert collection.last["document"] == "Quest report: Session1"


# --- safe_index ---

def test_safe_index_skips_non_markdown(collection):
    indexer.safe_index(indexer.route_werewolf_file, "/vault/image.png", collection, "werewolf")
    assert collection.upserts == []


def test_safe_index_survives_a_bad_file(collection, capsys):
    indexer.safe_index(indexer.route_werewolf_file, "/does/not/exist.md", collection, "werewolf")
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


def test_reconcile_ignores_ids_from_other_folders_sharing_the_collection(write_note, tmp_path):
    """Regression test: a shared collection (e.g. werewolf + werewolf_reports) must not have one
    folder's reconcile pass delete the other folder's notes just because they're not on its disk."""
    from tests.conftest import FakeCollection

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    live_report = write_note("reports/Session1.md", body="the report")
    other_folder_note = str(tmp_path / "other_folder" / "Bob.md")  # not under reports_dir at all

    collection = FakeCollection(ids=[live_report, other_folder_note])
    indexer.reconcile_collection(collection, str(reports_dir))

    assert collection.deleted == []


# --- index_changed_files ---

def test_index_changed_files_indexes_new_files(write_note, collection, tmp_path):
    write_note("data/mechanics/Rage.md", frontmatter="text: v1")
    indexer.index_changed_files(str(tmp_path), collection, indexer.route_werewolf_file, "werewolf")
    assert len(collection.upserts) == 1


def test_index_changed_files_skips_unchanged_files_on_a_second_pass(write_note, collection, tmp_path):
    write_note("data/mechanics/Rage.md", frontmatter="text: v1")
    indexer.index_changed_files(str(tmp_path), collection, indexer.route_werewolf_file, "werewolf")
    indexer.index_changed_files(str(tmp_path), collection, indexer.route_werewolf_file, "werewolf")
    assert len(collection.upserts) == 1


def test_index_changed_files_reindexes_when_mtime_changes(write_note, collection, tmp_path):
    path = write_note("data/mechanics/Rage.md", frontmatter="text: v1")
    indexer.index_changed_files(str(tmp_path), collection, indexer.route_werewolf_file, "werewolf")

    future = time.time() + 5  # bump well past the 1-second mtime resolution we store
    os.utime(path, (future, future))
    indexer.index_changed_files(str(tmp_path), collection, indexer.route_werewolf_file, "werewolf")

    assert len(collection.upserts) == 2
