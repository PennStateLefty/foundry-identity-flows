"""Reject likely identifiers, credentials, runtime files, and unsafe result fields."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
GUID = re.compile(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b")
TOKEN = re.compile(r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}")
ENDPOINT = re.compile(r"https://(?!<)[a-zA-Z0-9-]+\.(?:services\.ai\.azure\.com|azurecontainerapps\.io|azurecr\.io)")
SECRET = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")
RUNTIME = {".local", ".azure", ".venv", ".git", "__pycache__", "build", "dist"}
RESULT_KEYS = {"alias", "pattern", "configuration", "status", "reason", "observation", "expectation"}
RESULT_VALUES = {
    "alias": {"user-a", "user-b"},
    "pattern": {f"P{n:02}" for n in range(1, 10)},
    "configuration": {"user", "service", "drop-context"},
    "status": {"PASS", "FAIL", "BLOCKED", "NOT RUN"},
    "reason": {"prerequisite", "authorization-denied", "identity-missing", "user-preserved",
               "identity-changed", "http-error", "probe-unavailable", "cross-user-collision", "not-run"},
    "observation": {"unavailable", "denied", "missing", "same-user", "different-principal"},
    "expectation": {"preserve-user", "different-principal-or-denial"},
}


def inspect(path: Path, content: str | None = None) -> list[str]:
    relative = path.relative_to(ROOT)
    if set(relative.parts) & RUNTIME or any(p.startswith(".venv-") for p in relative.parts):
        return ["runtime-file"]
    if path.is_symlink():
        return ["symlink"]
    if path.suffix in {".pem", ".pfx", ".key", ".log"} or (
        path.name.startswith(".env") and path.name != ".env.example"
    ):
        return ["runtime-file"]
    try:
        text = path.read_text() if content is None else content
    except (UnicodeDecodeError, OSError):
        return ["non-text-file"]
    failures = []
    for name, pattern in (("identifier", GUID), ("jwt", TOKEN), ("real-endpoint", ENDPOINT), ("credential", SECRET)):
        if pattern.search(str(relative) + "\n" + text):
            failures.append(name)
    if relative.parts[0] == "results" and path.suffix == ".json":
        try:
            data = json.loads(text)
            if set(data) != {"schema", "results"} or data["schema"] != 1:
                raise ValueError
            for row in data["results"]:
                if set(row) != RESULT_KEYS:
                    raise ValueError
                if any(value not in RESULT_VALUES[key] for key, value in row.items()):
                    raise ValueError
        except (ValueError, TypeError, KeyError):
            failures.append("non-allowlisted-evidence")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true", help="Inspect the exact index contents, not working files.")
    args = parser.parse_args()
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=False,
    )
    if tracked.returncode == 0 and tracked.stdout:
        paths = [ROOT / p.decode() for p in tracked.stdout.split(b"\0") if p]
    else:
        paths = [
            p for p in ROOT.rglob("*")
            if p.is_file() and not set(p.relative_to(ROOT).parts) & RUNTIME
            and not any(part.startswith(".venv-") or part.endswith(".egg-info") for part in p.parts)
        ]
    failures = []
    for path in paths:
        if args.staged:
            blob = subprocess.run(["git", "show", f":{path.relative_to(ROOT)}"], cwd=ROOT, capture_output=True, check=True)
            try:
                reasons = inspect(path, blob.stdout.decode())
            except UnicodeDecodeError:
                reasons = ["non-text-file"]
        else:
            reasons = inspect(path) if path.exists() else ["missing-file"]
        failures.append((str(path.relative_to(ROOT)), reasons))
    failures = [(path, reasons) for path, reasons in failures if reasons]
    for path, reasons in failures:
        print(f"{path}: {', '.join(reasons)}")
    print(f"Publication check: {'FAIL' if failures else 'PASS'} ({len(paths)} files)")
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
