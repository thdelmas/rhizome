// Client-side tests for the inline-script functions, extracted from index.html.
// Run: node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const html = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "index.html"), "utf8");
// NOTE: the first </script> in the file is the vendor tag — always slice with lastIndexOf.
const escLine = html.split("\n").find(l => l.startsWith("function esc"));
const renderPart = html.slice(html.indexOf("// Minimal markdown renderer"), html.lastIndexOf("</script>"));

// minimal DOM stub for esc()
const escStub = `const document = { createElement: () => ({
  set textContent(v) { this._v = String(v); },
  get innerHTML() { return this._v.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); },
}) };\n`;

const harness = new Function("byStem", escStub + escLine + "\n" + renderPart + "\nreturn { renderMd, inline };");
const { renderMd } = harness(new Map([["target-note", "notes/target-note.md"]]));

test("GFM table renders with wikilinks and escaping in cells", () => {
  const out = renderMd("| a | b |\n|---|---|\n| <x> | [[target-note]] |\n");
  assert.ok(out.includes("<table><thead><tr><th>a</th><th>b</th></tr></thead><tbody>"));
  assert.ok(out.includes("&lt;x&gt;"));
  assert.ok(out.includes('data-id="notes/target-note.md"'));
});

test("pipe row without separator is not a table", () => {
  assert.ok(!renderMd("| not | a table |\n").includes("<table>"));
});

test("bold tolerates nested italics", () => {
  assert.ok(renderMd("**Own your *tools* now**\n").includes("<b>Own your <i>tools</i> now</b>"));
});

test("bold spans hard-wrapped paragraph lines", () => {
  assert.ok(renderMd("**start of bold\nend of bold** tail\n").includes("<b>start of bold end of bold</b>"));
});

test("bold spans hard-wrapped blockquote lines", () => {
  const out = renderMd("> **Own your tools,\n> your data.** Rest.\n");
  assert.ok(out.includes("<p><b>Own your tools, your data.</b> Rest.</p>"));
  assert.ok(out.includes("<blockquote>") && out.includes("</blockquote>"));
});

test("blank quote line splits blockquote paragraphs", () => {
  const out = renderMd("> one\n>\n> two\n");
  assert.ok(out.includes("<p>one</p>") && out.includes("<p>two</p>"));
});

test("unresolved wikilink is dead", () => {
  assert.ok(renderMd("[[missing]]\n").includes('class="dead"'));
});

// ---- geometry builders ----
const geo = new Function(html.slice(html.indexOf("function face"), html.indexOf("function geomFor")) + "\nreturn SHAPE_BUILDERS;");
const SHAPE_BUILDERS = geo();

test("polyhedra: finite, whole triangles, outward faces", () => {
  const expectTris = { 1: 12, 2: 8, 3: 4, 4: 20, 5: 6, 6: 36, 7: 8 };
  for (let s = 1; s < SHAPE_BUILDERS.length; s++) {
    const arr = [];
    SHAPE_BUILDERS[s](arr);
    assert.equal(arr.length % 9, 0, `shape ${s} fractured`);
    assert.equal(arr.length / 9, expectTris[s], `shape ${s} triangle count`);
    for (let i = 0; i < arr.length; i += 9) {
      const a = arr.slice(i, i + 3), b = arr.slice(i + 3, i + 6), c = arr.slice(i + 6, i + 9);
      assert.ok([...a, ...b, ...c].every(Number.isFinite), `shape ${s} NaN`);
      const u = [b[0]-a[0], b[1]-a[1], b[2]-a[2]], w = [c[0]-a[0], c[1]-a[1], c[2]-a[2]];
      const n = [u[1]*w[2]-u[2]*w[1], u[2]*w[0]-u[0]*w[2], u[0]*w[1]-u[1]*w[0]];
      const ctr = [(a[0]+b[0]+c[0])/3, (a[1]+b[1]+c[1])/3, (a[2]+b[2]+c[2])/3];
      assert.ok(n[0]*ctr[0] + n[1]*ctr[1] + n[2]*ctr[2] >= 0, `shape ${s} inward face`);
    }
  }
});
