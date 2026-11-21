"""Verify Azure, Fabric and GitHub identities without changing resources."""

import argparse
import sys

from common import ContextError, verify_context


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Checks are always read-only.")
    parser.parse_args()
    try:
        verify_context()
    except ContextError as error:
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
