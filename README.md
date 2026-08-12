# Rhizome

Local knowledge-base graph explorer for markdown vaults (Obsidian-compatible).

Parses a vault's wikilinks and markdown links, then serves a split view:
an interactive 3D force-graph on the left, a reading panel on the right.
Click a node to isolate its sub-graph (depth 1–4) and read the note beside it.

Fully self-owned: the JS library is vendored, the server binds localhost only,
nothing ever leaves your machine.

## Features

- **Live parse** — the graph is rebuilt from the vault on every refresh, no export step.
- **Sub-graph (ego) views** — click a node, adjust depth, exit back to the full graph.
- **Type legend as filter** — node type = parent folder; the top types get a
  CVD-validated categorical palette, the rest fold into "Other"; chips toggle visibility.
- **Reader panel** — self-contained markdown rendering; wikilinks inside a note
  navigate the graph; "Open in Obsidian" jumps to the file.
- **Search** and `?open=path/to/note.md` deep links.
- Notion-export friendly: trailing 32-hex IDs are stripped from display names.

## Run

```
python3 server.py --vault /path/to/vault        # default port 8321
```

Open http://localhost:8321

No dependencies beyond Python 3.9+ stdlib.

Run it as a background service (systemd):

```
systemd-run --user --unit=rhizome --working-directory=/path/to/rhizome \
  python3 server.py --vault /path/to/vault
```

## How it reads the vault

- Node = every `.md` file (`.git`, `.obsidian` excluded).
- Node type = immediate parent folder.
- Edge = resolved `[[wikilink]]` (by filename stem) or relative markdown link.

## Roadmap

- Typed relations from frontmatter keys (`client:`, `project:`, …) → labeled,
  filterable edge kinds.
- 2D mode for reading-oriented sessions.

## License

MIT
