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
4. **Explains** every flag with a Gemini-written rationale + recommended action
   (Monitor → EDD → Escalate to MLRO → File SAR) grounded in the evidence.
5. **Presents** it in a Streamlit dashboard: executive summary, ranked register,
   per-entity drill-down, natural-language Q&A, and CSV/JSON export.

## Architecture

```
Inputs (CSV transactions / JSON customers / pasted alert text)
  -> [1] Ingestion & normalisation (pandas): parse, standardise, join on customer_id
  -> [4] LLM extraction (Gemini): unstructured alerts -> structured hits per entity
  -> [2] Rule engine (deterministic): fire weighted signals with evidence
  -> [3] Scoring: aggregate -> 0-100 score -> tier -> priority rank
  -> [5] AI reasoning (Gemini): per-entity rationale + action; portfolio exec summary
  -> [6] Streamlit dashboard: register, drill-down, charts, NL query, export
```

Layers 1–3 run with **zero LLM calls**; layers 4–5 enrich the result. If no API
key is present the app degrades gracefully to a rules + heuristic fallback mode,
so it always works.

## Tech stack

| Layer | Tool |
|---|---|
| Language | Python 3.11+ |
| Data | pandas |
| LLM | Google Gemini (`gemini-flash-latest`, fallback `gemini-flash-lite-latest`) via the `google-genai` SDK |
| UI | Streamlit |
| Charts | Plotly |
| Validation | pydantic |
| Config/secrets | python-dotenv + `st.secrets` |
| Tests | pytest |

## Data assumptions

- Synthetic dataset generated for demonstration — **no proprietary or client data**.
- All amounts are USD; one row per transaction.
- Thresholds (e.g. `$10k` CTR line, `$50k` wire) are **illustrative and fully
  configurable** in [`config.py`](config.py).
- External alerts are unstructured text; entities are matched by customer **name**.

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

The clean control customer (*Priya Shah*) scores **0 / Low** with no signals,
demonstrating the model does not over-flag.

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
- Next: graph-based network analysis across counterparties, an analyst feedback loop
  to auto-tune weights, streaming ingestion, and a case-management workflow.

## Project layout

```
app.py            Streamlit UI            config.py     rule weights & thresholds
src/ingestion.py  load + join sources     src/rules.py  deterministic signal rules
src/scoring.py    aggregate -> rank       src/llm.py    Gemini: extract/rationale/summary/Q&A
src/schemas.py    pydantic models         prompts/      LLM prompt templates
data/             sample CSV/JSON/text    tests/        pytest scenario tests
docs/             5-slide deck + screenshots (docs/Financial_Risk_Signal_Aggregator_Deck.pptx)
```

## Submission assets

- **Live demo:** https://financial-risk-signal-aggregator-production.up.railway.app
- **5-slide summary deck:** [`docs/Financial_Risk_Signal_Aggregator_Deck.pptx`](docs/Financial_Risk_Signal_Aggregator_Deck.pptx)
- **Screenshots:** [`docs/screenshots/`](docs/screenshots/) — captured from the live running app
- **Repo:** https://github.com/ramkumar03ace/Financial-Risk-Signal-Aggregator
