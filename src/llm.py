"""
LLM layer — multi-provider (Google Gemini, or any OpenAI-compatible API such
as NVIDIA NIM, OpenAI itself, or Groq).

Responsibilities — and their strict limits:
  1. extract_alerts   : parse unstructured alert text into structured hits.
  2. entity_rationale : explain a flagged entity, grounded in its signals.
  3. exec_summary     : portfolio-level narrative for a compliance lead.
  4. nl_query         : answer questions grounded in the risk register.

The LLM NEVER computes a risk score — the deterministic rule engine does that.
Every function degrades gracefully: if no provider is configured (or a call
fails), a transparent heuristic/templated fallback is used so the app always
works. Fallback results are flagged so the UI can say "AI unavailable".

Provider selection: `get_provider()` checks (in order) a Streamlit session
override (set by the sidebar dropdown), the LLM_PROVIDER env var, defaulting
to Gemini. Everything below `_generate()` — extract_alerts, entity_rationale,
exec_summary, nl_query — is provider-agnostic; they only ever call
`is_available()` / `_generate()`, so adding a provider means touching only
the block below, not the four functions that use it.
"""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import config
from src.schemas import AlertHit, EntityRisk

# Optional dependencies — the app must still run if either is missing.
try:
    from google import genai

    _GENAI_IMPORTED = True
except Exception:  # pragma: no cover
    genai = None
    _GENAI_IMPORTED = False

try:
    import openai as _openai_sdk

    _OPENAI_IMPORTED = True
except Exception:  # pragma: no cover
    _openai_sdk = None
    _OPENAI_IMPORTED = False

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

PROVIDER_GEMINI = "gemini"
PROVIDER_OPENAI = "openai_compatible"
PROVIDERS = {
    PROVIDER_GEMINI: "Google Gemini",
    PROVIDER_OPENAI: "NVIDIA NIM / OpenAI-compatible",
}

PROVIDER_KEY_NAMES = {
    PROVIDER_GEMINI: ("GEMINI_API_KEY",),
    # NVIDIA's examples use NVIDIA_API_KEY. OPENAI_API_KEY remains supported so
    # the same provider path can still target OpenAI, Groq, or another gateway.
    PROVIDER_OPENAI: ("NVIDIA_API_KEY", "OPENAI_API_KEY"),
}

_NEGATIVE_KEYWORDS = (
    "probe", "sanction", "ofac", "adverse", "bribery", "kickback",
    "watchlist", "suspicious", "laundering", "fraud", "investigation",
)
_CLEAN_PHRASES = (
    "no adverse", "no derogatory", "no findings", "clean", "no action required",
    "no direct sanctions match", "within policy",
)


# ---------------------------------------------------------------------------
# Provider selection, API keys, availability
# ---------------------------------------------------------------------------
# NOTE: this is a *different* key from the sidebar's "llm_provider" widget key.
# Streamlit forbids programmatically overwriting st.session_state for a key
# that's already bound to a widget instantiated in the current script run — so
# use_provider() must NOT touch "llm_provider" directly (it silently fails via
# a caught StreamlitAPIException, leaving get_provider() stuck on whatever the
# sidebar dropdown shows — this was a real bug: the "Gemini vs NVIDIA" compare
# feature silently called Gemini twice whenever the sidebar was on its default
# Gemini selection). A separate, non-widget-bound key sidesteps that entirely.
_PROVIDER_OVERRIDE_KEY = "_llm_provider_override"


def _session_get(key: str) -> Optional[str]:
    """Read a Streamlit session_state value if Streamlit is running; else None."""
    try:
        import streamlit as st  # local import — keep core LLM usable without Streamlit

        return st.session_state.get(key)
    except Exception:
        return None


def get_provider() -> str:
    """Currently selected provider: use_provider() override > sidebar widget >
    env var > Gemini default."""
    return (
        _session_get(_PROVIDER_OVERRIDE_KEY)
        or _session_get("llm_provider")
        or os.getenv("LLM_PROVIDER", PROVIDER_GEMINI)
    )


@contextmanager
def use_provider(provider: str) -> Iterator[None]:
    """Temporarily route provider-agnostic LLM calls to a specific provider,
    without touching the sidebar widget's own session_state key."""
    try:
        import streamlit as st

        had_value = _PROVIDER_OVERRIDE_KEY in st.session_state
        previous = st.session_state.get(_PROVIDER_OVERRIDE_KEY)
        st.session_state[_PROVIDER_OVERRIDE_KEY] = provider
        try:
            yield
        finally:
            if had_value:
                st.session_state[_PROVIDER_OVERRIDE_KEY] = previous
            else:
                st.session_state.pop(_PROVIDER_OVERRIDE_KEY, None)
    except Exception:
        previous_env = os.getenv("LLM_PROVIDER")
        os.environ["LLM_PROVIDER"] = provider
        try:
            yield
        finally:
            if previous_env is None:
                os.environ.pop("LLM_PROVIDER", None)
            else:
                os.environ["LLM_PROVIDER"] = previous_env


