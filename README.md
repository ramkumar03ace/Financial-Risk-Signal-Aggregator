# 🛡️ Financial Risk Signal Aggregator

An AI prototype that ingests **fragmented financial data from multiple sources** —
transaction records (CSV), customer/account data (JSON) and free-text external
alerts — and produces a **prioritised, risk-scored summary with an AI-generated
rationale** for each flagged customer. Built for compliance / risk analysts who
today review these signals manually.

> **Core design principle:** *deterministic rules score; the LLM explains.*
> A transparent Python rule engine computes an auditable 0–100 risk score.
> Google Gemini does only what LLMs are best at — parsing unstructured alert text
> into structured signals and writing an evidence-grounded rationale. **The LLM
> never invents the score**, which is what makes the output defensible in a
> compliance setting.

---

## What it does

1. **Ingests** three fragmented sources and joins them per customer.
2. **Detects** risk signals with 11 deterministic rules (structuring, pass-through
   layering, sanctioned-jurisdiction exposure, velocity spikes, dormant
   reactivation, PEP, adverse media, …).
3. **Scores & ranks** each customer 0–100 → tier (Low / Medium / High / Critical),
   prioritised for the analyst.
4. **Explains** every flag with an AI-written rationale + recommended action
   (Monitor → EDD → Escalate to MLRO → File SAR) grounded in the evidence, plus a
   waterfall chart showing exactly how each signal's points built the final score.
5. **Presents** it in a Streamlit dashboard: executive summary, ranked register,
   per-entity drill-down, a floating multi-turn chat for natural-language questions,
   and CSV/JSON export.

## Architecture

```
Inputs (CSV transactions / JSON customers / pasted alert text)
  -> [1] Ingestion & normalisation (pandas): parse, standardise, join on customer_id
  -> [4] LLM extraction: unstructured alerts -> structured hits per entity
  -> [2] Rule engine (deterministic): fire weighted signals with evidence
  -> [3] Scoring: aggregate -> 0-100 score -> tier -> priority rank
  -> [5] AI reasoning: per-entity rationale + action; portfolio exec summary
  -> [6] Streamlit dashboard: register, drill-down, score waterfall, floating
         chat, export
```

Layers 1–3 run with **zero LLM calls**; layers 4–5 enrich the result. If no API
key is present the app degrades gracefully to a rules + heuristic fallback mode,
so it always works.

## Tech stack

| Layer | Tool |
|---|---|
| Language | Python 3.11+ |
| Data | pandas |
| LLM | **Multi-provider** (sidebar-selectable) — Google Gemini (`gemini-flash-latest`, default, fully tested) or any OpenAI-compatible API (NVIDIA NIM, OpenAI, Groq, …) via the `openai` SDK. See [`src/llm.py`](src/llm.py) — `get_provider()` / `_generate()` are the only provider-aware functions; everything else is provider-agnostic. |
| UI | Streamlit (`st.popover` + `st.chat_message`/`st.chat_input` for the floating chat) |
| Charts | Plotly (bar charts, score gauge, score-breakdown waterfall) |
| Validation | pydantic |
| Config/secrets | python-dotenv + `st.secrets` |
| Tests | pytest |

### Adding a second LLM provider

Gemini is the default and the only provider verified end-to-end (screenshots, tests,
and the deployed app all use it). A second **OpenAI-compatible** path exists in the
code and sidebar dropdown for NVIDIA NIM / OpenAI / Groq / etc. — set these env vars
(see [`.env.example`](.env.example)) and select it in the sidebar:
```
LLM_PROVIDER=openai_compatible
OPENAI_API_KEY=your_key_here
OPENAI_BASE_URL=https://integrate.api.nvidia.com/v1   # default: NVIDIA's free catalog
OPENAI_MODEL=meta/llama-3.3-70b-instruct
```
This path has not been live-tested against a real key (none was available at build
time) — the code is verified not to crash without one (graceful fallback, same as
Gemini), but hasn't been confirmed to produce a real response yet.

## Data assumptions

