"""Commit explicitly selected step files and verify the pushed main branch."""

import argparse
import sys

from common import ContextError, ROOT, cli, load_config, mutate, run, verify_context


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", type=int, choices=range(10), required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--paths", nargs="+", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    verify_context()
    config = load_config()["github"]
    git = cli("git")
    if run([git, "branch", "--show-current"]).strip() != config["branch"]:
        raise ContextError("Current branch is not the configured main branch.")
    expected = f"https://github.com/{config['owner']}/{config['repository']}.git"
    if run([git, "remote", "get-url", "--push", "origin"]).strip() != expected:
        raise ContextError("Git push remote differs from the expected demo repository.")
    if run([git, "diff", "--cached", "--name-only"]).strip():
        raise ContextError("Pre-existing staged changes must not be included in this step.")
    for path in args.paths:
        resolved = (ROOT / path).resolve()
        if not resolved.is_relative_to(ROOT) or resolved == ROOT:
            parser.error(f"Only explicit repository files/subdirectories may be staged: {path}")
    mutate([git, "add", "--", *args.paths], args.dry_run)
    message = (
        f"step {args.step}: {args.message}\n\n"
        "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
    )
    mutate([git, "commit", "-m", message], args.dry_run)
    mutate([git, "push", "origin", config["branch"]], args.dry_run)
    if not args.dry_run:
        local = run([git, "rev-parse", "HEAD"]).strip()
        remote = run([git, "ls-remote", "origin", f"refs/heads/{config['branch']}"]).split()
        if len(remote) != 2 or remote[0] != local:
            raise ContextError("Push verification failed: remote main does not match local HEAD.")
        print(f"Remote main verification: PASS ({local})")


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
