"""
Generate a compact showcase dataset for the Financial Risk Signal Aggregator.

The main dataset stays broad and regression-tested. This second dataset is
small, story-driven, and intentionally dense with shared wire counterparties so
the Network tab, OFAC SDN rule, and drill-down evidence are easy to demo.

Run:  python scripts/generate_showcase_dataset.py
"""

from __future__ import annotations

import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")


CUSTOMERS = [
    {
        "customer_id": "demo_001", "name": "Maya Chen", "kyc_status": "verified",
        "base_risk_rating": "medium", "account_open_date": "2018-04-12", "country": "SG",
        "is_pep": False, "expected_monthly_volume": 180000, "occupation": "Import/Export Director",
    },
    {
        "customer_id": "demo_002", "name": "Omar Rahman", "kyc_status": "verified",
        "base_risk_rating": "high", "account_open_date": "2016-09-01", "country": "AE",
        "is_pep": True, "expected_monthly_volume": 45000, "occupation": "Municipal Procurement Advisor",
    },
    {
        "customer_id": "demo_003", "name": "Elena Kovacs", "kyc_status": "verified",
        "base_risk_rating": "medium", "account_open_date": "2019-02-17", "country": "DE",
        "is_pep": False, "expected_monthly_volume": 70000, "occupation": "Logistics Consultant",
    },
    {
        "customer_id": "demo_004", "name": "Scott Roberts", "kyc_status": "verified",
        "base_risk_rating": "medium", "account_open_date": "2022-02-18", "country": "US",
        "is_pep": False, "expected_monthly_volume": 65000, "occupation": "Import Consultant",
    },
    {
        "customer_id": "demo_005", "name": "Luis Martinez", "kyc_status": "verified",
        "base_risk_rating": "medium", "account_open_date": "2021-06-23", "country": "MX",
        "is_pep": False, "expected_monthly_volume": 38000, "occupation": "Freight Broker",
    },
    {
        "customer_id": "demo_006", "name": "Amina Haddad", "kyc_status": "pending",
        "base_risk_rating": "medium", "account_open_date": "2026-06-15", "country": "GB",
        "is_pep": False, "expected_monthly_volume": 11000, "occupation": "Market Trader",
    },
    {
        "customer_id": "demo_007", "name": "Noah Williams", "kyc_status": "verified",
        "base_risk_rating": "low", "account_open_date": "2020-03-02", "country": "US",
        "is_pep": False, "expected_monthly_volume": 7000, "occupation": "Teacher",
    },
    {
        "customer_id": "demo_008", "name": "Priya Shah", "kyc_status": "verified",
        "base_risk_rating": "low", "account_open_date": "2020-11-11", "country": "US",
        "is_pep": False, "expected_monthly_volume": 6000, "occupation": "Software Engineer",
    },
    {
        "customer_id": "demo_009", "name": "Grace Miller", "kyc_status": "verified",
        "base_risk_rating": "low", "account_open_date": "2018-07-04", "country": "CA",
        "is_pep": False, "expected_monthly_volume": 8500, "occupation": "Nurse",
    },
    {
        "customer_id": "demo_010", "name": "Kenji Tanaka", "kyc_status": "verified",
        "base_risk_rating": "low", "account_open_date": "2017-12-19", "country": "JP",
        "is_pep": False, "expected_monthly_volume": 9500, "occupation": "Architect",
    },
]


