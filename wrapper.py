"""
wrapper.py

n8n integration layer for the rules engine.
Reads JSON from stdin, writes JSON to stdout.

Usage:
    echo '{"Zip": "76016", ...}' | python3 wrapper.py
    echo '{"Zip": "76016", ..., "debug": true}' | python3 wrapper.py
"""

import json
import sys
from datetime import date, datetime
import yaml
from rules_engine import evaluate_call

CONFIG_PATH = "config.yaml"


def load_config(path=CONFIG_PATH):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _coerce_float(value, default, strict=False):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        if strict:
            return None
        return default


def _coerce_int(value, default):
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def map_sheet_row(row, config):
    defaults = config.get("batch_defaults", {})

    zip_raw = row.get("Zip") or row.get("zip") or ""
    zip_code = str(zip_raw).replace(".0", "").strip()

    storm_date_raw = row.get("storm_date") or defaults.get("storm_date")
    storm_date = _parse_date(storm_date_raw)
    if storm_date:
        days_since = (date.today() - storm_date).days
    else:
        days_since = 0

    hail = _coerce_float(row.get("hail_size_in"), defaults.get("hail_size_in", 1.0), strict=True)
    confidence = _coerce_float(row.get("storm_confidence"), defaults.get("storm_confidence", 0.5), strict=True)
    owner = row.get("owner_occupied") or defaults.get("owner_occupied", "unknown")
    capacity = _coerce_int(row.get("capacity_remaining"), defaults.get("capacity_remaining", 10))

    first = row.get("Owner 1 First Name") or ""
    last = row.get("Owner 1 Last Name") or ""
    lead_id = row.get("lead_id") or f"{first} {last}".strip() or zip_code
    caller_intent = row.get("caller_intent") or "inspection"

    return {
        "lead_id": lead_id,
        "zip": zip_code,
        "hail_size_in": hail,
        "storm_confidence": confidence,
        "days_since_storm": days_since,
        "owner_occupied": str(owner).lower().strip(),
        "caller_intent": caller_intent,
        "capacity_remaining": capacity,
    }


def process_lead(lead_row, config, debug=False):
    mapped = map_sheet_row(lead_row, config)

    if mapped["hail_size_in"] is None or mapped["storm_confidence"] is None:
        return {
            "lead_id": mapped["lead_id"],
            "call_intent": "route_to_human",
            "booking_allowed": False,
            "confidence_level": 0.0,
            "hard_stop_reason": "INVALID_INPUT",
        }

    result = evaluate_call(mapped, config)

    output = {
        "lead_id": result["lead_id"],
        "call_intent": result["call_intent"],
        "booking_allowed": result["call_intent"] == "book_now",
        "confidence_level": result["confidence_level"],
        "hard_stop_reason": result["hard_stop_reason"],
    }

    if debug:
        output["explain"] = result.get("explain", {})

    return output


if __name__ == "__main__":
    raw = json.loads(sys.stdin.read())
    config = load_config()
    debug = raw.pop("debug", False)
    print(json.dumps(process_lead(raw, config, debug=debug)))
