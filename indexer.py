import os
import re
import sys
import time
import yaml
import socket
import chromadb

# PollingObserver guarantees file save triggers cross the Windows-to-WSL mount boundary
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler

# --- CONFIGURATION ---

try:
    from config import FOLDERS, DB_PATH, LOCK_PORT, collection_name
except ImportError:
    sys.exit("[ERROR] No config.py found. Copy config.example.py to config.py and set VAULT_ROOT.")

_lock_socket = None # Global placeholder for our socket connection to prevent garbage collection

def maintain_single_instance():
    global _lock_socket
    try:
        _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_socket.bind(('127.0.0.1', LOCK_PORT))
    except socket.error:
        print("[NOTICE] Another instance of indexer.py is already active. Exiting.")
        sys.exit(0)

# --- SHARED HELPERS ---

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
    """Extracts standard properties and strips wiki-links [[brackets]]."""
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
    return metadata

def deindex_note(file_path, collection):
    """Removes a deleted/moved note from the collection so ghosts don't poison retrieval."""
    try:
        collection.delete(ids=[file_path])
        print(f"[DEINDEXED] {os.path.basename(file_path)}")
    except Exception as e:
        print(f"[DEINDEX ERROR] {file_path}: {e}")

def walk_markdown(folder_path):
    """Yields every markdown file path under a folder."""
    for root, _, files in os.walk(folder_path):
        for file in files:
            if is_markdown(file):
                yield os.path.join(root, file)

def reconcile_collection(collection, folder_path):
    """Deletes DB entries whose files no longer exist on disk (deletes/renames that happened while the indexer was off)."""
    indexed_ids = set(collection.get(include=[])["ids"])
    on_disk = set(walk_markdown(folder_path))
    for ghost in indexed_ids - on_disk:
        deindex_note(ghost, collection)

# --- PARSERS FOR PROJECT-ROUTED FOLDERS (E.G. WEREWOLF) ---

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

def parse_generic_project_note(frontmatter, file_path, collection, name, file_body):
    """Fallback for project files that live outside the recognized data/ silos."""
    metadata = clean_frontmatter(frontmatter, file_path)
    metadata["data_category"] = "general_project"

    collection.upsert(documents=[str(file_body or os.path.basename(file_path))], metadatas=[metadata], ids=[file_path])
    print(f"[{name.upper()} GENERAL INDEXED] {os.path.basename(file_path)}")

# --- PARSER FOR STANDALONE-ROUTED FOLDERS ---

def parse_standalone_note(frontmatter, file_path, collection, name, file_body):
    """Standard parser for simple standalone folders (t odo, writing)."""
    text_content = frontmatter.get('text', '') or file_body or os.path.basename(file_path)
    metadata = clean_frontmatter(frontmatter, file_path)
    metadata["data_category"] = "standalone"
    collection.upsert(documents=[str(text_content)], metadatas=[metadata], ids=[file_path])
    print(f"[{name.upper()} INDEXED] {os.path.basename(file_path)}")

# --- SMART PATH ROUTERS ---

def extract_note_subtype(norm_path):
    """Pulls the subfolder name after data/notes/ as the sub_type. Loose files get 'root'."""
    parts = norm_path.split("data/notes/")[1].split("/")
    return parts[0] if len(parts) > 1 else "root"

def route_project_file(file_path, collection, name):
    """Pure switchboard: reads the note once, then hands it to exactly one parser."""
    norm_path = file_path.replace("\\", "/")
    frontmatter, file_body = split_note(file_path)

    if "data/notes/" in norm_path:
        parse_structured_note(frontmatter, file_path, collection, name, extract_note_subtype(norm_path))
    elif "data/mechanics" in norm_path:
        parse_mechanics_note(frontmatter, file_path, collection, name, file_body)
    elif "data/lore" in norm_path:
        parse_lore_note(frontmatter, file_path, collection, name, file_body)
    else:
        parse_generic_project_note(frontmatter, file_path, collection, name, file_body)

def route_standalone_file(file_path, collection, name):
    """Switchboard for standalone folders. Trivial today, but new routing rules slot in here."""
    frontmatter, file_body = split_note(file_path)
    parse_standalone_note(frontmatter, file_path, collection, name, file_body)

# Maps the "router" string in FOLDERS config to an actual routing function.
ROUTERS = {
    "project": route_project_file,
    "standalone": route_standalone_file,
}

def safe_index(route_func, file_path, collection, name):
    """One wrapper owns filtering + error reporting for every indexing path."""
    if not is_markdown(file_path):
        return
    try:
        route_func(file_path, collection, name)
    except Exception as e:
        print(f"[INDEX ERROR] {file_path}: {e}")

# --- WATCHDOG HANDLER ---

class VaultHandler(FileSystemEventHandler):
    """Shared watcher: indexes on create/modify, deindexes on delete, and treats moves as delete+create."""
    def __init__(self, collection, route_func, name):
        self.collection = collection
        self.route_func = route_func
        self.name = name
        super().__init__()

    def _index(self, file_path):
        safe_index(self.route_func, file_path, self.collection, self.name)

    def on_created(self, event):
        if not event.is_directory: self._index(event.src_path)

    def on_modified(self, event):
        if not event.is_directory: self._index(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory and is_markdown(event.src_path):
            deindex_note(event.src_path, self.collection)

    def on_moved(self, event):
        if not event.is_directory:
            if is_markdown(event.src_path):
                deindex_note(event.src_path, self.collection)
            self._index(event.dest_path)

if __name__ == "__main__":
    # Check for active processes before initializing DB or structures
    maintain_single_instance()

    # Initialize Vector DB
    chroma_client = chromadb.PersistentClient(path=DB_PATH)
    observer = Observer()

    # One loop for everything: each configured folder gets its own collection, router, reconciliation, and watcher.
    for name, config in FOLDERS.items():
        folder_path = config["path"]
        if not os.path.exists(folder_path):
            print(f"[SKIPPED] {name}: path does not exist ({folder_path})")
            continue

        route_func = ROUTERS[config["router"]]
        collection = chroma_client.get_or_create_collection(name=collection_name(name))

        print(f"Scanning collection: vault_{name} ({config['router']} router)...")
        for file_path in walk_markdown(folder_path):
            safe_index(route_func, file_path, collection, name)

        reconcile_collection(collection, folder_path)
        observer.schedule(VaultHandler(collection, route_func, name), path=folder_path, recursive=True)

    observer.start()
    print(f"\nAll configurations loaded! Watching all folders simultaneously.")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt: observer.stop()
    observer.join()
