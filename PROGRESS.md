# PROGRESS — Financial Risk Signal Aggregator

> Status handoff for any agent/developer picking this up. Read this first, then
> [PLAN.md](PLAN.md) for the full design rationale.

**Last updated:** 2026-07-24
**Overall status:** ✅ Working prototype complete and verified end-to-end (local).
Remaining: GitHub push + Streamlit Cloud deploy, screenshots, demo video, 5-slide deck.

---

## TL;DR of what exists

A runnable Streamlit app that ingests CSV + JSON + free-text alerts and outputs a
prioritised, risk-scored register with per-entity AI rationale. Deterministic rule
engine computes the score; Gemini (with a full no-key fallback) parses unstructured
alerts and writes the narrative. All tests pass; app boots clean.

Run it: `.venv\Scripts\activate` → `streamlit run app.py` → **Load sample dataset** →
**Run risk analysis**.

---

## Build status by component

| Component | File | Status | Notes |
|---|---|---|---|
| Dependencies | `requirements.txt` | ✅ | Uses modern `google-genai` (not deprecated `google-generativeai`) |
| Config (weights/thresholds/tiers) | `config.py` | ✅ | Single source of truth; all rules read from here |
| Data models | `src/schemas.py` | ✅ | pydantic: `Signal`, `AlertHit`, `EntityRisk` |
| Ingestion + join | `src/ingestion.py` | ✅ | CSV/JSON/text; joins on `customer_id`; derives direction/is_cash/is_wire |
| Rule engine (11 rules) | `src/rules.py` | ✅ | Pure functions, independently testable |
| Scoring + ranking | `src/scoring.py` | ✅ | 0–100 cap, tiers, tie-broken rank; has `python -m src.scoring` CLI |
| LLM layer | `src/llm.py` | ✅ | Gemini extract/rationale/summary/Q&A + heuristic + templated fallbacks |
| Prompts | `prompts/*.txt` | ✅ | 4 templates, all demand strict JSON / grounded output |
| Streamlit app | `app.py` | ✅ | 5 tabs: Overview, Register, Drill-down, Ask, Export |
| Sample dataset | `data/*` | ✅ | 5 planted scenarios incl. a clean control case |
| Tests | `tests/test_scoring.py` | ✅ | 7 tests, all passing |
| README (1-page) | `README.md` | ✅ | Approach, stack, data assumptions, example I/O, deploy |
| **Deployment** | Streamlit Cloud | ⬜ | Not done — needs GitHub repo + secrets |
| **Screenshots** | `docs/screenshots/` | ⬜ | Not captured yet |
| **Demo video (<3 min)** | — | ⬜ | Not recorded |
| **5-slide deck** | — | ⬜ | Not built (structure specified in PLAN.md §13) |

---

## Verified results (reproducible)

`python -m src.scoring` (rules only, no LLM) →

| Rank | Customer | Score | Tier | Signals |
|---|---|---|---|---|
| 1 | Wei Chen | 65 | High | high-value wire, dormant reactivation, pass-through, round number |
| 2 | John Doe | 60 | High | high-value wire, high-risk jurisdiction, round number, PEP |
| 3 | Ravi Menon | 60 | High | structuring, velocity spike, cash intensive |
| 4 | Sara Lopez | 30 | Medium | velocity spike, KYC incomplete |
| 5 | Priya Shah | 0 | Low | (none — control case) |

With external alerts processed, **Ravi Menon and John Doe escalate to Critical (80)**
via the `ADVERSE_MEDIA` signal — the intended "unstructured data changes the picture"
demo moment. The clean customer (Priya) is correctly *not* flagged.

- `pytest -q` → **7 passed**.
- `streamlit run app.py` → boots healthy (HTTP 200), no errors.

---

## Environment notes (important for reproducing)

- **Python:** 3.12.6 at `C:\Python312`.
- The **global pip was broken** (`No module named 'pip'`) and the global site-packages
  had **write-permission issues**. Fixed by creating a **project virtualenv** at `.venv`.
- **Always use the venv:** `.venv\Scripts\python.exe` / `.venv\Scripts\streamlit.exe`.
- Deps are installed in `.venv` (pandas, pydantic, streamlit, plotly, pytest,
  google-genai). `.venv/` and `.env` are gitignored.
- **No Gemini API key is set yet** → the app currently runs in **fallback mode**
  (rules + heuristic extraction + templated rationale). It is fully functional this
  way; adding `GEMINI_API_KEY` upgrades the narrative quality. Get a free key at
  https://aistudio.google.com/apikey and put it in `.env`.

---

## Key design decisions (so you don't undo them)

1. **Rules score, LLM explains.** Never let the LLM compute or alter the numeric
   score — this is the core selling point for a compliance audience.
2. **Graceful degradation.** Every LLM call has a fallback; the app must never break
   because a key is missing or an API call fails.
3. **Planted, story-driven sample data.** Amounts/dates are tuned so specific rules
   fire; the control case proves precision. If you change `config.py` weights or the
   sample data, re-run `pytest` — the scenario tests will catch regressions.
4. **Everything tunable in `config.py`** to keep scoring auditable.

---

## Next steps (to finish the submission)

1. `git init` → push to GitHub.
2. Deploy to Streamlit Community Cloud; add `GEMINI_API_KEY` in Secrets; capture the URL.
3. Take screenshots of Overview + Drill-down (Ravi Menon) → `docs/screenshots/`.
4. Record a <3-min demo (script in PLAN.md §12).
5. Build the 5-slide deck (structure + content in PLAN.md §13).
6. (Optional polish) add a real sanctions-list check; more sample entities.
