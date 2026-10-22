from pathlib import Path
import re
import unittest


class DocumentationTests(unittest.TestCase):
    def test_nine_diagram_first_patterns_and_short_steps(self):
        readme = Path("README.md").read_text()
        sections = re.split(r"(?m)^### P[0-9]{2} ", readme)[1:]
        self.assertEqual(len(sections), 9)
        for section in sections:
            first_body = section.split("\n", 1)[1].lstrip()
            self.assertTrue(first_body.startswith("```mermaid\nsequenceDiagram"))
            for step in re.findall(r"(?m)^[0-9]+\. (.+)$", section):
                self.assertLessEqual(len(step.split()), 20, step)

    def test_local_markdown_links_resolve(self):
        documents = list(Path("docs").glob("*.md")) + [Path("README.md"), Path("PUBLICATION.md")]
        for document in documents:
            for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
                if "://" in target or target.startswith("#"):
                    continue
                path = (document.parent / target.split("#")[0]).resolve()
                self.assertTrue(path.is_file(), f"{document}: {target}")

    def test_initial_manifest_has_all_42_not_run_observations(self):
        import json
        manifest = json.loads(Path("results/latest.json").read_text())
        rows = manifest["results"]
        self.assertEqual(len(rows), 42)
        combinations = {(row["alias"], row["pattern"], row["configuration"]) for row in rows}
        self.assertEqual(len(combinations), 42)
        self.assertTrue(all(row["status"] in ("NOT RUN", "PASS", "FAIL", "BLOCKED") for row in rows))
