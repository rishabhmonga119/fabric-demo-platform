"""Generate validated Python-cleaning and PySpark-integration Git notebook sources."""

import argparse
import json
from uuid import NAMESPACE_URL, uuid5

import nbformat
import yaml

from common import ContextError, ROOT, load_config


def notebooks(config: dict) -> dict:
    mappings = yaml.safe_load((ROOT / "config" / "mappings.yml").read_text(encoding="utf-8"))
    actors = [config["tenant"]["admin_object_id"],
              config["entra"]["application"]["service_principal_id"],
              config["entra"]["application"]["client_id"]]
    parameters = "\n".join([
        "stage = 'dev'",
        "expected_tenant = " + repr(config["tenant"]["id"]),
        "allowed_actors = " + repr(actors),
        "mappings = " + repr(mappings),
    ]) + "\n"
    logic = (ROOT / "tools" / "forecast_logic.py").read_text(encoding="utf-8")
    runtime = (ROOT / "tools" / "fabric_notebook_runtime.py").read_text(encoding="utf-8")
    outputs = {}
    for name, lakehouse, execution_file in (
        ("NB_Clean_Forecast", "LH_Landing", "fabric_clean_forecast_cell.py"),
        ("NB_Integrate", "LH_Curated", "fabric_integrate_cell.py"),
    ):
        binding = config["environments"]["dev"]["items"][lakehouse]["id"]
        is_spark = name == "NB_Integrate"
        metadata = {
            "kernel_info": {"name": "synapse_pyspark"} if is_spark else
                {"name": "jupyter", "jupyter_kernel_name": "python3.11"},
            "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark", "language": "python"} if is_spark else
                {"name": "python3.11", "display_name": "Python 3.11", "language": "python"},
            "language_info": {"name": "python"},
            "dependencies": {"lakehouse": {
                "default_lakehouse": binding, "default_lakehouse_name": lakehouse,
                "default_lakehouse_workspace_id": config["environments"]["dev"]["workspace_id"],
            }},
        }
        cells = []
        execution = (ROOT / "tools" / execution_file).read_text(encoding="utf-8")
        sources = (parameters, execution) if is_spark else (parameters, logic, runtime, execution)
        for index, code in enumerate(sources):
            cell = nbformat.v4.new_code_cell(code, id=uuid5(NAMESPACE_URL, f"{name}/{index}").hex[:12])
            cell.metadata.update({"language": "python",
                                  "language_group": "synapse_pyspark" if is_spark else "jupyter_python"})
            if index == 0:
                cell.metadata["tags"] = ["parameters"]
            cells.append(cell)
        notebook = nbformat.v4.new_notebook(cells=cells, metadata=metadata)
        nbformat.validate(notebook)
        outputs[name] = notebook
    return outputs


def git_source(notebook) -> str:
    lines = ["# Fabric notebook source", "", "# METADATA ********************"]
    lines.extend("# META " + line for line in json.dumps(dict(notebook.metadata), indent=2).splitlines())
    for cell in notebook.cells:
        marker = "# PARAMETERS CELL ********************" if "parameters" in cell.metadata.get("tags", []) \
            else "# CELL ********************"
        lines.extend(["", marker, "", cell.source.rstrip(), "", "# METADATA ********************"])
        lines.extend("# META " + line for line in json.dumps(dict(cell.metadata), indent=2).splitlines())
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = load_config()
    for name, notebook in notebooks(config).items():
        folder = ROOT / "fabric" / f"{name}.Notebook"
        platform = {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "Notebook", "displayName": name,
                         "description": "Managed by fabric-demo-platform demo automation: " +
                             ("Spark SQL join and PySpark Delta write; default starter pool." if name == "NB_Integrate"
                              else "pure Python forecast cleaning.")},
            "config": {"version": "2.0", "logicalId": str(uuid5(NAMESPACE_URL, "fabric-demo-platform/" + name))},
        }
        files = {"notebook-content.py": git_source(notebook),
                 ".platform": json.dumps(platform, indent=2) + "\n"}
        if folder.exists():
            marker = folder / ".platform"
            if not marker.exists() or not json.loads(marker.read_text(encoding="utf-8"))["metadata"]["description"].startswith(
                    "Managed by fabric-demo-platform demo automation"):
                raise ContextError(f"Refusing to overwrite unowned local notebook folder {name}.")
        print(f"{'DRY-RUN: ' if args.dry_run else ''}Generate valid {name}: {notebook.metadata['kernel_info']['name']}")
        if not args.dry_run:
            folder.mkdir(parents=True, exist_ok=True)
            for filename, content in files.items():
                path = folder / filename
                if not path.exists() or path.read_text(encoding="utf-8") != content:
                    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
