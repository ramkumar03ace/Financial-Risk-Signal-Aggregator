"""
Tests that the planted scenarios in the sample dataset produce the expected
risk tiers. These double as living documentation of what "good" looks like and
guard against silent regressions when rule weights/thresholds are tuned.
"""

import os

import pytest

import config
from src import llm
from src.ingestion import build_entities, load_alerts, load_customers, load_transactions
from src.scoring import build_risk_register, score_signals

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


@pytest.fixture(scope="module")
def sample():
    txns = load_transactions(os.path.join(DATA, "transactions.csv"))
    customers = load_customers(os.path.join(DATA, "customers.json"))
    alerts = load_alerts(os.path.join(DATA, "external_alerts.txt"))
    entities = build_entities(txns, customers)
    name_map = {c["customer_id"]: c["name"] for c in customers}
    return entities, alerts, name_map


def _by_name(register):
    return {er.name: er for er in register}


def test_deterministic_tiers(sample):
    """Rules-only (no external alerts) must land in these tiers."""
    entities, _, _ = sample
    reg = _by_name(build_risk_register(entities))
    assert reg["Ravi Menon"].tier == "High"
    assert reg["John Doe"].tier == "High"
    assert reg["Wei Chen"].tier == "High"
    assert reg["Sara Lopez"].tier == "Medium"
    assert reg["Priya Shah"].tier == "Low"


def test_control_case_has_no_signals(sample):
    """The control customer must NOT be over-flagged (proves precision)."""
    entities, _, _ = sample
    reg = _by_name(build_risk_register(entities))
    assert reg["Priya Shah"].score == 0
    assert reg["Priya Shah"].num_signals == 0


def test_adverse_media_escalates_to_critical(sample):
    """Unstructured alerts should push structuring/PEP cases to Critical."""
    entities, alerts, name_map = sample
    hits = llm.extract_alerts(alerts, name_map)  # heuristic fallback if no key
    reg = _by_name(build_risk_register(entities, hits))
    assert reg["Ravi Menon"].tier == "Critical"
    assert reg["John Doe"].tier == "Critical"


def test_clean_customer_not_extracted(sample):
    """The 'no adverse findings' customer must not get an adverse-media hit."""
    _, alerts, name_map = sample
    hits = llm.extract_alerts(alerts, name_map)
    flagged_ids = {h.entity_id for h in hits}
    assert "cust_004" not in flagged_ids  # Priya Shah — explicitly clean


def test_expected_signals_present(sample):
    """Spot-check that the right rules fire for the right customers."""
    entities, _, _ = sample
    reg = _by_name(build_risk_register(entities))
    assert "STRUCTURING" in reg["Ravi Menon"].signal_codes
    assert "PASS_THROUGH" in reg["Wei Chen"].signal_codes
    assert "HIGH_RISK_JURISDICTION" in reg["John Doe"].signal_codes
    assert "PEP_EXPOSURE" in reg["John Doe"].signal_codes
    assert "KYC_INCOMPLETE" in reg["Sara Lopez"].signal_codes


def test_score_is_capped_at_100():
    """Even many signals cannot exceed 100."""
    from src.schemas import Signal

    huge = [Signal(code="X", label="X", weight=40, evidence="e") for _ in range(5)]
    assert score_signals(huge) == 100


def test_tier_mapping():
    assert config.score_to_tier(80) == "Critical"
    assert config.score_to_tier(60) == "High"
    assert config.score_to_tier(30) == "Medium"
    assert config.score_to_tier(0) == "Low"
