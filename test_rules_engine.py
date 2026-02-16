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


class TestScoringAndDecision:

    def test_tier_a_book_now(self, config):
        result = evaluate_call(
            _base_input(zip="76016", hail_size_in=1.5, storm_confidence=0.9,
                        days_since_storm=20, owner_occupied="true"),
            config,
        )
        assert result["hard_stop_reason"] is None
        assert result["call_intent"] == "book_now"
        assert result["confidence_level"] > 0.0

    def test_tier_a_below_threshold(self, config):
        result = evaluate_call(
            _base_input(zip="76016", hail_size_in=1.0, storm_confidence=0.36,
                        days_since_storm=300, owner_occupied="unknown"),
            config,
        )
        assert result["hard_stop_reason"] is None
        assert result["call_intent"] == "collect_info_only"

    def test_tier_b_book_now(self, config):
        result = evaluate_call(
            _base_input(zip="76010", hail_size_in=1.5, storm_confidence=0.9,
                        days_since_storm=20, owner_occupied="true"),
            config,
        )
        assert result["hard_stop_reason"] is None
        assert result["call_intent"] == "book_now"

    def test_tier_b_gated_collect_info(self, config):
        result = evaluate_call(
            _base_input(zip="76010", hail_size_in=1.0, storm_confidence=0.5,
                        days_since_storm=100, owner_occupied="unknown"),
            config,
        )
        assert result["hard_stop_reason"] is None
        assert result["call_intent"] == "collect_info_only"

    def test_tier_c_always_routes(self, config):
        result = evaluate_call(
            _base_input(zip="76101", hail_size_in=1.5, storm_confidence=0.9,
                        days_since_storm=20, owner_occupied="true"),
            config,
        )
        assert result["hard_stop_reason"] is None
        assert result["call_intent"] == "route_to_human"


class TestBorderlineCases:

    def test_storm_confidence_at_threshold(self, config):
        result = evaluate_call(_base_input(storm_confidence=0.35), config)
        assert result["hard_stop_reason"] is None

    def test_storm_confidence_just_below(self, config):
        result = evaluate_call(_base_input(storm_confidence=0.34), config)
        assert result["hard_stop_reason"] == "LOW_STORM_CONFIDENCE"

    def test_hail_size_at_threshold(self, config):
        result = evaluate_call(_base_input(hail_size_in=1.0), config)
        assert result["hard_stop_reason"] is None

    def test_hail_size_just_below(self, config):
        result = evaluate_call(_base_input(hail_size_in=0.99), config)
        assert result["hard_stop_reason"] == "HAIL_TOO_SMALL"

    def test_days_since_storm_at_max(self, config):
        result = evaluate_call(_base_input(days_since_storm=365), config)
        assert result["hard_stop_reason"] is None

    def test_days_since_storm_just_over(self, config):
        result = evaluate_call(_base_input(days_since_storm=366), config)
        assert result["hard_stop_reason"] == "TOO_OLD"

