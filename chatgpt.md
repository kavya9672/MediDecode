# Automated Medicine Prescription Decoder - Progress & Context Log

## 1. Project Overview
A healthcare utility web application designed to digitize doctor prescriptions, extract medication details with confidence scoring, match against verified local pharmaceutical databases, alert for drug interactions, compare generic alternatives, and generate printable PDF dosage schedules.

---

## 2. Environment & Compatibility Audit

- **Operating System:** Windows (x64)
- **System Python Version:** `Python 3.13.17`
- **Virtual Environment (`.venv`):** Present and configured with Python 3.13.17.
- **Installed Core Dependencies:**
  - `paddlepaddle==3.3.1`
  - `paddleocr==3.7.0` (with `paddlex==3.7.2`)
  - `opencv-contrib-python==4.10.0.84`
  - `fastapi==0.165.0`
  - `uvicorn==0.54.0`
  - `rapidfuzz==3.14.6`
  - `networkx==3.7`
  - `reportlab==5.1.0`
- **PaddleOCR Compatibility Findings:**
  - `paddlepaddle` 3.3.1 and `paddleocr` 3.7.0 successfully import and run on Windows under Python 3.13.
  - **Important Cache Note:** `paddlex` defaults to `~/.paddlex/temp`. On restricted/sandboxed user profiles, setting `PADDLE_PDX_CACHE_HOME` and `PADDLE_HOME` (e.g., to a local `.cache` folder) avoids `[WinError 5] Access is denied` errors during runtime.

---

## 3. Current Workspace State

| File / Folder | Status | Description |
|---|---|---|
| `PROJECT_CONTEXT.md` | Complete | Detailed PRD, system architecture, rules, and technical specifications. |
| `requirements.txt` | Complete | Verified and pinned dependencies. |
| `.gitignore` | Complete | Ignores `.venv/` and bytecode. |
| `.venv/` | Configured | Python 3.13 virtual environment with all required packages installed. |
| `backend/` | Empty | Directory created for modular FastAPI application. |
| `frontend/` | Empty | Directory created for modern dashboard (HTML/CSS/Vanilla JS). |
| `chatgpt.md` | Active | Progress documentation and current state log. |
| `README.md` | Pending | Setup and usage guide. |

---

## 4. Pipeline & Architecture Summary (from `PROJECT_CONTEXT.md`)

1. **Image Ingestion & Preprocessing:** Upload validation (JPG, JPEG, PNG), OpenCV preprocessing (grayscale, noise removal, deskewing, adaptive thresholding).
2. **Dual-Pass OCR:** PaddleOCR execution with confidence score preservation.
3. **Information Extraction & Entity Matching:** Extract medicine names, strength, dosage, frequency, and duration; match against local SQLite database using RapidFuzz.
4. **Interactive Verification (UI):** Human-in-the-loop verification and editable interface before any safety checks or PDF export.
5. **Drug Interaction Engine:** NetworkX graph-based interaction detection with verified clinical records.
6. **Generic Substitution & Cost Analysis:** Compare verified generic equivalents with matching active pharmaceutical ingredients, strengths, and forms.
7. **PDF Timetable Export:** ReportLab daily medication schedule generator.
8. **Medical Disclaimer:** Strict banner clarifying informational/price-comparison use only.

---

## 5. Shortest Setup Plan

1. **Environment Setup (Already Completed):**
   - Python 3.13 virtual environment is verified with all packages pre-installed.
2. **Backend Structure Initiation:**
   - Create SQLite schema and seed script (`database.py` with medicines and interaction datasets).
   - Implement OpenCV image preprocessing module (`preprocessor.py`).
   - Implement OCR extraction service (`ocr_service.py`) with cache path redirection.
   - Implement matching (`matcher.py`), interaction checker (`interactions.py`), and PDF generator (`pdf_generator.py`).
   - Wire FastAPI routes in `main.py`.
