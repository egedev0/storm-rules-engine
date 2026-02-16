"""
wrapper.py

n8n integration layer for the rules engine.
Reads JSON from stdin, writes JSON to stdout.

Usage:
    echo '{"lead_id": "L-1001", ...}' | python3 wrapper.py
    echo '{"lead_id": "L-1001", ..., "debug": true}' | python3 wrapper.py
"""

import json
import sys
import yaml
from rules_engine import evaluate_call

CONFIG_PATH = "config.yaml"


def load_config(path=CONFIG_PATH):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def process_lead(lead_row, config, debug=False):
    result = evaluate_call(lead_row, config)

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
