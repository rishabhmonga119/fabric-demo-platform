"""Generate the approved two-page Sales PBIR from the official CLI shell."""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sys
import tempfile
from uuid import NAMESPACE_URL, uuid5

import yaml

from bootstrap_fabric_items import MARKER
from common import ContextError, ROOT, cli, load_config, run

sys.path.insert(0, str(ROOT))
from infra.deploy import record, save_config

VISUAL_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.9.0/schema.json"
REFERENCES = ("powerbi-report-cli/references/authoring-part-02.md; "
              "authoring/authoring-workflows.md; cartesian.md; table.md; slicers.md; "
              "card.md; card-part-02.md; textbox.md; theming.md")


def literal(value: str | bool | int | float) -> dict:
    if isinstance(value, bool):
        text = str(value).lower()
    elif isinstance(value, int):
        text = f"{value}D"
    elif isinstance(value, float):
        text = f"{value}D"
    else:
        text = "'" + value.replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": text}}}


def color(value: str) -> dict:
    return {"solid": {"color": literal(value)}}


def properties(values: dict, selector: dict | None = None) -> list:
    entry = {"properties": values}
    if selector:
        entry["selector"] = selector
    return [entry]


def field(binding: str, measure: bool) -> dict:
    table, name = binding.rstrip("]").split("[", 1)
    kind = "Measure" if measure else "Column"
    return {kind: {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def projection(binding: str, measure: bool) -> dict:
    table, name = binding.rstrip("]").split("[", 1)
    return {"field": field(binding, measure), "queryRef": f"{table}.{name}",
            "nativeQueryRef": name}


def position(layout: dict, placement: dict, order: int) -> dict:
    canvas, grid = layout["canvas"], layout["grid"]
    width, height, margin, gutter = (canvas[key] for key in ("width", "height", "margin", "gutter"))
    col1, row1, col2, row2 = grid["regions"][placement["region"]]
    cell_width = (width - 2 * margin) / grid["columns"]
    # Reserve enough height for the required 80px dropdown chrome and a gutter.
    header = max((height - 2 * margin) / grid["rows"], 80 + gutter)
    cell_height = (height - 2 * margin - header) / (grid["rows"] - 1)
    boundary = lambda row: margin if row == 1 else margin + header + (row - 2) * cell_height
    x = margin + (col1 - 1) * cell_width
    y = boundary(row1)
    w, h = (col2 - col1) * cell_width - gutter, boundary(row2) - y - gutter
    if "slot" in placement:
        count = placement["of"]
        slot_width = (w - (count - 1) * gutter) / count
        x += (placement["slot"] - 1) * (slot_width + gutter)
        w = slot_width
    snap = canvas["snap"]
    return {"x": round(x / snap) * snap, "y": round(y / snap) * snap,
            "width": math.floor(w / snap) * snap, "height": math.floor(h / snap) * snap,
            "z": order * 1000, "tabOrder": order * 1000}


def make_visual(page: dict, placement: dict, order: int, colors: dict) -> dict:
    kind = placement["kind"]
    name = sha256(f"RPT_Sales/{page['name']}/{placement['id']}".encode()).hexdigest()[:20]
    geometry = position(page["layout_contract"], placement, order)
    vco = {
        "title": properties({"show": literal(False)}),
        "visualHeader": properties({"show": literal(False)}),
        "general": properties({"altText": literal(placement.get("purpose", placement.get("text", "")))}),
        "background": properties({"show": literal(True), "color": color("#FFFFFF"),
                                  "transparency": literal(0)}),
        "padding": properties({side: literal(8) for side in ("top", "bottom", "left", "right")}),
    }
    visual = {"visualType": kind, "visualContainerObjects": vco}
    if kind == "textbox":
        text = placement["text"]
        size = 32 if placement["id"] == "page_title" else 22
        visual["objects"] = {"general": properties({"paragraphs": [{
            "textRuns": [{"value": text, "textStyle": {
                "fontFamily": "Segoe UI Semibold" if placement["id"] == "page_title" else "Segoe UI",
                "fontSize": f"{size}px", "color": "#172B4D"}}],
            "horizontalTextAlignment": "left"}]})}
        vco["background"] = properties({"show": literal(False)})
        vco["border"] = properties({"show": literal(False)})
        vco["padding"] = properties({side: literal(0) for side in ("top", "bottom", "left", "right")})
    elif kind == "pageNavigator":
        vco["background"] = properties({"show": literal(False)})
        vco["border"] = properties({"show": literal(False)})
    else:
        bindings = placement["field_bindings"]
        if kind == "cardVisual":
            roles = {"Data": [bindings]}
        elif kind == "slicer":
            roles = {"Values": [bindings]}
        else:
            roles = {role: values if isinstance(values, list) else [values]
                     for role, values in bindings.items()}
        visual["query"] = {"queryState": {
            role: {"projections": [projection(value, role in ("Y", "Data") or
                                             role == "Values" and kind != "slicer")
                                   for value in values]}
            for role, values in roles.items()}}
        if kind in ("lineChart", "barChart", "pivotTable"):
            sort_binding = bindings["Y"] if kind == "barChart" else \
                bindings["Category"] if kind == "lineChart" else bindings["Rows"]
            visual["query"]["sortDefinition"] = {
                "sort": [{"field": field(sort_binding, kind == "barChart"),
                          "direction": "Descending" if kind == "barChart" else "Ascending"}],
                "isDefaultSort": True}
        objects = visual["objects"] = {}
        if kind == "lineChart":
            objects["dataPoint"] = [
                {"properties": {"fill": color(colors[binding])},
                 "selector": {"metadata": projection(binding, True)["queryRef"]}}
                for binding in bindings["Y"]]
            objects["legend"] = properties({"show": literal(True), "position": literal("Top"),
                                             "fontSize": literal(12)})
            objects["lineStyles"] = properties({"areaShow": literal(False),
                                                 "lineChartType": literal("linear"),
                                                 "strokeWidth": literal(3)})
            objects["labels"] = properties({"show": literal(False)})
        elif kind == "barChart":
            objects["dataPoint"] = properties({"defaultColor": color(colors[bindings["Y"]])})
        elif kind == "pivotTable":
            objects["columnHeaders"] = properties({
                "columnAdjustment": literal("growToFit"), "autoSizeColumnWidth": literal(True),
                "fontSize": literal(12), "wordWrap": literal(True)})
            objects["values"] = properties({"fontSize": literal(12)})
            vco["stylePreset"] = properties({"name": literal("None")})
        elif kind == "slicer":
            objects["data"] = properties({"mode": literal("Dropdown")})
            objects["header"] = properties({"show": literal(True)})
            geometry["height"] = 80
        elif kind == "cardVisual":
            value_size = min(28, max(12, math.floor(page["layout_contract"]["canvas"]["height"] * .028)))
            label_size = min(14, max(8, math.floor(value_size * .55)))
            height = 16 + 24 + 2 + math.ceil(value_size * 1.5) + math.ceil(max(label_size, 12) * 1.5)
            geometry["height"] = math.ceil(height / 8) * 8
            selector = {"id": "default"}
            objects["value"] = properties({"fontSize": literal(value_size),
                                           "fontColor": color(colors[bindings])}, selector)
            objects["label"] = properties({"fontSize": literal(label_size), "show": literal(True)}, selector)
            objects["layout"] = properties({"paddingUniform": {"expr": {"Literal": {"Value": "0L"}}}}, selector)
            vco["spacing"] = properties({"customizeSpacing": literal(True), "verticalSpacing": literal(2)}, selector)
    return {"$schema": VISUAL_SCHEMA, "name": name, "position": geometry, "visual": visual}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    text = args.spec.read_text(encoding="utf-8")
    match = re.search(r"```yaml\s*\n(.*?)\n```", text, re.DOTALL)
    if "Status: approved." not in text or not match:
        raise ContextError("An explicitly approved canonical report spec is required.")
    design = yaml.safe_load(match.group(1))["Design Brief"]
    if design["generated_by"] != "powerbi-report-cli" or design["contract_version"] != 1 or \
            [page["name"] for page in design["pages"]] != ["Actual vs Forecast", "Margin"]:
        raise ContextError("The report spec differs from the approved two-page scope.")
    config = load_config()
    configured = config["environments"]["dev"]["items"].get("RPT_Sales", {})
    folder = ROOT / "fabric" / "RPT_Sales.Report"
    if folder.exists():
        marker = folder / ".platform"
        if marker.exists():
            if not json.loads(marker.read_text(encoding="utf-8"))["metadata"]["description"].startswith(MARKER):
                raise ContextError("The local report is unowned; no overwrite.")
        elif {path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()} != {"definition.pbir"}:
            raise ContextError("Unexpected files in the initial report scaffold; no overwrite.")
        else:
            binding = json.loads((folder / "definition.pbir").read_text(encoding="utf-8"))
            if binding.get("datasetReference") != {"byPath": {"path": "../SM_Sales.SemanticModel"}}:
                raise ContextError("The initial local binding differs from the owned Sales model.")
    with tempfile.TemporaryDirectory(prefix="fabric-sales-report-") as directory:
        shell = Path(directory)
        response = json.loads(run([cli("powerbi-report-author"), "scaffold", str(shell),
                                   "--name", "RPT_Sales", "--model-path", "../SM_Sales.SemanticModel",
                                   "--page-name", "Actual vs Forecast", "--offline"]))["data"]
        source = shell / "RPT_Sales.Report"
        generated = {path.relative_to(source).as_posix(): path.read_bytes()
                     for path in source.rglob("*") if path.is_file()
                     and not path.relative_to(source).as_posix().startswith("definition/pages/")}
        platform = json.loads(generated[".platform"])
        platform["metadata"]["description"] = MARKER + ": actual versus forecast and margin report."
        platform["config"]["logicalId"] = str(uuid5(NAMESPACE_URL, "fabric-demo-platform/RPT_Sales"))
        generated[".platform"] = (json.dumps(platform, indent=2) + "\n").encode()
        original_page = json.loads((source / "definition" / "pages" / response["pageId"] / "page.json").read_text())
        page_ids = []
        colors = {item["measure"]: item["color"] for item in design["color_map"]}
        for page in design["pages"]:
            page_id = sha256(f"RPT_Sales/{page['name']}".encode()).hexdigest()[:20]
            page_ids.append(page_id)
            metadata = deepcopy(original_page)
            metadata.update({"name": page_id, "displayName": page["name"],
                             "width": 1920, "height": 1080,
                             "objects": {"background": properties({"color": color(page["page_background"]),
                                                                  "transparency": literal(0)})}})
            for order, placement in enumerate(page["layout_contract"]["placements"], start=1):
                visual = make_visual(page, placement, order, colors)
                path = f"definition/pages/{page_id}/visuals/{visual['name']}/visual.json"
                generated[path] = (json.dumps(visual, indent=2) + "\n").encode()
            generated[f"definition/pages/{page_id}/page.json"] = (json.dumps(metadata, indent=2) + "\n").encode()
        index = json.loads((source / "definition" / "pages" / "pages.json").read_text())
        index.update({"pageOrder": page_ids, "activePageName": page_ids[0]})
        generated["definition/pages/pages.json"] = (json.dumps(index, indent=2) + "\n").encode()
        skill = Path.home() / ".copilot" / "installed-plugins" / "fabric-collection" / "powerbi-authoring" / "skills" / "powerbi-report-cli"
        theme = json.loads((skill / "references" / "design" / "assets" / "base.json").read_text())
        theme["$schema"] = "https://raw.githubusercontent.com/microsoft/powerbi-desktop-samples/main/Report%20Theme%20JSON%20Schema/reportThemeSchema-2.159.json"
        theme["dataColors"] = list(colors.values())
        theme.update({"foreground": "#172B4D", "background": "#FFFFFF", "tableAccent": "#0072B2"})
        for value in theme["textClasses"].values():
            value["fontFace"] = "Segoe UI"
        theme["visualStyles"]["*"]["*"]["visualHeader"] = [{"show": False}]
        card_theme = theme["visualStyles"]["cardVisual"]["*"]
        card_theme.pop("border")
        card_theme.pop("padding")
        card_theme["spacing"] = [{"verticalSpacing": 2}]
        suffix = uuid5(NAMESPACE_URL, json.dumps(theme, sort_keys=True)).hex[:12]
        theme_name = f"SalesAnalytics-{suffix}.json"
        theme["name"] = theme_name
        generated[f"StaticResources/RegisteredResources/{theme_name}"] = (json.dumps(theme, indent=2) + "\n").encode()
        report = json.loads(generated["definition/report.json"])
        report["themeCollection"]["customTheme"] = {
            "name": theme_name, "type": "RegisteredResources",
            "reportVersionAtImport": {"visual": "2.9.0", "report": "3.3.0", "page": "2.1.0"}}
        report["resourcePackages"].append({"name": "RegisteredResources", "type": "RegisteredResources",
                                           "items": [{"name": theme_name, "path": theme_name, "type": "CustomTheme"}]})
        generated["definition/report.json"] = (json.dumps(report, indent=2) + "\n").encode()
    manifest = {name: sha256(content).hexdigest() for name, content in generated.items()}
    if configured.get("local_files"):
        for name, digest in configured["local_files"].items():
            path = folder / name
            if not path.is_file() or sha256(path.read_bytes()).hexdigest() != digest:
                raise ContextError(f"Report file changed outside the generator: {name}; no overwrite.")
    if args.dry_run:
        print(f"DRY-RUN: {len(generated)} report files, 2 pages, 12 visuals; no repository writes.")
        return
    for name in set(configured.get("local_files", {})) - set(generated):
        (folder / name).unlink()
    for name, content in generated.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != content:
            path.write_bytes(content)
    configured = config["environments"]["dev"]["items"].setdefault("RPT_Sales", {})
    configured.update({"type": "Report", "local_files": manifest})
    save_config(config)
    record(f"Generated RPT_Sales from the approved report spec and official CLI shell: "
           f"2 FHD pages, 12 visuals, stable IDs, bound to existing SM_Sales. References: {REFERENCES}.")
    print(run([cli("powerbi-report-author"), "validate", str(folder)]))


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ValueError, OSError) as error:
        record(f"Sales report generation blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