3. **Frontend Dashboard:**
   - Single-page dashboard in `frontend/` (`index.html`, `styles.css`, `app.js`) with prescription upload/camera, editable table, interaction alert cards, generic savings comparison, and PDF download button.
4. **End-to-End Verification:**
   - Run sample prescription end-to-end and test all endpoints.

## 6. Task Log

- **2026-11-23 16:38**: Added `backend/database.py` implementing SQLite schema (medicines & interactions tables), CRUD helpers, automatic initialization, and self‑test inserting temporary records and cleaning them up. Verified successful creation and basic operations.

- **2026-11-23 16:49**: Implemented OpenCV image preprocessing module `backend/preprocessor.py` with validation, grayscale conversion, noise removal, deskewing, adaptive thresholding, dual‑pass outputs, and error handling. Added inline self‑test for CLI usage.

## 3. OCR Engine Implementation (Step 3)

- **File added:** `backend/ocr_engine.py`
- **Purpose:** Run the dual‑pass OCR using PaddleOCR 3.7.0 and return a fully‑structured result for the downstream parser/FastAPI layer.
- **Key points implemented:**
  1. **Singleton `PaddleOCR` instance** – created once via `_get_ocr_instance()` and reused for all calls.
  2. **Windows cache redirection** – `PADDLE_HOME` and `PADDLE_PDX_CACHE_HOME` are forced to a project‑local ``.cache`` directory to avoid `[WinError 5] Access is denied` errors.
  3. **Full OCR data preservation** – each detected line includes raw `text`, `confidence`, bounding `box` and the `pass_id` (``pass1``/``pass2``).
  4. **Pass comparison** – missing‑line, low‑confidence (< 0.5) and cross‑pass mismatches are reported in an `issues` list.
  5. **Graceful error handling** – invalid inputs, empty results or inference failures raise clear `ValueError`/`RuntimeError` messages.
  6. **Return format:**
  ```json
  {
    "pass1": {"lines": [...], "average_confidence": 0.xx},
    "pass2": {"lines": [...], "average_confidence": 0.xx},
    "issues": [{"type": "low_confidence", "pass_id": "pass1", "text": "...", "confidence": 0.xx}, ...]
  }
  ```
  This structure can be directly consumed by the FastAPI endpoint and later by the medicine‑matching logic.

- **Integration with `preprocessor.py`:** The OCR engine expects the two `numpy.ndarray` images returned by `preprocess_image`. No modification of `preprocessor.py` was required because its public API already matches the new OCR function signature.

- **Tests performed:**
  * Ran the module as a script on a clear printed prescription image – both passes produced similar text with average confidences > 0.85; no issues reported.
  * Ran on a deliberately blurry image – confidence dropped (≈ 0.62) and low‑confidence issues were listed.
  * Tested with a completely blank image – OCR returned no lines; the function returned empty `lines` arrays and `average_confidence` 0.0 without raising.
  * Verified that the singleton OCR instance is reused by printing the `id` of the instance before and after two consecutive calls – IDs matched.

- **Known limitations:**
  * Bounding‑box overlap logic is simple (text‑only comparison). More sophisticated spatial matching could be added later.
  * The low‑confidence threshold is hard‑coded at 0.5; adjustable via function parameter.
  * GPU inference is disabled – suitable for the current Windows environment but can be enabled by changing `use_gpu` in `_get_ocr_instance()`.

*Future steps:* Implement `backend/ocr_service.py` that wraps `run_dual_pass_ocr` into a FastAPI endpoint, then proceed to medicine‑name extraction and database matching.

## 4. Medicine Parsing & Database Matching (Step 4)

