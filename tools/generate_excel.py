"""Generate deterministic standard, messy and live forecasts from the Gold seed."""

import argparse
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from random import Random
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.writer.excel import ExcelWriter

from common import ContextError, ROOT, load_config

sys.path.insert(0, str(ROOT / "databricks" / "src"))
from data_model import CHANNELS, REGIONS, VALID_COMBINATIONS, generate_model, money
sys.path.insert(0, str(ROOT))
from infra.deploy import record

CREATOR = "fabric-demo-platform demo automation"
HEADERS = ("month", "sku", "package_code", "region_code", "channel_code", "forecast_hl")
GERMAN = ("Monat", "Artikelnummer", "Gebinde", "Region", "Kanal", "Menge (hl)")


def forecasts() -> list[tuple]:
    actuals = {row[:5]: row[5] for row in generate_model("dev")["fact_sales_monthly"]}
    rng = Random(42)
    rows = []
    for month in range(1, 13):
        for sku, package in VALID_COMBINATIONS:
            for region, _, _ in REGIONS:
                for channel, _ in CHANNELS:
                    source_month = date(2026 if month <= 10 else 2025, month, 1)
                    actual = actuals[(source_month, sku, package, region, channel)]
                    projection = Decimal("1") if month <= 10 else Decimal("1.04")
                    forecast = money(actual * projection * Decimal(str(rng.uniform(.85, 1.15))))
                    rows.append((date(2026, month, 1), sku, package, region, channel, forecast))
    return rows


def workbook_bytes(rows: list[tuple], layout: str, mappings: dict) -> bytes:
    workbook = Workbook()
    workbook.properties.creator = CREATOR
    workbook.properties.created = datetime(2000, 1, 1)
    workbook.properties.modified = datetime(2000, 1, 1)
    sheet = workbook.active
    sheet.title = "Forecast" if layout == "standard" else "Planung"
    if layout != "standard":
        sheet.append(["Absatzplanung 2026 - Vertrieb West"])
        sheet.merge_cells("A1:F1")
        sheet.append(["Department forecast"])
        sheet.append([])
    sheet.append(HEADERS if layout == "standard" else GERMAN)
    header_row = 1 if layout == "standard" else 4
    for cell in sheet[header_row]:
        cell.font = Font(bold=True)
    package_text = {code: text for text, code in mappings["packages"].items()}
    channels = {code: text for text, code in mappings["channels"].items()}
    for index, row in enumerate(rows):
        month, sku, package, region, channel, volume = row
        if layout == "gastro" and index == len(rows) // 2:
            sheet.append([])
        if layout == "standard":
            sheet.append([month, sku, package, region, channel, float(volume)])
            sheet.cell(sheet.max_row, 1).number_format = "yyyy-mm-dd"
            sheet.cell(sheet.max_row, 6).number_format = "0.00"
        else:
            text_month = month.strftime("%b %y") if layout == "gastro" else \
                month.strftime("%m/%Y") if layout == "wholesale" else month.isoformat()
            text_volume = f"{volume:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
            sheet.append([text_month, sku, package_text[package] if layout == "wholesale" else package,
                          region, channels[channel], text_volume])
    if layout == "wholesale":
        first = list(rows[0])
        first[1] = "SKU-XXX-999"
        sheet.append([first[0].strftime("%m/%Y"), first[1], package_text[first[2]], first[3],
                      channels[first[4]], "99,00"])
        sheet.append([rows[0][0].strftime("%m/%Y"), rows[0][1], package_text[rows[0][2]],
                      rows[0][3], channels[rows[0][4]],
                      f"{rows[0][5]:.2f}".replace(".", ",")])
    buffer = BytesIO()
    # Workbook.save() would replace the fixed modified timestamp with the clock.
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        ExcelWriter(workbook, archive).write_data()
    # XLSX zip timestamps otherwise change even when business data is identical.
    output = BytesIO()
    with ZipFile(buffer) as source, ZipFile(output, "w", compression=ZIP_DEFLATED) as target:
        for name in sorted(source.namelist()):
            target.writestr(ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0)), source.read(name),
                            compress_type=ZIP_DEFLATED)
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    import yaml
    mappings = yaml.safe_load((ROOT / "config" / "mappings.yml").read_text(encoding="utf-8"))
    rows = forecasts()
    baseline = [row for row in rows if row[0].month <= 11]
    outputs = {}
    for region in ("NORTH", "SOUTH", "EAST"):
        outputs[Path("standard") / f"forecast_{region}_2026.xlsx"] = workbook_bytes(
            [row for row in baseline if row[3] == region], "standard", mappings)
    west = [row for row in baseline if row[3] == "WEST"]
    for filename, layout, channels in (
        ("Planung_West_Handel.xlsx", "retail", ("RETAIL", "ECOM")),
        ("west_gastro_forecast_v3_FINAL.xlsx", "gastro", ("HORECA",)),
        ("West-GFGH.xlsx", "wholesale", ("WHOLESALE",)),
    ):
        outputs[Path("raw") / filename] = workbook_bytes(
            [row for row in west if row[4] in channels], layout, mappings)
    paths = [(ROOT / "seed" / "excel" / stage / relative, content)
             for stage in load_config()["environments"] for relative, content in outputs.items()]
    paths.append((ROOT / "seed" / "excel" / "live" / "forecast_2026-12_late.xlsx",
                  workbook_bytes([row for row in rows if row[0].month == 12 and row[3] != "WEST"],
                                 "standard", mappings)))
    for path, content in paths:
        if path.exists() and path.read_bytes() != content:
            with path.open("rb") as source:
                existing = load_workbook(source, read_only=True)
                creator = existing.properties.creator
                existing.close()
                if creator != CREATOR:
                    raise ContextError(f"Refusing to overwrite workbook not created by this automation: {path}")
        print(f"{'DRY-RUN: ' if args.dry_run else ''}Generate {path}")
        if not args.dry_run and (not path.exists() or path.read_bytes() != content):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    if not args.dry_run:
        record("Generated six deterministic forecast workbooks per stage plus one unuploaded live workbook; 4,928 unique baseline forecast grains per stage, one raw unknown-SKU reject and one intentional raw duplicate.")


if __name__ == "__main__":
    try:
        main()
    except ContextError as error:
        record(f"Excel generation blocked: {error}")
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
