import yaml
import pytest
from rules_engine import evaluate_call


@pytest.fixture
def config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


def _base_input(**overrides):
    data = {
        "lead_id": "TEST-001",
        "zip": "76016",
        "hail_size_in": 1.5,
        "storm_confidence": 0.9,
        "days_since_storm": 20,
        "owner_occupied": "true",
        "caller_intent": "inspection",
        "capacity_remaining": 10,
    }
    data.update(overrides)
    return data


class TestHardStops:

    def test_no_capacity(self, config):
        result = evaluate_call(_base_input(capacity_remaining=0), config)
        assert result["call_intent"] == "route_to_human"
        assert result["hard_stop_reason"] == "NO_CAPACITY"
        assert result["confidence_level"] == 0.0

    def test_low_storm_confidence(self, config):
        result = evaluate_call(_base_input(storm_confidence=0.2), config)
        assert result["call_intent"] == "route_to_human"
        assert result["hard_stop_reason"] == "LOW_STORM_CONFIDENCE"
        assert result["confidence_level"] == 0.0

    def test_hail_too_small(self, config):
        result = evaluate_call(_base_input(hail_size_in=0.5), config)
        assert result["call_intent"] == "route_to_human"
        assert result["hard_stop_reason"] == "HAIL_TOO_SMALL"

    def test_too_old(self, config):
        result = evaluate_call(_base_input(days_since_storm=400), config)
        assert result["call_intent"] == "route_to_human"
        assert result["hard_stop_reason"] == "TOO_OLD"

    def test_unknown_zip_blocked(self, config):
        result = evaluate_call(_base_input(zip="99999"), config)
        assert result["hard_stop_reason"] == "UNKNOWN_ZIP"

    def test_missing_field(self, config):
        data = _base_input()
        del data["zip"]
        result = evaluate_call(data, config)
        assert result["hard_stop_reason"] == "INVALID_INPUT"
