"""Server-side tests: alias parsing, graph building, search. Stdlib only."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import build_graph, parse_aliases, search_vault


class ParseAliases(unittest.TestCase):
    def test_list_form(self):
        self.assertEqual(
            parse_aliases("title: x\naliases:\n  - one\n  - 'two'\nother: y"),
            ["one", "two"],
        )

    def test_inline_form(self):
        self.assertEqual(parse_aliases('aliases: [a, "b c"]'), ["a", "b c"])

    def test_nested_under_metadata(self):
        self.assertEqual(
            parse_aliases("metadata:\n  aliases:\n    - deep\n  type: note"),
            ["deep"],
        )

    def test_absent(self):
        self.assertEqual(parse_aliases("title: x\ntags: [a]"), [])


class BuildGraphTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        (self.vault / "sub").mkdir()
        (self.vault / ".obsidian").mkdir()
        (self.vault / "a.md").write_text(
            "---\naliases: [ay]\n---\nlinks [[b]] and [[ay]] and [[nowhere]]\n"
        )
        (self.vault / "sub" / "b.md").write_text("back to [[ay]]\n")
        (self.vault / ".obsidian" / "skip.md").write_text("[[a]]\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_nodes_exclude_hidden_dirs(self):
        g = build_graph(self.vault)
        self.assertEqual({n["id"] for n in g["nodes"]}, {"a.md", "sub/b.md"})

    def test_types_are_parent_folder(self):
        g = build_graph(self.vault)
        types = {n["id"]: n["type"] for n in g["nodes"]}
        self.assertEqual(types["sub/b.md"], "sub")
        self.assertEqual(types["a.md"], "root")

    def test_alias_links_resolve_and_self_links_drop(self):
        g = build_graph(self.vault)
        links = {(l["source"], l["target"]) for l in g["links"]}
        # [[ay]] in a.md points to a.md itself -> dropped; [[b]] resolves
        self.assertEqual(links, {("a.md", "sub/b.md"), ("sub/b.md", "a.md")})

    def test_aliases_shipped(self):
        g = build_graph(self.vault)
        self.assertEqual(g["aliases"], {"ay": "a.md"})


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        (self.vault / "hit.md").write_text("line one\nthe Needle is here\n")
        (self.vault / "miss.md").write_text("nothing\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_case_insensitive_hit_with_line(self):
        hits = search_vault(self.vault, "needle")["hits"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["path"], "hit.md")
        self.assertEqual(hits[0]["line"], 2)
        self.assertIn("Needle", hits[0]["snippet"])

    def test_no_hit(self):
        self.assertEqual(search_vault(self.vault, "absent")["hits"], [])

    def test_limit(self):
        for i in range(5):
            (self.vault / f"n{i}.md").write_text("needle\n")
        self.assertEqual(len(search_vault(self.vault, "needle", limit=3)["hits"]), 3)


if __name__ == "__main__":
    unittest.main()