- Synthetic dataset generated for demonstration — **no proprietary or client data**.
- Scale: **67 customers, 1,971 transactions**, generated with
  [`scripts/generate_dataset.py`](scripts/generate_dataset.py) (Faker + fixed seed, so
  it's reproducible). 12 customers carry a distinct planted risk typology
  (structuring, sanctions/PEP, layering, velocity spike, cash-intensive, round-number
  wire, KYC+adverse-media); the remaining 55 are genuinely clean, normal-activity
  customers — proving the system flags the few that matter (11/67) rather than
  everyone.
- All amounts are USD; one row per transaction.
- Thresholds (e.g. `$10k` CTR line, `$50k` wire) are **illustrative and fully
  configurable** in [`config.py`](config.py).
- External alerts are unstructured text; entities are matched by customer **name**.
- Only 5 CSV columns are structurally required (`txn_id`, `timestamp`, `customer_id`,
  `amount`, `txn_type`) and 1 JSON field (`customer_id`) — everything else is optional
  and degrades gracefully (a missing field just means the rule that depends on it can't
  fire for that customer; nothing crashes). Extra columns are ignored, not rejected.

## Setup

```bash
# 1. Create & activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) add your free Gemini API key for full AI narrative
copy .env.example .env         # then edit .env and paste your key
# Get a free key at https://aistudio.google.com/apikey

# 4. Run
streamlit run app.py
```

In the app: click **Load sample dataset → Run risk analysis**.

Run the tests: `pytest -q`
Run the rules-only CLI: `python -m src.scoring`

## Example — input → output

**Input (excerpt):**
- `transactions.csv`: 8 cash deposits of ~$9,500 by *Ravi Menon* over 3 days.
- `external_alerts.txt`: *"Acme Trading, linked to Ravi Menon, named in a bribery probe."*

**Output (register row + rationale):**

| Rank | Customer | Score | Tier | Top signals | Action |
|---|---|---|---|---|---|
| 1 | Ravi Menon | 80 | **Critical** | Structuring, Velocity Spike, Cash Intensive, Adverse Media | File SAR |

> *Rationale:* "Ravi Menon placed eight cash deposits just under the $10,000
> reporting threshold within three days — a classic structuring pattern — alongside
> cash-intensive activity 5× above expected volume, and is the subject of adverse
> media linking him to a bribery probe. The combination of independent signals
> warrants a Suspicious Activity Report."

Across the full sample (67 customers), only **11 are flagged** and **56 score 0/Low**
— including the explicit control customer *Priya Shah* — demonstrating the model
prioritises rather than over-flagging at realistic scale.

## Deployment

**Live on Railway:** https://financial-risk-signal-aggregator-production.up.railway.app

Deployed with the Railway CLI (`railway up`) from this repo. A [`Procfile`](Procfile)
gives Streamlit an explicit start command bound to Railway's injected `$PORT`:
```
web: streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true
```
`GEMINI_API_KEY` is set as a Railway service variable (never committed). To redeploy:
```bash
railway up --detach -m "<summary>"
```

**Alternative — Streamlit Community Cloud:**
1. Push this repo to GitHub (`.env` is gitignored).
2. On https://share.streamlit.io → **New app** → select repo / `app.py`.
3. **Settings → Secrets:** add `GEMINI_API_KEY = "..."`.
4. Deploy → share the public URL.

## Limitations & next steps

- Rules and thresholds are illustrative; production would tune them on labelled data.
- Entity matching is name-based; production would use resolved customer IDs / fuzzy
  matching and a real sanctions-list API (OFAC, UN, EU).
- CSV/JSON column names must match the canonical schema exactly (see *Data
  assumptions* above for the 5 required fields). A safer next step than silent
  auto-inference: a **human-confirmed column-mapping step** — if an uploaded file's
  columns don't match, show dropdowns ("which of your columns is the amount? the
  timestamp?") for a person to confirm once before scoring runs. Full autonomous
  schema-guessing was deliberately avoided — a wrong mapping is more dangerous in a
  compliance context than an upfront "column not found" error.
- Next: graph-based network analysis across counterparties, an analyst feedback loop
  to auto-tune weights, streaming ingestion, and a case-management workflow.

## Project layout

```
app.py            Streamlit UI            config.py     rule weights & thresholds
src/ingestion.py  load + join sources     src/rules.py  deterministic signal rules
src/scoring.py    aggregate -> rank       src/llm.py    multi-provider LLM: extract/rationale/summary/chat
src/schemas.py    pydantic models         prompts/      LLM prompt templates
data/             sample CSV/JSON/text    tests/        pytest scenario tests
scripts/          generate_dataset.py (regenerate the sample data, seeded/reproducible)
docs/             5-slide deck + screenshots (docs/Financial_Risk_Signal_Aggregator_Deck.pptx)
SUMMARY.md        Problem / architecture / implementation / challenges write-up
```

## Submission assets

- **Live demo:** https://financial-risk-signal-aggregator-production.up.railway.app
- **5-slide summary deck:** [`docs/Financial_Risk_Signal_Aggregator_Deck.pptx`](docs/Financial_Risk_Signal_Aggregator_Deck.pptx)
- **Screenshots:** [`docs/screenshots/`](docs/screenshots/) — captured from the live running app
- **Repo:** https://github.com/ramkumar03ace/Financial-Risk-Signal-Aggregator
