import yaml
import pytest
from datetime import date, timedelta
from wrapper import process_lead, map_sheet_row


@pytest.fixture
def config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


def _lead(**overrides):
    storm_date = (date.today() - timedelta(days=overrides.pop("days_since_storm", 20))).isoformat()
    data = {
        "lead_id": "L-1001",
        "Zip": "76016",
        "hail_size_in": 1.5,
        "storm_confidence": 0.9,
        "storm_date": storm_date,
        "owner_occupied": "true",
        "caller_intent": "inspection",
        "capacity_remaining": 10,
    }
    data.update(overrides)
    return data


def _sheet_row(**overrides):
    data = {
        "Address": "2315 Englishoak Dr",
        "City": "Arlington",
        "State": "TX",
        "Zip": "76016.0",
        "Owner 1 First Name": "Maikhanh",
        "Owner 1 Last Name": "Ho",
        "Email": "test@example.com",
        "Mobile": "512-539-7008",
        "selected_phone": "15125397008",
        "contact_strategy": "call",
        "decision_reason": "Callable non-DNC phone found",
        "storm_date": None,
        "hail_size_in": None,
        "storm_confidence": None,
        "owner_occupied": None,
        "capacity_remaining": None,
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
            _lead(Zip="76010", hail_size_in=1.0, storm_confidence=0.5,
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


class TestMapSheetRow:

    def test_zip_strips_decimal(self, config):
        mapped = map_sheet_row(_sheet_row(Zip="76016.0"), config)
        assert mapped["zip"] == "76016"

    def test_zip_plain_string(self, config):
        mapped = map_sheet_row(_sheet_row(Zip="76016"), config)
        assert mapped["zip"] == "76016"

    def test_defaults_fill_missing_fields(self, config):
        mapped = map_sheet_row(_sheet_row(), config)
        assert mapped["hail_size_in"] == 1.5
        assert mapped["storm_confidence"] == 0.9
        assert mapped["owner_occupied"] == "unknown"
        assert mapped["capacity_remaining"] == 10

    def test_sheet_values_override_defaults(self, config):
        mapped = map_sheet_row(
            _sheet_row(hail_size_in=1.25, storm_confidence=0.7,
                       owner_occupied="true", capacity_remaining=5),
            config,
        )
        assert mapped["hail_size_in"] == 1.25
        assert mapped["storm_confidence"] == 0.7
        assert mapped["owner_occupied"] == "true"
        assert mapped["capacity_remaining"] == 5

    def test_days_since_storm_from_storm_date(self, config):
        yesterday = (date.today() - timedelta(days=10)).isoformat()
        mapped = map_sheet_row(_sheet_row(storm_date=yesterday), config)
        assert mapped["days_since_storm"] == 10

    def test_days_since_storm_from_default_date(self, config):
        mapped = map_sheet_row(_sheet_row(), config)
        expected = (date.today() - date(2025, 3, 8)).days
        assert mapped["days_since_storm"] == expected

    def test_lead_id_from_owner_name(self, config):
        mapped = map_sheet_row(_sheet_row(), config)
        assert mapped["lead_id"] == "Maikhanh Ho"

    def test_lead_id_falls_back_to_zip(self, config):
        row = _sheet_row()
        row["Owner 1 First Name"] = None
        row["Owner 1 Last Name"] = None
        mapped = map_sheet_row(row, config)
        assert mapped["lead_id"] == "76016"

    def test_full_sheet_row_produces_valid_output(self, config):
        result = process_lead(_sheet_row(), config)
        assert result["call_intent"] in ("book_now", "collect_info_only", "route_to_human")
        assert isinstance(result["booking_allowed"], bool)
        assert isinstance(result["confidence_level"], float)

    def test_non_numeric_hail_returns_invalid_input(self, config):
        result = process_lead(_sheet_row(hail_size_in="abc"), config)
        assert result["call_intent"] == "route_to_human"
        assert result["booking_allowed"] is False
        assert result["hard_stop_reason"] == "INVALID_INPUT"

    def test_non_numeric_confidence_returns_invalid_input(self, config):
        result = process_lead(_sheet_row(storm_confidence="xyz"), config)
        assert result["call_intent"] == "route_to_human"
        assert result["booking_allowed"] is False
        assert result["hard_stop_reason"] == "INVALID_INPUT"