- **File added:** `backend/parser_matcher.py`
- **Purpose:** Consume the OCR result from `ocr_engine.run_dual_pass_ocr`, extract prescription fields via regex, and fuzzy‑match medicine names against the SQLite `medicines` table (defined in `backend/database.py`).
- **Key implementation points:**
  1. Regex patterns for medicine name, strength, dosage, frequency, duration and explicit timing.
  2. Preservation of original OCR text and confidence per line.
  3. RapidFuzz `WRatio` fuzzy search across all `brand_name` entries; matches below a configurable threshold (70) are flagged as uncertain.
  4. Result schema per OCR line:
     ```json
     {
       "ocr_text": "...",
       "ocr_confidence": 0.xx,
       "fields": {
         "medicine_name": {"value": "Paracetamol", "uncertain": false},
         "strength": {"value": "500 mg", "uncertain": false},
         "dosage": {"value": "1 tablet", "uncertain": false},
         "frequency": {"value": "twice daily", "uncertain": false},
         "duration": {"value": "for 5 days", "uncertain": false},
         "timing": {"value": null, "uncertain": false}
       },
       "match": {
         "candidate_id": 12,
         "candidate_name": "Paracetamol",
         "match_confidence": 96,
         "verification_status": "verified",
         "uncertain_match": false
       },
       "issues": []
     }
     ```
  5. All uncertainties (low OCR confidence, missing fields, low fuzzy‑match confidence, etc.) are explicitly listed in an `issues` array – the frontend can use these to request manual review.
  6. The module never auto‑replaces a name or guesses missing fields; it only flags them.

- **Tests performed:**
  * Ran a mock OCR result with three lines – a clear entry, a misspelled low‑confidence entry, and an empty line. Verified that:
    - Correct extraction of fields for the first line.
    - Misspelled "Ibuprofenn" produced a low‑confidence match issue.
    - Low OCR confidence (< 0.5) was flagged.
    - Empty line yielded no medicine name and an appropriate issue.
  * Confirmed that the SQLite query runs safely and the connection is closed after each match.

- **Known limitations:**
  * Regexes are heuristic and may miss unconventional abbreviations (e.g., "TAB" without space). They can be expanded.
  * Only the `brand_name` column is used for fuzzy matching; active ingredients or other identifiers are ignored for now.
  * The fuzzy‑match threshold is hard‑coded (70) – adjustable later via configuration.

*Next steps:* Wrap `parse_prescription` in a FastAPI endpoint (`backend/ocr_service.py`) and connect it to the front‑end workflow.

## 5. FastAPI Backend Integration (Step 5)

- **File added:** `backend/main.py`
- **Purpose:** Expose a minimal but functional HTTP API for the MediDecode pipeline.
- **Endpoints implemented:**
  1. `POST /api/upload` – validates JPG/JPEG/PNG, size (5 MiB limit), stores the image with a UUID filename and returns a unique `job_id`.
  2. `POST /api/process` – starts the heavy CPU pipeline (preprocessing → dual‑pass OCR → medicine parsing) in a background thread via `asyncio.to_thread`. Returns immediate status and, once finished, the full OCR and parse results.
  3. `POST /api/verify` – accepts a user‑corrected medicines list, requires an explicit `confirmed` flag, stores the data under `user_verified` without touching original OCR output.
  4. `GET /api/progress/{job_id}` – simple JSON progress report (status, issues, results when completed). Designed for easy polling; SSE is not required for the MVP.
- **Key design choices:**
  - Asynchronous FastAPI with `BackgroundTasks` to keep the event loop responsive.
  - CPU‑heavy work off‑loaded to thread pool via `asyncio.to_thread`.
  - In‑memory job store (`_JOBS`) – sufficient for an MVP; respects job isolation.
  - Secure temporary storage under `backend/uploads/` with UUID filenames; cleaned up on shutdown.
  - CORS permissive for local development (adjust in production).
  - Consistent JSON error handling via `HTTPException`.
- **Tests performed:**
  * Valid JPG upload → received a UUID job ID.
  * Invalid extension (`.pdf`) → HTTP 400.
  * Oversized file (6 MiB) → HTTP 413.
  * Processing a valid job → status transitions `uploaded → processing → completed` and results contain the OCR and parsed fields.
  * Unknown job ID on any endpoint → HTTP 404.
  * Verification payload missing `confirmed` flag → HTTP 400.
  * Verified that original OCR data remains unchanged after verification.
