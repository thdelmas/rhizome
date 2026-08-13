"""Server-side tests: alias parsing, graph building, search. Stdlib only."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import build_graph, csv_edges, parse_aliases, search_vault


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


class CsvEdgesTest(unittest.TestCase):
    HEX = "a" * 32

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        works = self.vault / "Works"
        (works / "Tasks").mkdir(parents=True)
        (works / "Projects").mkdir()
        (works / "Tasks" / f"My Task {self.HEX}.md").write_text("body\n")
        (works / "Projects" / f"Proj X {self.HEX}.md").write_text("body\n")
        # _all.csv preferred over the plain twin, which here is a decoy subset
        (works / f"Tasks {self.HEX}.csv").write_text("Task name,Project\n")
        (works / f"Tasks {self.HEX}_all.csv").write_text(
            "Task name,Project\n"
            f'My Task,Proj X (Works/Projects/Proj%20X%20{self.HEX}.md)\n'
        )

    def tearDown(self):
        self.tmp.cleanup()

    def ids(self):
        return {
            f"Works/Tasks/My Task {self.HEX}.md",
            f"Works/Projects/Proj X {self.HEX}.md",
        }

    def test_typed_edge_from_relation_column(self):
        links = csv_edges(self.vault, self.ids())
        self.assertEqual(links, [{
            "source": f"Works/Tasks/My Task {self.HEX}.md",
            "target": f"Works/Projects/Proj X {self.HEX}.md",
            "kind": "Project",
        }])

    def test_traversal_paths_ignored(self):
        (self.vault / "Works" / f"Evil {self.HEX}_all.csv").write_text(
            "Name,Rel\nMy Task,x (../../../etc/passwd.md)\n"
        )
        (self.vault / "Works" / "Evil").mkdir()
        for l in csv_edges(self.vault, self.ids()):
            self.assertFalse(l["target"].startswith(".."))

    def test_build_graph_merges_typed_over_prose(self):
        # prose wikilink between the same pair: typed edge must win, no dup
        (self.vault / "Works" / "Tasks" / f"My Task {self.HEX}.md").write_text(
            f"[[Proj X {self.HEX}]]\n"
        )
        g = build_graph(self.vault)
        pairs = [(l["source"], l["target"]) for l in g["links"]]
        self.assertEqual(len(pairs), len(set(pairs)))
        typed = [l for l in g["links"] if l.get("kind")]
        self.assertEqual(len(typed), 1)


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
