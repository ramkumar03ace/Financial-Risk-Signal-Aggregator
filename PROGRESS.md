# PROGRESS — Financial Risk Signal Aggregator

> Status handoff for any agent/developer picking this up. Read this first, then
> [PLAN.md](PLAN.md) for the full design rationale.

**Last updated:** 2026-07-25
**Overall status:** ✅ Working prototype complete, verified end-to-end with a **live**
Gemini API key, deployed to Railway with a custom-designed UI, pushed to GitHub, and the
5-slide deck is built. Remaining: the <3-min demo video (the brief accepts a hosted link
OR a video — the hosted link is already done, so the video is optional polish, not a
blocker).

**Network graph + deck refresh round (2026-07-25, later still):** user asked "is there
more to improve, and what about a counterparty network graph" (a previously-documented
"next step" that was never built). Delivered:

1. **Counterparty network graph** (`src/network.py`, new `Network` tab in `app.py`) —
   builds a graph of customer↔counterparty links, keeping only counterparties used by
   2+ *distinct* customers (a counterparty used by one customer carries no cross-
   customer signal; deliberately excludes routine bill payments like rent/utilities,
   which reuse a small shared payee pool across the 55 clean customers purely for
   dataset realism and would otherwise flood the graph with meaningless links —
   restricted to wire transactions only). Rendered with networkx (`spring_layout`) +
   Plotly scatter traces, styled consistent with the rest of the app (tier-colored
   customer nodes, diamond counterparty nodes).
2. **Planted a real link for the demo to show**: `scripts/generate_dataset.py`'s
   `gen_layering_case` (Jordan Johnson) now routes its outbound wire through "Silver
   Crescent Trading" — the same sanctioned shell company already used by
   `gen_sanctions_pep_case` (Joshua Diaz). Regenerated dataset: still 67 customers /
   1,971 transactions (only a counterparty name changed); all 7 pytest tests
   unaffected (they only assert on the 5 original hero customers). Side effect: Jordan
   Johnson's score rose 65→90 (High→Critical) since "Silver Crescent Trading" is also
   flagged as a high-risk jurisdiction (MM) — a realistic, not contrived, change.
