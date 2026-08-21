import os

from notes import clean_frontmatter, split_note


def parse_standalone_note(frontmatter, file_path, collection, name, file_body):
    """Standard parser for simple standalone folders (t odo, writing)."""
    text_content = frontmatter.get('text', '') or file_body or os.path.basename(file_path)
    metadata = clean_frontmatter(frontmatter, file_path)
    metadata["data_category"] = "standalone"
    collection.upsert(documents=[str(text_content)], metadatas=[metadata], ids=[file_path])
    print(f"[{name.upper()} INDEXED] {os.path.basename(file_path)}")

def route_standalone_file(file_path, collection, name):
    """Switchboard for standalone folders. Trivial today, but new routing rules slot in here."""
    frontmatter, file_body = split_note(file_path)
    parse_standalone_note(frontmatter, file_path, collection, name, file_body)
