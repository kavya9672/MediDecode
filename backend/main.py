# backend/main.py
"""FastAPI entry point for MediDecode.

Provides three primary endpoints:
1. ``POST /api/upload`` – store an image upload and return a unique job ID.
2. ``POST /api/process`` – run the full OCR‑parse pipeline for a stored job.
3. ``POST /api/verify`` – accept user‑corrected medicine data for a job.
4. ``GET /api/progress/{job_id}`` – query the current processing state.

The heavy CPU work (OpenCV preprocessing, PaddleOCR inference and regex
parsing) is off‑loaded to a background thread via ``asyncio.to_thread`` so the
event loop stays responsive.
"""

import os
import uuid
import shutil
from pathlib import Path
from typing import Dict, Any
import asyncio

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
import io
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

# Import the internal modules – they expose the exact public functions we need.
# Lazy imports – will be performed inside _run_pipeline to avoid import errors when optional deps are missing

from .interaction_engine import analyze_interactions
from .generic_matcher import compare_generics

app = FastAPI(title="MediDecode API", version="0.1")

# Very permissive CORS for local development – adjust in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Simple in‑memory job store. In a real system this would be persisted.
# ---------------------------------------------------------------------------
_JOBS: Dict[str, Dict[str, Any]] = {}

# Directory for uploaded files – placed under the project root.
_UPLOAD_DIR = Path(__file__).parent / "uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MiB – adjust as required.
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

def _validate_upload(file: UploadFile) -> bytes:
    """Read the uploaded file, enforce size and extension limits.

    Returns the raw bytes if validation passes, otherwise raises HTTPException.
    """
    filename = file.filename
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file extension.")
    # Read the whole file – FastAPI streams it, so we need to enforce size.
    content = file.file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large.")
    # Basic sanity check – try to decode via OpenCV in the pipeline later.
    return content

def _store_upload(content: bytes, original_name: str) -> Path:
    """Write the bytes to a uniquely‑named file inside ``_UPLOAD_DIR``.
    Returns the absolute Path of the stored file.
    """
    unique_name = f"{uuid.uuid4().hex}{Path(original_name).suffix.lower()}"
    target_path = _UPLOAD_DIR / unique_name
    with open(target_path, "wb") as f:
        f.write(content)
    return target_path

# ---------------------------------------------------------------------------
# Endpoint implementations
# ---------------------------------------------------------------------------

# Existing endpoints ... (unchanged above) ...

# ---------------------------------------------------------------------------
# PDF Report endpoint
# ---------------------------------------------------------------------------

from fastapi.responses import StreamingResponse
from .pdf_generator import generate_pdf

@app.post("/api/report")
async def generate_report(request: Request):
    """Generate a printable PDF medication timetable for a verified job.

    Expected JSON payload: {"job_id": "..."}
    Returns the PDF as a downloadable file.
    """
    data = await request.json()
    job_id = data.get("job_id")
    if not job_id or job_id not in _JOBS:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    job = _JOBS[job_id]
    verified = job.get("user_verified")
    if not verified:
        raise HTTPException(status_code=400, detail="No verified medicines for this job.")
    if not isinstance(verified, list) or len(verified) == 0:
        raise HTTPException(status_code=400, detail="Verified medicines list is empty.")
    try:
        pdf_bytes = generate_pdf(verified)
    except Exception as exc:
        job["status"] = "error"
        job["issues"].append(str(exc))
        import traceback
        print(f"[PIPELINE] Exception in job_id={job_id}: {exc}", flush=True)
        traceback.print_exc()

        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}")

    pdf_stream = io.BytesIO(pdf_bytes)
    filename = f"medication_timetable_{job_id}.pdf"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(pdf_stream, media_type="application/pdf", headers=headers)

@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    """Accept an image, validate it and store it for later processing.

    Returns a JSON payload ``{"job_id": "<uuid>"}``.
    """
    content = _validate_upload(file)
    stored_path = _store_upload(content, file.filename)
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {
        "file_path": stored_path,
        "status": "uploaded",
        "ocr_result": None,
        "parse_result": None,
        "issues": [],
    }
    return {"job_id": job_id}

