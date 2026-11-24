-
- Build a healthcare utility portal where users upload a prescription image; the backend extracts medicine names, dosages, and schedules, flags interaction warnings ,Allow users to manually verify and correct extracted information., suggests verified generic salt equivalents with price comparisons, and exports a clean daily dosage printable timetable in pdf format.I have cleared about the system architecture in above image.

  Implement the following pipeline:

  1. Accept prescription images in JPG, JPEG and PNG formats.
  2. Validate uploaded files and their size.
  3. Process images using OpenCV:
     - Grayscale conversion
     - Noise removal
     - Deskewing where possible
     - Adaptive thresholding
  4. Extract text using PaddleOCR.
  5. Preserve extracted text and OCR confidence information.
  6. Identify medicine names, strength, dosage, frequency and duration.
  7. Use RapidFuzz to match extracted medicine names against the local medicine database.
  8. Flag low-confidence or uncertain results.
  9. Display the extracted information in an editable interface.
  10. Require user confirmation before safety analysis and PDF generation.

  Important: Handwritten prescription recognition is not guaranteed. Never silently guess unclear medicine names or missing dosage information.

  Create a structured SQLite database containing:

  - Medicine brand name
  - Active pharmaceutical ingredient / salt
  - Strength
  - Dosage form
  - Route of administration
  - Manufacturer
  - Price
  - Price source
  - Verification date

  Compare potential generic equivalents only when the relevant pharmaceutical properties match.

  Never invent medicine prices, manufacturers or generic equivalence claims. Clearly distinguish verified records from unavailable information.

  ## 5. Drug Interaction Engine

  Use NetworkX to build a graph-based drug interaction checker.

  Each medicine should represent a node.

  Each verified interaction should represent an edge containing:

  - Interacting medicine
  - Interaction severity
  - Interaction description
  - Source/reference

  Display appropriate warnings when known interactions are detected.

  Do not generate medical interaction claims using assumptions or fabricated sample data. If interaction information is unavailable, clearly display that it has not been verified.

  ## 6. PDF Generation

  Use ReportLab to generate a downloadable, printable medication timetable containing:

  - Medicine name
  - Confirmed strength
  - Confirmed dosage
  - Frequency
  - Duration
  - Morning / afternoon / evening schedule, only when supported by the confirmed prescription
  - Relevant warnings
  - Date of generation

  Do not infer missing instructions or modify prescribed dosages.

  ## Frontend Requirements

  Create a modern, professional healthcare dashboard with:

  - Prescription upload and camera capture.
  - Image preview.
  - Processing progress indicator.
  - OCR-extracted medicine information.
  - Editable medicine table.
  - Medicine verification status.
  - Drug interaction warning section.
  - Generic medicine comparison section.
  - Price and savings display.
  - Daily medication timetable.
  - PDF download functionality.

  ## Code Quality and Development Rules

  - Keep frontend and backend code separate.
  - Use modular Python files.
  - Write readable, maintainable code.
  - Use reusable functions.
  - Maintain consistent API response formats.
  - Include requirements.txt.
  - Include .gitignore.
  - Include a README.md with installation and execution instructions.
  - Keep configuration and database access organized.
  - Do not hardcode fake medical claims or present demo data as verified real-world data.
  - Protect uploaded prescription images and avoid unnecessary retention of sensitive information.

    \
    Note: Be sure to display a clear medical disclaimer banner on the UI stating that the tool is for informational and price-comparison assistance only and does not replace a licensed pharmacist or doctor.

  Follow the previously defined system architecture and use HTML5, CSS3, Vanilla JavaScript, Fetch API, Server-Sent Events (SSE), Python with asynchronous FastAPI, OpenCV, PaddleOCR, Regex, RapidFuzz, SQLite, NetworkX and ReportLab. Implement a dual-pass OCR pipeline using differently processed images, compare extracted text and confidence scores, and flag uncertain results for manual verification. Never guess unclear medicine names, strengths, dosages, frequency or duration; preserve original OCR output and allow users to edit extracted information before proceeding. Maintain a structured pharmaceutical database with trustworthy data sources, source references, verification dates and verification status. Only compare generic alternatives when active ingredients, strength, dosage form, route and other relevant pharmaceutical properties match; never fabricate medicine information, interaction warnings, manufacturers, prices or savings. Build a NetworkX interaction graph using verified interaction records containing severity, descriptions and references, and clearly indicate when information is unavailable. Implement separate FastAPI endpoints for image upload, SSE processing progress, OCR processing, medicine verification, interaction analysis, generic comparison and PDF generation. Ensure the frontend and backend communicate correctly, include proper input validation, error handling, secure temporary image storage and cleanup, and display a prominent medical disclaimer stating that the application is for informational and price-comparison assistance only and does not replace a licensed doctor or pharmacist. Generate downloadable ReportLab PDFs containing only user-confirmed prescription information, without inferring missing instructions or modifying prescribed dosages. Develop this as a functional MVP within a strict 12-hour development window, prioritizing image upload, OCR, manual verification, medicine matching, interaction checking, generic comparison and PDF generation before optional features such as SSE refinements and offline Service Worker support. Include requirements.txt, .gitignore, README.md, modular code, and clear setup instructions. Test every API and the complete end-to-end workflow. If any feature or external data source is unavailable, implement a clearly labelled fallback and document its limitations rather than pretending it works. Prioritize functional integration, medical data accuracy, maintainable code and a polished, responsive healthcare dashboard over unnecessary complexity. Do not leave nonfunctional buttons, fabricated medical data or incomplete features disguised as working functionality.

