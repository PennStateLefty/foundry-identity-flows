"""Render an ignored image-pinned manifest for azd versions validating raw image fields."""

import argparse
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent


def render(image: str, output: Path):
    if not re.fullmatch(r"[a-z0-9.-]+(?::[0-9]+)?/[a-z0-9._/-]+@sha256:[0-9a-f]{64}", image):
        raise ValueError("A fully qualified, immutable registry image digest is required.")
    root = ROOT.resolve()
    output = output.resolve()
    if not output.is_relative_to((root / ".local").resolve()):
        raise ValueError("The rendered manifest must remain in the ignored .local directory.")
    template = (root / "agents/azure.yaml").read_text()
    if template.count("${LAB_HOSTED_IMAGE}") != 2 or template.count("    project: .\n") != 2:
        raise ValueError("Review the updated agent template before rendering it.")
    template = template.replace("${LAB_HOSTED_IMAGE}", image)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(template)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / ".local/agents/azure.yaml")
    args = parser.parse_args()
    render(os.environ["LAB_HOSTED_IMAGE"], args.output)
    print("Rendered the private, image-pinned agent manifest; no Azure changes were made.")


if __name__ == "__main__":
    main()
