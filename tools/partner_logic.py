"""Project only Partner A delivery facts and their many-to-one product names."""

from datetime import date, datetime
from decimal import Decimal

PARTNER_COLUMNS = (
    "month", "sku", "product_name", "package_code", "region_code",
    "delivered_hl", "on_time_pct",
)


def partner_deliveries(deliveries: list[dict], products: list[dict]) -> list[dict]:
    if not deliveries or not products:
        raise ValueError("Partner extraction requires nonempty delivery and product sources.")
    names = {}
    for product in products:
        if product["env_marker"] != "prod":
            raise ValueError("Product source is not exclusively Prod.")
        sku, name = product["sku"], product["product_name"]
        if sku in names or not sku or not name:
            raise ValueError("Product SKU must uniquely identify a nonempty product name.")
        names[sku] = name
    result = []
    for row in deliveries:
        if row["env_marker"] != "prod":
            raise ValueError("Delivery source is not exclusively Prod.")
        if row["partner_id"] != "P-A":
            continue
        if row["sku"] not in names:
            raise ValueError("A Partner A delivery has no matching product.")
        month = row["month"]
        if isinstance(month, datetime):
            month = month.date()
        if not isinstance(month, date) or month.day != 1:
            raise ValueError("Delivery month must be a month-start date.")
        volume, on_time = Decimal(str(row["delivered_hl"])), Decimal(str(row["on_time_pct"]))
        if not volume.is_finite() or not on_time.is_finite() or volume < 0 or not 0 <= on_time <= 100:
            raise ValueError("Invalid delivered volume or on-time percentage.")
        if not row["package_code"] or not row["region_code"]:
            raise ValueError("Partner A delivery keys must not be empty.")
        result.append(dict(zip(PARTNER_COLUMNS, (
            month, row["sku"], names[row["sku"]], row["package_code"],
            row["region_code"], volume, on_time,
        ))))
    if not result:
        raise ValueError("There are no Partner A deliveries.")
    return sorted(result, key=lambda row: (row["month"], row["sku"],
                                           row["package_code"], row["region_code"]))
