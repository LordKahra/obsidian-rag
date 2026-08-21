import os
import re
import yaml


def is_markdown(file_path):
    """Only markdown notes get indexed. Everything else (images, PDFs, .obsidian junk) is ignored."""
    return file_path.endswith('.md')

def split_note(file_path):
    """Reads a file and splits it into (frontmatter dict, body text)."""
    with open(file_path, 'r', encoding='utf-8') as f:
        full_content = f.read()

    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', full_content, re.DOTALL)
    if match:
        return yaml.safe_load(match.group(1)) or {}, match.group(2).strip()
    return {}, full_content.strip()

def clean_frontmatter(frontmatter, file_path):
    """Extracts standard properties, strips wiki-links [[brackets]], and stamps mtime
    so a later run can skip re-indexing (and re-embedding) files that haven't changed."""
    metadata = {}
    for key, value in frontmatter.items():
        if key == 'text':
            continue
        if isinstance(value, list):
            clean_vals = [str(v).replace('[[', '').replace(']]', '') for v in value]
            metadata[key] = ", ".join(clean_vals)
        else:
            metadata[key] = str(value).replace('[[', '').replace(']]', '')
    metadata["file_path"] = file_path
    metadata["mtime"] = int(os.path.getmtime(file_path))
    return metadata

def walk_markdown(folder_path):
    """Yields every markdown file path under a folder."""
    for root, _, files in os.walk(folder_path):
        for file in files:
            if is_markdown(file):
                yield os.path.join(root, file)

def extract_note_subtype(norm_path):
    """Pulls the subfolder name after data/notes/ as the sub_type. Loose files get 'root'."""
    parts = norm_path.split("data/notes/")[1].split("/")
    return parts[0] if len(parts) > 1 else "root"
