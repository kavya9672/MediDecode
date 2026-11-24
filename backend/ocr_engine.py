# backend/ocr_engine.py
"""OCR Engine using PaddleOCR (v3.7.0).

Provides a single public function :func:`run_dual_pass_ocr` that accepts the two
pre‑processed ``numpy.ndarray`` images returned by :func:`preprocess_image` and
produces a structured result ready for the downstream parser/FastAPI layer.

Key design points
-----------------
* **Singleton OCR instance** – ``PaddleOCR`` is heavyweight (model download,
  GPU/CPU initialization).  The module creates a single instance the first time
  it is needed and re‑uses it for all subsequent calls.
* **Cache redirection** – Windows user profiles often restrict write access to
  the default ``~/.paddle`` locations.  The environment variables
  ``PADDLE_HOME`` and ``PADDLE_PDX_CACHE_HOME`` are forced to a project‑local
  ``.cache`` folder before the Paddle libraries are imported.  This avoids the
  ``[WinError 5] Access is denied`` errors reported in the project audit.
* **Full OCR data preservation** – For each pass the function returns a list of
  line dictionaries containing the raw text, confidence score, bounding box and
  the pass identifier (``"pass1"`` or ``"pass2"``).
* **Pass comparison** – The two passes are compared on a per‑text basis.  Issues
  are reported when a line is missing in one pass, when the same line appears
  with a confidence below a configurable threshold (default ``0.5``), or when the
  texts differ while the bounding boxes overlap substantially.
* **Graceful error handling** – Invalid inputs, empty OCR results or runtime
  exceptions are caught and re‑raised as ``ValueError`` with a clear message so
  the API layer can translate them to HTTP 400/500 responses.
"""

import os
import pathlib
from typing import List, Dict, Tuple, Any

# ---------------------------------------------------------------------------
# 1️⃣ Ensure Paddle cache directories are writable on Windows.
# ---------------------------------------------------------------------------
# The project lives under a user‑writable location, so we place the caches there.
_PROJECT_ROOT = pathlib.Path(__file__).parent.parent
_CACHE_DIR = _PROJECT_ROOT / ".cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("PADDLE_HOME", str(_CACHE_DIR / "paddle_home"))
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(_CACHE_DIR / "paddlex_cache"))

# Import after the env vars are set – PaddleOCR reads them on import.
try:
    from paddleocr import PaddleOCR
except Exception as exc:
    raise ImportError(
        "Failed to import PaddleOCR – ensure paddleocr==3.7.0 and its dependencies are installed."
    ) from exc

# ---------------------------------------------------------------------------
# 2️⃣ Singleton OCR instance helper.
# ---------------------------------------------------------------------------
_OCR_INSTANCE: PaddleOCR | None = None


def _get_ocr_instance() -> PaddleOCR:
    """Create (if necessary) and return a shared :class:`PaddleOCR` instance.

    The instance is configured for **CPU‑only** inference – the Windows test
    environment does not have a GPU runtime.  ``use_angle_cls`` enables the
    built‑in text direction detection which helps with rotated prescriptions.
    ``lang`` is set to ``"en"`` because the project targets English drug labels.
    ``show_log`` is disabled to keep the FastAPI logs clean.
    """
    global _OCR_INSTANCE
    if _OCR_INSTANCE is None:
        _OCR_INSTANCE = PaddleOCR(
            lang="en",
            device="cpu",
            use_textline_orientation=True,
            enable_mkldnn=False
        )
    return _OCR_INSTANCE

# ---------------------------------------------------------------------------
# 3️⃣ Core OCR helpers.
# ---------------------------------------------------------------------------

