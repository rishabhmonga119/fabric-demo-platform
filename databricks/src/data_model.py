"""Deterministic illustrative beverage data; no customer records."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from random import Random


MARKER = "Managed by fabric-demo-platform demo automation"
TABLES = {
    "dim_product": {
        "description": "Illustrative beverage products.",
        "columns": [
            ("sku", "STRING", "Product code; the number is a legacy code, not a package."),
            ("product_name", "STRING", "Product display name."),
            ("product_line", "STRING", "Still, Sparkling, Medium, Flavoured or Soft drink."),
            ("launch_year", "INT", "Illustrative product launch year."),
            ("env_marker", "STRING", "Source environment: dev, test or prod."),
        ], "keys": ["sku"],
    },
    "dim_package": {
        "description": "Package types, sizes and returnability; Gebinde.",
        "columns": [
            ("package_code", "STRING", "Package identifier."),
            ("package_type", "STRING", "Glass or PET."),
            ("volume_l", "DOUBLE", "Individual package volume in litres."),
            ("returnable", "BOOLEAN", "Whether the package is returnable."),
            ("env_marker", "STRING", "Source environment: dev, test or prod."),
        ], "keys": ["package_code"],
    },
    "dim_channel": {
        "description": "Food retail, gastronomy, wholesale and online sales channels.",
        "columns": [
            ("channel_code", "STRING", "Sales channel identifier."),
            ("channel_name", "STRING", "Sales channel display name."),
            ("env_marker", "STRING", "Source environment: dev, test or prod."),
        ], "keys": ["channel_code"],
    },
    "dim_region": {
        "description": "Four illustrative sales regions.",
        "columns": [
            ("region_code", "STRING", "NORTH, SOUTH, EAST or WEST."),
            ("region_name", "STRING", "Sales region display name."),
            ("sales_manager", "STRING", "Fictional sales manager name."),
            ("env_marker", "STRING", "Source environment: dev, test or prod."),
        ], "keys": ["region_code"],
    },
    "dim_partner": {
        "description": "Three fictional business partners.",
        "columns": [
            ("partner_id", "STRING", "Partner identifier."),
            ("partner_name", "STRING", "Fictional partner display name."),
            ("partner_type", "STRING", "Logistics, Retail or Wholesale."),
            ("country", "STRING", "Illustrative partner country code."),
            ("env_marker", "STRING", "Source environment: dev, test or prod."),
        ], "keys": ["partner_id"],
    },
    "fact_sales_monthly": {
        "description": "Monthly sales at product/package/region/channel grain.",
        "columns": [
            ("month", "DATE", "First day of the sales month."),
            ("sku", "STRING", "Product key."),
            ("package_code", "STRING", "Package key."),
            ("region_code", "STRING", "Sales region key."),
            ("channel_code", "STRING", "Sales channel key."),
            ("actual_hl", "DECIMAL(12,2)", "Sold volume in hectolitres."),
            ("revenue_eur", "DECIMAL(14,2)", "Net sales revenue in EUR."),
            ("margin_eur", "DECIMAL(14,2)", "Contribution margin in EUR; sensitive in the security demo."),
            ("env_marker", "STRING", "Source environment: dev, test or prod."),
        ], "keys": ["month", "sku", "package_code", "region_code", "channel_code"],
    },
    "fact_deliveries": {
        "description": "Monthly partner deliveries; P-A serves NORTH and EAST.",
        "columns": [
            ("month", "DATE", "First day of the delivery month."),
            ("partner_id", "STRING", "Delivery partner key."),
            ("sku", "STRING", "Product key."),
            ("package_code", "STRING", "Package key."),
            ("region_code", "STRING", "Delivery region key."),
            ("delivered_hl", "DECIMAL(12,2)", "Delivered volume in hectolitres."),
            ("on_time_pct", "DECIMAL(5,2)", "On-time delivery percentage, from 85 to 99."),
            ("env_marker", "STRING", "Source environment: dev, test or prod."),
        ], "keys": ["month", "partner_id", "sku", "package_code", "region_code"],
    },
}
PRODUCTS = (
    ("SKU-STL-075", "Spring Still", "Still", 2010),
    ("SKU-SPK-100", "Spring Sparkling", "Sparkling", 2010),
    ("SKU-MED-100", "Spring Medium", "Medium", 2012),
    ("SKU-NAT-075", "Spring Naturelle", "Still", 2015),
    ("SKU-LEM-050", "Spring Lemon", "Flavoured", 2018),
    ("SKU-APS-050", "Spring Apple Spritz", "Soft drink", 2018),
    ("SKU-COZ-050", "Spring Cola Zero", "Soft drink", 2021),
    ("SKU-ITP-050", "Spring Iced Tea Peach", "Soft drink", 2023),
)
PACKAGES = (
    ("GL-075-RET", "Glass", 0.75, True),
    ("GL-025-RET", "Glass", 0.25, True),
    ("PET-100", "PET", 1.0, False),
    ("PET-050", "PET", 0.5, False),
    ("PET-150", "PET", 1.5, False),
)
CHANNELS = (("RETAIL", "Food retail"), ("HORECA", "Gastronomy"),
            ("WHOLESALE", "Beverage wholesale"), ("ECOM", "Online"))
REGIONS = (("NORTH", "North", "Alex North"), ("SOUTH", "South", "Blair South"),
           ("EAST", "East", "Casey East"), ("WEST", "West", "Drew West"))
PARTNERS = (("P-A", "Logistics partner A", "Logistics", "DE"),
            ("P-B", "Retail partner B", "Retail", "DE"),
            ("P-C", "Wholesale partner C", "Wholesale", "DE"))
VALID_COMBINATIONS = tuple(
    (product[0], package)
    for index, product in enumerate(PRODUCTS)
    for package in (("GL-075-RET", "GL-025-RET", "PET-100", "PET-150") if index < 4
                    else ("PET-050", "PET-100", "GL-025-RET"))
)


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def business_checksums(rows: list[tuple]) -> tuple[str, str]:
    sums = [0, 0]
    for row in rows:
        text = "|".join(str(value).lower() if isinstance(value, bool) else str(value)
                        for value in row[:-1])
        digest = sha256(text.encode("utf-8")).hexdigest()
        sums[0] += int(digest[:15], 16)
        sums[1] += int(digest[-15:], 16)
    return str(sums[0]), str(sums[1])


def generate_model(stage: str) -> dict[str, list[tuple]]:
    if stage not in ("dev", "test", "prod"):
        raise ValueError("Expected dev, test or prod.")
    rng = Random(42)
    data = {
        "dim_product": [(*row, stage) for row in PRODUCTS],
        "dim_package": [(*row, stage) for row in PACKAGES],
        "dim_channel": [(*row, stage) for row in CHANNELS],
        "dim_region": [(*row, stage) for row in REGIONS],
        "dim_partner": [(*row, stage) for row in PARTNERS],
    }
    sales = []
    totals = {}
    price = {"GL-075-RET": 65, "GL-025-RET": 95, "PET-100": 48, "PET-050": 62, "PET-150": 42}
    channel_mix = {"RETAIL": ".55", "WHOLESALE": ".25", "HORECA": ".15", "ECOM": ".05"}
    region_mix = {"NORTH": ".28", "SOUTH": ".26", "EAST": ".22", "WEST": ".24"}
    margin_by_line = {"Still": ".22", "Sparkling": ".26", "Medium": ".24",
                      "Flavoured": ".28", "Soft drink": ".30"}
    for year, months in ((2025, 12), (2026, 10)):
        for number in range(1, months + 1):
            month = date(year, number, 1)
            for sku, package in VALID_COMBINATIONS:
                product_index = next(index for index, product in enumerate(PRODUCTS) if product[0] == sku)
                volume = next(item[2] for item in PACKAGES if item[0] == package)
                base = Decimal(str(4000 + product_index * 550 + volume * 1000))
                season = Decimal("1.35") if number in (6, 7, 8) else Decimal("1")
                if number == 12 and product_index >= 4:
                    season *= Decimal("1.1")
                growth = Decimal("1.04") if year == 2026 else Decimal("1")
                for region, _, _ in REGIONS:
                    total = Decimal("0")
                    for channel, _ in CHANNELS:
                        noise = Decimal(str(rng.uniform(.94, 1.06)))
                        actual = money(base * season * growth * Decimal(region_mix[region])
                                       * Decimal(channel_mix[channel]) * noise)
                        revenue = money(actual * Decimal(price[package]))
                        margin = money(revenue * Decimal(margin_by_line[PRODUCTS[product_index][2]]))
                        sales.append((month, sku, package, region, channel, actual, revenue, margin, stage))
                        total += actual
                    totals[(month, sku, package, region)] = total
    deliveries = []
    for (month, sku, package, region), total in totals.items():
        split = (("P-A", ".5"), ("P-B", ".3"), ("P-C", ".2")) if region in ("NORTH", "EAST") \
            else (("P-B", ".6"), ("P-C", ".4"))
        for partner, share in split:
            deliveries.append((month, partner, sku, package, region, money(total * Decimal(share)),
                               money(Decimal(str(rng.uniform(85, 99)))), stage))
    data["fact_sales_monthly"], data["fact_deliveries"] = sales, deliveries
    return data
