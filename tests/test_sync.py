import os
import time

import sync
from parsers_werewolf import route_werewolf_file


# --- safe_index ---

def test_safe_index_skips_non_markdown(collection):
    sync.safe_index(route_werewolf_file, "/vault/image.png", collection, "werewolf")
    assert collection.upserts == []


def test_safe_index_survives_a_bad_file(collection, capsys):
    sync.safe_index(route_werewolf_file, "/does/not/exist.md", collection, "werewolf")
    assert collection.upserts == []
    assert "[INDEX ERROR]" in capsys.readouterr().out


# --- reconcile_collection ---

def test_reconcile_removes_ghosts_but_keeps_live_files(write_note, tmp_path):
    from tests.conftest import FakeCollection

    live = write_note("Alive.md", body="still here")
    ghost = str(tmp_path / "Deleted.md")

    collection = FakeCollection(ids=[live, ghost])
    sync.reconcile_collection(collection, str(tmp_path))

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
    sync.reconcile_collection(collection, str(reports_dir))

    assert collection.deleted == []


# --- index_changed_files ---

def test_index_changed_files_indexes_new_files(write_note, collection, tmp_path):
    write_note("data/mechanics/Rage.md", frontmatter="text: v1")
    sync.index_changed_files(str(tmp_path), collection, route_werewolf_file, "werewolf")
    assert len(collection.upserts) == 1


def test_index_changed_files_skips_unchanged_files_on_a_second_pass(write_note, collection, tmp_path):
    write_note("data/mechanics/Rage.md", frontmatter="text: v1")
    sync.index_changed_files(str(tmp_path), collection, route_werewolf_file, "werewolf")
    sync.index_changed_files(str(tmp_path), collection, route_werewolf_file, "werewolf")
    assert len(collection.upserts) == 1


def test_index_changed_files_reindexes_when_mtime_changes(write_note, collection, tmp_path):
    path = write_note("data/mechanics/Rage.md", frontmatter="text: v1")
    sync.index_changed_files(str(tmp_path), collection, route_werewolf_file, "werewolf")

    future = time.time() + 5  # bump well past the 1-second mtime resolution we store
    os.utime(path, (future, future))
    sync.index_changed_files(str(tmp_path), collection, route_werewolf_file, "werewolf")

    assert len(collection.upserts) == 2
