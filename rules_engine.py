"""
rules_engine.py

Deterministic lead-scoring engine for storm-damage calls.
Entry point: evaluate_call(input_data, config)
"""

REQUIRED_FIELDS = {
    "lead_id": str,
    "zip": str,
    "hail_size_in": (int, float),
    "storm_confidence": (int, float),
    "days_since_storm": int,
    "owner_occupied": str,
    "caller_intent": str,
    "capacity_remaining": int,
}

VALID_OWNER_OCCUPIED = {"true", "false", "unknown"}
VALID_CALLER_INTENT = {"inspection", "repair", "price", "insurance", "unknown"}


def _validate_input(input_data):
    """Returns 'INVALID_INPUT' if data is malformed, None otherwise."""
    if not isinstance(input_data, dict):
        return "INVALID_INPUT"

    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in input_data:
            return "INVALID_INPUT"
        if not isinstance(input_data[field], expected_type):
            return "INVALID_INPUT"

    if input_data["owner_occupied"] not in VALID_OWNER_OCCUPIED:
        return "INVALID_INPUT"
    if input_data["caller_intent"] not in VALID_CALLER_INTENT:
        return "INVALID_INPUT"
    if not 0 <= input_data["storm_confidence"] <= 1:
        return "INVALID_INPUT"
    if input_data["hail_size_in"] < 0:
        return "INVALID_INPUT"
    if input_data["days_since_storm"] < 0:
        return "INVALID_INPUT"
    if input_data["capacity_remaining"] < 0:
        return "INVALID_INPUT"

    return None


def _resolve_zip_tier(zip_code, config):
    for tier, zips in config["zip_tiers"].items():
        if zip_code in zips:
            return tier
    return "UNKNOWN"


def _hard_stop_result(lead_id, reason, zip_tier, applied_rules):
    return {
        "lead_id": lead_id,
        "confidence_level": 0.0,
        "call_intent": "route_to_human",
        "hard_stop_reason": reason,
        "debug": {
            "zip_tier": zip_tier,
            "score_components": {},
            "applied_rules": applied_rules,
        },
    }


def _check_hard_stops(input_data, config, zip_tier):
    """Evaluates hard stops in spec order. Returns (reason, applied_rules)."""
    hs = config["hard_stops"]
    applied = []

    if hs.get("capacity_zero", True) and input_data["capacity_remaining"] <= 0:
        applied.append("hard_stop:NO_CAPACITY")
        return "NO_CAPACITY", applied
    applied.append("pass:capacity_check")

    if input_data["storm_confidence"] < hs["storm_confidence_min"]:
        applied.append("hard_stop:LOW_STORM_CONFIDENCE")
        return "LOW_STORM_CONFIDENCE", applied
    applied.append("pass:storm_confidence_check")

    if input_data["hail_size_in"] < hs["hail_size_min_in"]:
        applied.append("hard_stop:HAIL_TOO_SMALL")
        return "HAIL_TOO_SMALL", applied
    applied.append("pass:hail_size_check")

    if input_data["days_since_storm"] > hs["days_since_storm_max"]:
        applied.append("hard_stop:TOO_OLD")
        return "TOO_OLD", applied
    applied.append("pass:recency_check")

    if zip_tier == "UNKNOWN" and hs.get("block_unknown_zip", True):
        applied.append("hard_stop:UNKNOWN_ZIP")
        return "UNKNOWN_ZIP", applied
    applied.append("pass:zip_tier_check")

    if input_data["owner_occupied"] == "false" and hs.get("block_owner_occupied_false", False):
        applied.append("hard_stop:NOT_OWNER_OCCUPIED")
        return "NOT_OWNER_OCCUPIED", applied
    applied.append("pass:owner_occupied_check")

    return None, applied


def evaluate_call(input_data, config):
    """Evaluate a single lead against the rules config and return a decision dict."""

    validation_error = _validate_input(input_data)
    if validation_error:
        lead_id = input_data.get("lead_id", "UNKNOWN") if isinstance(input_data, dict) else "UNKNOWN"
        return _hard_stop_result(lead_id, validation_error, "UNKNOWN", ["hard_stop:INVALID_INPUT"])

    lead_id = input_data["lead_id"]
    zip_tier = _resolve_zip_tier(input_data["zip"], config)

    hard_stop_reason, applied_rules = _check_hard_stops(input_data, config, zip_tier)
    if hard_stop_reason:
        return _hard_stop_result(lead_id, hard_stop_reason, zip_tier, applied_rules)

    return {
        "lead_id": lead_id,
        "confidence_level": 0.0,
        "call_intent": "route_to_human",
        "hard_stop_reason": None,
        "debug": {
            "zip_tier": zip_tier,
            "score_components": {},
            "applied_rules": applied_rules,
        },
    }
