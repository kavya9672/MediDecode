# backend/parser_matcher.py
"""Medicine parsing and database matching.

This module consumes the structured OCR result produced by
``backend/ocr_engine.run_dual_pass_ocr`` and attempts to extract the core
prescription fields using regular expressions.  For every line that yields a
medicine name the module performs a fuzzy lookup against the SQLite ``medicines``
table (see ``backend/database.py``) using **RapidFuzz**.

The public function :func:`parse_prescription` returns a list of dictionaries –
one per OCR line – containing:

* ``ocr_text`` and ``ocr_confidence`` (preserved from the OCR engine).
* Extracted ``fields`` with a ``value`` and an ``uncertain`` flag.
* ``match`` information with the best database candidate, the similarity score
  and the verification status from the DB.
* An ``issues`` list describing any uncertainty (low OCR confidence, missing
  fields, low‑confidence fuzzy match, etc.).

All uncertainties are **explicitly flagged**; the downstream FastAPI endpoint can
use these flags to request manual confirmation instead of silently correcting the
prescription.
"""

import re
from typing import List, Dict, Any, Tuple

from rapidfuzz import process, fuzz

# Import the SQLite helper defined in ``backend/database.py``
from .database import get_connection

# ---------------------------------------------------------------------------
# Regex patterns for the various prescription components.
# ---------------------------------------------------------------------------
_NAME_REGEX = re.compile(r"(?P<name>[A-Z][A-Za-z\d\-\s]+?)\s+(?=\d|mg|g|mcg|µg|ml|units|tablet|capsule|tab|cap|pills?)", re.IGNORECASE)
_STRENGTH_REGEX = re.compile(r"(?P<strength>\d+(?:\.\d+)?\s*(?:mg|g|mcg|µg|ml|units))", re.IGNORECASE)
_DOSAGE_REGEX = re.compile(r"(?P<dosage>\d+\s*(?:tablet|capsule|tab|cap|pills?))", re.IGNORECASE)
_FREQUENCY_REGEX = re.compile(r"(?P<frequency>(?:once|twice|thrice|\d+\s*(?:x|times?)\s*daily|bid|tid|qid|qhs|qam|q\d+h))", re.IGNORECASE)
_DURATION_REGEX = re.compile(r"(?P<duration>for\s+\d+\s*(?:days?|weeks?|months?))", re.IGNORECASE)
_TIMING_REGEX = re.compile(r"(?P<timing>\b\d{1,2}:\d{2}\s*(?:am|pm)?\b)", re.IGNORECASE)

# Confidence thresholds – can be tuned later.
_LOW_OCR_CONFIDENCE = 0.5  # below this we flag an issue
_LOW_MATCH_CONFIDENCE = 70  # RapidFuzz score (0‑100) below this is uncertain


def _extract_fields(text: str) -> Tuple[Dict[str, Any], List[str]]:
    """Extract prescription components from a line of OCR text.

    Returns a ``fields`` dict (with ``value`` and ``uncertain`` flags) and a list of
    textual ``issues`` discovered during extraction.
    """
    issues: List[str] = []
    fields: Dict[str, Any] = {
        "medicine_name": {"value": None, "uncertain": True},
        "strength": {"value": None, "uncertain": False},
        "dosage": {"value": None, "uncertain": False},
        "frequency": {"value": None, "uncertain": False},
        "duration": {"value": None, "uncertain": False},
        "timing": {"value": None, "uncertain": False},
    }

    # Medicine name – attempt a generous match first.
    name_match = _NAME_REGEX.search(text)
    if name_match:
        fields["medicine_name"]["value"] = name_match.group("name").strip()
        fields["medicine_name"]["uncertain"] = False
    else:
        issues.append("missing_medicine_name")

    # Optional components – they may appear zero or more times; we take the first.
    strength_match = _STRENGTH_REGEX.search(text)
    if strength_match:
        fields["strength"]["value"] = strength_match.group("strength").strip()
    dosage_match = _DOSAGE_REGEX.search(text)
    if dosage_match:
        fields["dosage"]["value"] = dosage_match.group("dosage").strip()
    frequency_match = _FREQUENCY_REGEX.search(text)
    if frequency_match:
        fields["frequency"]["value"] = frequency_match.group("frequency").strip()
    duration_match = _DURATION_REGEX.search(text)
    if duration_match:
        fields["duration"]["value"] = duration_match.group("duration").strip()
    timing_match = _TIMING_REGEX.search(text)
    if timing_match:
        fields["timing"]["value"] = timing_match.group("timing").strip()

    return fields, issues


