"""
Generates a larger, more realistic sample dataset for the Financial Risk
Signal Aggregator.

Design goals:
  - Keep the 5 original hero customers (cust_001..cust_005) and their exact
    planted transactions/alerts UNCHANGED, byte-for-byte in substance, so the
    existing pytest scenario tests keep passing without modification.
  - Add ~55 more customers: the large majority genuinely clean (normal salary
    / bills / shopping patterns, zero rule triggers) to prove the tool doesn't
    just flag everyone at scale, plus a handful of NEW distinct suspicious
    archetypes (different countries/typologies) for variety beyond the
    original 5.
  - Realistic spread: many countries, occupations, transaction channels, and
    a multi-month timestamp window rather than a compressed 3-week window.
  - Deterministic: fixed random seed so re-running reproduces the same file.

Requires Faker (dev-only — not in requirements.txt, not needed at app runtime):
  pip install Faker

Run:  python scripts/generate_dataset.py
Then: pytest -q   (must still pass 7/7)
"""

from __future__ import annotations

import csv
import json
import os
import random
from datetime import datetime, timedelta

from faker import Faker

SEED = 7
random.seed(SEED)
fake = Faker()
Faker.seed(SEED)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")

# Window for newly generated ("background" + new-scenario) activity.
WINDOW_START = datetime(2026, 2, 1)
WINDOW_END = datetime(2026, 7, 20)

COUNTRIES = [
    "US", "GB", "CA", "AU", "DE", "FR", "SG", "IN", "AE", "ZA",
    "BR", "MX", "NL", "JP", "KE", "NG", "PH", "ES", "IT", "SE",
]
OCCUPATIONS = [
    "Software Engineer", "Nurse", "Teacher", "Accountant", "Sales Manager",
    "Graphic Designer", "Electrician", "Retail Manager", "Marketing Analyst",
    "Civil Engineer", "Consultant", "Small Business Owner", "Chef",
    "HR Manager", "Pharmacist", "Architect", "Logistics Coordinator",
    "Financial Analyst", "Physiotherapist", "Real Estate Agent",
]
CHANNELS = ["online", "mobile", "branch"]
UTILITY_PAYEES = [
    "City Utilities", "Regional Electric Board", "Metro Water Authority",
    "National Broadband Co", "Mobile Telecom", "Gas & Power Ltd",
]
RENT_PAYEES = ["City Rentals", "Metro Landlord LLC", "Parkview Apartments", "Home Realty Trust"]
SHOP_PAYEES = ["Grocery Mart", "Superstore Retail", "Online Marketplace", "Corner Pharmacy", "Home Goods Co"]


def money(low: float, high: float) -> float:
    return round(random.uniform(low, high), 2)


def random_dt(start: datetime = WINDOW_START, end: datetime = WINDOW_END) -> datetime:
    delta = end - start
    seconds = random.randint(0, int(delta.total_seconds()))
    dt = start + timedelta(seconds=seconds)
    return dt.replace(hour=random.randint(7, 21), minute=random.randint(0, 59))


def fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# 1. The five original hero customers — kept exactly as before.
# ---------------------------------------------------------------------------
ORIGINAL_CUSTOMERS = [
    {
        "customer_id": "cust_001", "name": "Ravi Menon", "kyc_status": "verified",
        "base_risk_rating": "medium", "account_open_date": "2021-03-14", "country": "US",
        "is_pep": False, "expected_monthly_volume": 15000, "occupation": "Restaurant Owner",
    },
    {
        "customer_id": "cust_002", "name": "John Doe", "kyc_status": "verified",
        "base_risk_rating": "high", "account_open_date": "2019-08-02", "country": "US",
        "is_pep": True, "expected_monthly_volume": 12000, "occupation": "Regional Government Official",
    },
    {
        "customer_id": "cust_003", "name": "Wei Chen", "kyc_status": "verified",
        "base_risk_rating": "medium", "account_open_date": "2018-05-20", "country": "SG",
        "is_pep": False, "expected_monthly_volume": 300000, "occupation": "Import/Export Business",
    },
    {
        "customer_id": "cust_004", "name": "Priya Shah", "kyc_status": "verified",
        "base_risk_rating": "low", "account_open_date": "2020-11-11", "country": "US",
        "is_pep": False, "expected_monthly_volume": 6000, "occupation": "Software Engineer",
    },
    {
        "customer_id": "cust_005", "name": "Sara Lopez", "kyc_status": "pending",
        "base_risk_rating": "medium", "account_open_date": "2026-07-01", "country": "US",
        "is_pep": False, "expected_monthly_volume": 8000, "occupation": "Freelance Consultant",
    },
]