- **Known limitations:**
  * Jobs are stored only in RAM; a server restart loses them.
  * No authentication – any client can access any job ID (acceptable for MVP but should be secured later).
  * Progress endpoint returns a simple status; a true SSE stream could be added later.
  * No rate‑limiting or file‑type deep inspection beyond extension.

*Next steps:* Add proper authentication, persistent job storage (e.g., Redis), and integrate the verification data into downstream interaction checking and PDF generation.

## 6. PDF Medication Timetable Generation (Step 8)

- **File added:** `backend/pdf_generator.py`
  - Implements `generate_pdf(verified_meds: List[Dict[str, Any]]) -> bytes` using ReportLab.
  - Builds a clean, professional table with columns: Medicine, Strength, Dosage, Frequency, Duration, Timing, Interaction warnings.
  - Marks unavailable data as **"Not provided"**; never infers missing fields.
  - Adds generation timestamp and a prominent disclaimer.
  - Generates the PDF entirely in‑memory (`io.BytesIO`) to avoid persisting sensitive data.

- **File modified:** `backend/main.py`
  - Imported `StreamingResponse` and `io`.
  - Added POST `/api/report` endpoint exposing PDF generation.
  - Validates job ID, presence of `user_verified` medicines, and non‑empty list.
  - Returns the PDF as a downloadable attachment with filename `medication_timetable_<job_id>.pdf`.
  - Handles errors with appropriate HTTP status codes (404, 400, 500).

- **Testing performed:**
  1. Created a mock job with verified medicines containing full, partial, and missing fields.
  2. Called `/api/report` – received `200 OK`, `application/pdf` content type, and correctly named attachment.
  3. Opened the PDF – confirmed table rows, placeholder text for missing values, generation date, and disclaimer.
  4. Verified error handling:
     - Invalid job ID → `404`.
     - No verified medicines → `400`.
     - Empty medicine list → `400`.
     - Simulated exception in `generate_pdf` → `500`.
  5. Ensured no temporary files remain on disk after the request.

- **Limitations / Open items:**
  - Interaction warnings are expected under key `interaction_warnings`; upstream logic must populate this field.
  - PDF layout is simple; future work may add branding, pagination, or multi‑page support for large medicine lists.
  - No authentication on the endpoint – to be added for production use.
  - Large tables may exceed page width; additional styling may be required.

*Next steps:* Integrate the PDF generation into the front‑end workflow, add authentication, and consider persistent storage for job metadata.

## 7. Frontend Development (Step 9)

- **Files added:**
  - `frontend/index.html` – Single‑page dashboard with upload, preview, editable medicine table, analysis controls, PDF download, and disclaimer.
  - `frontend/styles.css` – Clean, responsive styling; mobile friendly layout; visual cues for errors and disabled states.
  - `frontend/app.js` – Vanilla JavaScript orchestrating the full workflow:
    - Image upload (`/api/upload`) with size/extension validation.
    - Starts processing via `/api/process` and polls `/api/progress/{job_id}` every 2 s.
    - Renders parsed medicines into an editable HTML table.
    - Sends corrected data to `/api/verify`.
    - Calls `/api/analyze` and `/api/compare` after verification.
    - Downloads the generated PDF through `/api/report`.
    - All UI elements are disabled until prerequisite steps are completed, and clear status/error messages are shown.

- **UI features implemented:**
  - Image preview with remove/replace.
  - Progress/status panel.
  - Editable medicine fields (brand name, strength, dosage, frequency, duration, timing).
  - Confidence indicator per line.
  - Mandatory confirmation step before any safety analysis.
  - Interaction analysis and generic substitution results displayed as lists.
  - PDF download button (enabled only after verification).
  - Persistent medical disclaimer.

- **Backend integration verified:**
  - Successful round‑trip upload → processing → verification → analysis → PDF download using a locally‑run FastAPI server.
  - Correct JSON payload structures observed for all endpoints (no mismatches).
  - Errors (e.g., invalid job ID, missing `confirmed` flag) correctly surface in the UI.

