# PROGRESS — Financial Risk Signal Aggregator

> Status handoff for any agent/developer picking this up. Read this first, then
> [PLAN.md](PLAN.md) for the full design rationale.

**Last updated:** 2026-07-24
**Overall status:** ✅ Working prototype complete, verified end-to-end with a **live**
Gemini API key, pushed to GitHub, and the 5-slide deck is built.
Remaining: Streamlit Community Cloud deploy (needs your browser/GitHub login) + demo video.

---

## TL;DR of what exists

A runnable Streamlit app that ingests CSV + JSON + free-text alerts and outputs a
prioritised, risk-scored register with per-entity AI rationale. Deterministic rule
engine computes the score; Gemini parses unstructured alerts and writes the narrative
(with a full no-key fallback). All tests pass against the live API; app boots clean;
real screenshots captured; a 5-slide PowerPoint deck is built and visually verified.

Run it: `.venv\Scripts\activate` → `streamlit run app.py` → **Load sample dataset** →
**Run risk analysis**. `.env` already has a working `GEMINI_API_KEY`.

**GitHub repo (already pushed):** https://github.com/ramkumar03ace/Financial-Risk-Signal-Aggregator

---

## Build status by component

| Component | File | Status | Notes |
|---|---|---|---|
| Dependencies | `requirements.txt` | ✅ | Modern `google-genai` SDK |
| Config (weights/thresholds/tiers) | `config.py` | ✅ | Uses `gemini-flash-latest` / `gemini-flash-lite-latest` aliases |
| Data models | `src/schemas.py` | ✅ | pydantic: `Signal`, `AlertHit`, `EntityRisk` |
| Ingestion + join | `src/ingestion.py` | ✅ | CSV/JSON/text; joins on `customer_id` |
| Rule engine (11 rules) | `src/rules.py` | ✅ | Pure functions, independently testable |
| Scoring + ranking | `src/scoring.py` | ✅ | 0–100 cap, tiers, tie-broken rank |
| LLM layer | `src/llm.py` | ✅ | Live-tested against real Gemini API; retries fallback model on failure |
| Prompts | `prompts/*.txt` | ✅ | 4 templates, evidence-grounded, strict JSON |
| Streamlit app | `app.py` | ✅ | 5 tabs; **`md_safe()` fix** so `$` amounts don't render as LaTeX |
| Sample dataset | `data/*` | ✅ | 5 planted scenarios incl. a clean control case |
| Tests | `tests/test_scoring.py` | ✅ | 7 tests, passing against the **live** Gemini API |
| README (1-page) | `README.md` | ✅ | Approach, stack, data assumptions, example I/O, deploy |
| **Git / GitHub** | — | ✅ | Pushed to `origin/main`; `.env` confirmed never committed |
| **Screenshots** | `docs/screenshots/*.png` | ✅ | Real captures via Playwright: landing, overview, register, drill-down |
| **5-slide deck** | `docs/Financial_Risk_Signal_Aggregator_Deck.pptx` | ✅ | Built with python-pptx, visually verified slide-by-slide via PowerPoint COM render |
| **Deployment** | Streamlit Community Cloud | ⬜ | Needs interactive GitHub OAuth login in a browser — see steps below |
| **Demo video (<3 min)** | — | ⬜ | Not recorded — script in PLAN.md §12 |

---

## Verified results (reproducible, live Gemini API)

Full pipeline (`data/` sample, real Gemini extraction + rationale) — one representative run:

| Rank | Customer | Score | Tier | Top signals | Action |
|---|---|---|---|---|---|
| 1 | John Doe | 80 | Critical | high-value wire, high-risk jurisdiction, round number, PEP, adverse media | File SAR |
| 2 | Ravi Menon | 80 | Critical | structuring, velocity spike, cash intensive, adverse media | File SAR |
| 3 | Wei Chen | 65 | High | high-value wire, dormant reactivation, pass-through, round number | Enhanced Due Diligence |
| 4 | Sara Lopez | 30 | Medium | velocity spike, KYC incomplete | Enhanced Due Diligence |
| 5 | Priya Shah | 0 | Low | (none — control case) | Monitor |