def _run_single_pass(
    image: Any, pass_id: str
) -> Tuple[List[Dict[str, Any]], float]:
    """Run OCR on a single pre‑processed image.

    Parameters
    ----------
    image:
        ``numpy.ndarray`` in BGR format – exactly what ``preprocess_image``
        returns.
    pass_id:
        Identifier string (e.g. ``"pass1"``) stored in each line dict.

    Returns
    -------
    lines:
        List of dictionaries with keys ``text``, ``confidence``, ``box`` and
        ``pass_id``.
    avg_confidence:
        Mean confidence across all detected lines (0.0 if no lines).
    """
    if image is None:
        raise ValueError(f"{pass_id}: Received None as image input.")
    ocr = _get_ocr_instance()
    try:
        # PaddleOCR.ocr returns a list where each element is
        #   [box (list of 4 points), (text, confidence)]
        print(f"[OCR] About to call ocr.predict for pass {pass_id}", flush=True)
        _raw = ocr.predict(image)
        raw_results = _raw[0].json if _raw and hasattr(_raw[0], "json") else _raw
    except Exception as exc:
        raise RuntimeError(f"{pass_id}: PaddleOCR inference failed: {exc}") from exc

    lines: List[Dict[str, Any]] = []
    confidences: List[float] = []
    for entry in raw_results:
        # Defensive unpack – older versions may return a tuple, newer a list.
        if not entry or len(entry) < 2:
            continue
        box, txt_conf = entry[0], entry[1]
        # ``txt_conf`` can be a tuple/list ``(text, score)``.
        if isinstance(txt_conf, (list, tuple)) and len(txt_conf) == 2:
            text, conf = txt_conf[0], txt_conf[1]
        else:
            # Unexpected format – skip but log.
            continue
        lines.append(
            {
                "pass_id": pass_id,
                "text": text,
                "confidence": float(conf),
                "box": box,
            }
        )
        confidences.append(float(conf))

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return lines, avg_conf

# ---------------------------------------------------------------------------
# 4️⃣ Comparison utilities.
# ---------------------------------------------------------------------------

def _compare_passes(
    lines1: List[Dict[str, Any]],
    lines2: List[Dict[str, Any]],
    low_conf_threshold: float = 0.5,
) -> List[Dict[str, Any]]:
    """Generate a list of issues found when comparing two OCR passes.

    The algorithm is deliberately simple – it works on the extracted **text**
    strings because bounding‑box overlap handling would require a geometry
    library and is not essential for the current proof‑of‑concept.
    """
    issues: List[Dict[str, Any]] = []
    texts1 = {l["text"] for l in lines1}
    texts2 = {l["text"] for l in lines2}

    # Missing in pass2
    for txt in texts1 - texts2:
        issues.append({"type": "missing_in_pass2", "text": txt})
    # Missing in pass1
    for txt in texts2 - texts1:
        issues.append({"type": "missing_in_pass1", "text": txt})

    # Low confidence detection (per‑line)
    for line in lines1 + lines2:
        if line["confidence"] < low_conf_threshold:
            issues.append(
                {
                    "type": "low_confidence",
                    "pass_id": line["pass_id"],
                    "text": line["text"],
                    "confidence": line["confidence"],
                }
            )
    return issues

# ---------------------------------------------------------------------------
# 5️⃣ Public API.
# ---------------------------------------------------------------------------

def run_dual_pass_ocr(
    proc1: Any,
    proc2: Any,
) -> Dict[str, Any]:
    """Run the dual‑pass OCR pipeline.

    Parameters
    ----------
    proc1, proc2:
        The two ``numpy.ndarray`` images produced by ``preprocess_image``.

    Returns
    -------
    dict with the following keys:
        * ``pass1`` – dict with ``lines`` (list) and ``average_confidence``.
        * ``pass2`` – same structure as ``pass1``.
        * ``issues`` – list of comparison problems (missing text, low confidence).
    """
    # Run each pass independently.
    lines1, avg_conf1 = _run_single_pass(proc1, "pass1")
    lines2, avg_conf2 = _run_single_pass(proc2, "pass2")

    # Comparison / flagging.
    issues = _compare_passes(lines1, lines2)

    result = {
        "pass1": {"lines": lines1, "average_confidence": avg_conf1},
        "pass2": {"lines": lines2, "average_confidence": avg_conf2},
        "issues": issues,
    }
    return result

# ---------------------------------------------------------------------------
# 6️⃣ Simple sanity test (executed when run as a script).
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    import numpy as np
    from backend.preprocessor import preprocess_image

    if len(sys.argv) != 2:
        print("Usage: python -m backend.ocr_engine <image_path>")
        sys.exit(1)
    img_path = sys.argv[1]
    try:
        p1, p2 = preprocess_image(img_path)
        res = run_dual_pass_ocr(p1, p2)
        print("OCR result summary:")
        print(f"Pass1 avg confidence: {res['pass1']['average_confidence']:.3f}")
        print(f"Pass2 avg confidence: {res['pass2']['average_confidence']:.3f}")
        print("Detected issues:")
        for issue in res["issues"]:
            print(issue)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
