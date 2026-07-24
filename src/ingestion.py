"""
Ingestion & normalisation layer.

Accepts the three fragmented sources — transactions (CSV), customer/account
records (JSON) and free-text external alerts — and turns them into one clean,
per-entity structure the rule engine can reason over.
"""

from __future__ import annotations

import io
import json
from typing import Any, Dict, List, Union

import pandas as pd

# Direction / classification of transaction types.
INFLOW_TYPES = {"cash_deposit", "deposit", "wire_in", "salary", "credit"}
OUTFLOW_TYPES = {"cash_withdrawal", "withdrawal", "wire_out", "payment", "debit"}
CASH_TYPES = {"cash_deposit", "cash_withdrawal"}
WIRE_TYPES = {"wire_in", "wire_out"}

Source = Union[str, bytes, io.IOBase, pd.DataFrame]

REQUIRED_TXN_COLS = [
    "txn_id",
    "timestamp",
    "customer_id",
    "amount",
    "txn_type",
]


def load_transactions(source: Source) -> pd.DataFrame:
    """Load transactions from a CSV path/buffer or an existing DataFrame."""
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        df = pd.read_csv(source)

    missing = [c for c in REQUIRED_TXN_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Transactions missing required columns: {missing}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    for col in ("counterparty", "counterparty_country", "channel"):
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("")
    df["direction"] = df["txn_type"].apply(_direction)
    df["is_cash"] = df["txn_type"].isin(CASH_TYPES)
    df["is_wire"] = df["txn_type"].isin(WIRE_TYPES)
    return df.sort_values("timestamp").reset_index(drop=True)


def load_customers(source: Source) -> List[Dict[str, Any]]:
    """Load customer records from a JSON path/buffer, raw string, or list."""
    if isinstance(source, list):
        return source
    if isinstance(source, (str, bytes)) and _looks_like_json_text(source):
        return json.loads(source)
    if hasattr(source, "read"):
        return json.load(source)
    with open(source, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_alerts(source: Source) -> str:
    """Load the unstructured alerts as a single text blob."""
    if isinstance(source, str) and not _looks_like_path(source):
        return source
    if hasattr(source, "read"):
        data = source.read()
        return data.decode("utf-8") if isinstance(data, bytes) else data
    with open(source, "r", encoding="utf-8") as fh:
        return fh.read()


def build_entities(
    txns: pd.DataFrame, customers: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Join transactions to customer profiles on customer_id.

    Returns: { customer_id: {"profile": {...}, "txns": DataFrame, "as_of": Timestamp} }
    """
    as_of = txns["timestamp"].max() if not txns.empty else pd.Timestamp.now()
    entities: Dict[str, Dict[str, Any]] = {}
    for cust in customers:
        cid = cust["customer_id"]
        cust_txns = txns[txns["customer_id"] == cid].sort_values("timestamp")
        entities[cid] = {
            "profile": cust,
            "txns": cust_txns.reset_index(drop=True),
            "as_of": as_of,
        }
    return entities


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _direction(txn_type: str) -> str:
    if txn_type in INFLOW_TYPES:
        return "in"
    if txn_type in OUTFLOW_TYPES:
        return "out"
    return "other"


def _looks_like_json_text(source: Union[str, bytes]) -> bool:
    text = source.decode("utf-8") if isinstance(source, bytes) else source
    return text.lstrip().startswith(("[", "{"))


def _looks_like_path(source: str) -> bool:
    return source.endswith((".txt", ".md", ".csv", ".json")) and "\n" not in source