def _fuzzy_match_medicine(name: str) -> Tuple[Dict[str, Any], List[str]]:
    """Find the best candidate in the ``medicines`` table for *name*.

    Returns a ``match`` dict and a list of issues (e.g. low confidence).
    """
    issues: List[str] = []
    match_info: Dict[str, Any] = {
        "candidate_id": None,
        "candidate_name": None,
        "match_confidence": None,
        "verification_status": None,
        "uncertain_match": True,
    }
    if not name:
        issues.append("no_name_for_matching")
        return match_info, issues

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, brand_name, verification_status FROM medicines")
    rows = cur.fetchall()
    # Build a list of (brand_name, row) for RapidFuzz.
    choices = [(row["brand_name"], row) for row in rows]
    if not choices:
        issues.append("empty_medicine_table")
        conn.close()
        return match_info, issues

    # RapidFuzz expects a list of strings; we keep mapping via a dict.
    names = [c[0] for c in choices]
    best = process.extractOne(
        name,
        names,
        scorer=fuzz.WRatio,
    )
    if best:
        best_name, score, idx = best
        row = choices[idx][1]
        match_info.update(
            {
                "candidate_id": row["id"],
                "candidate_name": best_name,
                "match_confidence": score,
                "verification_status": row["verification_status"],
                "uncertain_match": score < _LOW_MATCH_CONFIDENCE,
            }
        )
        if score < _LOW_MATCH_CONFIDENCE:
            issues.append("low_match_confidence")
    else:
        issues.append("no_fuzzy_match")

    conn.close()
    return match_info, issues


def parse_prescription(ocr_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse OCR output into medicines and perform DB matching.

    Parameters
    ----------
    ocr_result:
        The dictionary returned by ``run_dual_pass_ocr`` – it contains the two
        passes under ``pass1``/``pass2`` with a ``lines`` list.

    Returns
    -------
    List of per‑line dictionaries with OCR data, extracted fields, fuzzy match
    information and any detected issues.
    """
    # Gather all lines from both passes – we keep the original confidence per line.
    lines = []
    for pass_key in ("pass1", "pass2"):
        pass_info = ocr_result.get(pass_key, {})
        lines.extend(pass_info.get("lines", []))

    results: List[Dict[str, Any]] = []
    for line in lines:
        text = line.get("text", "")
        ocr_conf = line.get("confidence", 0.0)
        line_issues: List[str] = []

        # 1️⃣ Low OCR confidence flag.
        if ocr_conf < _LOW_OCR_CONFIDENCE:
            line_issues.append("low_ocr_confidence")

        # 2️⃣ Extract fields via regex.
        fields, extraction_issues = _extract_fields(text)
        line_issues.extend(extraction_issues)

        # 3️⃣ Fuzzy match the medicine name if we have one.
        match_info, match_issues = _fuzzy_match_medicine(fields["medicine_name"]["value"])
        line_issues.extend(match_issues)

        results.append(
            {
                "ocr_text": text,
                "ocr_confidence": ocr_conf,
                "fields": fields,
                "match": match_info,
                "issues": line_issues,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Simple sanity test (run directly).
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Mock an OCR result with a few representative lines.
    mock_result = {
        "pass1": {
            "lines": [
                {"pass_id": "pass1", "text": "Paracetamol 500 mg Tablet 1 tablet twice daily for 5 days", "confidence": 0.92, "box": []},
                {"pass_id": "pass1", "text": "Ibuprofenn 200 mg 1 cap q8h", "confidence": 0.48, "box": []},
                {"pass_id": "pass1", "text": "   ", "confidence": 0.80, "box": []},
            ]
        },
        "pass2": {"lines": []},
    }
    parsed = parse_prescription(mock_result)
    import json, pprint
    pprint.pprint(parsed)
    print("\n--- Done ---")
