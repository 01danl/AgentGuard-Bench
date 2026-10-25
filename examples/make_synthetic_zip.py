"""Build a demonstrative Harness-layout archive from synthetic fixtures only."""

import argparse
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    # Exclusive creation avoids overwriting an existing artifact.
    with zipfile.ZipFile(args.output, "x", zipfile.ZIP_DEFLATED) as archive:
        archive.write(fixtures / "synthetic-ignored.jsonl", "session.v4.jsonl")
        archive.write(
            fixtures / "synthetic-changed.jsonl", "subagents/synthetic-changed/session.v4.jsonl"
        )
        archive.writestr("files/aa/synthetic/attachment.jsonl", "Synthetic attachment, not a log.")
    print(args.output)


if __name__ == "__main__":
    main()