ORIGINAL_TRANSACTIONS = [
    ["t001", "2026-07-10 09:15", "cust_001", "acct_1001", 9500, "USD", "cash_deposit", "Self", "US", "branch"],
    ["t002", "2026-07-10 14:20", "cust_001", "acct_1001", 9300, "USD", "cash_deposit", "Self", "US", "branch"],
    ["t003", "2026-07-11 10:05", "cust_001", "acct_1001", 9700, "USD", "cash_deposit", "Self", "US", "branch"],
    ["t004", "2026-07-11 15:40", "cust_001", "acct_1001", 9500, "USD", "cash_deposit", "Self", "US", "branch"],
    ["t005", "2026-07-11 16:55", "cust_001", "acct_1001", 9600, "USD", "cash_deposit", "Self", "US", "branch"],
    ["t006", "2026-07-12 09:30", "cust_001", "acct_1001", 9400, "USD", "cash_deposit", "Self", "US", "branch"],
    ["t007", "2026-07-12 12:10", "cust_001", "acct_1001", 9900, "USD", "cash_deposit", "Self", "US", "branch"],
    ["t008", "2026-07-12 17:00", "cust_001", "acct_1001", 9500, "USD", "cash_deposit", "Self", "US", "branch"],
    ["t009", "2026-07-13 11:00", "cust_001", "acct_1001", 1200, "USD", "payment", "Metro Landlord LLC", "US", "online"],
    ["t010", "2026-06-30 08:00", "cust_002", "acct_1002", 8000, "USD", "salary", "State Payroll Office", "US", "online"],
    ["t011", "2026-07-05 19:30", "cust_002", "acct_1002", 2500, "USD", "payment", "City Utilities", "US", "online"],
    ["t012", "2026-07-08 14:00", "cust_002", "acct_1002", 120000, "USD", "wire_out", "Pardis Holdings", "IR", "online"],
    ["t013", "2024-11-01 10:00", "cust_003", "acct_1003", 500, "USD", "payment", "Office Supplies Co", "US", "online"],
    ["t014", "2026-07-15 09:00", "cust_003", "acct_1003", 250000, "USD", "wire_in", "Global Traders Ltd", "AE", "online"],
    ["t015", "2026-07-15 15:30", "cust_003", "acct_1003", 248000, "USD", "wire_out", "Sunrise Import Co", "SG", "online"],
    ["t016", "2026-06-28 08:00", "cust_004", "acct_1004", 5200, "USD", "salary", "Acme Corp Payroll", "US", "online"],
    ["t017", "2026-07-01 09:10", "cust_004", "acct_1004", 1400, "USD", "payment", "City Rentals", "US", "online"],
    ["t018", "2026-07-03 18:45", "cust_004", "acct_1004", 320, "USD", "payment", "Regional Electric Board", "US", "online"],
    ["t019", "2026-07-09 13:20", "cust_004", "acct_1004", 210, "USD", "payment", "Grocery Mart", "US", "mobile"],
    ["t020", "2026-07-12 20:05", "cust_004", "acct_1004", 150, "USD", "payment", "Mobile Telecom", "US", "mobile"],
    ["t021", "2026-07-02 11:00", "cust_005", "acct_1005", 21000, "USD", "wire_in", "Crypto Exchange X", "US", "online"],
    ["t022", "2026-07-03 12:30", "cust_005", "acct_1005", 18000, "USD", "wire_in", "Crypto Exchange X", "US", "online"],
    ["t023", "2026-07-05 16:10", "cust_005", "acct_1005", 22000, "USD", "wire_in", "P2P Transfer Network", "US", "online"],
    ["t024", "2026-07-06 09:45", "cust_005", "acct_1005", 25000, "USD", "wire_in", "P2P Transfer Network", "US", "online"],
]

