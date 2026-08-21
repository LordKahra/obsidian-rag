import os

# Point this at your Obsidian vault's root.
VAULT_ROOT = "/mnt/c/Users/YOUR_USERNAME/path/to/YourVault"

# Absolute WSL path to this repo.
REPO_PATH = "/home/YOUR_WSL_USERNAME/obsidian-rag"

# WSL distro name (`wsl -l -v` on the Windows side) and your WSL username.
# Only used by tray/tray.py, which runs on native Windows Python and needs
# to know how to reach into WSL via `wsl.exe -d <distro> -u <user>`.
WSL_DISTRO = "Ubuntu"
WSL_USER = "YOUR_WSL_USERNAME"

# Every indexed folder lives here. Each name maps to its own Chroma collection
# (vault_{name}) and declares which router parses its files. Folders not listed
# are never indexed. An optional "collection" key redirects a folder into an
# existing collection instead of getting its own (see werewolf_reports below) —
# such folders are feeders, not domains, and rag_server.py excludes them from
# its domain list accordingly.
FOLDERS = {
    "werewolf": {"path": f"{VAULT_ROOT}/Creation/LARP/Werewolf", "router": "werewolf"},
    "todo":     {"path": f"{VAULT_ROOT}/____system/_todo",       "router": "standalone"},
    "writing":  {"path": f"{VAULT_ROOT}/Creation/Writing",       "router": "standalone"},
    "werewolf_reports": {
        "path": f"{VAULT_ROOT}/Hivemind/workspace/werewolf/reports",
        "router": "werewolf",
        "collection": "werewolf",  # feeds vault_werewolf, not its own vault_werewolf_reports
    },
}

DB_PATH = os.path.join(REPO_PATH, "chroma_db")
LOCK_PORT = 54321  # Arbitrary local port used to ensure only one indexer instance runs


def collection_name(name):
    """Single source of truth for how folder names map to Chroma collection names."""
    return f"vault_{name}"