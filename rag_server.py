import sys
import chromadb
from mcp.server.mcpserver import MCPServer

# --- CONFIGURATION ---

try:
    from config import FOLDERS, DB_PATH, collection_name
except ImportError:
    sys.exit("[ERROR] No config.py found. Copy config.example.py to config.py and set VAULT_ROOT.")

# Maps friendly domain names to their Chroma collections.
DOMAINS = {name: collection_name(name) for name in FOLDERS}

# Explains the werewolf priority hierarchy to the model reading results.
PRIORITY_LEGEND = (
    "Priority guide: priority_score 1 (structured_note) is live chronicle truth and "
    "overrides 2 (mechanics), which overrides 3 (lore). 4 is general project text. "
    "When results conflict, trust the lower number."
)

mcp = MCPServer("obsidian-rag")
_client = None  # Lazily created so importing this module never opens the DB.

# --- HELPERS ---

def get_client():
    """Lazily creates the Chroma client on first use (not at import time)."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=DB_PATH)
    return _client

def get_collection(domain: str):
    """Resolves a domain name to its Chroma collection, or raises a readable error."""
    if domain not in DOMAINS:
        raise ValueError(f"Unknown domain '{domain}'. Valid domains: {', '.join(DOMAINS)}")
    return get_client().get_or_create_collection(name=DOMAINS[domain])

def format_hit(document: str, metadata: dict, distance: float) -> str:
    """Renders one search hit as a readable block: source path, key metadata, then content."""
    lines = [f"### {metadata.get('file_path', 'unknown')}"]

    tags = []
    for key in ("data_category", "sub_type", "chronicle_layer", "priority_score"):
        if key in metadata:
            tags.append(f"{key}={metadata[key]}")
    tags.append(f"distance={distance:.4f}")
    lines.append(" | ".join(tags))

    extra = {k: v for k, v in metadata.items()
             if k not in ("file_path", "data_category", "sub_type", "chronicle_layer", "priority_score")}
    if extra:
        lines.append("Properties: " + " | ".join(f"{k}: {v}" for k, v in extra.items()))

    lines.append("")
    lines.append(document)
    return "\n".join(lines)

def format_results(results: dict, header: str = "") -> str:
    """Renders a full Chroma query result set, or a clear empty-state message."""
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    if not documents:
        return "No results found."

    blocks = [header] if header else []
    blocks += [format_hit(d, m, dist) for d, m, dist in zip(documents, metadatas, distances)]
    return "\n\n---\n\n".join(filter(None, blocks))

# --- TOOLS ---

@mcp.tool()
def list_domains() -> str:
    """Lists the searchable note domains and how many notes each contains."""
    lines = []
    for domain, col_name in DOMAINS.items():
        count = get_client().get_or_create_collection(name=col_name).count()
        lines.append(f"- {domain}: {count} notes")
    return "\n".join(lines)

@mcp.tool()
def search_notes(domain: str, query: str, n_results: int = 5) -> str:
    """Semantic search over one domain of the Obsidian vault.

    domain: one of 'werewolf' (LARP chronicle: people, quotes, locations, groups,
    mechanics, lore), 'todo' (task notes), or 'writing' (creative writing).
    query: natural-language description of what you're looking for.
    n_results: how many notes to return (default 5).
    """
    collection = get_collection(domain)
    results = collection.query(query_texts=[query], n_results=n_results)
    header = PRIORITY_LEGEND if domain == "werewolf" else ""
    return format_results(results, header)

@mcp.tool()
def search_werewolf_by_type(query: str, sub_type: str, n_results: int = 5) -> str:
    """Semantic search over the werewolf chronicle, restricted to one structured note type.

    sub_type: the atomic note category to search within — 'person', 'quote',
    'location', 'group', or 'info'.
    query: natural-language description of what you're looking for.
    """
    collection = get_collection("werewolf")
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where={"sub_type": sub_type},
    )
    return format_results(results)

@mcp.tool()
def get_note(domain: str, file_path: str) -> str:
    """Fetches one specific indexed note by its exact file path (as returned in search results)."""
    collection = get_collection(domain)
    result = collection.get(ids=[file_path])
    if not result["ids"]:
        return f"No indexed note found at: {file_path}"
    return format_hit(result["documents"][0], result["metadatas"][0], distance=0.0)

if __name__ == "__main__":
    mcp.run()