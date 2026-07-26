"""
Financial Risk Signal Aggregator — Streamlit dashboard.

Data in (CSV + JSON + free text)  ->  rules + LLM  ->  prioritised risk view.

Run:  streamlit run app.py
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from src import llm
from src.ingestion import build_entities, load_alerts, load_customers, load_transactions
from src.network import build_counterparty_graph, shared_counterparty_summary
from src.scoring import build_risk_register
from src.schemas import EntityRisk

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def md_safe(text: str) -> str:
    """Escape lone $ so Streamlit's markdown renderer doesn't treat dollar
    amounts (e.g. "$250,000") as LaTeX math delimiters."""
    return (text or "").replace("$", "\\$")


TIER_COLORS = {
    "Critical": "#9B1C1C",
    "High": "#B45309",
    "Medium": "#8A6D1B",
    "Low": "#166534",
}
TIER_ORDER = ["Critical", "High", "Medium", "Low"]
OK_COLOR = "#166534"
WARN_COLOR = "#B45309"

st.set_page_config(
    page_title="Financial Risk Signal Aggregator",
    page_icon=None,
    layout="wide",
)


def inject_theme() -> None:
    """Custom type system + a small colored-chip indicator language, used in
    place of emoji throughout (status, tiers, KPIs)."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600;8..60,700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

        :root {
            --ink: #14171C;
            --slate: #5B6472;
            --accent: #1B2A4A;
            --hairline: #DDD9CF;
        }
        html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
        h1, h2, h3, .stMarkdown h3, .stMarkdown h4 {
            font-family: 'Source Serif 4', Georgia, serif !important;
            font-weight: 600;
            letter-spacing: -0.01em;
        }
        [data-testid="stHeader"] { height: 2rem; background: transparent; }
        .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1200px; }
        [data-testid="stSidebar"] .block-container { padding-top: 1.6rem; }
        [data-testid="stSidebar"] h1 {
            font-size: 1.3rem;
            border-bottom: 1px solid var(--hairline);
            padding-bottom: 0.6rem;
        }
        .stButton > button, .stDownloadButton > button {
            font-family: 'IBM Plex Sans', sans-serif;
            font-weight: 500;
            letter-spacing: 0.01em;
            border-radius: 4px;
        }
        [data-testid="stTabs"] button[role="tab"] {
            font-family: 'IBM Plex Sans', sans-serif;
            font-weight: 500;
            font-size: 0.85rem;
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }
        [data-testid="stTabs"] [data-baseweb="tab-highlight"] {
            background-color: var(--accent) !important;
        }
        [data-testid="stMetricValue"] { font-family: 'IBM Plex Mono', monospace; }
        [data-testid="stMetricLabel"] {
            font-family: 'IBM Plex Sans', sans-serif;
            text-transform: uppercase;
            font-size: 0.7rem;
            letter-spacing: 0.05em;
            color: var(--slate);
        }
        [data-testid="stDataFrame"] thead tr th, [data-testid="stTable"] thead tr th {
            font-family: 'IBM Plex Sans', sans-serif;
            text-transform: uppercase;
            font-size: 0.7rem;
            letter-spacing: 0.04em;
            color: var(--slate);
        }
        .rag-chip {
            display: inline-flex; align-items: center; gap: 0.5rem;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.76rem; letter-spacing: 0.03em;
            padding: 0.5rem 0.7rem;
            border: 1px solid var(--hairline); border-radius: 4px;
            background: #FFFFFF;
        }
        .rag-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }
        .kpi-row { display: flex; gap: 0; margin-bottom: 0.5rem; flex-wrap: wrap; }
        .kpi-tile {
            flex: 1; min-width: 110px;
            padding: 0 1.4rem 0 0; margin-right: 1.4rem;
            border-right: 1px solid var(--hairline);
        }
        .kpi-tile:last-child { border-right: none; margin-right: 0; }
        .kpi-label {
            display: flex; align-items: center; gap: 0.4rem;
            font-family: 'IBM Plex Sans', sans-serif; text-transform: uppercase;
            font-size: 0.7rem; letter-spacing: 0.05em; color: var(--slate);
            margin-bottom: 0.3rem;
        }
        .kpi-value {
            font-family: 'IBM Plex Mono', monospace; font-size: 1.9rem;
            font-weight: 600; color: var(--ink);
        }
        .st-key-floating_chat {
            position: fixed !important;
            bottom: 24px;
            right: 24px;
            z-index: 9999;
            width: fit-content !important;
        }
        .st-key-floating_chat button {
            border-radius: 999px !important;
            box-shadow: 0 4px 16px rgba(20, 23, 28, 0.25);
            background: var(--accent) !important;
            color: white !important;
            border: none !important;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def chip(label: str, color: str) -> str:
    return (
        f'<span class="rag-chip"><span class="rag-dot" '
        f'style="background:{color}"></span>{label}</span>'
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_analysis(
    txns_df: pd.DataFrame, customers: List[Dict[str, Any]], alert_text: str
) -> Dict[str, Any]:
    entities = build_entities(txns_df, customers)
    name_map = {c["customer_id"]: c.get("name", c["customer_id"]) for c in customers}

    # 1) LLM (or fallback) turns unstructured alerts into structured hits.
    hits = llm.extract_alerts(alert_text or "", name_map)

    # 2) Deterministic rules + scoring produce the ranked register.
    register = build_risk_register(entities, hits)

    # 3) LLM (or fallback) writes a rationale + recommended action per entity.
    for er in register:
        profile = entities[er.customer_id]["profile"]
        result = llm.entity_rationale(er, profile)
        er.rationale = result["rationale"]
        er.recommended_action = result["recommended_action"]
        er.confidence = result["confidence"]

    summary = llm.exec_summary(register)
    return {
        "register": register,
        "summary": summary,
        "entities": entities,
        "hits": hits,
        "ai_used": llm.is_available(),
    }


def run_model_comparison(
    txns_df: pd.DataFrame,
    customers: List[Dict[str, Any]],
    alert_text: str,
    rationale_limit: int = 5,
) -> Dict[str, Any]:
    """Run Gemini and NVIDIA/OpenAI-compatible models on the same inputs."""
    entities = build_entities(txns_df, customers)
    name_map = {c["customer_id"]: c.get("name", c["customer_id"]) for c in customers}
    compared: Dict[str, Any] = {}

    for provider in (llm.PROVIDER_GEMINI, llm.PROVIDER_OPENAI):
        with llm.use_provider(provider):
            hits = llm.extract_alerts(alert_text or "", name_map)
            register = build_risk_register(entities, hits)
            flagged = [er for er in register if er.score > 0][:rationale_limit]
            rationales: Dict[str, Dict[str, Any]] = {}

            for er in flagged:
                profile = entities[er.customer_id]["profile"]
                result = llm.entity_rationale(er, profile)
                er.rationale = result["rationale"]
                er.recommended_action = result["recommended_action"]
                er.confidence = result["confidence"]
                rationales[er.customer_id] = {
                    "name": er.name,
                    "tier": er.tier,
                    "score": er.score,
                    "signals": er.signal_codes,
                    "rationale": er.rationale,
                    "recommended_action": er.recommended_action,
                    "confidence": er.confidence,
                    "ai_generated": result.get("ai_generated", False),
                }

            compared[provider] = {
                "label": llm.PROVIDERS[provider],
                "available": llm.is_available(provider),
                "model": llm.provider_status()["model"],
                "hits": hits,
                "register": register,
                "rationales": rationales,
            }

    return {"providers": compared}


def register_to_df(register: List[EntityRisk]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Rank": i,
                "Customer": er.name,
                "Score": er.score,
                "Tier": er.tier,
                "Signals": er.num_signals,
                "Top Signals": ", ".join(er.signal_codes) or "—",
                "Recommended Action": er.recommended_action or "—",
            }
            for i, er in enumerate(register, 1)
        ]
    )