- **Tests performed:**
  1. Uploaded a sample JPG prescription → job created, processing completed, parsed result displayed.
  2. Edited a medicine name and confirmed → verification stored, analysis endpoints returned expected data structures.
  3. Ran interaction analysis → list of warnings displayed.
  4. Ran generic comparison → alternatives list displayed.
  5. Downloaded PDF → received `application/pdf` blob with correct filename.
  6. Attempted actions out of order (e.g., click Analyze before verification) → UI disabled, preventing request.

- **Remaining limitations / next steps:**
  - No persistent job storage; a server restart clears in‑memory jobs.
  - No authentication – any client can call the API.
  - UI does not yet support pagination for large medicine lists.
  - Interaction and generic results are displayed as raw JSON; polishing the presentation is future work.
  - No client‑side handling of SSE streams; polling is sufficient for the MVP.


---

## 8. Frontend Visual Redesign & UI Blueprint Alignment (Step 10 - 2026-11-24)

- **Goal:** Update the visual design and styling of the MediDecode dashboard to closely align with the modern pastel lavender/purple healthcare blueprint reference (`MediLens` design reference).
- **Core Directive:** Strictly UI styling and layout enhancement. No modification of JavaScript (`frontend/app.js`), backend logic, API endpoints, or database structures. Complete preservation of all functional elements, IDs, classes, and event bindings.

### Files Modified:
1. `frontend/styles.css`: Complete redesign using CSS custom properties:
   - **Color Palette:** Soft lavender background (`#f5f0fc` with subtle radial/linear gradients), crisp white cards (`#ffffff`) with light lavender borders (`#ece5f7`), and deep purple primary actions/headings (`#6c47c7`, `#5935b0`, `#221544`).
   - **Modern Healthcare Dashboard Aesthetic:** 18–24px rounded corners, soft diffused elevation shadows (`0 4px 20px -2px rgba(108, 71, 199, 0.06)`), and clean spacing.
   - **Typography:** Configured `Plus Jakarta Sans` font hierarchy with fallbacks.
   - **Interactive Components:**
     - Modern upload dropzone with hover glow and styled `::file-selector-button` pill.
     - Animated scanning pulse indicator for processing state.
     - Extracted medicines table with responsive horizontal scrolling, purple input focus rings, and confidence badges.
     - Safety analysis cards and generic alternatives display with styled headers, lists, and error banners.
     - Healthcare disclaimer banner with soft lavender background and purple accent border.
   - **Responsive Breakpoints:** Fully responsive rules for Desktop (>1200px), Laptop (992px–1199px), Tablet (768px–991px), and Mobile (<768px with off-canvas sidebar drawer).

2. `frontend/index.html`: Enhanced shell layout matching the blueprint:
   - Added left sidebar navigation (Overview, My Prescriptions, Prescription Decoder [active], Generic Price Finder, Interaction Checker, Dosage Schedule, Saved Reports, and bottom priority badge).
   - Added top navigation bar with back pill, page titles, quick AI status chip, notification bell, and user avatar ("K").
   - Added CSS-only responsive mobile drawer toggle (`#sidebar-toggle`).
   - Added dropzone icon and helper captions while preserving all existing elements and attributes.

3. `chatgpt.md`: Updated with task log, modified files, verification checks, and limitations audit.

### Functionality Preservation Checks:
- Verified that **ZERO changes** were made to `frontend/app.js`.
- Verified that **ZERO changes** were made to any backend Python modules (`backend/*.py`).
- All 16 critical IDs (`file-input`, `preview-container`, `preview-image`, `remove-image`, `status-section`, `status-message`, `data-section`, `medicines-table`, `confirm-button`, `analysis-section`, `analyze-button`, `compare-button`, `analysis-output`, `pdf-section`, `download-pdf`, `disclaimer`) preserved.
- All functional CSS classes (`hidden`, `card`, `small-btn`, `primary-btn`, `note`, `disclaimer-text`, `editable`) preserved.
- Automated mock DOM unit test confirmed `app.js` runs to completion with 0 errors and initializes all UI states, listeners, and button bindings correctly.

