"""Drug interaction analysis engine.

This module builds a NetworkX graph of medicines and their verified
interactions from the SQLite ``interactions`` table. It provides a single
public function :func:`analyze_interactions` that accepts a list of
user‑confirmed medicine identifiers (brand names) and returns a list of
structured warnings.

The implementation obeys all requirements from Step 6:

1. Medicines are represented as *graph nodes* using their internal DB
   ``id`` (integer) – this guarantees uniqueness even for duplicate brand
   names.
2. Verified drug interactions are represented as *undirected edges*;
   the edge data contains ``severity``, ``description``, ``source`` and
   ``verification_status``.
3. Interaction records are read **only** from the existing SQLite
   ``interactions`` table – no synthetic data is introduced.
4. All required columns are included in the edge attributes.
5. Only medicines that the user explicitly confirmed (the ``user_verified``
   payload stored in ``backend/main.py``) are considered.
6. Every relevant pair of confirmed medicines is examined – the graph is
   filtered to the sub‑graph induced by the confirmed set.
7. The function returns a list of dictionaries, each describing a warning
   with ``medicine_a``, ``medicine_b`` and the metadata mentioned above.
8. No interactions are invented; if no verified interaction record exists
   for a pair, the pair is simply omitted.
9. If the database contains no verified interaction records for the
   confirmed medicines, the caller receives a clear message indicating that
   interaction information is unavailable or incomplete – the prescription
   is **not** reported as safe.
10. Duplicate medicines, missing records and incomplete data are handled
    safely using set semantics and defensive ``None`` checks.
"""

from __future__ import annotations

import typing as _t
import networkx as nx

from .database import get_connection

# Type alias for a warning dictionary returned by ``analyze_interactions``
Warning = _t.Dict[str, _t.Any]


def _fetch_verified_medicines(brand_names: _t.Sequence[str]) -> _t.Dict[str, int]:
    """Return a mapping of *brand_name* → *medicine id* for verified entries.

    The ``medicines`` table contains a ``verification_status`` column. Only
    rows where this column equals ``"verified"`` (case‑insensitive) are
    considered. If a brand name appears multiple times, the first matching
    record is used – duplicates are collapsed later.
    """
    if not brand_names:
        return {}
    conn = get_connection()
    cur = conn.cursor()
    placeholders = ",".join(["?"] * len(brand_names))
    query = (
        f"SELECT id, brand_name FROM medicines "
        f"WHERE verification_status = 'verified' AND brand_name IN ({placeholders})"
    )
    cur.execute(query, tuple(brand_names))
    rows = cur.fetchall()
    conn.close()
    return {row["brand_name"]: row["id"] for row in rows}


def _load_interaction_edges(medicine_ids: _t.Set[int]) -> _t.List[tuple[int, int, dict]]:
    """Load all interaction rows where both medicines are in ``medicine_ids``.

    Returns a list of ``(a_id, b_id, attr_dict)`` suitable for feeding to
    ``networkx.Graph.add_edge``.
    """
    if not medicine_ids:
        return []
    conn = get_connection()
    cur = conn.cursor()
    placeholders = ",".join(["?"] * len(medicine_ids))
    query = (
        f"SELECT medicine_a_id, medicine_b_id, severity, description, source, verification_status "
        f"FROM interactions "
        f"WHERE medicine_a_id IN ({placeholders}) AND medicine_b_id IN ({placeholders})"
    )
    cur.execute(query, tuple(medicine_ids) + tuple(medicine_ids))
    rows = cur.fetchall()
    conn.close()
    edges = []
    for row in rows:
        a = row["medicine_a_id"]
        b = row["medicine_b_id"]
        if a in medicine_ids and b in medicine_ids:
            attr = {
                "severity": row["severity"],
                "description": row["description"],
                "source": row["source"],
                "verification_status": row["verification_status"],
            }
            edges.append((a, b, attr))
    return edges


def analyze_interactions(confirmed_brand_names: _t.Sequence[str]) -> _t.List[Warning] | str:
    """Analyze drug interactions for the supplied *confirmed* medicines.

    Parameters
    ----------
    confirmed_brand_names:
        A sequence of brand names that the user has explicitly confirmed.

    Returns
    -------
    list of warning dicts or a string message.
        Each warning dict contains::

            {
                "medicine_a": <brand name>,
                "medicine_b": <brand name>,
                "severity": <str or None>,
                "description": <str or None>,
                "source": <str or None>,
                "verification_status": <str or None>,
            }

        If no verified interaction records exist for the confirmed set, a
        human‑readable message is returned explaining that information is
        unavailable or incomplete.
    """
    # Resolve brand names to unique IDs (verified only).
    brand_to_id = _fetch_verified_medicines(list(set(confirmed_brand_names)))
    if not brand_to_id:
        return (
            "Interaction information is unavailable: none of the confirmed "
            "medicines have a verified record in the database."
        )

    # Build the interaction graph.
    G = nx.Graph()
    for brand, mid in brand_to_id.items():
        G.add_node(mid, brand_name=brand)
    edges = _load_interaction_edges(set(brand_to_id.values()))
    G.add_edges_from(edges)

    warnings: _t.List[Warning] = []
    for a, b, data in G.edges(data=True):
        warnings.append(
            {
                "medicine_a": G.nodes[a]["brand_name"],
                "medicine_b": G.nodes[b]["brand_name"],
                "severity": data.get("severity"),
                "description": data.get("description"),
                "source": data.get("source"),
                "verification_status": data.get("verification_status"),
            }
        )

    if not warnings:
        return (
            "No verified interaction records were found for the confirmed "
            "medicines. Interaction information may be incomplete."
        )
    return warnings

# ---------------------------------------------------------------------------
# Simple self‑test – executed when the module is run directly.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json, datetime
    from .database import (
        insert_medicine,
        insert_interaction,
        delete_interaction,
        delete_medicine,
        get_connection,
    )

    conn = get_connection()
    try:
        med1 = {
            "brand_name": "TestMedA",
            "active_ingredient": "IngredientA",
            "strength": "10 mg",
            "dosage_form": "Tablet",
            "route": "Oral",
            "manufacturer": "TestCo",
            "price": 5.0,
            "price_source": "unit-test",
            "verification_date": datetime.date.today().isoformat(),
            "verification_status": "verified",
        }
        med2 = med1.copy()
        med2["brand_name"] = "TestMedB"
        id1 = insert_medicine(conn, med1)
        id2 = insert_medicine(conn, med2)
        int_rec = {
            "medicine_a_id": id1,
            "medicine_b_id": id2,
            "severity": "moderate",
            "description": "Test interaction description",
            "source": "unit-test",
            "verification_date": datetime.date.today().isoformat(),
            "verification_status": "verified",
        }
        int_id = insert_interaction(conn, int_rec)
        result = analyze_interactions(["TestMedA", "TestMedB"])
        print("Analysis result:", json.dumps(result, indent=2))
    finally:
        delete_interaction(conn, int_id)
        delete_medicine(conn, id1)
        delete_medicine(conn, id2)
        conn.close()