# ---------------------------------------------------------------------------
# Sidebar — inputs
# ---------------------------------------------------------------------------
def sidebar() -> None:
    st.sidebar.title("Risk Aggregator")
    st.sidebar.caption("Structured + unstructured signals → prioritised risk view")

    st.sidebar.selectbox(
        "AI provider",
        options=list(llm.PROVIDERS.keys()),
        format_func=lambda p: llm.PROVIDERS[p],
        key="llm_provider",
    )
    provider = llm.get_provider()
    if provider == llm.PROVIDER_OPENAI:
        st.sidebar.text_input(
            "NVIDIA / OpenAI-compatible API key",
            type="password",
            placeholder="Paste nvapi-... key here",
            key="openai_api_key",
            help=(
                "Stored only in this Streamlit session. For permanent local use, "
                "put NVIDIA_API_KEY=... in .env or Railway variables."
            ),
        )
        if st.session_state.get("openai_api_key", "").strip():
            st.sidebar.caption("Session key detected for NVIDIA/OpenAI-compatible calls.")
    else:
        st.sidebar.text_input(
            "Gemini API key",
            type="password",
            placeholder="Paste AIza... key here",
            key="gemini_api_key",
            help=(
                "Stored only in this Streamlit session. For permanent local use, "
                "put GEMINI_API_KEY=... in .env or Railway variables."
            ),
        )
        if st.session_state.get("gemini_api_key", "").strip():
            st.sidebar.caption("Session key detected for Gemini calls.")

    status = llm.provider_status()
    short_label = status["label"].split(" (")[0]
    if status["available"]:
        st.sidebar.markdown(
            chip(f"{short_label} connected — {status['model']}", OK_COLOR),
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            chip(f"{short_label} — no key, using rules + fallback mode", WARN_COLOR),
            unsafe_allow_html=True,
        )

    if not status["available"]:
        key_names = " / ".join(llm.expected_key_names(status["provider"]))
        if status["provider"] == llm.PROVIDER_OPENAI:
            st.sidebar.caption(
                "For NVIDIA: open build.nvidia.com, choose a free endpoint model, "
                "click Generate API Key, then paste it below or save it as NVIDIA_API_KEY."
            )
        else:
            st.sidebar.caption(
                "For Gemini: create a key in Google AI Studio, then paste it below "
                "or save it as GEMINI_API_KEY."
            )
        st.sidebar.caption(f"Accepted key name(s): {key_names}")

    st.sidebar.subheader("1 · Load data")
    if st.sidebar.button("Load sample dataset", use_container_width=True):
        _load_sample_into_state()

    if st.session_state.get("sample_loaded"):
        n_cust = len(st.session_state.get("customers", []))
        n_txn = len(st.session_state.get("txns_df", []))
        st.sidebar.markdown(
            chip(f"Sample loaded — {n_cust} customers, {n_txn} transactions", OK_COLOR),
            unsafe_allow_html=True,
        )

    txn_file = st.sidebar.file_uploader("Transactions (CSV)", type=["csv"])
    cust_file = st.sidebar.file_uploader("Customer records (JSON)", type=["json"])
    if "alert_text" not in st.session_state:
        st.session_state["alert_text"] = ""
    alert_text = st.sidebar.text_area(
        "External alerts / adverse media (paste text)",
        height=160,
        key="alert_text",
    )

    st.sidebar.subheader("2 · Analyse")
    if st.sidebar.button("Run risk analysis", type="primary", use_container_width=True):
        _run_from_inputs(txn_file, cust_file, alert_text)
    if st.sidebar.button("Run Gemini vs NVIDIA comparison", use_container_width=True):
        _run_comparison_from_inputs(txn_file, cust_file, alert_text)


