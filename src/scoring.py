"""
Signal aggregation, scoring and prioritisation.

Turns the per-entity signals from the rule engine into a capped 0-100 score, a
risk tier, and a ranked register. Sorting is deliberate: highest score first,
then the entity with the most *distinct* independent signals (a stronger case
than one big signal), then the single heaviest signal.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import config
from src.rules import run_all_rules
from src.schemas import AlertHit, EntityRisk, Signal


def score_signals(signals: List[Signal]) -> int:
    """Sum signal weights, capped at 100."""
    return min(100, sum(s.weight for s in signals))


def assess_entity(
    entity: Dict[str, Any], adverse_hits: Optional[List[AlertHit]] = None
) -> EntityRisk:
    """Run the rules for one entity and build its scored risk view."""
    adverse_hits = adverse_hits or []
    signals = run_all_rules(entity, adverse_hits)
    score = score_signals(signals)
    my_hits = [h for h in adverse_hits if h.entity_id == entity["profile"]["customer_id"]]
    return EntityRisk(
        customer_id=entity["profile"]["customer_id"],
        name=entity["profile"].get("name", entity["profile"]["customer_id"]),
        score=score,
        tier=config.score_to_tier(score),
        signals=signals,
        alert_hits=my_hits,
    )


def _rank_key(er: EntityRisk):
    heaviest = max((s.weight for s in er.signals), default=0)
    return (-er.score, -er.num_signals, -heaviest)


def rank_entities(entities_risk: List[EntityRisk]) -> List[EntityRisk]:
    """Return entities sorted from most to least risky."""
    return sorted(entities_risk, key=_rank_key)


def build_risk_register(
    entities: Dict[str, Dict[str, Any]],
    adverse_hits: Optional[List[AlertHit]] = None,
) -> List[EntityRisk]:
    """Assess every entity and return the ranked risk register (no LLM)."""
    assessed = [assess_entity(e, adverse_hits) for e in entities.values()]
    return rank_entities(assessed)


# ---------------------------------------------------------------------------
# CLI sanity check — run:  python -m src.scoring
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os

    from src.ingestion import build_entities, load_customers, load_transactions

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    txns = load_transactions(os.path.join(here, "data", "transactions.csv"))
    customers = load_customers(os.path.join(here, "data", "customers.json"))
    entities = build_entities(txns, customers)
    register = build_risk_register(entities)

    print(f"\n{'RANK':<5}{'CUSTOMER':<16}{'SCORE':<7}{'TIER':<10}{'SIGNALS'}")
    print("-" * 78)
    for i, er in enumerate(register, 1):
        codes = ", ".join(er.signal_codes) or "(none)"
        print(f"{i:<5}{er.name:<16}{er.score:<7}{er.tier:<10}{codes}")
    print()
