import tempfile
import unittest

from praxis.commands.vector_common import chunk_text
from praxis.intake.registry import convert_bytes


def capture(markup):
    return convert_bytes("specs.html", markup.encode(), media_type="text/html")


class TableCapture(unittest.TestCase):
    def test_late_spec_retains_headers_in_searchable_chunk(self):
        rows = "".join(f"<tr><td>Example aircraft {i}</td><td>9.80</td><td>3.72</td></tr>"
                       for i in range(150))
        result = capture("<h2>Fleet</h2><table><tr><th>Model</th><th>Length (m)</th>"
                         "<th>Span (m)</th></tr>" + rows +
                         "<tr><td>Target-017</td><td>19.43</td><td>11.20</td></tr></table>")
        chunks = chunk_text(result.text, path="fixture.raw.txt")
        targets = [c["text"] for c in chunks if "Target-017" in c["text"]]
        self.assertTrue(any("Length (m)" in t and "Span (m)" in t for t in targets))
        self.assertTrue(any("Length (m): 19.43" in t and "Span (m): 11.20" in t for t in targets))

    def test_infobox_and_prose(self):
        result = capture("<p>Before</p><h2>X-1</h2><table><tr><td colspan='2'>Photo</td></tr>"
                         "<tr><th colspan='2'>History</th></tr>"
                         "<tr><th>First flight</th><td>19 <b>January</b> 1946</td></tr></table><p>After</p>")
        row, = [u for u in result.units if u.unit_type == "table_row"]
        self.assertIn("First flight: 19 January 1946", row.text)
        self.assertIn("X-1", row.text)
        self.assertLess(result.text.index("Before"), result.text.index(row.text))
        self.assertLess(result.text.index(row.text), result.text.index("After"))

    def test_search_serves_labeled_row_from_capture(self):
        from tests.test_release_hardening import make_root, run_praxis

        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp)
            path = root / "specs.html"
            path.write_text("<table><caption>Fleet</caption><tr><th>Model</th><th>Length (m)</th></tr>"
                            "<tr><td>Target-017</td><td>19.43</td></tr></table>")
            run_praxis(root, "capture", str(path))
            raw, = (root / "workspace/research/captures").rglob("*.raw.txt")
            run_praxis(root, "chunk", "--file", str(raw))
            run_praxis(root, "embed", "--provider", "local-hash")
            result = run_praxis(root, "search", "Target-017 length", "--show-text", "--limit", "1")
            self.assertIn("Fleet; Model: Target-017; Length (m): 19.43", result.stdout)

    def test_ambiguous_table_preserves_text_without_claims(self):
        for markup in ("<table><tr><td rowspan='2'>A</td><td>3</td></tr></table>",
                       "<table><tr><th>Outer</th><td><table><tr><th>A</th><td>3</td></tr></table></td></tr></table>"):
            result = capture(markup)
            self.assertIn("3", result.text)
            self.assertNotIn("table_row", result.unit_counts)
            self.assertTrue(result.warnings)