TRANSACTIONS = [
    # Layering cluster through Orion Trade Brokers.
    ["sd001", "2026-07-08 09:00", "demo_001", "acct_d001", 220000, "USD", "wire_in", "Cedar Exchange House", "AE", "online"],
    ["sd002", "2026-07-08 16:30", "demo_001", "acct_d001", 214000, "USD", "wire_out", "Orion Trade Brokers", "RU", "online"],
    ["sd003", "2026-07-09 11:00", "demo_002", "acct_d002", 118000, "USD", "wire_out", "Orion Trade Brokers", "RU", "online"],
    ["sd004", "2025-09-01 10:00", "demo_003", "acct_d003", 700, "USD", "payment", "Office Lease Co", "DE", "online"],
    ["sd005", "2026-07-10 10:00", "demo_003", "acct_d003", 90000, "USD", "wire_in", "Cedar Exchange House", "AE", "online"],
    ["sd006", "2026-07-10 18:00", "demo_003", "acct_d003", 88000, "USD", "wire_out", "Orion Trade Brokers", "RU", "online"],
    # Real OFAC SDN near-match cluster.
    ["sd007", "2026-07-11 13:30", "demo_004", "acct_d004", 48000, "USD", "wire_out", "Banco Nacional Cuba", "CU", "online"],
    ["sd008", "2026-07-12 14:15", "demo_005", "acct_d005", 42000, "USD", "wire_out", "Banco Nacional Cuba", "CU", "online"],
    ["sd009", "2026-07-13 09:10", "demo_005", "acct_d005", 12000, "USD", "wire_in", "Cedar Exchange House", "AE", "online"],
    # Structuring + incomplete KYC.
    ["sd010", "2026-07-15 09:05", "demo_006", "acct_d006", 9400, "USD", "cash_deposit", "Self", "GB", "branch"],
    ["sd011", "2026-07-15 13:20", "demo_006", "acct_d006", 9600, "USD", "cash_deposit", "Self", "GB", "branch"],
    ["sd012", "2026-07-16 10:40", "demo_006", "acct_d006", 9300, "USD", "cash_deposit", "Self", "GB", "branch"],
    ["sd013", "2026-07-17 12:10", "demo_006", "acct_d006", 9100, "USD", "cash_deposit", "Self", "GB", "branch"],
    # Clean controls with routine activity.
    ["sd014", "2026-07-01 08:00", "demo_007", "acct_d007", 6800, "USD", "salary", "School District Payroll", "US", "online"],
    ["sd015", "2026-07-03 11:00", "demo_007", "acct_d007", 1550, "USD", "payment", "City Rentals", "US", "online"],
    ["sd016", "2026-07-01 08:30", "demo_008", "acct_d008", 5900, "USD", "salary", "Acme Corp Payroll", "US", "online"],
    ["sd017", "2026-07-04 17:20", "demo_008", "acct_d008", 240, "USD", "payment", "Regional Electric Board", "US", "mobile"],
    ["sd018", "2026-07-01 08:15", "demo_009", "acct_d009", 8200, "USD", "salary", "Regional Hospital Payroll", "CA", "online"],
    ["sd019", "2026-07-06 18:30", "demo_009", "acct_d009", 180, "USD", "payment", "Grocery Mart", "CA", "mobile"],
    ["sd020", "2026-07-01 09:00", "demo_010", "acct_d010", 9100, "USD", "salary", "Design Studio Payroll", "JP", "online"],
    ["sd021", "2026-07-05 10:10", "demo_010", "acct_d010", 1200, "USD", "payment", "Parkview Apartments", "JP", "online"],
]


ALERTS = """COMPLIANCE INBOX - SHOWCASE ALERTS
(Compact demo dataset built to highlight shared counterparties, OFAC screening, and analyst rationale.)

[Analyst note] Maya Chen received a large inbound wire from Cedar Exchange House and sent nearly the same amount to Orion Trade Brokers within hours. Orion Trade Brokers appears in multiple customer files and is tied to a high-risk jurisdiction.

[Public integrity bulletin] Omar Rahman, a municipal procurement advisor, is a politically exposed person. His recent wire to Orion Trade Brokers was escalated by transaction monitoring.

[Nightly sanctions screen] Scott Roberts wired funds to "Banco Nacional Cuba", a close match to the OFAC SDN entry BANCO NACIONAL DE CUBA. Treat as a high-priority sanctions review.

[Nightly sanctions screen] Luis Martinez also wired funds to "Banco Nacional Cuba", creating a second shared-counterparty link to the same OFAC hit.

[Branch review] Amina Haddad made several cash deposits just below the reporting threshold within a short window. KYC is still pending.

Control review: Priya Shah, Noah Williams, Grace Miller, and Kenji Tanaka show routine salary and household payments only. No adverse findings.
"""


def main() -> None:
    transactions = sorted(TRANSACTIONS, key=lambda row: row[1])

    with open(os.path.join(DATA_DIR, "showcase_transactions.csv"), "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "txn_id", "timestamp", "customer_id", "account_id", "amount", "currency",
            "txn_type", "counterparty", "counterparty_country", "channel",
        ])
        writer.writerows(transactions)

    with open(os.path.join(DATA_DIR, "showcase_customers.json"), "w", encoding="utf-8") as fh:
        json.dump(CUSTOMERS, fh, indent=2)

    with open(os.path.join(DATA_DIR, "showcase_external_alerts.txt"), "w", encoding="utf-8") as fh:
        fh.write(ALERTS)

    print(f"Customers: {len(CUSTOMERS)}")
    print(f"Transactions: {len(transactions)}")
    print(f"Written showcase dataset to: {DATA_DIR}")


if __name__ == "__main__":
    main()
