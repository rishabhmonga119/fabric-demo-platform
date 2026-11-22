"""Pure forecast parsing shared by the generated Fabric notebook and local checks."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

FIELDS = ("month", "sku", "package_code", "region_code", "channel_code", "forecast_hl")
GRAIN = FIELDS[:-1]


def parse_month(value):
    if isinstance(value, (datetime, date)):
        return date(value.year, value.month, 1)
    text = str(value).strip()
    text = re.sub(r"\b(?:Mär|Maerz|März)\b", "Mar", text, flags=re.IGNORECASE)
    for pattern in ("%Y-%m-%d", "%Y-%m", "%m/%Y", "%b %y"):
        try:
            parsed = datetime.strptime(text, pattern)
            return date(parsed.year, parsed.month, 1)
        except ValueError:
            continue
    raise ValueError(f"Invalid forecast month: {value}")


def parse_volume(value):
    if value is None or isinstance(value, bool):
        raise ValueError("Forecast volume is missing or invalid.")
    text = str(value).strip().replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        volume = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"Invalid forecast volume: {value}") from error
    if not volume.is_finite() or volume < 0:
        raise ValueError("Forecast volume must be finite and non-negative.")
    return volume.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def header_key(value, mappings):
    text = str(value or "").strip()
    aliases = {key.casefold(): target for key, target in mappings["headers"].items()}
    aliases.update({field.casefold(): field for field in FIELDS})
    return aliases.get(text.casefold())


def normalize_record(record, mappings, dimensions):
    normalized = {
        "month": parse_month(record.get("month")),
        "sku": str(record.get("sku") or "").strip().upper(),
        "region_code": str(record.get("region_code") or "").strip().upper(),
        "forecast_hl": parse_volume(record.get("forecast_hl")),
    }
    package = str(record.get("package_code") or "").strip()
    package_aliases = {text.casefold(): code for text, code in mappings["packages"].items()}
    normalized["package_code"] = package_aliases.get(package.casefold(), package.upper())
    channel = str(record.get("channel_code") or "").strip()
    channel_aliases = {text.casefold(): code for text, code in mappings["channels"].items()}
    normalized["channel_code"] = channel_aliases.get(channel.casefold(), channel.upper())
    for field in ("sku", "package_code", "region_code", "channel_code"):
        if normalized[field] not in dimensions[field]:
            raise ValueError(f"Unknown {field}: {normalized[field]}")
    if (normalized["sku"], normalized["package_code"]) not in dimensions["valid_pairs"]:
        raise ValueError("Invalid product/package combination.")
    return normalized


def parse_sheet(rows, filename, mappings, dimensions):
    records, rejects = [], []
    indexes = None
    for number, values in enumerate(rows, start=1):
        if not any(value is not None and str(value).strip() for value in values):
            continue
        if indexes is None:
            candidates = {header_key(value, mappings): index for index, value in enumerate(values)}
            if all(field in candidates for field in FIELDS):
                indexes = {field: candidates[field] for field in FIELDS}
            continue
        source = {field: values[index] if index < len(values) else None
                  for field, index in indexes.items()}
        try:
            records.append(normalize_record(source, mappings, dimensions))
        except ValueError as error:
            rejects.append({"filename": filename, "row_number": number,
                            "reason": str(error), "raw_values": repr(source)})
    if indexes is None:
        raise ValueError(f"{filename}: required forecast headers were not found.")
    return records, rejects
