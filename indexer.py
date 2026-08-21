import os
import sys
import time
import socket
import chromadb

# PollingObserver guarantees file save triggers cross the Windows-to-WSL mount boundary
from watchdog.observers.polling import PollingObserver as Observer

from parsers_standalone import route_standalone_file
from parsers_werewolf import route_werewolf_file
from sync import index_changed_files, reconcile_collection
from watcher import VaultHandler

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

# Maps the "router" string in FOLDERS config to an actual routing function.
ROUTERS = {
    "werewolf": route_werewolf_file,
    "standalone": route_standalone_file,
}

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
        collection = chroma_client.get_or_create_collection(name=collection_name(config.get("collection", name)))

        print(f"Scanning collection: vault_{name} ({config['router']} router)...")
        index_changed_files(folder_path, collection, route_func, name)
        reconcile_collection(collection, folder_path)
        observer.schedule(VaultHandler(collection, route_func, name), path=folder_path, recursive=True)

    observer.start()
    print(f"\nAll configurations loaded! Watching all folders simultaneously.")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt: observer.stop()
    observer.join()