# ---------------------------------------------------------------------------
async def _run_pipeline(job_id: str) -> None:
    import traceback
    print(f"[PIPELINE] Entry into _run_pipeline, job_id={job_id}", flush=True)

    """Internal helper that performs the heavy processing steps.
    Updates the global ``_JOBS`` entry with results and status.
    """
    job = _JOBS.get(job_id)
    if not job:
        return
    job["status"] = "processing"
    try:
        from .preprocessor import preprocess_image
        from .ocr_engine import run_dual_pass_ocr
        from .parser_matcher import parse_prescription

        # 1️⃣ Preprocess (CPU bound)
        print(f"[PIPELINE] Starting preprocessing for job_id={job_id}", flush=True)
        proc1, proc2 = await asyncio.to_thread(preprocess_image, str(job["file_path"]))
        print(f"[PIPELINE] Finished preprocessing for job_id={job_id}", flush=True)
        # 2️⃣ OCR (CPU bound, heavy)
        print(f"[PIPELINE] Starting OCR for job_id={job_id}", flush=True)
        ocr_res = await asyncio.to_thread(run_dual_pass_ocr, proc1, proc2)
        print(f"[PIPELINE] Finished OCR for job_id={job_id}", flush=True)
        # 3️⃣ Parsing (lightweight)
        print(f"[PIPELINE] Starting parsing for job_id={job_id}", flush=True)
        parse_res = await asyncio.to_thread(parse_prescription, ocr_res)
        print(f"[PIPELINE] Finished parsing for job_id={job_id}", flush=True)
        job["ocr_result"] = ocr_res
        job["parse_result"] = parse_res
        job["status"] = "completed"
        print(f"[PIPELINE] Job {job_id} completed", flush=True)
        proc1, proc2 = await asyncio.to_thread(preprocess_image, str(job["file_path"]))
        # 2️⃣ OCR (CPU bound, heavy)
        ocr_res = await asyncio.to_thread(run_dual_pass_ocr, proc1, proc2)
        # 3️⃣ Parsing (lightweight)
        parse_res = await asyncio.to_thread(parse_prescription, ocr_res)
        job["ocr_result"] = ocr_res
        job["parse_result"] = parse_res
        job["status"] = "completed"
    except Exception as exc:
        job["status"] = "error"
        job["issues"].append(str(exc))
        import traceback
        print(f"[PIPELINE] Exception in job_id={job_id}: {exc}", flush=True)
        traceback.print_exc()

        job["status"] = "error"
        job["issues"].append(str(exc))

@app.post("/api/process")
async def process_job(request: Request, background: BackgroundTasks):
    """Trigger the OCR and parsing pipeline for a previously uploaded file.

    Expected JSON body: ``{"job_id": "<uuid>"}``
    The processing runs in a background thread; the endpoint immediately returns
    the current status (``processing``) and, once finished, the full result.
    """
    data = await request.json()
    job_id = data.get("job_id")
    if not job_id or job_id not in _JOBS:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    job = _JOBS[job_id]
    if job["status"] == "completed":
        return {
            "job_id": job_id,
            "status": job["status"],
            "ocr_result": job["ocr_result"],
            "parse_result": job["parse_result"],
        }
    if job["status"] in {"uploaded", "error"}:
        # Start (or restart) processing in a background thread.
        background.add_task(_run_pipeline, job_id)
        return {"job_id": job_id, "status": "processing"}
    # If already processing, just inform the client.
    return {"job_id": job_id, "status": job["status"]}

@app.post("/api/analyze")
async def analyze_interactions_endpoint(request: Request):
    """Analyze drug interactions for a verified prescription.

    Expected JSON payload::
        {"job_id": "..."}
    The endpoint reads the previously stored ``user_verified`` medicines for the job,
    extracts their ``brand_name`` (or falls back to ``ocr_text``), and returns a list of
    interaction warnings using :func:`interaction_engine.analyze_interactions`.
    """
    payload = await request.json()
    job_id = payload.get("job_id")
    if not job_id or job_id not in _JOBS:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    job = _JOBS[job_id]
    verified = job.get("user_verified")
    if not verified:
        raise HTTPException(status_code=400, detail="No verified medicines for this job.")
    # Extract brand names; the payload from verify may contain only ocr_text.
    brand_names = []
    for med in verified:
        name = med.get("brand_name") or med.get("ocr_text")
        if name:
            brand_names.append(name)
    from .interaction_engine import analyze_interactions
from .generic_matcher import compare_generics
@app.post("/api/analyze")
async def analyze_interactions_endpoint(request: Request):
    """Analyze drug interactions for a verified prescription.

    Expected JSON payload::
        {"job_id": "..."}
    The endpoint reads the previously stored ``user_verified`` medicines for the job,
    extracts their ``brand_name`` (or falls back to ``ocr_text``), and returns a list of
    interaction warnings using :func:`interaction_engine.analyze_interactions`.
    """
    payload = await request.json()
    job_id = payload.get("job_id")
    if not job_id or job_id not in _JOBS:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    job = _JOBS[job_id]
    verified = job.get("user_verified")
    if not verified:
        raise HTTPException(status_code=400, detail="No verified medicines for this job.")
    brand_names = []
    for med in verified:
        name = med.get("brand_name") or med.get("ocr_text")
        if name:
            brand_names.append(name)
    from .interaction_engine import analyze_interactions
    result = analyze_interactions(brand_names)
    return {"job_id": job_id, "interaction_analysis": result}

