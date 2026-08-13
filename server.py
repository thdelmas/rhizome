#!/usr/bin/env python3
"""Rhizome — local knowledge-base graph explorer.

Serves a 3D force-graph view of a markdown vault. No external requests:
the JS lib is vendored, the graph is parsed live from the vault on each
/graph.json request, everything stays on this machine.

Usage: python3 server.py --vault /path/to/vault [--port N]
"""
import argparse
import csv
import json
import re
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

DEFAULT_VAULT = Path.cwd()
EXCLUDE_DIRS = {".git", ".obsidian", "node_modules"}
NOTION_HEX = re.compile(r"\s+[0-9a-f]{32}$")
WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
MDLINK = re.compile(r"\]\(([^)]+?\.md)\)")
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
CSV_DB = re.compile(r"^(.*?)\s+[0-9a-f]{32}(_all)?$")
CSV_RELPATH = re.compile(r"\(([^()]+?\.md)\)")
ALIAS_KEY = re.compile(r"^\s*aliases:\s*(.*)$")
ALIAS_ITEM = re.compile(r"^\s*-\s+(.+?)\s*$")


def parse_aliases(fm: str):
    """Obsidian-style aliases from frontmatter: inline [a, b] or a - list."""
    aliases = []
    lines = fm.split("\n")
    for i, line in enumerate(lines):
        m = ALIAS_KEY.match(line)
        if not m:
            continue
        inline = m.group(1).strip()
        if inline.startswith("[") and inline.endswith("]"):
            aliases += [a.strip().strip("'\"") for a in inline[1:-1].split(",")]
        else:
            for nxt in lines[i + 1:]:
                lm = ALIAS_ITEM.match(nxt)
                if not lm:
                    break
                aliases.append(lm.group(1).strip("'\""))
    return [a for a in aliases if a]


