"""
Counterparty network analysis.

Per-customer scoring (src/rules.py) can only ever see one customer's own
transactions. It cannot notice that two *independently* flagged customers
happen to route money through the same intermediary — a classic layering /
mule-network pattern where the individual cases already look suspicious on
their own, but the shared counterparty reveals they may be part of one
underlying scheme. That structural, cross-customer view is what this module
adds: a graph of customer <-> counterparty links, kept to only the
counterparties actually shared by two or more distinct customers (a
counterparty used by exactly one customer carries no network signal).
"""

from __future__ import annotations

from typing import Any, Dict, List

import networkx as nx

from src.schemas import EntityRisk


def build_counterparty_graph(
    entities: Dict[str, Dict[str, Any]],
    register: List[EntityRisk],
    wires_only: bool = True,
) -> nx.Graph:
    """
    Build a bipartite graph: customer nodes <-> shared-counterparty nodes.

    wires_only=True (default) restricts this to wire transactions. Routine
    bill payments (rent, utilities) are deliberately excluded — with many
    customers drawing from the same small pool of realistic payee names,
    including them would flood the graph with meaningless "everyone pays the
    same power company" edges. Wire counterparties are where genuine
    cross-customer laundering/layering links actually show up.
    """
    scores = {er.customer_id: er for er in register}

    # Pass 1: which customers use each counterparty at all?
    counterparty_customers: Dict[str, set] = {}
    for cid, ent in entities.items():
        txns = ent["txns"]
        rows = txns[txns["is_wire"]] if wires_only else txns
        for _, row in rows.iterrows():
            cp = str(row["counterparty"]).strip()
            if not cp:
                continue
            counterparty_customers.setdefault(cp, set()).add(cid)

    shared = {cp for cp, custs in counterparty_customers.items() if len(custs) >= 2}

    # Pass 2: build the graph using only shared counterparties.
    g = nx.Graph()
    for cid, ent in entities.items():
        txns = ent["txns"]
        rows = txns[txns["is_wire"]] if wires_only else txns
        for _, row in rows.iterrows():
            cp = str(row["counterparty"]).strip()
            if cp not in shared:
                continue
            if cid not in g:
                er = scores.get(cid)
                g.add_node(
                    cid,
                    kind="customer",
                    label=ent["profile"].get("name", cid),
                    tier=er.tier if er else "Low",
                    score=er.score if er else 0,
                )
            if cp not in g:
                g.add_node(
                    cp,
                    kind="counterparty",
                    label=cp,
                    country=str(row.get("counterparty_country", "")),
                )
            amount = float(row["amount"])
            if g.has_edge(cid, cp):
                g[cid][cp]["amount"] += amount
                g[cid][cp]["count"] += 1
            else:
                g.add_edge(cid, cp, amount=amount, count=1, txn_type=row["txn_type"])
    return g


def shared_counterparty_summary(g: nx.Graph) -> List[Dict[str, Any]]:
    """One row per shared counterparty: which customers it links, at what tiers."""
    rows = []
    for node, data in g.nodes(data=True):
        if data.get("kind") != "counterparty":
            continue
        linked = [
            {
                "customer_id": nbr,
                "name": g.nodes[nbr]["label"],
                "tier": g.nodes[nbr]["tier"],
                "amount": g[node][nbr]["amount"],
            }
            for nbr in g.neighbors(node)
        ]
        rows.append(
            {
                "counterparty": node,
                "country": data.get("country", ""),
                "linked_customers": linked,
                "customer_count": len(linked),
            }
        )
    rows.sort(key=lambda r: r["customer_count"], reverse=True)
    return rows
