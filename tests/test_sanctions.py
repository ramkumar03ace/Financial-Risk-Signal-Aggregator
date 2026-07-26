"""
Tests for OFAC SDN snapshot loading and fuzzy sanctions matching.

The names below are real entries from data/sdn_snapshot.csv, which is a
point-in-time OFAC SDN snapshot downloaded on 2026-07-26.
"""

from src.sanctions import load_sdn_list, match_sanctions


def test_load_sdn_snapshot_contains_real_entries():
    entries = load_sdn_list()
    names = {entry["name"] for entry in entries}
    assert "BANCO NACIONAL DE CUBA" in names
    assert "AEROCARIBBEAN AIRLINES" in names
    assert "COMERCIAL CIMEX, S.A." in names
    assert "EMPRESA CUBANA DE AVIACION" in names


def test_missing_sdn_snapshot_degrades_to_empty_list(tmp_path):
    assert load_sdn_list(str(tmp_path / "missing_sdn.csv")) == []


def test_exact_sdn_matches_score_above_threshold():
    for name in [
        "BANCO NACIONAL DE CUBA",
        "AEROCARIBBEAN AIRLINES",
        "COMERCIAL CIMEX, S.A.",
        "EMPRESA CUBANA DE AVIACION",
    ]:
        match = match_sanctions(name)
        assert match is not None
        assert match["sdn_name"] == name
        assert match["score"] >= 0.99


def test_near_exact_sdn_match_scores_above_threshold():
    match = match_sanctions("Banco Nacional Cuba")
    assert match is not None
    assert match["sdn_name"] == "BANCO NACIONAL DE CUBA"
    assert match["program"] == "CUBA"
    assert match["score"] >= 0.88


def test_unrelated_name_does_not_match_sdn_threshold():
    assert match_sanctions("Priya Shah") is None
