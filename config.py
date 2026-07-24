"""
Central configuration for the Financial Risk Signal Aggregator.

Every threshold, weight and tier cut-off lives here so the risk model stays
transparent and auditable — a compliance analyst can trace exactly why any
score is what it is by reading this one file.
"""

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
# Use the rolling "-latest" aliases rather than pinned version numbers: Google
# retires pinned free-tier model versions for new API keys fairly quickly, and
# the aliases keep pointing at whatever current model those keys can access.
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
FALLBACK_GEMINI_MODEL = "gemini-flash-lite-latest"

# ---------------------------------------------------------------------------
# Rule thresholds
# ---------------------------------------------------------------------------
# Currency Transaction Report threshold — cash reports required at/above this.
CTR_THRESHOLD = 10_000

# Structuring / smurfing: several cash deposits placed just under the CTR line.
STRUCTURING_LOWER = 9_000
STRUCTURING_UPPER = 9_999
STRUCTURING_MIN_COUNT = 3
STRUCTURING_WINDOW_DAYS = 7

# Large single transfers.
HIGH_VALUE_WIRE_THRESHOLD = 50_000

# Velocity spike: recent inflow greatly exceeds the customer's expected volume.
VELOCITY_MULTIPLIER = 5
VELOCITY_WINDOW_DAYS = 30

# Dormant-then-active: a long silence broken by a large movement.
DORMANCY_DAYS = 180
DORMANCY_REACTIVATION_MIN = 50_000

# Pass-through / layering: money in, almost the same amount straight back out.
PASS_THROUGH_WINDOW_HOURS = 48
PASS_THROUGH_RATIO = 0.90
PASS_THROUGH_MIN = 50_000

# Round-number wires.
ROUND_NUMBER_DIVISOR = 10_000

# Cash-intensive: cash makes up most of the inflow.
CASH_INTENSIVE_RATIO = 0.60

# Adverse-media severity (from LLM extraction) that counts as a signal.
ADVERSE_MEDIA_MIN_SEVERITY = "medium"  # one of: low, medium, high

# High-risk / sanctioned counterparty jurisdictions (illustrative, ISO-2 codes).
HIGH_RISK_COUNTRIES = {"IR", "KP", "SY", "MM", "AF", "RU"}

# ---------------------------------------------------------------------------
# Signal weights (points added to the raw score when a rule fires)
# ---------------------------------------------------------------------------
WEIGHTS = {
    "STRUCTURING": 30,
    "HIGH_VALUE_WIRE": 15,
    "HIGH_RISK_JURISDICTION": 25,
    "VELOCITY_SPIKE": 20,
    "DORMANT_REACTIVATION": 20,
    "PASS_THROUGH": 25,
    "ROUND_NUMBER": 5,
    "KYC_INCOMPLETE": 10,
    "PEP_EXPOSURE": 15,
    "CASH_INTENSIVE": 10,
    "ADVERSE_MEDIA": 20,
}

# ---------------------------------------------------------------------------
# Risk tiers (score is capped at 100)
# ---------------------------------------------------------------------------
TIER_CUTOFFS = [
    (75, "Critical"),
    (50, "High"),
    (25, "Medium"),
    (0, "Low"),
]

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3}

# Recommended actions the LLM (and fallback) may choose from.
RECOMMENDED_ACTIONS = [
    "Monitor",
    "Enhanced Due Diligence",
    "Escalate to MLRO",
    "File SAR",
]


def score_to_tier(score: int) -> str:
    """Map a 0-100 score to its risk tier."""
    for cutoff, tier in TIER_CUTOFFS:
        if score >= cutoff:
            return tier
    return "Low"