3. **Deck refresh** across slides 2–5: slide 3's screenshot swapped from the drilldown
   to the network graph (now the most differentiated visual), code snippet swapped to
   `src/network.py`'s shared-counterparty filter; slide 4's weakest card ("free-tier
   model churn") replaced with the real widget/session-state bug story (see below);
   slide 5 moved "network analysis" from Next Steps to What Was Delivered, since it's
   no longer a future item.

**Also fixed while verifying the Gemini-vs-NVIDIA comparison feature (added by the user
in a prior round, outside this session): a real bug** — the comparison silently compared
Gemini to itself. `use_provider()` tried to overwrite `st.session_state["llm_provider"]`,
the exact key the sidebar's `st.selectbox(key="llm_provider")` widget owns; Streamlit
silently rejects that once the widget is instantiated in the current run. A standalone
Python script test misleadingly "confirmed" the feature worked, because outside a real
Streamlit session there's no widget to conflict with. Fixed by routing the override
through a separate key (`_llm_provider_override`) in `src/llm.py`. Re-verified inside
the actual browser session (not a script) both locally and on the live Railway
deployment: Gemini and NVIDIA now show genuinely different models and results.
**Lesson for future sessions: never trust a standalone script test of Streamlit
session_state behavior — always verify by driving the real browser-rendered app.**

**"Make it more impressive" round (2026-07-25):** user felt the app was too basic vs.
other candidates' submissions and asked for 3 things: (1) multi-LLM support, not just
Gemini, (2) the "Ask" tab turned into a floating chat-bubble instead of a plain tab,
(3) general "make it more impressive." Delivered:

1. **Multi-provider LLM** (`src/llm.py` refactor) — Gemini stays the default and is the
   only one fully verified (all screenshots/tests/deploy use it). Added a second
   **OpenAI-compatible** path (`_generate_openai_compatible`, uses the `openai` SDK)
   that works with NVIDIA NIM (default base URL), OpenAI itself, Groq, or anything
   speaking the same API shape — selectable via a sidebar dropdown
   (`st.session_state["llm_provider"]`). **Not live-tested** — no second-provider key
   was available at build time. If given an NVIDIA/OpenAI key later, verify with:
   `LLM_PROVIDER=openai_compatible OPENAI_API_KEY=... python -c "from src import llm; print(llm._generate('hello'))"`.
   The refactor is low-risk: `extract_alerts`/`entity_rationale`/`exec_summary`/
   `nl_query` never changed — they only ever call `is_available()`/`_generate()`,
   which now dispatch on `get_provider()`.
2. **Floating chat bubble** (`floating_chat()` in `app.py`, replaces the old "Ask" tab)
   — a real multi-turn chat (`st.chat_message`/`st.chat_input`, history in
   `st.session_state["chat_history"]`) inside a `st.popover`, pinned to the
   bottom-right corner of the viewport via `st.container(key="floating_chat")` + CSS.
   **Non-obvious CSS gotcha hit and fixed:** Streamlit's `.stVerticalBlock` sets
   `width: 100%` by default; combined with `position: fixed; right: 24px` and no
   `left`, the browser computed the container at full viewport width with its left
   edge at `-24px` (verified via Playwright `getComputedStyle` — this is NOT a
   `contain`/`transform` containing-block issue, both were `none` up the whole
   ancestor chain; it's purely the inherited 100% width fighting the right-anchored
   fixed position). Fix: add `width: fit-content !important` to `.st-key-floating_chat`.
   If any *other* element is ever pinned with `position: fixed` in this app, expect
   the same bug and apply the same fix.
3. **Score breakdown waterfall chart** (`_score_waterfall()` in `app.py`, drill-down
   tab) — a Plotly waterfall showing each fired signal's point contribution building
   up to the final score, visually reinforcing the "auditable score" story. Handles
   the case where raw signal weights sum above 100 (score is capped) by drawing a
   dashed "score cap (100)" reference line rather than misrepresenting the total.

All 7 pytest tests still pass unchanged (provider defaults to Gemini, so the tested
path is untouched). Screenshots, deck, and the live Railway deploy were all refreshed
to reflect the new UI after this round — see the git log for the exact commit.

**Update (2026-07-25, later):** the user independently extended this (own edits, not
mine) with real polish: session-based API key entry directly in the sidebar (no .env
needed to try a key), and a full **"Run Gemini vs NVIDIA comparison"** feature
(`run_model_comparison()` in `app.py`, `llm.use_provider()` context manager, new
Model Compare tab) that runs the same input through both providers and shows
side-by-side extracted alerts, score/tier deltas, and rationales. The user added a
real `NVIDIA_API_KEY`.

**Real bug found and fixed while verifying the comparison feature (2026-07-25):**
a standalone Python test (`llm._generate()` outside a real Streamlit session) showed
Gemini and NVIDIA producing different results — looked verified. But testing the
actual feature *inside the running app* showed the comparison tab reporting
`Model: gemini-2.0-flash` under **both** the Gemini and NVIDIA columns, with
near-identical extracted text. Root cause: `use_provider()` tried to overwrite
`st.session_state["llm_provider"]` — the exact key the sidebar's
`st.selectbox(..., key="llm_provider")` widget owns. Streamlit silently rejects
programmatic overwrites of a widget-bound key once that widget has been
instantiated in the current run (raises `StreamlitAPIException`, caught by
`use_provider()`'s broad `except Exception:`, falling back to setting
`os.environ["LLM_PROVIDER"]` — which does nothing, because `get_provider()` checks
session_state *first* and the widget's real value, unchanged, always wins). Net
effect: the compare feature silently called Gemini twice whenever the sidebar was
on its default Gemini selection — which is virtually always, since NVIDIA is opt-in.
My standalone test didn't catch this because outside a real Streamlit run there's no
widget to conflict with, so the (broken) code path "worked" for the wrong reason.

**Fix:** `get_provider()`/`use_provider()` now use a separate, non-widget-bound
session key (`_llm_provider_override`) instead of touching `"llm_provider"`
directly. Re-verified in the actual browser-driven app after the fix: Gemini and
NVIDIA now show genuinely different models, different extracted alerts (NVIDIA
caught a `cust_003` watchlist hit Gemini missed, causing a real Wei Chen
65→85 / High→Critical delta), and distinctly different rationale writing styles.
**Lesson reinforced:** a standalone script test of Streamlit-adjacent code is not
equivalent to testing inside a real running session — session_state/widget
interactions can only be verified by actually driving the browser-rendered app.

**UI redesign (2026-07-24, later):** the original UI used Streamlit defaults (large top
whitespace, emoji-prefixed labels/tabs, default red/blue alert boxes) — flagged by the
user as looking generic/templated, plus a real bug: "Load sample dataset" gave no visible
confirmation. Replaced with a deliberate compliance-tool identity: Source Serif 4
headlines, IBM Plex Sans/Mono for UI and data, a muted ink/paper palette, and a custom
colored-chip component (`chip()` in `app.py`) used consistently for AI status, tier
badges, and KPIs instead of emoji. `.streamlit/config.toml` themes native widgets to
match and sets `toolbarMode = "minimal"`. The sample-data bug was a real Streamlit
issue — the text_area widget had both `value=` and a matching `key=` in session_state,
triggering a silent warning; fixed by relying on `key=` alone. See `inject_theme()` and
`chip()` in `app.py` before making further UI changes — don't reintroduce emoji or
Streamlit's default `st.metric`/`st.success`/`st.warning` styling, use `chip()` instead.

**Dataset scale-up (2026-07-24, later still):** user asked for a bigger, more realistic
dataset ("close to real"). Replaced the 5-customer demo data with a generated 67-customer,
1,971-transaction dataset via [`scripts/generate_dataset.py`](scripts/generate_dataset.py)
(Faker, fixed seed = reproducible). The original 5 hero customers (cust_001..cust_005,
Ravi Menon/John Doe/Wei Chen/Priya Shah/Sara Lopez) and their exact transactions/alerts
are preserved unchanged so all 7 pytest scenario tests still pass without modification.
Added: 7 new distinct suspicious archetypes (cust_006..cust_012, different countries/
typologies — GB structuring, ZA/MM PEP+sanctions, AE layering, US velocity spike, NG
cash-intensive, DE round-number wire, PH KYC+adverse-media) and 55 clean background
customers (cust_013+) with realistic multi-month salary/rent/bills/shopping activity.
Result: 11 flagged / 56 clean — a real precision demonstration at scale, not just one
control case.

**Important follow-on fix required by the scale-up:** `overview_tab`'s "Risk score by
customer" chart used to plot *every* customer — with 67 rows that's unreadable. Now
filtered to flagged-only (score > 0, capped at 20) and retitled "Top N flagged customers
(of M reviewed)". `register_tab` now defaults to flagged-only (11) with a checkbox to
reveal all 67 — both changes directly serve the brief's "help analysts focus on what
matters" framing, not just cosmetic. If you regenerate the dataset again with a very
different flagged count, sanity-check these two UI elements still read well.

Re-run `python scripts/generate_dataset.py` any time to regenerate (deterministic, same
output every time) — e.g. after tuning `config.py` weights, if you want fresh Faker names.

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
**Live app (Railway, already deployed):** https://financial-risk-signal-aggregator-production.up.railway.app

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
| **5-slide deck** | `docs/Financial_Risk_Signal_Aggregator_Deck.pptx` | ✅ | Built with python-pptx, visually verified slide-by-slide via PowerPoint COM render; links to the live Railway URL |
| **Deployment** | Railway | ✅ | Deployed via `railway up`; `GEMINI_API_KEY` set as a service variable; public domain generated; smoke-tested end-to-end incl. real Gemini output — see below |
| **Demo video (<3 min)** | — | ⬜ | Not recorded — script in PLAN.md §12. Optional: the brief accepts a hosted link OR a video, and the hosted link is done |

---

## Verified results (reproducible, live Gemini API)

Full pipeline on the current 67-customer / 1,971-transaction dataset (real Gemini
extraction + rationale) — one representative run, showing the 11 flagged customers
(56 others correctly score 0/Low and are omitted here):

| Rank | Customer | Score | Tier | Top signals | Action |
|---|---|---|---|---|---|
| 1 | John Doe | 80 | Critical | high-value wire, high-risk jurisdiction, round number, PEP, adverse media | File SAR |
| 2 | Joshua Diaz | 80 | Critical | high-value wire, high-risk jurisdiction, round number, PEP, adverse media | File SAR |
| 3 | Ravi Menon | 80 | Critical | structuring, velocity spike, cash intensive, adverse media | File SAR |
| 4 | Wei Chen | 65 | High | high-value wire, dormant reactivation, pass-through, round number | Enhanced Due Diligence |
| 5 | Jordan Johnson | 65 | High | high-value wire, dormant reactivation, pass-through, round number | Enhanced Due Diligence |
| 6 | Chris Curtis | 60 | High | structuring, cash intensive, adverse media | File SAR |
| 7 | Sara Lopez | 30 | Medium | velocity spike, KYC incomplete | Enhanced Due Diligence |
| 8 | Benjamin Davis | 30 | Medium | velocity spike, KYC incomplete | Enhanced Due Diligence |
| 9 | Mark Meza | 20 | Low | high-value wire, round number | Monitor |
| 10 | Ronald Martinez | 10 | Low | cash intensive | Monitor |
| 11 | Jennifer Cherry | 10 | Low | KYC incomplete (adverse-media hit was low-severity, below the medium threshold) | Monitor |

Note: live Gemini extraction is non-deterministic — exact scores for the 7 new archetype
customers can shift slightly run-to-run (e.g. whether a borderline-severity alert is read
as low vs medium), same as it always could for the original 5. The original 5 heroes'
*rules-only* tiers (no LLM) are fully deterministic and unchanged from before the scale-up
— see `test_deterministic_tiers` in `tests/test_scoring.py`.

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
| 1. Working demo | ✅ Local + ✅ hosted | Local: `streamlit run app.py`. Hosted: https://financial-risk-signal-aggregator-production.up.railway.app |
| 2. Five-slide deck | ✅ Done | `docs/Financial_Risk_Signal_Aggregator_Deck.pptx` — links to the live URL |
| 3. README + sample data + screenshots | ✅ Done | `README.md`, `data/`, `docs/screenshots/` (incl. `04_railway_live.png` from prod) |
| GitHub repo | ✅ Pushed | https://github.com/ramkumar03ace/Financial-Risk-Signal-Aggregator |

## Railway deployment details

- **Project:** `financial-risk-signal-aggregator` (workspace: `vishvajnavin's Projects`)
- **Project ID:** `135277b3-6b7f-4331-a7ec-9e6c44eecfd6`
- **Service ID:** `34cf88d3-dbe2-46bb-ae4a-5e5b6d00bcc9`
- **Environment ID:** `c8ad7050-b13f-4e57-83d8-d919160ea68a` (`production`)
- **Public URL:** https://financial-risk-signal-aggregator-production.up.railway.app
- Deployed by uploading the local directory via `railway up` (not GitHub-linked — a plain
  local deploy). `.gitignore` was respected automatically (`.venv`/`.env` excluded from
  the ~830KB upload). `GEMINI_API_KEY` was set via `railway variable set --stdin` so it
  never appeared in shell history or logs.
- To redeploy after code changes: `railway up --detach -m "<summary>" --service 34cf88d3-dbe2-46bb-ae4a-5e5b6d00bcc9 --project 135277b3-6b7f-4331-a7ec-9e6c44eecfd6 --environment c8ad7050-b13f-4e57-83d8-d919160ea68a`
- To connect this service to GitHub for auto-deploy-on-push instead of manual `railway up`:
  `railway service source connect --repo ramkumar03ace/Financial-Risk-Signal-Aggregator --branch main --service 34cf88d3-dbe2-46bb-ae4a-5e5b6d00bcc9` (not yet done — currently a one-off manual deploy, code and deployed app can drift if you push to GitHub without re-running `railway up`).
- Verified via a live Playwright smoke test against the production URL: "Gemini connected"
  banner present, sample data loads, AI-generated executive summary renders correctly
  (dollar amounts display properly, confirming the `md_safe()` fix works in prod too).

## Next steps (optional — nothing is blocking submission)

1. *(Optional)* **Record the <3-min demo video** (script in PLAN.md §12) — the brief
   accepts a hosted link OR a video, and the hosted link is already live, so this is
   polish, not a requirement.
2. *(Optional)* Connect the Railway service to GitHub for auto-deploy (see command above)
   so future pushes deploy automatically instead of requiring a manual `railway up`.
3. Submit: live demo link (or video) + the `.pptx` deck + README (already in the repo).
