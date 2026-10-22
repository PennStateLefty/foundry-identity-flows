import json
from pathlib import Path
import unittest

from identity_lab.catalog import PATTERNS
from identity_lab.evidence import evaluate, extract_probe
from identity_lab.transport import context_headers, require_https, responses_url


class EvidenceTests(unittest.TestCase):
    def test_user_preserved(self):
        self.assertEqual(evaluate("P04", "user", "alpha", "alpha").status, "PASS")

    def test_wrong_identity_fails(self):
        self.assertEqual(evaluate("P04", "user", "alpha", "beta").status, "FAIL")

    def test_expected_negative_is_not_propagation_success(self):
        row = evaluate("P04", "service", "alpha", "service").public()
        self.assertEqual(row["status"], "PASS")
        self.assertEqual(row["observation"], "different-principal")
        self.assertEqual(row["expectation"], "different-principal-or-denial")

    def test_denial_requires_explicit_target_evidence(self):
        self.assertEqual(evaluate("P04", "user", "a", None, denied=True).status, "FAIL")
        self.assertEqual(evaluate("P04", "service", "a", None, denied=True).status, "PASS")

    def test_missing_identity_not_a_negative_pass(self):
        self.assertEqual(evaluate("P04", "drop-context", "a", None).status, "FAIL")

    def test_blocked_not_pass(self):
        self.assertEqual(evaluate("P04", "user", "a", None, blocked=True).status, "BLOCKED")

    def test_no_baseline_rejected(self):
        with self.assertRaises(ValueError):
            evaluate("P01", "user", "", "a")

    def test_public_result_has_no_identifiers(self):
        row = json.dumps(evaluate("P01", "user", "PRIVATE_ALPHA", "PRIVATE_BETA").public())
        self.assertNotIn("PRIVATE_", row)

    def test_nested_probe(self):
        probe = {"kind": "identity-probe-v1", "user_id": "alpha"}
        body = {"output": [{"content": [{"text": json.dumps({"content": [{"text": json.dumps(probe)}]})}]}]}
        self.assertEqual(extract_probe(body), probe)

    def test_ambiguous_or_absent_probe_rejected(self):
        for body in ({}, [{"kind": "identity-probe-v1", "user_id": "a"},
                         {"kind": "identity-probe-v1", "user_id": "b"}]):
            with self.assertRaises(ValueError):
                extract_probe(body)

    def test_mcp_mirrored_results_are_not_ambiguous(self):
        probe = {"kind": "identity-probe-v1", "user_id": "a"}
        self.assertEqual(extract_probe({"content": [{"text": json.dumps(probe)}],
                                      "structuredContent": probe}), probe)

    def test_invalid_identity_type_rejected(self):
        with self.assertRaises(ValueError):
            extract_probe({"kind": "identity-probe-v1", "user_id": {"unexpected": "object"}})


class TransportTests(unittest.TestCase):
    def test_only_call_id_forwarded(self):
        self.assertEqual(context_headers("opaque"), {"x-agent-foundry-call-id": "opaque"})
        self.assertEqual(context_headers("opaque", forward=False), {})
        self.assertEqual(context_headers(None), {})

    def test_invalid_destinations_rejected(self):
        for url in ("http://example.com", "https://u:p@example.com", "https://example.com?token=secret"):
            with self.assertRaises(ValueError):
                require_https(url)

    def test_local_http_opt_in(self):
        self.assertEqual(require_https("http://127.0.0.1:8000", local=True), "http://127.0.0.1:8000")

    def test_agent_path_cannot_escape(self):
        with self.assertRaises(ValueError):
            responses_url("https://example.com", "../other")

    def test_all_patterns_are_documented(self):
        readme = Path("README.md").read_text()
        for pattern in PATTERNS:
            self.assertIn(f"### {pattern}", readme)


if __name__ == "__main__":
    unittest.main()
