"""
OFAC SDN sanctions screening helpers.

The committed CSV is a point-in-time snapshot downloaded from OFAC on
2026-07-26. A production service should refresh this list on a schedule and
record the source timestamp, but this demo intentionally avoids live network
calls during app startup.
"""

from __future__ import annotations

import csv
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

try:
    from rapidfuzz import fuzz

    _RAPIDFUZZ_AVAILABLE = True
except Exception:  # pragma: no cover - difflib fallback keeps app resilient
    fuzz = None
    _RAPIDFUZZ_AVAILABLE = False


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SDN_PATH = ROOT / "data" / "sdn_snapshot.csv"


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _clean(value: str) -> str:
    cleaned = (value or "").strip()
    return "" if cleaned == "-0-" else cleaned


@lru_cache(maxsize=1)
def load_sdn_list(path: str = str(DEFAULT_SDN_PATH)) -> List[dict]:
    """Load OFAC SDN rows as {name, program, sdn_type} dicts."""
    sdn_path = Path(path)
    if not sdn_path.exists():
        return []

    entries: List[dict] = []
    try:
        with sdn_path.open(encoding="utf-8-sig", newline="") as fh:
            rows = csv.reader(fh)
            for row in rows:
                if not row:
                    continue
                if row[0].lower() in {"ent_num", "ent num"}:
                    continue
                if len(row) < 4:
                    continue
                name = _clean(row[1])
                if not name:
                    continue
                entries.append(
                    {
                        "name": name,
                        "program": _clean(row[3]),
                        "sdn_type": _clean(row[2]),
                    }
                )
    except OSError:
        return []
    return entries


@lru_cache(maxsize=1)
def _normalized_sdn_entries(path: str = str(DEFAULT_SDN_PATH)) -> tuple[dict, ...]:
    return tuple(
        {**entry, "normalized_name": _normalize(entry["name"])}
        for entry in load_sdn_list(path)
    )


@lru_cache(maxsize=4096)
def match_sanctions(name: str, threshold: float = 0.88) -> Optional[dict]:
    """Return the best OFAC SDN fuzzy match for a name above threshold."""
    query = _normalize(name or "")
    if not query:
        return None

    best_entry: Optional[Dict[str, str]] = None
    best_score = 0.0
    query_len = len(query)
    # rapidfuzz is preferred because the SDN snapshot is large and Streamlit
    # reruns often; difflib remains as a dependency-free fallback.
    for entry in _normalized_sdn_entries():
        candidate = entry["normalized_name"]
        candidate_len = len(candidate)
        max_possible = 2 * min(query_len, candidate_len) / (query_len + candidate_len)
        if max_possible < threshold:
            continue
        if _RAPIDFUZZ_AVAILABLE:
            score = fuzz.ratio(query, candidate) / 100
        else:
            matcher = SequenceMatcher(None, query, candidate)
            if matcher.quick_ratio() < threshold:
                continue
            score = matcher.ratio()
        if score > best_score:
            best_score = score
            best_entry = entry

    if best_entry and best_score >= threshold:
        return {
            "sdn_name": best_entry["name"],
            "program": best_entry["program"],
            "sdn_type": best_entry["sdn_type"],
            "score": best_score,
        }
    return None