def get_api_key(provider: Optional[str] = None) -> Optional[str]:
    """Look for the active provider's key in Streamlit secrets, then the env."""
    provider = provider or get_provider()
    session_key = "gemini_api_key" if provider == PROVIDER_GEMINI else "openai_api_key"
    session_value = _session_get(session_key)
    if session_value:
        return session_value.strip()
    key_names = PROVIDER_KEY_NAMES.get(provider, ("OPENAI_API_KEY",))
    try:
        import streamlit as st

        for key_name in key_names:
            if key_name in st.secrets:
                return st.secrets[key_name]
    except Exception:
        pass
    for key_name in key_names:
        value = os.getenv(key_name)
        if value:
            return value
    return None


def expected_key_names(provider: Optional[str] = None) -> tuple[str, ...]:
    """Environment/secret names accepted for the selected provider."""
    provider = provider or get_provider()
    return PROVIDER_KEY_NAMES.get(provider, ("OPENAI_API_KEY",))


def is_available(provider: Optional[str] = None) -> bool:
    provider = provider or get_provider()
    if provider == PROVIDER_GEMINI:
        return _GENAI_IMPORTED and bool(get_api_key(PROVIDER_GEMINI))
    return _OPENAI_IMPORTED and bool(get_api_key(PROVIDER_OPENAI))


def provider_status() -> Dict[str, Any]:
    """Everything the sidebar needs to render a status chip."""
    provider = get_provider()
    return {
        "provider": provider,
        "label": PROVIDERS.get(provider, provider),
        "available": is_available(provider),
        "model": _model_name(provider),
    }


def _model_name(provider: Optional[str] = None) -> str:
    provider = provider or get_provider()
    if provider == PROVIDER_GEMINI:
        return os.getenv("GEMINI_MODEL", config.DEFAULT_GEMINI_MODEL)
    return os.getenv("OPENAI_MODEL", config.DEFAULT_OPENAI_MODEL)


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Low-level generation
# ---------------------------------------------------------------------------
def _generate(prompt: str) -> Optional[str]:
    """Call the active provider and return raw text, or None on failure."""
    provider = get_provider()
    if not is_available(provider):
        return None
    if provider == PROVIDER_GEMINI:
        return _generate_gemini(prompt)
    return _generate_openai_compatible(prompt)


def _generate_gemini(prompt: str) -> Optional[str]:
    client = genai.Client(api_key=get_api_key(PROVIDER_GEMINI))
    for model in (_model_name(PROVIDER_GEMINI), config.FALLBACK_GEMINI_MODEL):
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            text = (resp.text or "").strip()
            if text:
                return text
        except Exception:
            continue
    return None


