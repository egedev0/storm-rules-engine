# Storm-Damage Lead Scoring Engine

Deterministic rules engine that evaluates storm-damage leads and returns a call-routing decision.

## Files

- `rules_engine.py` — main engine with `evaluate_call(input_data, config)`
- `config.yaml` — all thresholds, tiers, weights, and mappings
- `test_rules_engine.py` — pytest test suite

## Run Tests

```bash
pip install pytest pyyaml
pytest test_rules_engine.py -v
```

## Config

Edit `config.yaml` to adjust thresholds, ZIP tiers, or scoring weights. No code changes needed.

## Example

```python
import yaml
from rules_engine import evaluate_call

with open("config.yaml") as f:
    config = yaml.safe_load(f)

result = evaluate_call({
    "lead_id": "L-1001",
    "zip": "76016",
    "hail_size_in": 1.5,
    "storm_confidence": 0.9,
    "days_since_storm": 20,
    "owner_occupied": "true",
    "caller_intent": "inspection",
    "capacity_remaining": 10
}, config)

print(result)
```

### Hard stop example

```python
result = evaluate_call({
    "lead_id": "L-1002",
    "zip": "76016",
    "hail_size_in": 1.5,
    "storm_confidence": 0.9,
    "days_since_storm": 20,
    "owner_occupied": "true",
    "caller_intent": "inspection",
    "capacity_remaining": 0
}, config)

# result["hard_stop_reason"] == "NO_CAPACITY"
# result["call_intent"] == "route_to_human"
# result["confidence_level"] == 0.0
```