@app.post("/api/verify")
async def verify_job(request: Request):
    """Accept user‑confirmed medicine data for a job.

    Expected JSON payload includes ``job_id``, a ``confirmed`` flag and a list
    of ``medicines``. Each medicine entry should contain at least a ``brand_name``
    (or ``ocr_text`` as a fallback) so that downstream analysis can resolve the
    corresponding DB records.
    """
    payload = await request.json()
    job_id = payload.get("job_id")
    if not job_id or job_id not in _JOBS:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    if not payload.get("confirmed"):
        raise HTTPException(status_code=400, detail="User confirmation flag required.")
    medicines = payload.get("medicines")
    if not isinstance(medicines, list):
        raise HTTPException(status_code=400, detail="'medicines' must be a list.")
    for med in medicines:
        if not isinstance(med, dict) or "ocr_text" not in med:
            raise HTTPException(status_code=400, detail="Each medicine entry must contain 'ocr_text'.")
    job = _JOBS[job_id]
    job["user_verified"] = medicines
    job["status"] = "verified"
    return {"job_id": job_id, "status": "verified"}
    return {"job_id": job_id, "interaction_analysis": result}

@app.post("/api/verify")
async def verify_job(request: Request):
    """Accept user‑confirmed medicine data for a job.

    Expected JSON payload includes ``job_id``, a ``confirmed`` flag and a list
    of ``medicines``. Each medicine entry should contain at least a ``brand_name``
    (or ``ocr_text`` as a fallback) so that downstream analysis can resolve the
    corresponding DB records.
    """
    payload = await request.json()
    job_id = payload.get("job_id")
    if not job_id or job_id not in _JOBS:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    if not payload.get("confirmed"):
        raise HTTPException(status_code=400, detail="User confirmation flag required.")
    medicines = payload.get("medicines")
    if not isinstance(medicines, list):
        raise HTTPException(status_code=400, detail="'medicines' must be a list.")
    # Very light validation – ensure each entry contains at least the OCR text.
    for med in medicines:
        if not isinstance(med, dict) or "ocr_text" not in med:
            raise HTTPException(status_code=400, detail="Each medicine entry must contain 'ocr_text'.")
    job = _JOBS[job_id]
    job["user_verified"] = medicines
    job["status"] = "verified"
    return {"job_id": job_id, "status": "verified"}

@app.post("/api/compare")
async def compare_endpoint(request: Request):
    """Compare user‑verified medicines to find verified generic alternatives.

    Expected JSON payload::
        {"job_id": "..."}
    The endpoint extracts brand names from the previously stored ``user_verified``
    list and returns a list of alternatives (or a message) from
    :func:`generic_matcher.compare_generics`.
    """
    payload = await request.json()
    job_id = payload.get("job_id")
    if not job_id or job_id not in _JOBS:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    job = _JOBS[job_id]
    verified = job.get("user_verified")
    if not verified:
        raise HTTPException(status_code=400, detail="No verified medicines for this job.")
    brand_names = [med.get("brand_name") or med.get("ocr_text") for med in verified if med.get("brand_name") or med.get("ocr_text")]
    result = compare_generics(brand_names)
    return {"job_id": job_id, "generic_comparison": result}

# ---------------------------------------------------------------------------
# PDF Report endpoint (Step 8)
# ---------------------------------------------------------------------------

