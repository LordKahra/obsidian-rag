import os

import pytest

import notes


# --- clean_frontmatter ---

def test_clean_frontmatter_strips_wikilinks(write_note):
    path = write_note("note.md")
    result = notes.clean_frontmatter({"pack": "[[Bone Gnawers]]"}, path)
    assert result["pack"] == "Bone Gnawers"


def test_clean_frontmatter_joins_lists(write_note):
    path = write_note("note.md")
    result = notes.clean_frontmatter({"allies": ["[[Bob]]", "[[Alice]]"]}, path)
    assert result["allies"] == "Bob, Alice"


def test_clean_frontmatter_excludes_text_and_adds_path(write_note):
    path = write_note("Bob.md")
    result = notes.clean_frontmatter({"text": "the body", "rank": 3}, path)
    assert "text" not in result
    assert result["rank"] == "3"
    assert result["file_path"] == path


def test_clean_frontmatter_stamps_mtime(write_note):
    path = write_note("note.md")
    result = notes.clean_frontmatter({}, path)
    assert result["mtime"] == int(os.path.getmtime(path))


# --- split_note ---

def test_split_note_separates_frontmatter_from_body(write_note):
    path = write_note("note.md", frontmatter="text: hello", body="Body text here.")
    frontmatter, body = notes.split_note(path)
    assert frontmatter == {"text": "hello"}
    assert body == "Body text here."


def test_split_note_handles_missing_frontmatter(write_note):
    path = write_note("note.md", body="Just prose.")
    frontmatter, body = notes.split_note(path)
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
    assert notes.extract_note_subtype(path) == expected
