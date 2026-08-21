import pytest

import parsers_werewolf


# --- parsers: the priority hierarchy ---

def test_structured_note_gets_top_priority(write_note, collection):
    path = write_note("Bob.md")
    parsers_werewolf.parse_structured_note({"text": "Bob is a Ragabash."}, path, collection, "werewolf", "person")
    meta = collection.last["metadata"]
    assert meta["priority_score"] == 1
    assert meta["sub_type"] == "person"
    assert meta["chronicle_layer"] == "chronicle_setting"
    assert collection.last["document"] == "Bob is a Ragabash."


def test_priority_ordering_across_layers(write_note, collection):
    a, b, c = write_note("a.md"), write_note("b.md"), write_note("c.md")
    parsers_werewolf.parse_structured_note({"text": "a"}, a, collection, "werewolf", "person")
    parsers_werewolf.parse_mechanics_note({}, b, collection, "werewolf", "rules")
    parsers_werewolf.parse_lore_note({}, c, collection, "werewolf", "history")
    scores = [u["metadata"]["priority_score"] for u in collection.upserts]
    assert scores == [1, 2, 3]  # live notes beat mechanics beat lore


def test_empty_mechanics_note_falls_back_to_filename(write_note, collection):
    """Regression test: splitext returns a tuple, so this once produced "('Rage', '.md')"."""
    path = write_note("Rage.md")
    parsers_werewolf.parse_mechanics_note({}, path, collection, "werewolf", "")
    assert collection.last["document"] == "Mechanics rule: Rage"


# --- parse_report_note ---

def test_report_note_is_zero_trust_bottom_tier(write_note, collection):
    path = write_note("Session1.md")
    parsers_werewolf.parse_report_note({}, path, collection, "werewolf", "Bob and Alice fought a wyrm-spawn.")
    meta = collection.last["metadata"]
    assert meta["priority_score"] == 4
    assert meta["data_category"] == "quest_report"
    assert meta["chronicle_layer"] == "derived_summary"
    assert collection.last["document"] == "Bob and Alice fought a wyrm-spawn."


def test_report_note_falls_back_to_filename_when_empty(write_note, collection):
    path = write_note("Session1.md")
    parsers_werewolf.parse_report_note({}, path, collection, "werewolf", "")
    assert collection.last["document"] == "Quest report: Session1"


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
    parsers_werewolf.route_werewolf_file(path, collection, "werewolf")
    assert collection.last["metadata"]["data_category"] == expected_category


def test_route_uses_file_path_as_id(write_note, collection):
    path = write_note("data/notes/person/Bob.md", frontmatter="text: Bob")
    parsers_werewolf.route_werewolf_file(path, collection, "werewolf")
    assert collection.last["id"] == path
