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
- **Type legend as filter** — node type = parent folder; the top 24 types get a
  shape × color encoding (8 CVD-validated hues × 8 node shapes), the rest fold
  into "Other"; chips toggle visibility.
- **Orphans chip** — isolate unlinked notes for cleanup.
- **Reader panel** — self-contained markdown rendering (incl. GFM tables);
  wikilinks inside a note navigate the graph; a "Linked from" backlinks list
  under each note; "Open in Obsidian" jumps to the file.
- **Search** — instant name matches plus full-text hits from the vault —
  and `?open=path/to/note.md` deep links.
- Frontmatter `aliases:` resolve in both graph edges and the reader.
- Notion-export friendly: trailing 32-hex IDs are stripped from display names.

## Run

```
python3 server.py --vault /path/to/vault        # default port 8321
```

Open http://localhost:8321

No dependencies beyond Python 3.9+ stdlib.

To survive reboots, install it as a systemd user service —
`~/.config/systemd/user/rhizome.service`:

```ini
[Unit]
Description=Rhizome KB graph explorer

[Service]
ExecStart=/usr/bin/python3 /path/to/rhizome/server.py --vault /path/to/vault
WorkingDirectory=/path/to/rhizome
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

```
systemctl --user daemon-reload && systemctl --user enable --now rhizome
loginctl enable-linger        # start at boot, not first login
```

## Tests

```
python3 -m unittest discover -s tests
node --test tests/
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
