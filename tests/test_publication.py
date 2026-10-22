import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("check_public", Path("scripts/check_public.py"))
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class PublicationTests(unittest.TestCase):
    def test_identifiers_detected_without_storing_real_identifiers(self):
        identifier = "-".join(["a" * 8, "b" * 4, "c" * 4, "d" * 4, "e" * 12])
        self.assertIsNotNone(scanner.GUID.search(identifier))

    def test_placeholders_allowed(self):
        self.assertIsNone(scanner.ENDPOINT.search("https://<account>.services.ai.azure.com"))

    def test_real_shaped_endpoints_rejected(self):
        self.assertIsNotNone(scanner.ENDPOINT.search("https://" + "private-account" + ".services.ai.azure.com"))

    def test_runtime_path_rejected(self):
        self.assertEqual(scanner.inspect(scanner.ROOT / ".local/config.json"), ["runtime-file"])

    def test_not_run_manifest_is_allowlisted(self):
        self.assertEqual(scanner.inspect(scanner.ROOT / "results/latest.json"), [])

    def test_additional_evidence_fields_rejected(self):
        with tempfile.TemporaryDirectory(dir=scanner.ROOT / "results") as directory:
            path = Path(directory) / "test.json"
            path.write_text(json.dumps({"schema": 1, "results": [{"secret": "unexpected"}]}))
            self.assertIn("non-allowlisted-evidence", scanner.inspect(path))


if __name__ == "__main__":
    unittest.main()
