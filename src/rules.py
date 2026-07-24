"""
Deterministic rule engine.

Each rule is a small, independently testable function that inspects one
entity's data and returns zero or more Signals. Rules are the *only* thing
that can add points to a risk score — this keeps scoring explainable and
reproducible, which is non-negotiable in a compliance setting. The LLM never
scores; it only explains what these rules found.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

import config
from src.schemas import AlertHit, Signal


def _signal(code: str, evidence: str) -> Signal:
    return Signal(
        code=code,
        label=code.replace("_", " ").title(),
        weight=config.WEIGHTS[code],
        evidence=evidence,
    )


def rule_structuring(txns: pd.DataFrame) -> List[Signal]:
    cash = txns[
        txns["is_cash"]
        & (txns["amount"] >= config.STRUCTURING_LOWER)
        & (txns["amount"] <= config.STRUCTURING_UPPER)
    ].sort_values("timestamp")
    if len(cash) < config.STRUCTURING_MIN_COUNT:
        return []
    window = pd.Timedelta(days=config.STRUCTURING_WINDOW_DAYS)
    times = cash["timestamp"].tolist()
    for i in range(len(times)):
        in_window = [t for t in times if times[i] <= t <= times[i] + window]
        if len(in_window) >= config.STRUCTURING_MIN_COUNT:
            total = cash["amount"].sum()
            return [
                _signal(
                    "STRUCTURING",
                    f"{len(cash)} cash deposits between "
                    f"${config.STRUCTURING_LOWER:,} and ${config.STRUCTURING_UPPER:,} "
                    f"(total ${total:,.0f}) just under the ${config.CTR_THRESHOLD:,} "
                    f"reporting threshold within {config.STRUCTURING_WINDOW_DAYS} days.",
                )
            ]
    return []


def rule_high_value_wire(txns: pd.DataFrame) -> List[Signal]:
    wires = txns[txns["is_wire"] & (txns["amount"] >= config.HIGH_VALUE_WIRE_THRESHOLD)]
    if wires.empty:
        return []
    top = wires.loc[wires["amount"].idxmax()]
    return [
        _signal(
            "HIGH_VALUE_WIRE",
            f"Wire of ${top['amount']:,.0f} to '{top['counterparty']}' "
            f"exceeds the ${config.HIGH_VALUE_WIRE_THRESHOLD:,} review threshold.",
        )
    ]


def rule_high_risk_jurisdiction(txns: pd.DataFrame) -> List[Signal]:
    hits = txns[txns["counterparty_country"].isin(config.HIGH_RISK_COUNTRIES)]
    if hits.empty:
        return []
    detail = ", ".join(
        f"${r['amount']:,.0f} to '{r['counterparty']}' ({r['counterparty_country']})"
        for _, r in hits.iterrows()
    )
    return [
        _signal(
            "HIGH_RISK_JURISDICTION",
            f"Exposure to high-risk/sanctioned jurisdiction(s): {detail}.",
        )
    ]


def rule_velocity_spike(entity: Dict[str, Any]) -> List[Signal]:
    txns, profile, as_of = entity["txns"], entity["profile"], entity["as_of"]
    expected = float(profile.get("expected_monthly_volume") or 0)
    if expected <= 0:
        return []
    window_start = as_of - pd.Timedelta(days=config.VELOCITY_WINDOW_DAYS)
    recent_inflow = txns[
        (txns["direction"] == "in") & (txns["timestamp"] >= window_start)
    ]["amount"].sum()
    threshold = config.VELOCITY_MULTIPLIER * expected
    if recent_inflow >= threshold:
        return [
            _signal(
                "VELOCITY_SPIKE",
                f"Inflow of ${recent_inflow:,.0f} in the last "
                f"{config.VELOCITY_WINDOW_DAYS} days is "
                f"{recent_inflow / expected:.1f}x the expected monthly volume "
                f"of ${expected:,.0f}.",
            )
        ]
    return []


def rule_dormant_reactivation(txns: pd.DataFrame) -> List[Signal]:
    if len(txns) < 2:
        return []
    ordered = txns.sort_values("timestamp").reset_index(drop=True)
    gap = pd.Timedelta(days=config.DORMANCY_DAYS)
    for i in range(1, len(ordered)):
        silence = ordered.loc[i, "timestamp"] - ordered.loc[i - 1, "timestamp"]
        if silence >= gap and ordered.loc[i, "amount"] >= config.DORMANCY_REACTIVATION_MIN:
            return [
                _signal(
                    "DORMANT_REACTIVATION",
                    f"Account dormant for {silence.days} days, then reactivated with a "
                    f"${ordered.loc[i, 'amount']:,.0f} movement on "
                    f"{ordered.loc[i, 'timestamp'].date()}.",
                )
            ]
    return []


def rule_pass_through(txns: pd.DataFrame) -> List[Signal]:
    inflows = txns[
        (txns["direction"] == "in") & (txns["amount"] >= config.PASS_THROUGH_MIN)
    ]
    window = pd.Timedelta(hours=config.PASS_THROUGH_WINDOW_HOURS)
    for _, inflow in inflows.iterrows():
        outflow_sum = txns[
            (txns["direction"] == "out")
            & (txns["timestamp"] >= inflow["timestamp"])
            & (txns["timestamp"] <= inflow["timestamp"] + window)
        ]["amount"].sum()
        if outflow_sum >= config.PASS_THROUGH_RATIO * inflow["amount"]:
            pct = outflow_sum / inflow["amount"] * 100
            return [
                _signal(
                    "PASS_THROUGH",
                    f"${inflow['amount']:,.0f} received then ${outflow_sum:,.0f} "
                    f"({pct:.0f}%) sent out within "
                    f"{config.PASS_THROUGH_WINDOW_HOURS}h — classic layering pattern.",
                )
            ]
    return []


def rule_round_number(txns: pd.DataFrame) -> List[Signal]:
    wires = txns[
        txns["is_wire"]
        & (txns["amount"] >= config.ROUND_NUMBER_DIVISOR)
        & (txns["amount"] % config.ROUND_NUMBER_DIVISOR == 0)
    ]
    if wires.empty:
        return []
    amounts = ", ".join(f"${a:,.0f}" for a in wires["amount"].tolist())
    return [
        _signal(
            "ROUND_NUMBER",
            f"Round-figure wire(s) ({amounts}) — uncommon in genuine trade flows.",
        )
    ]


def rule_kyc_incomplete(profile: Dict[str, Any]) -> List[Signal]:
    status = str(profile.get("kyc_status", "")).lower()
    if status and status != "verified":
        return [_signal("KYC_INCOMPLETE", f"KYC status is '{status}', not verified.")]
    return []


def rule_pep_exposure(profile: Dict[str, Any]) -> List[Signal]:
    if profile.get("is_pep"):
        occ = profile.get("occupation", "unknown role")
        return [
            _signal(
                "PEP_EXPOSURE",
                f"Customer is a Politically Exposed Person ({occ}).",
            )
        ]
    return []


def rule_cash_intensive(txns: pd.DataFrame) -> List[Signal]:
    inflow = txns[txns["direction"] == "in"]["amount"].sum()
    cash_inflow = txns[txns["is_cash"]]["amount"].sum()
    if inflow >= 5000 and cash_inflow / inflow > config.CASH_INTENSIVE_RATIO:
        return [
            _signal(
                "CASH_INTENSIVE",
                f"Cash makes up {cash_inflow / inflow * 100:.0f}% of inflow "
                f"(${cash_inflow:,.0f} of ${inflow:,.0f}).",
            )
        ]
    return []


def rule_adverse_media(
    profile: Dict[str, Any], adverse_hits: List[AlertHit]
) -> List[Signal]:
    cid = profile["customer_id"]
    min_sev = config.SEVERITY_ORDER[config.ADVERSE_MEDIA_MIN_SEVERITY]
    relevant = [
        h
        for h in adverse_hits
        if h.entity_id == cid
        and config.SEVERITY_ORDER.get(h.severity.lower(), 0) >= min_sev
    ]
    if not relevant:
        return []
    summary = "; ".join(f"[{h.severity}] {h.summary}" for h in relevant)
    return [_signal("ADVERSE_MEDIA", f"External alert(s): {summary}")]


def run_all_rules(
    entity: Dict[str, Any], adverse_hits: Optional[List[AlertHit]] = None
) -> List[Signal]:
    """Run every rule for one entity and return all fired signals."""
    txns = entity["txns"]
    profile = entity["profile"]
    adverse_hits = adverse_hits or []

    signals: List[Signal] = []
    signals += rule_structuring(txns)
    signals += rule_high_value_wire(txns)
    signals += rule_high_risk_jurisdiction(txns)
    signals += rule_velocity_spike(entity)
    signals += rule_dormant_reactivation(txns)
    signals += rule_pass_through(txns)
    signals += rule_round_number(txns)
    signals += rule_kyc_incomplete(profile)
    signals += rule_pep_exposure(profile)
    signals += rule_cash_intensive(txns)
    signals += rule_adverse_media(profile, adverse_hits)
    return signals