Note: because live Gemini extraction is non-deterministic, Wei Chen occasionally also
picks up an `ADVERSE_MEDIA` hit (escalating to Critical/85) depending on how the model
reads the "same-day in-and-out pattern" note — this is expected LLM variance, not a bug,
and is itself a good demo talking point (AI finding more than the rules alone).

- `pytest -q` → **7 passed** (run against the live API key).
- `streamlit run app.py` → boots healthy (HTTP 200), no errors.
- Screenshots in `docs/screenshots/` were captured from the **actual running app** via
  Playwright (not mockups).

---

## Environment notes (important for reproducing)

- **Python:** 3.12.6 at `C:\Python312`.
- The **global pip was broken** and global site-packages had **write-permission
  issues**. Fixed by creating a **project virtualenv** at `.venv`.
- **Always use the venv:** `.venv\Scripts\python.exe` / `.venv\Scripts\streamlit.exe`.
- Deps installed in `.venv`: pandas, pydantic, streamlit, plotly, pytest, google-genai,
  python-dotenv, playwright (dev-only, for screenshot capture), python-pptx (dev-only,
  for deck generation), Pillow. `.venv/` and `.env` are gitignored.
- **`.env` has a real working `GEMINI_API_KEY`** (user-provided, confirmed working).
  It was verified **never committed** to git (`git log --all -- .env` is empty).

### Gemini model gotcha (important if the app stops producing AI output)
Pinned model versions (`gemini-2.0-flash`, `gemini-2.5-flash`, `gemini-1.5-flash`, …)
returned `404`/`429 quota=0` for this API key — Google had already retired free-tier
access to pinned versions for new keys. **Fixed by switching to the rolling alias
models** `gemini-flash-latest` (primary) and `gemini-flash-lite-latest` (fallback) in
`config.py`. `src/llm.py::_generate()` tries the primary model then automatically
retries the fallback model before giving up. If AI output stops working again, first
check which models the key can actually call:
```python
from google import genai
client = genai.Client(api_key="...")
for m in client.models.list():
    print(m.name)
```

---

## Key design decisions (so you don't undo them)

1. **Rules score, LLM explains.** Never let the LLM compute or alter the numeric
   score — this is the core selling point for a compliance audience.
2. **Graceful degradation.** Every LLM call has a fallback; the app must never break
   because a key is missing, quota is exhausted, or a call fails.
3. **Planted, story-driven sample data.** Amounts/dates are tuned so specific rules
   fire; the control case (Priya Shah) proves precision. If you change `config.py`
   weights or the sample data, re-run `pytest` — the scenario tests will catch
   regressions.
4. **Everything tunable in `config.py`** to keep scoring auditable.
5. **Markdown-escape all LLM/evidence text before rendering** (`app.py::md_safe`).
   Streamlit treats `$...$` as LaTeX math; without escaping, dollar amounts in AI
   rationale/evidence render garbled (discovered via real screenshot QA, now fixed).

---

## Deliverables status

| Deliverable | Status | Location |
|---|---|---|
| 1. Working demo | ✅ Local, ⬜ hosted | Run locally now; Streamlit Cloud pending (see below) |
| 2. Five-slide deck | ✅ Done | `docs/Financial_Risk_Signal_Aggregator_Deck.pptx` |
| 3. README + sample data + screenshots | ✅ Done | `README.md`, `data/`, `docs/screenshots/` |
| GitHub repo | ✅ Pushed | https://github.com/ramkumar03ace/Financial-Risk-Signal-Aggregator |

## Next steps (only manual/interactive steps remain)

1. **Deploy to Streamlit Community Cloud** (requires your browser + GitHub OAuth login —
   cannot be automated by an agent):
   - Go to https://share.streamlit.io → **New app** → select the
     `Financial-Risk-Signal-Aggregator` repo → branch `main` → file `app.py`.
   - **Advanced settings → Secrets:** add `GEMINI_API_KEY = "<your key>"`.
   - Deploy → copy the public URL.
   - Update it into `docs/Financial_Risk_Signal_Aggregator_Deck.pptx` slide 5 (currently
     says "add after deploy") and into the submission email/README if desired.
2. **Record the <3-min demo video** (script in PLAN.md §12) — either screen-record the
   local app or the deployed Streamlit Cloud app.
3. Submit: demo link/video + the `.pptx` deck + README (already in the repo).
