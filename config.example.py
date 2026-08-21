import os

# Point this at your Obsidian vault's root.
VAULT_ROOT = "/mnt/c/Users/YOUR_USERNAME/path/to/YourVault"

# Every indexed folder lives here. Each name maps to its own Chroma collection
# (vault_{name}) and declares which router parses its files. Folders not listed
# are never indexed.
FOLDERS = {
    "werewolf": {"path": f"{VAULT_ROOT}/Creation/LARP/Werewolf", "router": "project"},
    "todo":     {"path": f"{VAULT_ROOT}/____system/_todo",       "router": "standalone"},
    "writing":  {"path": f"{VAULT_ROOT}/Creation/Writing",       "router": "standalone"},
}

DB_PATH = os.path.expanduser("~/obsidian-rag/chroma_db")
LOCK_PORT = 54321  # Arbitrary local port used to ensure only one indexer instance runs


def collection_name(name):
    """Single source of truth for how folder names map to Chroma collection names."""
    return f"vault_{name}"