def _load_sample_into_state() -> None:
    st.session_state["txns_df"] = load_transactions(
        os.path.join(DATA_DIR, "transactions.csv")
    )
    st.session_state["customers"] = load_customers(
        os.path.join(DATA_DIR, "customers.json")
    )
    st.session_state["alert_text"] = load_alerts(
        os.path.join(DATA_DIR, "external_alerts.txt")
    )
    st.session_state["sample_loaded"] = True
    st.rerun()


def _run_from_inputs(txn_file, cust_file, alert_text) -> None:
    try:
        if txn_file is not None:
            txns_df = load_transactions(txn_file)
        elif "txns_df" in st.session_state:
            txns_df = st.session_state["txns_df"]
        else:
            st.sidebar.error("Provide a transactions CSV (or load the sample dataset).")
            return

        if cust_file is not None:
            customers = load_customers(cust_file)
        elif "customers" in st.session_state:
            customers = st.session_state["customers"]
        else:
            st.sidebar.error("Provide a customers JSON (or load the sample dataset).")
            return

        with st.spinner("Aggregating signals and scoring risk…"):
            st.session_state["result"] = run_analysis(txns_df, customers, alert_text)
    except Exception as exc:  # surface ingestion/format errors to the user
        st.sidebar.error(f"Could not analyse inputs: {exc}")


