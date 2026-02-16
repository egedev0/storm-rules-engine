import yaml
import pytest
from wrapper import process_lead


@pytest.fixture
def config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


def _lead(**overrides):
    data = {
        "lead_id": "L-1001",
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


class TestProcessLead:

    def test_book_now_output(self, config):
        result = process_lead(_lead(), config)
        assert result["lead_id"] == "L-1001"
        assert result["call_intent"] == "book_now"
        assert result["booking_allowed"] is True
        assert result["confidence_level"] > 0.0
        assert result["hard_stop_reason"] is None
        assert "explain" not in result

    def test_collect_info_output(self, config):
        result = process_lead(
            _lead(zip="76010", hail_size_in=1.0, storm_confidence=0.5,
                  days_since_storm=100, owner_occupied="unknown"),
            config,
        )
        assert result["call_intent"] == "collect_info_only"
        assert result["booking_allowed"] is False
        assert result["hard_stop_reason"] is None
        assert "explain" not in result

    def test_hard_stop_output(self, config):
        result = process_lead(_lead(capacity_remaining=0), config)
        assert result["call_intent"] == "route_to_human"
        assert result["booking_allowed"] is False
        assert result["hard_stop_reason"] == "NO_CAPACITY"
        assert result["confidence_level"] == 0.0

    def test_debug_includes_explain(self, config):
        result = process_lead(_lead(), config, debug=True)
        assert "explain" in result
        assert "decision_path" in result["explain"]
        assert "score_breakdown" in result["explain"]

    def test_debug_false_excludes_explain(self, config):
        result = process_lead(_lead(), config, debug=False)
        assert "explain" not in result

    def test_output_contract_keys(self, config):
        result = process_lead(_lead(), config)
        expected_keys = {"lead_id", "call_intent", "booking_allowed",
                         "confidence_level", "hard_stop_reason"}
        assert set(result.keys()) == expected_keys