ORIGINAL_ALERTS = """COMPLIANCE INBOX — UNSTRUCTURED EXTERNAL ALERTS & ANALYST NOTES
(Free-text, mixed sources. The AI layer parses this into structured hits per customer.)

[Reuters, 12 Jun 2026] "Acme Trading, a firm linked to local businessman Ravi Menon,
has been named in an ongoing bribery and kickback probe by regional prosecutors."
Internal note (K. Rao): Menon operates a cash-heavy restaurant; recent branch deposits
look unusual. Flag for review.

--- forwarded message ---
Sanctions screening hit: The wire counterparty "Pardis Holdings" used by customer
John Doe appears on an OFAC advisory list associated with sanctioned Iranian entities.
Note: John Doe is a listed politically exposed person (PEP). Treat as high severity.

Watchlist run (nightly batch): Wei Chen — no direct sanctions match. Counterparties
"Global Traders Ltd" and "Sunrise Import Co" are not on any list, but the same-day
in-and-out pattern was noted by the transaction monitoring system.

New-account review: Sara Lopez opened an account on 01 Jul. Inbound transfers from a
crypto exchange are within policy for now; no derogatory information found in open
sources. Low priority.

Adverse media screen: Priya Shah — no adverse findings. Clean across sanctions,
PEP and negative-news sources. No action required.
"""