def _run_comparison_from_inputs(txn_file, cust_file, alert_text) -> None:
    try:
        if txn_file is not None:
            txns_df = load_transactions(txn_file)
        elif "txns_df" in st.session_state:
            txns_df = st.session_state["txns_df"]
        else:
            st.sidebar.error("Provide a transactions CSV (or load the sample dataset).")
            return

        if cust_file is not None:
            customers = load_customers(cust_file)
        elif "customers" in st.session_state:
            customers = st.session_state["customers"]
        else:
            st.sidebar.error("Provide a customers JSON (or load the sample dataset).")
            return

        with st.spinner("Comparing Gemini and NVIDIA on the same alert text..."):
            st.session_state["model_comparison"] = run_model_comparison(
                txns_df, customers, alert_text
            )
            if "result" not in st.session_state:
                st.session_state["result"] = run_analysis(txns_df, customers, alert_text)
            st.session_state["comparison_ready"] = True
    except Exception as exc:
        st.sidebar.error(f"Could not compare models: {exc}")


# ---------------------------------------------------------------------------
# Main views
# ---------------------------------------------------------------------------
def overview_tab(result: Dict[str, Any]) -> None:
    register: List[EntityRisk] = result["register"]
    counts = {t: sum(1 for e in register if e.tier == t) for t in TIER_ORDER}

    tiles = [("Customers", len(register), None)] + [
        (t, counts[t], TIER_COLORS[t]) for t in TIER_ORDER
    ]
    tiles_html = ""
    for label, value, color in tiles:
        dot = f'<span class="rag-dot" style="background:{color}"></span>' if color else ""
        tiles_html += (
            f'<div class="kpi-tile"><div class="kpi-label">{dot}{label}</div>'
            f'<div class="kpi-value">{value}</div></div>'
        )
    st.markdown(f'<div class="kpi-row">{tiles_html}</div>', unsafe_allow_html=True)

    st.subheader("Executive summary")
    tag = "AI-generated" if result["ai_used"] else "auto-generated (no API key)"
    st.info(md_safe(result["summary"]))
    st.caption(f"Summary source: {tag}")

    left, right = st.columns(2)
    with left:
        dist = pd.DataFrame(
            {"Tier": list(counts.keys()), "Count": list(counts.values())}
        )
        fig = px.bar(
            dist, x="Tier", y="Count", color="Tier",
            color_discrete_map=TIER_COLORS, title="Risk tier distribution",
        )
        fig.update_layout(showlegend=False, font_family="IBM Plex Sans")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        flagged = [e for e in register if e.score > 0][:20]
        chart_title = (
            f"Top {len(flagged)} flagged customers (of {len(register)} reviewed)"
            if flagged
            else "Risk score by customer"
        )
        scores = pd.DataFrame(
            [{"Customer": e.name, "Score": e.score, "Tier": e.tier} for e in flagged]
        )
        if scores.empty:
            st.info("No customers were flagged — nothing to chart.")
        else:
            fig2 = px.bar(
                scores, x="Score", y="Customer", color="Tier", orientation="h",
                color_discrete_map=TIER_COLORS, title=chart_title,
            )
            fig2.update_layout(
                yaxis={"categoryorder": "total ascending"}, font_family="IBM Plex Sans"
            )
            st.plotly_chart(fig2, use_container_width=True)