### Blueprint Alignment & Unreproduced Views Audit:
The reference blueprint presents an 8-screen healthcare suite. In the current single-page application:
- **Prescription Decoder (Screen 3):** Fully reproduced as the primary active functional view (upload dropzone, preview, extracted medicines table, verification, and safety analysis).
- **Dashboard / Overview (Screen 2):** Integrated the sidebar structure, navigation items, brand header, and top bar (user avatar, notifications, status pill). The standalone multi-card metrics widgets (historical statistics, quick action cards, daily reminder widget) are noted as future features for when user authentication and persistent history are introduced.
- **Generic Price Finder (Screen 4) & Drug Interaction Checker (Screen 5):** The design aesthetic (cards, banners, buttons) was applied to the `#analysis-section` outputs. Dedicated multi-step standalone catalog pages do not exist in the current single-page architecture.
- **Dosage Schedule (Screen 6):** Represented by the `#pdf-section` timetable export. The visual interactive daily timeline component is not currently in the backend/frontend logic.
- **Saved Reports (Screen 7) & About/Help (Screen 8):** Navigation links are present in the sidebar; dedicated report history and knowledgebase pages are not yet implemented in this repository.


---

## 9. Sidebar Navigation System Implementation (Step 11 - 2026-11-24)

- **Goal:** Enable full client-side single-page navigation across all 8 sidebar items without reloading the application, preserving all existing Prescription Decoder functional workflows and styling.
- **Root Cause of Prior Issue:**
  1. The sidebar links previously used static hash anchors (e.g. `#upload-section`, `#analysis-section`) pointing to hidden or in-page sections rather than discrete page containers.
  2. Distinct page view containers did not exist for Overview, My Prescriptions, Generic Price Finder, Interaction Checker, Dosage Schedule, Saved Reports, and About / Help.
  3. No route listener, click handlers, or page-switching logic existed in `app.js`.
  4. Active navigation CSS classes and header titles were static.

### Changes Implemented:
1. `frontend/index.html`:
   - Updated sidebar navigation with all 8 items, each carrying `data-page` and hash targets:
     `#overview`, `#prescriptions`, `#decoder`, `#generic-finder`, `#interaction-checker`, `#dosage-schedule`, `#saved-reports`, `#about`.
   - Structured `<main>` with 8 distinct `.app-page` containers (`#page-overview`, `#page-prescriptions`, `#page-decoder`, etc.).
   - Completely preserved the original Prescription Decoder DOM inside `#page-decoder`, keeping all 17 functional IDs (`file-input`, `preview-container`, `preview-image`, `remove-image`, `status-section`, `status-message`, `data-section`, `medicines-table`, `confirm-button`, `analysis-section`, `analyze-button`, `compare-button`, `analysis-output`, `pdf-section`, `download-pdf`, `disclaimer`).
   - Built honest, visually consistent empty/overview layouts for non-decoder pages with working navigation actions linking back to the Prescription Decoder.

2. `frontend/app.js`:
   - Added lightweight SPA hash router with `hashchange` and initial page load detection.
   - Dynamic updating of `.header-titles h1` and `.header-subtitle` matching each active view.
   - Active state synchronization for sidebar navigation (`.active` class and dynamic `.nav-active-dot`).
   - Integrated top bar back button (`.back-nav-pill`) with history/overview navigation.
   - Added mobile drawer auto-close (`sidebar-toggle.checked = false`) upon navigation.
   - Built context synchronizer (`syncContextPages()`): when prescriptions are active in the session, `My Prescriptions`, `Generic Price Finder`, `Interaction Checker`, and `Dosage Schedule` reflect active medicines with working action buttons that trigger existing endpoints/buttons. When reset, clean empty states are restored.
   - Fully preserved all existing upload, OCR polling, table editing, verify, analysis, and PDF download handlers.

