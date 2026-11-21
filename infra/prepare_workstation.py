"""Install local tooling; no cloud resources or authentication are changed."""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import venv
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = ROOT / ".venv"
DATABRICKS_VERSION = "1.27.0"
DATABRICKS_URL = (
    "https://github.com/databricks/cli/releases/download/v1.27.0/"
    "databricks_cli_1.27.0_windows_amd64.zip"
)
DATABRICKS_SHA256 = "335cf6b28397eb0b45880a9abf86c7016210ff6e40276fb82a7d855055a0e590"


def install_databricks(scripts: Path, dry_run: bool) -> None:
    # Official release: https://github.com/databricks/cli/releases/tag/v1.27.0
    executable = scripts / "databricks.exe"
    if os.name != "nt":
        raise RuntimeError("This workstation installer targets Windows.")
    if executable.exists():
        result = subprocess.run(
            [str(executable), "--version"], check=True, capture_output=True, text=True
        )
        if result.stdout.strip() != f"Databricks CLI v{DATABRICKS_VERSION}":
            raise RuntimeError(f"Unexpected existing Databricks CLI: {result.stdout.strip()}")
        print(result.stdout.strip())
        return
    print(f"Install Databricks CLI v{DATABRICKS_VERSION} locally from {DATABRICKS_URL}")
    if dry_run:
        return
    with tempfile.TemporaryDirectory(prefix="demo-databricks-") as directory:
        archive = Path(directory) / "databricks.zip"
        with urllib.request.urlopen(DATABRICKS_URL, timeout=120) as response:
            with archive.open("wb") as target:
                shutil.copyfileobj(response, target)
        with archive.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest != DATABRICKS_SHA256:
            raise RuntimeError("Official Databricks archive checksum mismatch.")
        with zipfile.ZipFile(archive) as package:
            entries = [
                entry for entry in package.infolist()
                if Path(entry.filename).name == "databricks.exe"
            ]
            if len(entries) != 1:
                raise RuntimeError("Official archive must contain exactly one databricks.exe.")
            with package.open(entries[0]) as source, executable.open("xb") as target:
                shutil.copyfileobj(source, target)
    subprocess.run([str(executable), "--version"], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required.")

    scripts = ENVIRONMENT / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    if not python.exists():
        print(f"Create repository-local virtual environment: {ENVIRONMENT}")
        if not args.dry_run:
            venv.EnvBuilder(with_pip=True).create(ENVIRONMENT)

    command = [
        str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")
    ]
    print(subprocess.list2cmdline(command))
    if not args.dry_run:
        subprocess.run(command, cwd=ROOT, check=True)
        subprocess.run([str(python), "-m", "pip", "check"], cwd=ROOT, check=True)
    install_databricks(scripts, args.dry_run)


if __name__ == "__main__":
    main()
