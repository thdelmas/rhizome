#!/usr/bin/env python3
"""Rhizome — local knowledge-base graph explorer.

Serves a 3D force-graph view of a markdown vault. No external requests:
the JS lib is vendored, the graph is parsed live from the vault on each
/graph.json request, everything stays on this machine.

Usage: python3 server.py --vault /path/to/vault [--port N]
"""
import argparse
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


def build_graph(vault: Path):
    files = [
        p for p in vault.rglob("*.md")
        if not any(part in EXCLUDE_DIRS for part in p.relative_to(vault).parts)
    ]
    by_stem = {}
    for p in files:
        by_stem.setdefault(p.stem, p)

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
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
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

    return {"nodes": nodes, "links": links, "vault": vault.name}


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