def register_tab(result: Dict[str, Any]) -> None:
    register: List[EntityRisk] = result["register"]
    n_flagged = sum(1 for e in register if e.score > 0)
    st.subheader("Prioritised risk register")

    show_all = True
    if n_flagged and n_flagged < len(register):
        show_all = st.checkbox(
            f"Show all {len(register)} customers (default: {n_flagged} flagged only)",
            value=False,
        )
    shown = register if show_all else [e for e in register if e.score > 0]
    df = register_to_df(shown)

    def _row_style(row):
        color = TIER_COLORS.get(row["Tier"], "#666")
        return [f"background-color: {color}22"] * len(row)

    st.dataframe(
        df.style.apply(_row_style, axis=1),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Ranked by score, then by number of independent signals, then heaviest signal."
    )


def drilldown_tab(result: Dict[str, Any]) -> None:
    register: List[EntityRisk] = result["register"]
    entities = result["entities"]
    names = [f"{e.name} — {e.tier} ({e.score})" for e in register]
    idx = st.selectbox(
        "Select a customer", range(len(register)), format_func=lambda i: names[i]
    )
    er = register[idx]
    profile = entities[er.customer_id]["profile"]

    head, gauge = st.columns([2, 1])
    with head:
        st.markdown(f"### {er.name}")
        st.markdown(
            chip(f"{er.tier} — score {er.score}/100", TIER_COLORS[er.tier])
            + f"&nbsp;&nbsp; **Recommended action:** {er.recommended_action} "
            f"&nbsp;|&nbsp; **Confidence:** {er.confidence}",
            unsafe_allow_html=True,
        )
        st.markdown("**Profile**")
        st.json(profile, expanded=False)
    with gauge:
        st.plotly_chart(_score_gauge(er.score, er.tier), use_container_width=True)

    sanctions_signals = [s for s in er.signals if s.code == "SANCTIONS_LIST_MATCH"]
    if sanctions_signals:
        st.markdown(
            chip("OFAC SDN match - immediate sanctions review", TIER_COLORS["Critical"]),
            unsafe_allow_html=True,
        )
        st.error(md_safe(sanctions_signals[0].evidence))

    if er.signals:
        st.markdown("#### How the score was built")
        st.plotly_chart(_score_waterfall(er), use_container_width=True)

    st.markdown("#### AI rationale")
    st.write(md_safe(er.rationale) or "—")

    st.markdown("#### Risk signals & evidence")
    if er.signals:
        st.table(
            pd.DataFrame(
                [
                    {"Signal": s.label, "Points": s.weight, "Evidence": md_safe(s.evidence)}
                    for s in er.signals
                ]
            )
        )
    else:
        st.success("No risk signals triggered — activity matches expected profile.")

    if er.alert_hits:
        st.markdown("#### External alert hits")
        st.table(
            pd.DataFrame(
                [
                    {
                        "Type": h.alert_type,
                        "Severity": h.severity,
                        "Summary": md_safe(h.summary),
                    }
                    for h in er.alert_hits
                ]
            )
        )

    st.markdown("#### Transactions")
    txns = entities[er.customer_id]["txns"]
    if not txns.empty:
        st.dataframe(
            txns[
                ["timestamp", "txn_type", "amount", "counterparty",
                 "counterparty_country", "channel"]
            ],
            use_container_width=True,
            hide_index=True,
        )


