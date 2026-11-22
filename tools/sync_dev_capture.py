"""Integrate the authoritative workspace Git capture without touching unrelated files."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys

from bootstrap_fabric_items import MARKER
from common import ContextError, ROOT, load_config

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config


def files(folder: Path) -> dict[str, Path]:
    result = {}
    for path in folder.rglob("*"):
        relative = path.relative_to(folder)
        if ".pbi" in relative.parts:
            continue
        if path.is_symlink():
            raise ContextError("A symlink in captured source is not supported.")
        if path.is_file():
            result[relative.as_posix()] = path
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = load_config()
    stage = config["environments"]["dev"]
    if not stage.get("git_capture_commit"):
        raise ContextError("A verified workspace Git capture is required.")
    source = args.source.resolve()
    expected = set(stage["items"])
    captured = {}
    for folder in source.iterdir():
        if not folder.is_dir():
            continue
        metadata = json.loads((folder / ".platform").read_text(encoding="utf-8"))
        name = metadata["metadata"]["displayName"]
        if name not in expected or name in captured:
            raise ContextError("Unexpected or duplicate captured item.")
        captured[name] = (folder, metadata)
    if set(captured) != expected:
        raise ContextError("Captured folders do not contain all 11 configured Dev items.")
    plans = []
    for name, (folder, metadata) in captured.items():
        destination = ROOT / "fabric" / folder.name
        local = files(destination) if destination.exists() else {}
        if local:
            marker = local.get(".platform")
            platform = json.loads(marker.read_text(encoding="utf-8")) if marker else {}
            tracked_capture = bool(stage["items"][name].get("local_files")) and \
                platform.get("config", {}).get("logicalId") == stage["items"][name].get("logical_id")
            if not marker or not (
                    (platform.get("metadata", {}).get("description") or "").startswith(MARKER) or tracked_capture):
                raise ContextError(f"Local {name} is not automation-owned.")
            for relative, digest in stage["items"][name].get("local_files", {}).items():
                if relative not in local or sha256(local[relative].read_bytes()).hexdigest() != digest:
                    raise ContextError(f"Local {name} changed outside automation: {relative}.")
        incoming = files(folder)
        known = set(stage["items"][name].get("local_files", {}))
        for relative in set(local) - set(incoming):
            if relative not in known and not (relative == ".platform" or
                                             relative == "notebook-content.py" or
                                             relative.endswith(".tmdl")):
                raise ContextError(f"Untracked extra source in {name}: {relative}; not deleted.")
        plans.append((name, destination, local, incoming, metadata))
    if args.dry_run:
        print(f"DRY-RUN: synchronize {len(plans)} known item folders; preserve .pbi and unrelated paths.")
        return
    for name, destination, local, incoming, metadata in plans:
        for relative in set(local) - set(incoming):
            local[relative].unlink()
        for relative, path in incoming.items():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != path.read_bytes():
                shutil.copyfile(path, target)
        stage["items"][name]["logical_id"] = metadata["config"]["logicalId"]
        stage["items"][name]["local_files"] = {
            relative: sha256(path.read_bytes()).hexdigest() for relative, path in incoming.items()}
    stage["items"]["DA_Sales"]["ontology_context_pending"] = False
    stage["items"]["DA_Sales"]["ontology_context_user_confirmed"] = True
    save_config(config)
    record(f"Step 5 source capture integrated: all 11 item folders from Git commit "
           f"`{stage['git_capture_commit']}`, actual logical IDs and opaque user-authored "
           "model/ontology/agent state preserved. No unrelated paths or preview caches touched.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, OSError, ValueError) as error:
        record(f"Workspace source integration blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