@app.post("/api/report")
async def generate_report(request: Request):
    """Generate a printable PDF medication timetable for a verified job.

    Expected JSON payload: {"job_id": "..."}
    Returns the PDF as a downloadable file.
    """
    data = await request.json()
    job_id = data.get("job_id")
    if not job_id or job_id not in _JOBS:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    job = _JOBS[job_id]
    verified = job.get("user_verified")
    if not verified:
        raise HTTPException(status_code=400, detail="No verified medicines for this job.")
    if not isinstance(verified, list) or len(verified) == 0:
        raise HTTPException(status_code=400, detail="Verified medicines list is empty.")
    try:
        pdf_bytes = generate_pdf(verified)
    except Exception as exc:
        job["status"] = "error"
        job["issues"].append(str(exc))
        import traceback
        print(f"[PIPELINE] Exception in job_id={job_id}: {exc}", flush=True)
        traceback.print_exc()

        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}")

    pdf_stream = io.BytesIO(pdf_bytes)
    filename = f"medication_timetable_{job_id}.pdf"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(pdf_stream, media_type="application/pdf", headers=headers)
    """Accept user‑confirmed medicine data for a job.

    Expected JSON payload includes ``job_id``, a ``confirmed`` flag and a list
    of ``medicines``. Each medicine entry should contain at least a ``brand_name``
    (or ``ocr_text`` as a fallback) so that downstream analysis can resolve the
    corresponding DB records.
    """
    """Accept user‑corrected medicine data for a job.

    Expected JSON payload::
        {
            "job_id": "...",
            "confirmed": true,
            "medicines": [
                {"ocr_text": "...", "fields": {...}, "match": {...}}
            ]
        }
    The endpoint validates the payload and stores the user‑confirmed version.
    It never overwrites the original OCR output.
    """
    payload = await request.json()
    job_id = payload.get("job_id")
    if not job_id or job_id not in _JOBS:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    if not payload.get("confirmed"):
        raise HTTPException(status_code=400, detail="User confirmation flag required.")
    medicines = payload.get("medicines")
    if not isinstance(medicines, list):
        raise HTTPException(status_code=400, detail="'medicines' must be a list.")
    # Very light validation – ensure each entry contains at least the OCR text.
    for med in medicines:
        if not isinstance(med, dict) or "ocr_text" not in med:
            raise HTTPException(status_code=400, detail="Each medicine entry must contain 'ocr_text'.")
    job = _JOBS[job_id]
    job["user_verified"] = medicines
    job["status"] = "verified"
    return {"job_id": job_id, "status": "verified"}

@app.post("/api/compare")
async def compare_endpoint(request: Request):
    """Compare user‑verified medicines to find verified generic alternatives.

    Expected JSON payload::
        {"job_id": "..."}
    The endpoint extracts brand names from the previously stored ``user_verified``
    list and returns a list of alternatives (or a message) from
    :func:`generic_matcher.compare_generics`.
    """
    payload = await request.json()
    job_id = payload.get("job_id")
    if not job_id or job_id not in _JOBS:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    job = _JOBS[job_id]
    verified = job.get("user_verified")
    if not verified:
        raise HTTPException(status_code=400, detail="No verified medicines for this job.")
    brand_names = [med.get("brand_name") or med.get("ocr_text") for med in verified if med.get("brand_name") or med.get("ocr_text")]
    result = compare_generics(brand_names)
    return {"job_id": job_id, "generic_comparison": result}

# ---------------------------------------------------------------------------
# PDF Report endpoint (Step 8)
# ---------------------------------------------------------------------------

@app.post("/api/report")
async def generate_report(request: Request):
    """Generate a printable PDF medication timetable for a verified job.

    Expected JSON payload: {"job_id": "..."}
    Returns the PDF as a downloadable file.
    """
    data = await request.json()
    job_id = data.get("job_id")
    if not job_id or job_id not in _JOBS:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    job = _JOBS[job_id]
    verified = job.get("user_verified")
    if not verified:
        raise HTTPException(status_code=400, detail="No verified medicines for this job.")
    if not isinstance(verified, list) or len(verified) == 0:
        raise HTTPException(status_code=400, detail="Verified medicines list is empty.")
    try:
        pdf_bytes = generate_pdf(verified)
    except Exception as exc:
        job["status"] = "error"
        job["issues"].append(str(exc))
        import traceback
        print(f"[PIPELINE] Exception in job_id={job_id}: {exc}", flush=True)
        traceback.print_exc()

        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}")

    pdf_stream = io.BytesIO(pdf_bytes)
    filename = f"medication_timetable_{job_id}.pdf"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(pdf_stream, media_type="application/pdf", headers=headers)

@app.get("/api/progress/{job_id}")
async def get_progress(job_id: str):
    """Return a simple JSON progress report for *job_id*.
    """
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job ID not found.")
    # Minimal progress structure – can be extended with percentages.
    resp = {
        "job_id": job_id,
        "status": job["status"],
        "issues": job.get("issues", []),
    }
    if job["status"] == "completed":
        resp["ocr_result"] = job["ocr_result"]
        resp["parse_result"] = job["parse_result"]
    if job.get("user_verified"):
        resp["user_verified"] = job["user_verified"]
    return JSONResponse(content=resp)

# ---------------------------------------------------------------------------
# Cleanup on shutdown – delete the temporary upload directory.
# ---------------------------------------------------------------------------
@app.on_event("shutdown")
def _cleanup_uploads():
    try:
        shutil.rmtree(_UPLOAD_DIR)
    except Exception:
        pass