def _generate_openai_compatible(prompt: str) -> Optional[str]:
    """Works for NVIDIA NIM, OpenAI itself, Groq, or any OpenAI-compatible API —
    swap OPENAI_BASE_URL / OPENAI_MODEL to point at a different one."""
    try:
        client = _openai_sdk.OpenAI(
            api_key=get_api_key(PROVIDER_OPENAI),
            base_url=os.getenv("OPENAI_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        )
        resp = client.chat.completions.create(
            model=_model_name(PROVIDER_OPENAI),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception:
        return None


def _parse_json(text: Optional[str]) -> Optional[Any]:
    """Extract a JSON object/array from a model response (tolerant of fences)."""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"(\[.*\]|\{.*\})", cleaned, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                return None
    return None


# ---------------------------------------------------------------------------
# 1. Alert extraction
# ---------------------------------------------------------------------------
def extract_alerts(alert_text: str, entities: Dict[str, str]) -> List[AlertHit]:
    """entities: {customer_id: name}. Returns structured AlertHits."""
    if not alert_text or not alert_text.strip():
        return []

    if is_available():
        listing = "\n".join(f"{cid} -> {name}" for cid, name in entities.items())
        prompt = _load_prompt("extract_alerts.txt").format(
            entities=listing, alert_text=alert_text
        )
        data = _parse_json(_generate(prompt))
        if isinstance(data, list):
            hits: List[AlertHit] = []
            for item in data:
                try:
                    hits.append(AlertHit(**item))
                except Exception:
                    continue
            return hits

    return _fallback_extract(alert_text, entities)


def _fallback_extract(alert_text: str, entities: Dict[str, str]) -> List[AlertHit]:
    """Heuristic extraction used when no LLM is available."""
    hits: List[AlertHit] = []
    paragraphs = re.split(r"\n\s*\n", alert_text)
    for cid, name in entities.items():
        for para in paragraphs:
            low = para.lower()
            if name.lower() not in low:
                continue
            if any(p in low for p in _CLEAN_PHRASES):
                continue
            if any(k in low for k in _NEGATIVE_KEYWORDS):
                sev = "high" if ("ofac" in low or "sanction" in low) else "medium"
                hits.append(
                    AlertHit(
                        entity_id=cid,
                        alert_type="adverse_media",
                        severity=sev,
                        summary=para.strip().replace("\n", " ")[:180],
                        source="heuristic",
                    )
                )
                break
    return hits


# ---------------------------------------------------------------------------
# 2. Per-entity rationale
# ---------------------------------------------------------------------------
def entity_rationale(entity_risk: EntityRisk, profile: Dict[str, Any]) -> Dict[str, str]:
    if entity_risk.signals and is_available():
        signals_txt = "\n".join(
            f"- {s.label} (+{s.weight}): {s.evidence}" for s in entity_risk.signals
        )
        prompt = _load_prompt("entity_rationale.txt").format(
            profile=json.dumps(profile, indent=2),
            score=entity_risk.score,
            tier=entity_risk.tier,
            signals=signals_txt,
            actions=" / ".join(config.RECOMMENDED_ACTIONS),
        )
        data = _parse_json(_generate(prompt))
        if isinstance(data, dict) and data.get("rationale"):
            action = data.get("recommended_action", "")
            if action not in config.RECOMMENDED_ACTIONS:
                action = _fallback_action(entity_risk.tier)
            return {
                "rationale": data["rationale"],
                "recommended_action": action,
                "confidence": str(data.get("confidence", "medium")).lower(),
                "ai_generated": True,
            }

    return _fallback_rationale(entity_risk)


def _fallback_rationale(er: EntityRisk) -> Dict[str, Any]:
    if not er.signals:
        return {
            "rationale": "No risk signals were triggered for this customer; activity "
            "is consistent with the expected profile.",
            "recommended_action": "Monitor",
            "confidence": "high",
            "ai_generated": False,
        }
    reasons = "; ".join(s.evidence for s in er.signals)
    n = er.num_signals
    confidence = "high" if n >= 3 else "medium" if n == 2 else "low"
    return {
        "rationale": f"Flagged {er.tier} on {n} signal(s): {reasons}",
        "recommended_action": _fallback_action(er.tier),
        "confidence": confidence,
        "ai_generated": False,
    }


def _fallback_action(tier: str) -> str:
    return {
        "Critical": "File SAR",
        "High": "Escalate to MLRO",
        "Medium": "Enhanced Due Diligence",
        "Low": "Monitor",
    }.get(tier, "Monitor")


# ---------------------------------------------------------------------------
# 3. Executive summary
# ---------------------------------------------------------------------------
def exec_summary(register: List[EntityRisk]) -> str:
    if is_available():
        compact = _register_json(register)
        prompt = _load_prompt("exec_summary.txt").format(register=compact)
        text = _generate(prompt)
        if text:
            return text
    return _fallback_summary(register)


def _fallback_summary(register: List[EntityRisk]) -> str:
    crit = [e.name for e in register if e.tier == "Critical"]
    high = [e.name for e in register if e.tier == "High"]
    parts = [f"Reviewed {len(register)} customers."]
    if crit:
        parts.append(f"{len(crit)} Critical: {', '.join(crit)}.")
    if high:
        parts.append(f"{len(high)} High: {', '.join(high)}.")
    if register:
        top = register[0]
        parts.append(
            f"Action {top.name} first ({top.tier}, score {top.score}): "
            f"{', '.join(top.signal_codes) or 'no signals'}."
        )
    return " ".join(parts)


# ---------------------------------------------------------------------------
# 4. Natural-language query
# ---------------------------------------------------------------------------
def nl_query(question: str, register: List[EntityRisk]) -> str:
    if is_available():
        prompt = _load_prompt("nl_query.txt").format(
            register=_register_json(register), question=question
        )
        text = _generate(prompt)
        if text:
            return text
    provider = get_provider()
    key_names = " or ".join(expected_key_names(provider))
    return (
        f"Natural-language answers need an API key for {PROVIDERS.get(provider, provider)}. "
        f"Configure {key_names} to enable this. "
        "(The rest of the dashboard works without it.)"
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _register_json(register: List[EntityRisk]) -> str:
    rows = [
        {
            "customer_id": e.customer_id,
            "name": e.name,
            "score": e.score,
            "tier": e.tier,
            "signals": [{"code": s.code, "evidence": s.evidence} for s in e.signals],
            "recommended_action": e.recommended_action,
        }
        for e in register
    ]
    return json.dumps(rows, indent=2)
