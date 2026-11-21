"""Read-only licence and availability checks for the three demo accounts."""

import argparse
import json
import sys
from urllib.parse import quote

from common import ContextError, load_config, verify_context
from http_api import Api, ApiError


def license_features(plans: set[str]) -> dict[str, bool]:
    return {
        "power_bi_pro": "BI_AZURE_P2" in plans,
        "m365_copilot": {
            "M365_COPILOT_APPS", "M365_COPILOT_TEAMS", "M365_COPILOT_BUSINESS_CHAT"
        }.issubset(plans),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="This check never assigns licences.")
    parser.parse_args()
    verify_context()
    config = load_config()
    api = Api("https://graph.microsoft.com", config["tenant"]["id"])
    accounts = [config["tenant"]["admin_upn"]]
    accounts.extend(user["upn"] for user in config["entra"]["users"].values())
    # https://learn.microsoft.com/graph/api/user-list-licensedetails
    for upn in accounts:
        licences = api.list(f"/v1.0/users/{quote(upn)}/licenseDetails")
        enabled = set()
        relevant = []
        for licence in licences:
            plans = {plan["servicePlanName"] for plan in licence["servicePlans"]
                     if plan["provisioningStatus"] == "Success"}
            enabled.update(plans)
            features = license_features(plans)
            if any(features.values()):
                relevant.append({"sku": licence["skuPartNumber"],
                                 "sku_id": licence["skuId"], "features": features})
        print(json.dumps({
            "account": upn,
            "features": license_features(enabled),
            "licences": relevant,
        }))
    # https://learn.microsoft.com/graph/api/subscribedsku-list
    skus = api.list("/v1.0/subscribedSkus")
    print("Relevant available tenant SKUs:")
    for sku in skus:
        name = sku["skuPartNumber"]
        features = license_features({plan["servicePlanName"] for plan in sku["servicePlans"]})
        if any(features.values()):
            print(json.dumps({"sku": name, "sku_id": sku["skuId"],
                              "features": features,
                              "enabled": sku["prepaidUnits"]["enabled"],
                              "consumed": sku["consumedUnits"],
                              "available": sku["prepaidUnits"]["enabled"] - sku["consumedUnits"]}))
    print("Licence check complete; no licences purchased or assigned.")


if __name__ == "__main__":
    try:
        main()
    except (ContextError, ApiError) as error:
        print(f"STOP: {error}", file=sys.stderr)
        raise SystemExit(1) from error