# ---------------------------------------------------------------------------
# 2. New suspicious archetypes — different typologies/countries for variety.
# ---------------------------------------------------------------------------
def gen_structuring_case(cid: str, acct: str, name: str) -> tuple[dict, list, str | None]:
    """Structuring, new country/timing — GB based small trader."""
    profile = {
        "customer_id": cid, "name": name, "kyc_status": "verified",
        "base_risk_rating": "medium", "account_open_date": "2020-02-10", "country": "GB",
        "is_pep": False, "expected_monthly_volume": 9000, "occupation": "Market Trader",
    }
    base = datetime(2026, 5, 4, 9, 0)
    txns = []
    for i in range(4):
        amt = round(random.uniform(9100, 9950), 0)
        ts = base + timedelta(days=i // 2, hours=(i % 2) * 5)
        txns.append([f"g_{cid}_{i}", fmt(ts), cid, acct, amt, "GBP", "cash_deposit", "Self", "GB", "branch"])
    txns.append([f"g_{cid}_rent", fmt(base + timedelta(days=6)), cid, acct, 950, "GBP", "payment", "City Rentals", "GB", "online"])
    alert = (
        f'[Regional Gazette] "{name}, who operates a market stall business, is under '
        f'review after an anonymous tip alleged undeclared cash income linked to '
        f'counterfeit goods." Internal note: cash deposit pattern flagged by branch staff.'
    )
    return profile, txns, alert


def gen_sanctions_pep_case(cid: str, acct: str, name: str) -> tuple[dict, list, str | None]:
    """PEP + high-risk jurisdiction wire, different country pairing."""
    profile = {
        "customer_id": cid, "name": name, "kyc_status": "verified",
        "base_risk_rating": "high", "account_open_date": "2017-09-01", "country": "ZA",
        "is_pep": True, "expected_monthly_volume": 20000, "occupation": "Ministry Advisor",
    }
    base = datetime(2026, 4, 12, 10, 0)
    txns = [
        [f"g_{cid}_salary", fmt(base - timedelta(days=10)), cid, acct, 18500, "USD", "salary", "National Treasury", "ZA", "online"],
        [f"g_{cid}_wire", fmt(base), cid, acct, 90000, "USD", "wire_out", "Silver Crescent Trading", "MM", "online"],
    ]
    alert = (
        f'Sanctions screening: wire counterparty "Silver Crescent Trading" used by {name} '
        f"is flagged on a regional sanctions advisory tied to Myanmar military-linked "
        f"entities. {name} holds a senior ministry advisory role (PEP)."
    )
    return profile, txns, alert


def gen_layering_case(cid: str, acct: str, name: str) -> tuple[dict, list, str | None]:
    """Dormant reactivation + same-day pass-through, different country.

    Deliberately routes the outbound leg through "Silver Crescent Trading" —
    the same sanctioned shell company used by the sanctions/PEP archetype
    (gen_sanctions_pep_case) — so the counterparty network graph has a real,
    non-trivial cross-customer link to reveal: two independently-flagged
    customers funnelling money through the same intermediary.
    """
    profile = {
        "customer_id": cid, "name": name, "kyc_status": "verified",
        "base_risk_rating": "medium", "account_open_date": "2016-01-20", "country": "AE",
        "is_pep": False, "expected_monthly_volume": 150000, "occupation": "Trading Company Director",
    }
    dormant_start = datetime(2025, 10, 1, 9, 0)
    reactivate = datetime(2026, 5, 20, 11, 0)
    txns = [
        [f"g_{cid}_old", fmt(dormant_start), cid, acct, 800, "USD", "payment", "Office Lease Co", "AE", "online"],
        [f"g_{cid}_in", fmt(reactivate), cid, acct, 180000, "USD", "wire_in", "Horizon Commodities FZE", "AE", "online"],
        [f"g_{cid}_out", fmt(reactivate + timedelta(hours=6)), cid, acct, 176000, "USD", "wire_out", "Silver Crescent Trading", "MM", "online"],
    ]
    return profile, txns, None


def gen_velocity_case(cid: str, acct: str, name: str) -> tuple[dict, list, str | None]:
    """Velocity spike only — crypto-linked inflows far above expected volume."""
    profile = {
        "customer_id": cid, "name": name, "kyc_status": "pending",
        "base_risk_rating": "medium", "account_open_date": "2026-06-01", "country": "US",
        "is_pep": False, "expected_monthly_volume": 5000, "occupation": "Freelance Consultant",
    }
    base = datetime(2026, 6, 15, 10, 0)
    txns = []
    for i in range(5):
        amt = round(random.uniform(6000, 9500), 0)
        ts = base + timedelta(days=i * 2)
        txns.append([f"g_{cid}_{i}", fmt(ts), cid, acct, amt, "USD", "wire_in", "Crypto Exchange Y", "US", "online"])
    return profile, txns, None


def gen_cash_intensive_case(cid: str, acct: str, name: str) -> tuple[dict, list, str | None]:
    """Small-business cash-intensive profile."""
    profile = {
        "customer_id": cid, "name": name, "kyc_status": "verified",
        "base_risk_rating": "medium", "account_open_date": "2019-04-15", "country": "NG",
        "is_pep": False, "expected_monthly_volume": 7000, "occupation": "Convenience Store Owner",
    }
    base = datetime(2026, 3, 10, 9, 0)
    txns = []
    for i in range(6):
        ts = base + timedelta(days=i * 5)
        txns.append([f"g_{cid}_c{i}", fmt(ts), cid, acct, round(random.uniform(1200, 3200), 0), "USD", "cash_deposit", "Self", "NG", "branch"])
    txns.append([f"g_{cid}_rent", fmt(base + timedelta(days=8)), cid, acct, 600, "USD", "payment", "Metro Landlord LLC", "NG", "online"])
    return profile, txns, None


def gen_round_number_case(cid: str, acct: str, name: str) -> tuple[dict, list, str | None]:
    """Round-figure wire only — mild signal, tests low-end scoring."""
    profile = {
        "customer_id": cid, "name": name, "kyc_status": "verified",
        "base_risk_rating": "low", "account_open_date": "2015-06-01", "country": "DE",
        "is_pep": False, "expected_monthly_volume": 25000, "occupation": "Consultant",
    }
    ts = datetime(2026, 6, 2, 14, 0)
    txns = [[f"g_{cid}_w", fmt(ts), cid, acct, 60000, "USD", "wire_out", "Alpine Equity Partners", "CH", "online"]]
    return profile, txns, None


def gen_kyc_adverse_case(cid: str, acct: str, name: str) -> tuple[dict, list, str | None]:
    """Incomplete KYC + a lower-severity adverse-media mention."""
    profile = {
        "customer_id": cid, "name": name, "kyc_status": "incomplete",
        "base_risk_rating": "medium", "account_open_date": "2026-05-01", "country": "PH",
        "is_pep": False, "expected_monthly_volume": 4000, "occupation": "Online Retailer",
    }
    ts = datetime(2026, 6, 20, 10, 0)
    txns = [
        [f"g_{cid}_in", fmt(ts), cid, acct, 4200, "USD", "payment", "Marketplace Payouts", "PH", "online"],
        [f"g_{cid}_out", fmt(ts + timedelta(days=2)), cid, acct, 900, "USD", "payment", "Home Goods Co", "PH", "online"],
    ]
    alert = (
        f'Local news brief: "{name}, an online retailer, was named alongside several '
        f'other small merchants in a consumer-complaint roundup about delayed refunds." '
        f"Note: account onboarding documents are still incomplete."
    )
    return profile, txns, alert


def gen_real_sdn_match_case(cid: str, acct: str, name: str) -> tuple[dict, list, str | None]:
    """Near-exact OFAC SDN counterparty match, below other wire thresholds."""
    profile = {
        "customer_id": cid, "name": name, "kyc_status": "verified",
        "base_risk_rating": "medium", "account_open_date": "2022-02-18", "country": "US",
        "is_pep": False, "expected_monthly_volume": 65000, "occupation": "Import Consultant",
    }
    base = datetime(2026, 6, 18, 13, 30)
    txns = [
        [f"g_{cid}_consulting", fmt(base - timedelta(days=12)), cid, acct, 62000, "USD", "salary", "Trade Advisory Payroll", "US", "online"],
        # Near-exact match for real OFAC SDN entry "BANCO NACIONAL DE CUBA".
        [f"g_{cid}_sdn", fmt(base), cid, acct, 48000, "USD", "wire_out", "Banco Nacional Cuba", "CU", "online"],
        [f"g_{cid}_rent", fmt(base + timedelta(days=3)), cid, acct, 1800, "USD", "payment", "City Rentals", "US", "online"],
    ]
    return profile, txns, None


NEW_SCENARIO_GENERATORS = [
    gen_structuring_case,
    gen_sanctions_pep_case,
    gen_layering_case,
    gen_velocity_case,
    gen_cash_intensive_case,
    gen_round_number_case,
    gen_kyc_adverse_case,
    gen_real_sdn_match_case,
]

# ---------------------------------------------------------------------------
# 3. Clean background customers — normal activity, should score 0.
# ---------------------------------------------------------------------------
def gen_clean_customer(cid: str, acct: str) -> tuple[dict, list]:
    name = fake.name()
    country = random.choice(COUNTRIES)
    volume = random.choice([3000, 4000, 5000, 6000, 7000, 8000, 9500, 11000, 13000])
    profile = {
        "customer_id": cid, "name": name, "kyc_status": "verified",
        "base_risk_rating": random.choice(["low", "low", "low", "medium"]),
        "account_open_date": fake.date_between(start_date="-8y", end_date="-1y").isoformat(),
        "country": country, "is_pep": False,
        "expected_monthly_volume": volume, "occupation": random.choice(OCCUPATIONS),
    }

    txns = []
    months = 5
    for m in range(months):
        month_start = WINDOW_START + timedelta(days=30 * m)
        # Salary — one clean inflow well under the velocity multiplier.
        salary = round(volume * random.uniform(0.75, 0.95), 2)
        salary_dt = month_start + timedelta(days=random.randint(0, 2), hours=random.randint(7, 10))
        txns.append([
            f"c_{cid}_sal_{m}", fmt(salary_dt), cid, acct, salary, "USD", "salary",
            fake.company() + " Payroll", country, "online",
        ])
        # Rent/mortgage.
        rent = round(volume * random.uniform(0.18, 0.3), 2)
        rent_dt = month_start + timedelta(days=random.randint(2, 5), hours=random.randint(8, 20))
        txns.append([
            f"c_{cid}_rent_{m}", fmt(rent_dt), cid, acct, rent, "USD", "payment",
            random.choice(RENT_PAYEES), country, "online",
        ])
        # 1-2 utility bills.
        for k in range(random.randint(1, 2)):
            util_dt = month_start + timedelta(days=random.randint(5, 15), hours=random.randint(8, 21))
            txns.append([
                f"c_{cid}_util_{m}_{k}", fmt(util_dt), cid, acct, money(30, 260), "USD", "payment",
                random.choice(UTILITY_PAYEES), country, random.choice(CHANNELS),
            ])
        # 2-4 everyday shopping/grocery payments.
        for k in range(random.randint(2, 4)):
            shop_dt = month_start + timedelta(days=random.randint(0, 27), hours=random.randint(9, 21))
            txns.append([
                f"c_{cid}_shop_{m}_{k}", fmt(shop_dt), cid, acct, money(15, 180), "USD", "payment",
                random.choice(SHOP_PAYEES), country, random.choice(["online", "mobile"]),
            ])
        # Occasional small cash withdrawal — nowhere near structuring range.
        if random.random() < 0.5:
            cash_dt = month_start + timedelta(days=random.randint(0, 27), hours=random.randint(10, 18))
            txns.append([
                f"c_{cid}_cash_{m}", fmt(cash_dt), cid, acct, money(60, 400), "USD",
                "cash_withdrawal", "Self", country, "branch",
            ])
    return profile, txns


# ---------------------------------------------------------------------------
# Build the full dataset.
# ---------------------------------------------------------------------------
def main():
    customers = list(ORIGINAL_CUSTOMERS)
    transactions = [list(row) for row in ORIGINAL_TRANSACTIONS]
    alert_blocks = [ORIGINAL_ALERTS.strip()]

    # New suspicious archetypes: cust_006 onward.
    for i, gen in enumerate(NEW_SCENARIO_GENERATORS, start=6):
        cid = f"cust_{i:03d}"
        acct = f"acct_{1000 + i}"
        name = fake.name()
        profile, txns, alert = gen(cid, acct, name)
        customers.append(profile)
        transactions.extend(txns)
        if alert:
            alert_blocks.append(alert)

    # Clean background customers: keep 55 controls after the planted scenarios.
    n_clean = 55
    clean_start = 6 + len(NEW_SCENARIO_GENERATORS)
    for i in range(clean_start, clean_start + n_clean):
        cid = f"cust_{i:03d}"
        acct = f"acct_{1000 + i}"
        profile, txns = gen_clean_customer(cid, acct)
        customers.append(profile)
        transactions.extend(txns)

    # A couple of "checked, nothing found" alert notes for realism/noise.
    clean_sample = random.sample(customers[19:], 2)  # a couple of clean customers
    for c in clean_sample:
        alert_blocks.append(
            f'Watchlist run (nightly batch): {c["name"]} — no matches across sanctions, '
            f"PEP or adverse-media sources. No action required."
        )

    # Sort transactions by timestamp for a realistic ledger export.
    transactions.sort(key=lambda r: r[1])

    # --- write transactions.csv ---
    txn_path = os.path.join(DATA_DIR, "transactions.csv")
    with open(txn_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "txn_id", "timestamp", "customer_id", "account_id", "amount", "currency",
            "txn_type", "counterparty", "counterparty_country", "channel",
        ])
        writer.writerows(transactions)

    # --- write customers.json ---
    cust_path = os.path.join(DATA_DIR, "customers.json")
    with open(cust_path, "w", encoding="utf-8") as fh:
        json.dump(customers, fh, indent=2)

    # --- write external_alerts.txt ---
    alerts_path = os.path.join(DATA_DIR, "external_alerts.txt")
    header = (
        "COMPLIANCE INBOX — UNSTRUCTURED EXTERNAL ALERTS & ANALYST NOTES\n"
        "(Free-text, mixed sources. The AI layer parses this into structured hits per customer.)\n\n"
    )
    body = alert_blocks[0].split("\n\n", 1)[1] if "\n\n" in alert_blocks[0] else alert_blocks[0]
    # alert_blocks[0] already has its own header from ORIGINAL_ALERTS; strip it, reuse ours.
    first_block_body = ORIGINAL_ALERTS.split("\n\n", 1)[1].strip()
    remaining = "\n\n".join(alert_blocks[1:])
    full_text = header + first_block_body + "\n\n" + remaining + "\n"
    with open(alerts_path, "w", encoding="utf-8") as fh:
        fh.write(full_text)

    print(f"Customers: {len(customers)}")
    print(f"Transactions: {len(transactions)}")
    print(f"Alert blocks: {len(alert_blocks)}")
    print(f"Written to: {DATA_DIR}")


if __name__ == "__main__":
    main()
