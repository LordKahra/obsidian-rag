import os

from notes import is_markdown, walk_markdown


def deindex_note(file_path, collection):
    """Removes a deleted/moved note from the collection so ghosts don't poison retrieval."""
    try:
        collection.delete(ids=[file_path])
        print(f"[DEINDEXED] {os.path.basename(file_path)}")
    except Exception as e:
        print(f"[DEINDEX ERROR] {file_path}: {e}")

def reconcile_collection(collection, folder_path):
    """Deletes DB entries whose files no longer exist on disk (deletes/renames that happened while the indexer was off).
    Scoped to ids under folder_path, since a collection may be fed by more than one folder (e.g. werewolf_reports)."""
    folder_prefix = os.path.join(folder_path, "")
    indexed_ids = {i for i in collection.get(include=[])["ids"] if i.startswith(folder_prefix)}
    on_disk = set(walk_markdown(folder_path))
    for ghost in indexed_ids - on_disk:
        deindex_note(ghost, collection)

def index_changed_files(folder_path, collection, route_func, name):
    """Indexes only files that are new or whose mtime has changed since last run, so a restart
    doesn't re-embed an entire folder's worth of unchanged notes."""
    folder_prefix = os.path.join(folder_path, "")
    existing = collection.get(include=["metadatas"])
    known_mtimes = {i: m.get("mtime") for i, m in zip(existing["ids"], existing["metadatas"])
                     if i.startswith(folder_prefix)}

    for file_path in walk_markdown(folder_path):
        if known_mtimes.get(file_path) != int(os.path.getmtime(file_path)):
            safe_index(route_func, file_path, collection, name)

def safe_index(route_func, file_path, collection, name):
    """One wrapper owns filtering + error reporting for every indexing path."""
    if not is_markdown(file_path):
        return
    try:
        route_func(file_path, collection, name)
    except Exception as e:
        print(f"[INDEX ERROR] {file_path}: {e}")