def model_compare_tab(comparison: Dict[str, Any], key_prefix: str = "model_compare") -> None:
    st.subheader("Gemini vs NVIDIA comparison")
    providers = comparison.get("providers", {})
    if not providers:
        st.info("Run the comparison from the sidebar to populate this view.")
        return

    status_cols = st.columns(len(providers))
    for col, (provider, data) in zip(status_cols, providers.items()):
        with col:
            state = "connected" if data["available"] else "fallback mode"
            color = OK_COLOR if data["available"] else WARN_COLOR
            st.markdown(
                chip(f"{data['label']} - {state}", color),
                unsafe_allow_html=True,
            )
            st.caption(f"Model: {data['model']}")

    st.markdown("#### Extracted alert differences")
    hit_rows = []
    for provider, data in providers.items():
        for hit in data["hits"]:
            hit_rows.append(
                {
                    "Provider": data["label"],
                    "Entity": hit.entity_id,
                    "Type": hit.alert_type,
                    "Severity": hit.severity,
                    "Summary": md_safe(hit.summary),
                }
            )
    if hit_rows:
        st.dataframe(pd.DataFrame(hit_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Neither model extracted an external alert hit.")

    st.markdown("#### Score / tier deltas after each model's extraction")
    delta_rows = _comparison_delta_rows(providers)
    changed = [row for row in delta_rows if row["Score delta"] != 0 or row["Tier changed"]]
    if changed:
        st.dataframe(pd.DataFrame(changed), use_container_width=True, hide_index=True)
    else:
        st.success("No score or tier differences from extracted alerts.")

    st.markdown("#### Side-by-side rationales")
    rationale_ids = sorted(
        {
            cid
            for data in providers.values()
            for cid in data.get("rationales", {}).keys()
        }
    )
    if not rationale_ids:
        st.info("No flagged customers were available for rationale comparison.")
        return

    id_to_name = {
        cid: rat["name"]
        for data in providers.values()
        for cid, rat in data.get("rationales", {}).items()
    }
    selected_id = st.selectbox(
        "Choose a flagged customer",
        rationale_ids,
        format_func=lambda cid: id_to_name.get(cid, cid),
        key=f"{key_prefix}_customer",
    )
    cols = st.columns(len(providers))
    for col, (_, data) in zip(cols, providers.items()):
        with col:
            rat = data.get("rationales", {}).get(selected_id)
            st.markdown(f"**{data['label']}**")
            if not rat:
                st.caption("This provider did not rank this customer in the compared top set.")
                continue
            source = "AI" if rat["ai_generated"] else "fallback"
            st.caption(
                f"{rat['tier']} / {rat['score']} | {rat['recommended_action']} | {source}"
            )
            st.write(md_safe(rat["rationale"]))


def _comparison_delta_rows(providers: Dict[str, Any]) -> List[Dict[str, Any]]:
    if llm.PROVIDER_GEMINI not in providers or llm.PROVIDER_OPENAI not in providers:
        return []
    gemini = {er.customer_id: er for er in providers[llm.PROVIDER_GEMINI]["register"]}
    nvidia = {er.customer_id: er for er in providers[llm.PROVIDER_OPENAI]["register"]}
    rows = []
    for customer_id in sorted(set(gemini) | set(nvidia)):
        g = gemini.get(customer_id)
        n = nvidia.get(customer_id)
        if not g or not n:
            continue
        rows.append(
            {
                "Customer": g.name,
                "Gemini score": g.score,
                "NVIDIA score": n.score,
                "Score delta": n.score - g.score,
                "Gemini tier": g.tier,
                "NVIDIA tier": n.tier,
                "Tier changed": g.tier != n.tier,
                "Gemini signals": ", ".join(g.signal_codes) or "-",
                "NVIDIA signals": ", ".join(n.signal_codes) or "-",
            }
        )
    return rows


def network_tab(result: Dict[str, Any]) -> None:
    st.subheader("Counterparty network")
    st.caption(
        "Per-customer scoring can't see this: two independently-flagged customers "
        "routing money through the same intermediary. Wire-transaction counterparties "
        "used by two or more different customers are shown as links between them — "
        "counterparties used by only one customer carry no network signal and are "
        "left out."
    )

    entities = result["entities"]
    register: List[EntityRisk] = result["register"]
    graph = build_counterparty_graph(entities, register)

    if graph.number_of_edges() == 0:
        st.info(
            "No shared wire counterparties found in this dataset — every flagged "
            "wire recipient was used by exactly one customer."
        )
        return

    st.plotly_chart(_network_graph_figure(graph), use_container_width=True)

    st.markdown("#### Shared counterparties")
    for row in shared_counterparty_summary(graph):
        names = ", ".join(
            f"{l['name']} ({l['tier']})" for l in row["linked_customers"]
        )
        st.markdown(
            f"**{row['counterparty']}** ({row['country']}) — linked to "
            f"{row['customer_count']} customers: {names}"
        )


def _network_graph_figure(g) -> go.Figure:
    import networkx as nx

    pos = nx.spring_layout(g, seed=42, k=0.9)

    edge_x, edge_y = [], []
    for u, v in g.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(width=1.5, color="#B8B2A3"),
        hoverinfo="none", showlegend=False,
    )

    cust_nodes = [n for n, d in g.nodes(data=True) if d["kind"] == "customer"]
    cp_nodes = [n for n, d in g.nodes(data=True) if d["kind"] == "counterparty"]

    cust_trace = go.Scatter(
        x=[pos[n][0] for n in cust_nodes],
        y=[pos[n][1] for n in cust_nodes],
        mode="markers+text",
        text=[g.nodes[n]["label"] for n in cust_nodes],
        textposition="top center",
        textfont=dict(family="IBM Plex Sans", size=11),
        marker=dict(
            size=[24 + g.nodes[n]["score"] * 0.25 for n in cust_nodes],
            color=[TIER_COLORS.get(g.nodes[n]["tier"], "#666") for n in cust_nodes],
            line=dict(width=2, color="white"),
        ),
        hovertext=[
            f"{g.nodes[n]['label']} — {g.nodes[n]['tier']} ({g.nodes[n]['score']}/100)"
            for n in cust_nodes
        ],
        hoverinfo="text", showlegend=False,
    )
    cp_trace = go.Scatter(
        x=[pos[n][0] for n in cp_nodes],
        y=[pos[n][1] for n in cp_nodes],
        mode="markers+text",
        text=[g.nodes[n]["label"] for n in cp_nodes],
        textposition="bottom center",
        textfont=dict(family="IBM Plex Sans", size=10, color="#5B6472"),
        marker=dict(
            symbol="diamond", size=16, color="#EDEBE6",
            line=dict(width=2, color="#5B6472"),
        ),
        hovertext=[
            f"{g.nodes[n]['label']} ({g.nodes[n]['country']}) — "
            f"{g.degree(n)} linked customers"
            for n in cp_nodes
        ],
        hoverinfo="text", showlegend=False,
    )

    fig = go.Figure(data=[edge_trace, cust_trace, cp_trace])
    fig.update_layout(
        font_family="IBM Plex Sans",
        height=420,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def floating_chat(result: Dict[str, Any]) -> None:
    """A chat bubble pinned to the bottom-right corner of the viewport (via a
    keyed container + CSS), open across every tab — not a separate page."""
    with st.container(key="floating_chat"):
        with st.popover("Ask", icon=":material/forum:"):
            st.markdown("**Ask the risk data**")
            st.caption("Answers are grounded in the current risk register.")

            history = st.session_state.setdefault("chat_history", [])
            if not history:
                st.caption(
                    "Try: \"Which customers have sanctions exposure?\" or "
                    "\"Why is Ravi Menon flagged?\""
                )
            for msg in history:
                with st.chat_message(msg["role"]):
                    st.write(md_safe(msg["content"]))

            question = st.chat_input("Ask a question…")
            if question:
                history.append({"role": "user", "content": question})
                with st.spinner("Thinking…"):
                    answer = llm.nl_query(question, result["register"])
                history.append({"role": "assistant", "content": answer})
                st.rerun()


def export_tab(result: Dict[str, Any]) -> None:
    register: List[EntityRisk] = result["register"]
    st.subheader("Export results")
    df = register_to_df(register)
    st.download_button(
        "Download register (CSV)",
        df.to_csv(index=False).encode("utf-8"),
        file_name="risk_register.csv",
        mime="text/csv",
    )
    detailed = [
        {
            "customer_id": e.customer_id,
            "name": e.name,
            "score": e.score,
            "tier": e.tier,
            "recommended_action": e.recommended_action,
            "confidence": e.confidence,
            "rationale": e.rationale,
            "signals": [s.model_dump() for s in e.signals],
            "alert_hits": [h.model_dump() for h in e.alert_hits],
        }
        for e in register
    ]
    st.download_button(
        "Download full findings (JSON)",
        json.dumps(detailed, indent=2).encode("utf-8"),
        file_name="risk_findings.json",
        mime="application/json",
    )
    st.json(detailed, expanded=False)


def _score_gauge(score: int, tier: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            title={"text": tier},
            domain={"x": [0.12, 0.88], "y": [0, 1]},
            gauge={
                "axis": {"range": [0, 100], "tickfont": {"size": 11}},
                "bar": {"color": TIER_COLORS.get(tier, "#666")},
                "steps": [
                    {"range": [0, 25], "color": "#E4ECE4"},
                    {"range": [25, 50], "color": "#EFE8D6"},
                    {"range": [50, 75], "color": "#F1E2CE"},
                    {"range": [75, 100], "color": "#F0D9D6"},
                ],
            },
        )
    )
    fig.update_layout(
        height=220, margin=dict(l=35, r=35, t=40, b=15), font_family="IBM Plex Sans"
    )
    return fig


def _score_waterfall(er: EntityRisk) -> go.Figure:
    """Shows exactly how each rule's weight stacked up to the final score —
    the visual proof that the number is auditable, not an AI guess."""
    labels = [s.label for s in er.signals] + ["Total"]
    weights = [s.weight for s in er.signals]
    raw_total = sum(weights)
    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=["relative"] * len(weights) + ["total"],
            x=labels,
            y=weights + [0],
            text=[f"+{w}" for w in weights] + [str(raw_total)],
            textposition="outside",
            connector={"line": {"color": "#DDD9CF"}},
            increasing={"marker": {"color": TIER_COLORS.get(er.tier, "#666")}},
            totals={"marker": {"color": "#14171C"}},
        )
    )
    if raw_total > 100:
        fig.add_hline(
            y=100, line_dash="dash", line_color="#9B1C1C",
            annotation_text="score cap (100)", annotation_position="top left",
            annotation_font_size=10,
        )
    fig.update_layout(
        showlegend=False, font_family="IBM Plex Sans", height=280,
        margin=dict(l=10, r=10, t=20, b=10),
        yaxis=dict(range=[0, max(105, raw_total + 10)], title="Points"),
    )
    return fig


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    inject_theme()
    sidebar()
    st.title("Financial Risk Signal Aggregator")
    st.caption(
        "Aggregates transaction records, account activity and external alerts into a "
        "prioritised, risk-scored view — deterministic rules score, Gemini explains."
    )

    if "result" not in st.session_state:
        st.info(
            "Click **Load sample dataset**, then **Run risk analysis** to see the "
            "prototype end-to-end. You can also upload your own CSV/JSON and paste alerts."
        )
        with st.expander("How scoring works"):
            st.markdown(
                "- **Rules engine** (transparent, in `config.py`) fires weighted signals "
                "such as structuring, pass-through layering, sanctioned-jurisdiction "
                "exposure, velocity spikes, PEP and adverse media.\n"
                "- Weights sum to a **0–100 score** → tier "
                "(**Low <25 · Medium <50 · High <75 · Critical ≥75**).\n"
                "- **Gemini** parses unstructured alerts into signals and writes the "
                "rationale — it never invents the score."
            )
        return

    result = st.session_state["result"]
    if st.session_state.pop("comparison_ready", False):
        st.success(
            "Model comparison complete. Showing it below; it is also available in "
            "the Model Compare tab."
        )
        model_compare_tab(
            st.session_state.get("model_comparison", {}),
            key_prefix="model_compare_inline",
        )

    tabs = st.tabs(
        ["Overview", "Risk Register", "Drill-down", "Network", "Model Compare", "Export"]
    )
    with tabs[0]:
        overview_tab(result)
    with tabs[1]:
        register_tab(result)
    with tabs[2]:
        drilldown_tab(result)
    with tabs[3]:
        network_tab(result)
    with tabs[4]:
        model_compare_tab(
            st.session_state.get("model_comparison", {}),
            key_prefix="model_compare_tab",
        )
    with tabs[5]:
        export_tab(result)

    floating_chat(result)


if __name__ == "__main__":
    main()