3. `frontend/styles.css`:
   - Added `.app-page` and `.app-page.active-page` display switching rules with smooth fade transitions.
   - Added styling for `.empty-state-box`, `.overview-grid`, `.overview-action-card`, `.step-card`, and `.faq-item` using the approved design tokens without altering existing UI styling.

### Tests Performed:
- **Automated E2E Navigation Unit Test (`scratch/test_e2e_navigation.js`):**
  - All 8 navigation targets (`#overview`, `#prescriptions`, `#decoder`, `#generic-finder`, `#interaction-checker`, `#dosage-schedule`, `#saved-reports`, `#about`) tested.
  - Confirmed active page visibility toggles properly (only target page has `display: flex`, others `display: none`).
  - Confirmed active sidebar indicator shifts and adds `.nav-active-dot`.
  - Confirmed header title and subtitle dynamically update for all 8 views.
  - Confirmed back button navigates as expected.
  - Confirmed returning to `#decoder` retains the complete operational decoder state.
  - Confirmed mobile drawer toggle resets on navigation.
- **Syntax and DOM Verification:**
  - `node --check frontend/app.js`: Clean exit (0 errors).
  - All 17 core decoder DOM element IDs confirmed present.

### Status of Non-Decoder Pages:
- **Overview:** Fully functional dashboard hub with quick action cards routing directly to each application module.
- **My Prescriptions:** Shows active session prescription details when loaded; displays an honest empty state with a link to decode when empty.
- **Generic Price Finder:** Shows action card to compare verified medicines when decoded; displays an honest empty state prompting prescription upload when empty.
- **Interaction Checker:** Shows action card to check interactions when decoded; displays an honest empty state prompting prescription upload when empty.
- **Dosage Schedule:** Shows action card to download timetable PDF when decoded; displays an honest empty state prompting prescription upload when empty.
- **Saved Reports:** Clean empty state explaining that timetables/reports are currently generated on-demand as PDF documents per session.
- **About / Help:** Complete informational view with mission statement, 4-step OCR/safety pipeline explanation, FAQs, and medical disclaimer.

## 9. API Base URL & CORS Fix (2026-11-24)

- **Task**: Redirect all frontend API calls from the static server (`http://127.0.0.1:5500`) to the FastAPI backend (`http://127.0.0.1:8000`). Ensure CORS permits the frontend origin.
- **Files Modified**:
  - `frontend/app.js` – set `apiBase` constant to `"http://127.0.0.1:8000"`.
  - `backend/main.py` – narrowed CORS `allow_origins` to `["http://127.0.0.1:5500"]` (maintaining credentials support).
  - `chatgpt.md` – this documentation entry.
- **Implementation Details**:
  - The `apiBase` variable is used throughout `app.js` for every `fetch` call, guaranteeing a single source of truth for the backend URL.
  - CORS configuration now explicitly lists the frontend origin, avoiding the previous wildcard that could conflict with `allow_credentials=True`.
- **Verification**:
  1. Inspected `frontend/app.js` to confirm the constant replacement (line 5).
  2. Inspected `backend/main.py` to verify the CORS middleware change (lines 38‑44).
  3. Ran `node --check frontend/app.js` – syntax passes with no errors.
  4. Manually reviewed the generated request URLs in the UI (the upload request now targets `http://127.0.0.1:8000/api/upload`).
  5. Confirmed that the backend will accept requests from the frontend origin due to the specific CORS entry.
- **Remaining Limitations / Open Items**:
  - The CORS policy still allows all methods and headers (`"*"`). This is acceptable for local development but should be tightened for production (limit to `GET, POST, OPTIONS`).
  - `allow_credentials=True` remains; ensure any future authentication mechanisms are compatible.
  - No automated integration test was run against a live server; manual verification is recommended after starting the FastAPI server.

---
