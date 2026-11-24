"""Generic medicine comparison engine.

Provides a function :func:`compare_generics` that, given a list of brand names
confirmed by the user, searches the SQLite ``medicines`` table for verified
generic alternatives.

Only medicines whose ``active_ingredient``, ``strength``, ``dosage_form`` and
``route`` match exactly are considered equivalent.  Manufacturer, price,
price_source and verification_date are returned *only* when present and the
record's ``verification_status`` is ``'verified'``.

The function never fabricates alternatives or pricing information.  When no
verified equivalents exist a clear message is returned.
"""

from __future__ import annotations

import typing as _t

try:
    from .database import get_connection
except ImportError:
    # Fallback for direct script execution (no package context)
    import database as _db
    get_connection = _db.get_connection

# Type alias for a generic alternative record returned by ``compare_generics``
Alternative = _t.Dict[str, _t.Any]


def _fetch_medicine_by_brand(conn, brand_name: str) -> _t.Optional[_t.Dict[str, _t.Any]]:
    """Return a single verified medicine row matching *brand_name*.

    If multiple rows exist, the first is used. Returns ``None`` if no verified
    record is found.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM medicines WHERE verification_status = 'verified' AND brand_name = ?",
        (brand_name,)
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _find_alternatives(conn, original: _t.Dict[str, _t.Any]) -> _t.List[Alternative]:
    """Return verified alternatives for *original* medicine.

    Matches on ``active_ingredient``, ``strength``, ``dosage_form`` and ``route``.
    Excludes the original record itself (by ``id``).
    """
    cur = conn.cursor()
    query = (
        "SELECT brand_name, manufacturer, price, price_source, verification_date "
        "FROM medicines "
        "WHERE verification_status = 'verified' "
        "AND active_ingredient = ? "
        "AND strength = ? "
        "AND dosage_form = ? "
        "AND route = ? "
        "AND id != ?"
    )
    cur.execute(
        query,
        (
            original["active_ingredient"],
            original["strength"],
            original["dosage_form"],
            original["route"],
            original["id"],
        ),
    )
    rows = cur.fetchall()
    alternatives: _t.List[Alternative] = []
    for row in rows:
        alt = {
            "original_brand": original["brand_name"],
            "alternative_brand": row["brand_name"],
        }
        # Include optional fields only when they are not NULL.
        if row["manufacturer"]:
            alt["manufacturer"] = row["manufacturer"]
        if row["price"] is not None:
            alt["price"] = row["price"]
        if row["price_source"]:
            alt["price_source"] = row["price_source"]
        if row["verification_date"]:
            alt["verification_date"] = row["verification_date"]
        alternatives.append(alt)
    return alternatives


def compare_generics(confirmed_brand_names: _t.Sequence[str]) -> _t.List[Alternative] | str:
    """Find verified generic alternatives for the supplied *confirmed* medicines.

    Parameters
    ----------
    confirmed_brand_names:
        List of brand names that the user has confirmed (from ``/api/verify``).

    Returns
    -------
    list of alternative dicts or a string message.
        Each dict contains the original brand, an alternative brand and, when
        available, ``manufacturer``, ``price``, ``price_source`` and
        ``verification_date``.
        If no verified alternatives are found for any of the supplied medicines,
        a human‑readable message is returned.
    """
    conn = get_connection()
    try:
        all_alternatives: _t.List[Alternative] = []
        for brand in confirmed_brand_names:
            original = _fetch_medicine_by_brand(conn, brand)
            if not original:
                # Skip unverified or missing medicines – they will be handled
                # upstream (verify step) but we guard against silent failures.
                continue
            alts = _find_alternatives(conn, original)
            all_alternatives.extend(alts)
        if not all_alternatives:
            return (
                "No verified generic alternatives are available for the confirmed "
                "medicines. Consult a pharmacist or doctor for possible swaps."
            )
        return all_alternatives
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Simple self‑test – run when the module is executed directly.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json, datetime
    from .database import insert_medicine, delete_medicine, get_connection

    conn = get_connection()
    try:
        # Create two medicines with identical active ingredient etc.
        med_a = {
            "brand_name": "BrandA",
            "active_ingredient": "Acetaminophen",
            "strength": "500 mg",
            "dosage_form": "Tablet",
            "route": "Oral",
            "manufacturer": "PharmaA",
            "price": 8.0,
            "price_source": "test",
            "verification_date": datetime.date.today().isoformat(),
            "verification_status": "verified",
        }
        med_b = med_a.copy()
        med_b["brand_name"] = "BrandB"
        med_b["manufacturer"] = "PharmaB"
        id_a = insert_medicine(conn, med_a)
        id_b = insert_medicine(conn, med_b)
        result = compare_generics(["BrandA"])
        print("Result:", json.dumps(result, indent=2))
    finally:
        delete_medicine(conn, id_a)
        delete_medicine(conn, id_b)
        conn.close()