def csv_edges(vault: Path, ids: set):
    """Typed edges from Notion-export database CSVs, read-only.

    A database exports as '<Name> <32hex>[_all].csv' beside a plain '<Name>/'
    dir holding one .md per row. Relation cells hold 'Title (url%20encoded/path.md)'
    entries; the edge kind is the column name. Nothing in the vault is modified.
    """
    picked = {}
    for p in vault.rglob("*.csv"):
        if any(part in EXCLUDE_DIRS for part in p.relative_to(vault).parts):
            continue
        m = CSV_DB.match(p.stem)
        if not m:
            continue
        key = (str(p.parent), m.group(1))
        if key not in picked or p.stem.endswith("_all"):  # _all holds every row
            picked[key] = p

    links = []
    for (_, base), p in sorted(picked.items()):
        rowdir = p.parent / base
        if not rowdir.is_dir():
            continue
        by_title, dups = {}, set()
        for f in rowdir.glob("*.md"):
            t = NOTION_HEX.sub("", f.stem)
            if t in by_title:
                dups.add(t)
            else:
                by_title[t] = str(f.relative_to(vault))
        for t in dups:
            by_title.pop(t, None)
        try:
            with p.open(encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                if not reader.fieldnames:
                    continue
                title_col = reader.fieldnames[0]
                for row in reader:
                    src = by_title.get((row.get(title_col) or "").strip())
                    if not src:
                        continue
                    for col, cell in row.items():
                        if col == title_col or not cell:
                            continue
                        for pm in CSV_RELPATH.finditer(cell):
                            raw = urllib.parse.unquote(pm.group(1))
                            for anc in [p.parent, *p.parent.parents]:
                                cand = (anc / raw).resolve()
                                try:
                                    tr = str(cand.relative_to(vault.resolve()))
                                except ValueError:
                                    break  # escaped the vault
                                if cand.is_file():
                                    if tr in ids and tr != src:
                                        links.append({"source": src, "target": tr, "kind": col})
                                    break
                                if anc == vault:
                                    break
        except (OSError, csv.Error):
            continue
    return links


def build_graph(vault: Path):
    files = [
        p for p in vault.rglob("*.md")
        if not any(part in EXCLUDE_DIRS for part in p.relative_to(vault).parts)
    ]
    texts = {}
    for p in files:
        try:
            texts[p] = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            texts[p] = ""

    by_stem = {}
    for p in files:
        by_stem.setdefault(p.stem, p)
    # aliases resolve after real stems so a filename always wins over an alias
    aliases = {}
    for p in files:
        fm = FRONTMATTER.match(texts[p])
        if not fm:
            continue
        for a in parse_aliases(fm.group(1)):
            by_stem.setdefault(a, p)
            aliases.setdefault(a, str(p.relative_to(vault)))

    nodes, links = [], []
    ids = set()
    for p in files:
        rel = str(p.relative_to(vault))
        parent = p.parent.relative_to(vault)
        ntype = parent.parts[-1] if parent.parts else "root"
        nodes.append({
            "id": rel,
            "name": NOTION_HEX.sub("", p.stem),
            "type": ntype,
        })
        ids.add(rel)

    for p in files:
        rel = str(p.relative_to(vault))
        text = texts[p]
        targets = set()
        for m in WIKILINK.finditer(text):
            t = by_stem.get(m.group(1).strip())
            if t is not None:
                targets.add(str(t.relative_to(vault)))
        for m in MDLINK.finditer(text):
            raw = urllib.parse.unquote(m.group(1))
            if raw.startswith(("http://", "https://")):
                continue
            resolved = (p.parent / raw).resolve()
            try:
                tr = str(resolved.relative_to(vault.resolve()))
            except ValueError:
                continue
            if tr in ids:
                targets.add(tr)
        targets.discard(rel)
        links.extend({"source": rel, "target": tr} for tr in targets)

    # typed edges from Notion CSVs; on a duplicate pair the typed edge wins
    typed, seen_typed = [], set()
    for l in csv_edges(vault, ids):
        k = (l["source"], l["target"], l["kind"])
        if k not in seen_typed:
            seen_typed.add(k)
            typed.append(l)
    typed_pairs = {(l["source"], l["target"]) for l in typed}
    links = [l for l in links if (l["source"], l["target"]) not in typed_pairs] + typed

    return {"nodes": nodes, "links": links, "aliases": aliases, "vault": vault.name}


def search_vault(vault: Path, query: str, limit: int = 40):
    """Case-insensitive full-text search; first matching line per file."""
    q = query.lower()
    hits = []
    for p in vault.rglob("*.md"):
        if any(part in EXCLUDE_DIRS for part in p.relative_to(vault).parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        idx = text.lower().find(q)
        if idx == -1:
            continue
        start = text.rfind("\n", 0, idx) + 1
        end = text.find("\n", idx)
        line = text[start:end if end != -1 else len(text)].strip()
        if len(line) > 140:
            cut = max(0, idx - start - 40)
            line = ("…" if cut else "") + line[cut:cut + 140] + "…"
        hits.append({
            "path": str(p.relative_to(vault)),
            "line": text.count("\n", 0, idx) + 1,
            "snippet": line,
        })
        if len(hits) >= limit:
            break
    return {"hits": hits}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--port", type=int, default=8321)
    args = ap.parse_args()
    root = Path(__file__).parent

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(root), **kw)

        def send_json(self, obj, status=200):
            payload = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            route = self.path.split("?")[0]
            if route == "/graph.json":
                self.send_json(build_graph(args.vault))
            elif route == "/search":
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                q = qs.get("q", [""])[0].strip()
                self.send_json(search_vault(args.vault, q) if len(q) >= 2 else {"hits": []})
            elif route == "/note":
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                rel = qs.get("path", [""])[0]
                target = (args.vault / rel).resolve()
                vault_root = args.vault.resolve()
                if (
                    not rel.endswith(".md")
                    or not target.is_relative_to(vault_root)
                    or not target.is_file()
                ):
                    self.send_json({"error": "not found"}, 404)
                    return
                self.send_json({
                    "path": rel,
                    "content": target.read_text(encoding="utf-8", errors="ignore"),
                })
            else:
                super().do_GET()

    print(f"rhizome: vault={args.vault}  http://localhost:{args.port}")
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
