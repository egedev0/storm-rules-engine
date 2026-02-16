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

REQUIRED_CONFIG_KEYS = {
    "zip_tiers": dict,
    "hard_stops": dict,
    "scoring": dict,
    "decision": dict,
}

REQUIRED_WEIGHT_KEYS = {"zip_tier", "hail_size", "storm_confidence", "recency", "owner_occupied"}


def _validate_config(config):
    """Returns 'INVALID_CONFIG' reason string if config is malformed, None otherwise."""
    if not isinstance(config, dict):
        return "INVALID_CONFIG"

    for key, expected_type in REQUIRED_CONFIG_KEYS.items():
        if key not in config or not isinstance(config[key], expected_type):
            return "INVALID_CONFIG"

    scoring = config["scoring"]
    if "weights" not in scoring or not isinstance(scoring["weights"], dict):
        return "INVALID_CONFIG"

    weights = scoring["weights"]
    if set(weights.keys()) != REQUIRED_WEIGHT_KEYS:
        return "INVALID_CONFIG"

    weight_sum = round(sum(weights.values()), 10)
    if weight_sum != 1.0:
        return "INVALID_CONFIG"

    if "hail_size_curve" not in scoring or not scoring["hail_size_curve"]:
        return "INVALID_CONFIG"
    if "recency_curve_days" not in scoring or not scoring["recency_curve_days"]:
        return "INVALID_CONFIG"
    if "mappings" not in scoring:
        return "INVALID_CONFIG"

    return None


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
            "decision_path": "HARD_STOP",
            "score_breakdown": [],
            "thresholds_used": {},
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


def _lookup_curve(value, curve, key_field):
    """Walk a sorted curve and return the score for the highest matching bracket."""
    result = 0.0
    for entry in curve:
        if value >= entry[key_field]:
            result = entry["score"]
        else:
            break
    return result


def _lookup_recency(days, curve):
    """First bracket where max_days >= days wins."""
    for entry in curve:
        if days <= entry["max_days"]:
            return entry["score"]
    return 0.0


def _compute_score(input_data, config, zip_tier):
    """Weighted sum of scoring components, clipped to [0, 1]."""
    scoring = config["scoring"]
    weights = scoring["weights"]
    mappings = scoring["mappings"]

    zip_score = mappings["zip_tier"].get(zip_tier, 0.0)
    hail_score = _lookup_curve(input_data["hail_size_in"], scoring["hail_size_curve"], "min")
    storm_score = input_data["storm_confidence"]
    recency_score = _lookup_recency(input_data["days_since_storm"], scoring["recency_curve_days"])
    owner_score = mappings["owner_occupied"].get(input_data["owner_occupied"], 0.0)

    raw_values = {
        "zip_tier": zip_score,
        "hail_size": hail_score,
        "storm_confidence": storm_score,
        "recency": recency_score,
        "owner_occupied": owner_score,
    }

    score_breakdown = []
    for component, raw in raw_values.items():
        w = weights[component]
        score_breakdown.append({
            "component": component,
            "raw_value": raw,
            "weight": w,
            "contribution": round(raw * w, 6),
        })

    total = max(0.0, min(1.0, sum(e["contribution"] for e in score_breakdown)))

    components = {
        e["component"]: {"raw": e["raw_value"], "weight": e["weight"], "weighted": e["contribution"]}
        for e in score_breakdown
    }

    return total, components, score_breakdown


def _decide_intent(zip_tier, score, config):
    decision = config["decision"]

    if zip_tier == "A":
        if score >= decision["tier_a_min_score_book"]:
            return "book_now", "SCORE_BOOK"
        return "collect_info_only", "SCORE_GATE"

    if zip_tier == "B":
        if score >= decision["tier_b_min_score_book"]:
            return "book_now", "SCORE_BOOK"
        return decision.get("tier_b_else", "collect_info_only"), "SCORE_GATE"

    if zip_tier == "C":
        return decision.get("tier_c_default", "route_to_human"), "DEFAULT_ROUTE"

    return decision.get("unknown_zip_default", "route_to_human"), "DEFAULT_ROUTE"


def _collect_thresholds(config, zip_tier):
    """Gather the exact config thresholds that were applied."""
    hs = config["hard_stops"]
    decision = config["decision"]
    thresholds = {
        "hard_stops": {
            "storm_confidence_min": hs["storm_confidence_min"],
            "hail_size_min_in": hs["hail_size_min_in"],
            "days_since_storm_max": hs["days_since_storm_max"],
            "capacity_zero": hs.get("capacity_zero", True),
            "block_unknown_zip": hs.get("block_unknown_zip", True),
            "block_owner_occupied_false": hs.get("block_owner_occupied_false", False),
        },
        "scoring": {
            "weights": config["scoring"]["weights"],
            "hail_size_curve": config["scoring"]["hail_size_curve"],
            "recency_curve_days": config["scoring"]["recency_curve_days"],
        },
    }

    if zip_tier == "A":
        thresholds["decision"] = {"min_score_book": decision["tier_a_min_score_book"]}
    elif zip_tier == "B":
        thresholds["decision"] = {
            "min_score_book": decision["tier_b_min_score_book"],
            "else": decision.get("tier_b_else", "collect_info_only"),
        }
    elif zip_tier == "C":
        thresholds["decision"] = {"default": decision.get("tier_c_default", "route_to_human")}
    else:
        thresholds["decision"] = {"default": decision.get("unknown_zip_default", "route_to_human")}

    return thresholds


def evaluate_call(input_data, config):
    """Evaluate a single lead against the rules config and return a decision dict."""

    config_error = _validate_config(config)
    if config_error:
        lead_id = input_data.get("lead_id", "UNKNOWN") if isinstance(input_data, dict) else "UNKNOWN"
        return _hard_stop_result(lead_id, config_error, "UNKNOWN", ["hard_stop:INVALID_CONFIG"])

    validation_error = _validate_input(input_data)
    if validation_error:
        lead_id = input_data.get("lead_id", "UNKNOWN") if isinstance(input_data, dict) else "UNKNOWN"
        return _hard_stop_result(lead_id, validation_error, "UNKNOWN", ["hard_stop:INVALID_INPUT"])

    lead_id = input_data["lead_id"]
    zip_tier = _resolve_zip_tier(input_data["zip"], config)

    hard_stop_reason, applied_rules = _check_hard_stops(input_data, config, zip_tier)
    if hard_stop_reason:
        return _hard_stop_result(lead_id, hard_stop_reason, zip_tier, applied_rules)

    score, components, score_breakdown = _compute_score(input_data, config, zip_tier)
    applied_rules.append("score_computed")

    call_intent, decision_path = _decide_intent(zip_tier, score, config)
    applied_rules.append(f"decision:{call_intent}")

    thresholds_used = _collect_thresholds(config, zip_tier)

    return {
        "lead_id": lead_id,
        "confidence_level": round(score, 4),
        "call_intent": call_intent,
        "hard_stop_reason": None,
        "debug": {
            "zip_tier": zip_tier,
            "score_components": components,
            "applied_rules": applied_rules,
            "decision_path": decision_path,
            "score_breakdown": score_breakdown,
            "thresholds_used": thresholds_used,
        },
    }