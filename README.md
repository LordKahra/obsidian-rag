# obsidian-rag

A local retrieval-augmented generation layer over an [Obsidian](https://obsidian.md) vault.
It keeps a vector index in sync with your Markdown notes as you edit them, and exposes
semantic search to LLM clients through an [MCP](https://modelcontextprotocol.io) server.

Everything runs on your machine. No note content leaves the host; the only external
dependency is whatever embedding backend ChromaDB is configured to use (by default, a
local sentence-transformers model downloaded on first run).

> **Status: personal project, shared as a reference — not a packaged tool.**
> This is built around one specific vault: my folder layout, my note conventions, a
> `werewolf` router that encodes the canon hierarchy of a LARP chronicle I play, and a
> Windows-host / WSL-guest setup. It's public so the code and the design decisions can be
> read, not because it's ready to drop into someone else's setup. Running it against your
> own vault means editing `config.py`, almost certainly writing your own router/parser, and
> working around assumptions that are currently hardcoded to my environment. There's no
> release, no versioning, and no support. Treat it as a worked example, not a product.

## Why

Obsidian's built-in search is lexical. If you keep a large vault — worldbuilding notes,
task lists, drafts — you often want *"what did I write about X"* rather than *"which files
contain the word X"*. This indexes the vault into a vector store and lets a model query it
by meaning, with per-folder scoping and metadata filters.

## Architecture

```
Obsidian vault (Markdown + YAML frontmatter)
        │
        │  watchdog PollingObserver  (survives the Windows→WSL mount boundary)
        ▼
   indexer.py ──► routers ──► parsers ──► ChromaDB (persistent, one collection per domain)
        │                                      ▲
        │  incremental: only new / mtime-changed files are re-embedded
        │  reconcile:   vectors whose source file is gone are deleted
        │
   rag_server.py  (MCP server)  ──►  search_notes / search_werewolf_by_type / get_note / list_domains
        │
        ▼
   LLM client (Claude Desktop, etc.)
```

| File | Responsibility |
|------|----------------|
| [`config.py`](config.example.py) | Vault root, which folders to index, which router parses each |
| [`indexer.py`](indexer.py) | Long-running process: initial scan, reconcile, then watch every folder |
| [`notes.py`](notes.py) | Markdown/frontmatter splitting, wiki-link stripping, metadata normalization |
| [`sync.py`](sync.py) | Incremental indexing (mtime skip) and orphan reconciliation |
| [`watcher.py`](watcher.py) | Filesystem-event handler: index on create/modify, deindex on delete, move = delete + create |
| [`parsers_werewolf.py`](parsers_werewolf.py) / [`parsers_standalone.py`](parsers_standalone.py) | Turn a note into a `(document, metadata, id)` upsert; assign source-trust priority |
| [`rag_server.py`](rag_server.py) | MCP server exposing the search tools |
| [`tray/tray.py`](tray/tray.py) | Optional Windows system-tray control (start/stop/restart/log) for the indexer running in WSL |

## Design notes

These are the parts that took thought rather than typing.

- **Incremental re-embedding.** Each indexed document is stamped with its file's `mtime`.
  On startup the indexer compares stamps and only re-embeds files that are new or changed,
  so restarting the process doesn't re-embed (and re-pay for) an unchanged vault.

- **Reconciliation.** Files deleted or renamed *while the indexer was off* leave vectors
  behind that would otherwise keep surfacing in results. On startup, `reconcile_collection`
  diffs the collection's IDs against what's on disk and deletes the ghosts. It's scoped by
  path prefix because one collection can be fed by more than one folder.

- **`PollingObserver`, not the native observer.** The vault lives on a Windows filesystem
  accessed from WSL over a 9P mount; native inotify events don't cross that boundary
  reliably. Polling is slower but actually fires.

- **Document IDs are file paths.** Upserts are idempotent and deletes are exact, with no
  separate ID bookkeeping to drift out of sync.

- **Source-trust priority.** Notes carry a `priority_score` in metadata reflecting how
  authoritative the source is (hand-maintained structured notes > rules > background lore >
  auto-generated summaries). Conflicting retrievals are meant to be resolved in favor of the
  lower number; `rag_server.py` prepends a short legend to results so the model knows the
  rule. This is domain-specific (it came from a LARP chronicle with layered canon) but the
  pattern generalizes to any vault where some notes are ground truth and others are derived.

- **`text` frontmatter override.** If a note has a `text:` frontmatter field, that becomes
  the embedded document instead of the note body — useful for atomic notes whose meaning
  lives in properties rather than prose.

## Setup

Requires Python 3.11+.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

```bash
cp config.example.py config.py
```

Edit `config.py`:

- `VAULT_ROOT` — absolute path to your vault
- `REPO_PATH` — absolute path to this checkout
- `FOLDERS` — the folders to index. Each entry maps to a Chroma collection (`vault_<name>`)
  and names a router (`standalone` for plain notes, `werewolf` for the layered-canon
  example). Delete the `werewolf*` entries unless you want the example behavior.
- `WSL_DISTRO` / `WSL_USER` — only used by the tray app; ignore otherwise.

## Running

Start the indexer (keep it running while you work):

```bash
python indexer.py
```

It does an initial scan, reconciles deletions, then watches all configured folders. A lock
on a local port prevents a second instance.

Then point an MCP client at the server. For Claude Desktop, in
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "obsidian-rag": {
      "command": "/absolute/path/to/venv/bin/python",
      "args": ["/absolute/path/to/rag_server.py"]
    }
  }
}
```

### MCP tools

| Tool | Purpose |
|------|---------|
| `list_domains` | List indexed domains and note counts |
| `search_notes(domain, query, n_results=5)` | Semantic search within one domain |
| `search_werewolf_by_type(query, sub_type, n_results=5)` | Semantic search filtered by structured-note type (example router only) |
| `get_note(domain, file_path)` | Fetch one indexed note by exact path |

### Windows tray (optional)

If the indexer runs in WSL and you want to control it from Windows, run `tray/tray.py` with
native Windows Python (`pip install -r tray/requirements.txt`). It shells into WSL to
start/stop/restart the indexer and tails its log.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Covers frontmatter parsing, incremental sync and reconciliation, the parsers' priority
assignment, and the MCP tools. Chroma is faked in `tests/conftest.py`, so the suite is
fast and needs no database or embedding model.

## Limitations / next steps

Honest about what this is not:

- **One note = one document.** No chunking or overlap. Fine for short atomic notes; long
  documents get embedded whole and retrieval on them is coarse.
- **Default embedding model.** Uses ChromaDB's default. No deliberate model choice or
  comparison.
- **No retrieval evaluation.** No recall@k / MRR harness, no labeled query set.
- **Vector-only.** No hybrid (BM25 + dense) search and no reranking step.
- **Retrieval only.** The generation half is whatever MCP client you connect; there's no
  answer synthesis or citation handling here.
- **Single user, single machine.**

The highest-value additions would be a real chunker, an explicit embedding-model choice
with a one-paragraph rationale, and a small evaluation script with numbers.
