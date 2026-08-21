import os

from notes import clean_frontmatter, extract_note_subtype, split_note


def parse_structured_note(frontmatter, file_path, collection, name, sub_type):
    """Handles your atomic notes folder (people, quotes, etc.). Flags them as the ultimate authority."""
    text_content = frontmatter.get('text', '') or f"Atomic {sub_type}: {os.path.basename(file_path)}"
    metadata = clean_frontmatter(frontmatter, file_path)

    # Priority Overwrites Injection
    metadata["data_category"] = "structured_note"
    metadata["sub_type"] = sub_type
    metadata["chronicle_layer"] = "chronicle_setting"  # Primary source of truth
    metadata["priority_score"] = 1

    collection.upsert(documents=[str(text_content)], metadatas=[metadata], ids=[file_path])
    print(f"[{name.upper()} {sub_type.upper()} INDEXED] {os.path.basename(file_path)}")

def parse_mechanics_note(frontmatter, file_path, collection, name, file_body):
    """Handles core rule files. Subservient to custom house rules in notes folder."""
    text_content = frontmatter.get('text', '') or file_body
    if not text_content.strip():
        text_content = f"Mechanics rule: {os.path.splitext(os.path.basename(file_path))[0]}"

    metadata = clean_frontmatter(frontmatter, file_path)
    metadata["data_category"] = "mechanics"
    metadata["chronicle_layer"] = "core_mechanics"
    metadata["priority_score"] = 2

    collection.upsert(documents=[str(text_content)], metadatas=[metadata], ids=[file_path])
    print(f"[{name.upper()} MECHANICS INDEXED] {os.path.basename(file_path)}")

def parse_lore_note(frontmatter, file_path, collection, name, file_body):
    """Handles baseline timeline / setting text. Subservient to live plot alterations."""
    text_content = frontmatter.get('text', '') or file_body
    if not text_content.strip():
        text_content = f"Lore document: {os.path.splitext(os.path.basename(file_path))[0]}"

    metadata = clean_frontmatter(frontmatter, file_path)
    metadata["data_category"] = "lore"
    metadata["chronicle_layer"] = "secondary_historical_lore"
    metadata["priority_score"] = 3

    collection.upsert(documents=[str(text_content)], metadatas=[metadata], ids=[file_path])
    print(f"[{name.upper()} LORE INDEXED] {os.path.basename(file_path)}")

def parse_report_note(frontmatter, file_path, collection, name, file_body):
    """Handles quest reports: human-facing catch-up summaries generated from the data, not the data itself. Zero trust — bottom of the priority hierarchy."""
    text_content = file_body or f"Quest report: {os.path.splitext(os.path.basename(file_path))[0]}"

    metadata = clean_frontmatter(frontmatter, file_path)
    metadata["data_category"] = "quest_report"
    metadata["chronicle_layer"] = "derived_summary"
    metadata["priority_score"] = 4

    collection.upsert(documents=[str(text_content)], metadatas=[metadata], ids=[file_path])
    print(f"[{name.upper()} REPORT INDEXED] {os.path.basename(file_path)}")

def parse_generic_project_note(frontmatter, file_path, collection, name, file_body):
    """Fallback for project files that live outside the recognized data/ silos."""
    metadata = clean_frontmatter(frontmatter, file_path)
    metadata["data_category"] = "general_project"

    collection.upsert(documents=[str(file_body or os.path.basename(file_path))], metadatas=[metadata], ids=[file_path])
    print(f"[{name.upper()} GENERAL INDEXED] {os.path.basename(file_path)}")

def route_werewolf_file(file_path, collection, name):
    """Pure switchboard for all werewolf-domain content, across both source folders
    (the LARP chronicle under data/, and the Hivemind quest-reports folder). Reads the
    note once, then hands it to exactly one parser."""
    norm_path = file_path.replace("\\", "/")
    frontmatter, file_body = split_note(file_path)

    if "data/notes/" in norm_path:
        parse_structured_note(frontmatter, file_path, collection, name, extract_note_subtype(norm_path))
    elif "data/mechanics" in norm_path:
        parse_mechanics_note(frontmatter, file_path, collection, name, file_body)
    elif "data/lore" in norm_path:
        parse_lore_note(frontmatter, file_path, collection, name, file_body)
    elif "workspace/werewolf/reports" in norm_path:
        parse_report_note(frontmatter, file_path, collection, name, file_body)
    else:
        parse_generic_project_note(frontmatter, file_path, collection, name, file_body)
