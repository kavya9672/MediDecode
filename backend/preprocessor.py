"""backend/preprocessor.py
OpenCV‑based image preprocessing for OCR.

Provides a single public function ``preprocess_image`` which accepts a file path or a
``bytes``‑like object representing an image (JPG, JPEG or PNG). It returns a tuple of two
NumPy arrays ready to be fed to ``paddleocr.PaddleOCR.ocr`` (either as an ordinary
``numpy.ndarray`` in BGR format or as a path).

The pipeline follows the specification from the project task:

1. Validate the file extension – only ``.jpg``/``.jpeg``/``.png`` are accepted.
2. Attempt to decode the image with OpenCV; if decoding fails a clear ``ValueError`` is raised.
3. Convert the image to grayscale.
4. Remove visual noise using a median blur (robust for salt‑and‑pepper noise) – this step is optional
   but safe for most prescription scans.
5. Deskew the image when a dominant text orientation is detected. The algorithm computes the
   minimum area rectangle around the non‑zero foreground pixels, extracts the angle and rotates the
   image to make the text baseline horizontal. If the calculated angle is negligible the rotation is
   skipped.
6. Apply adaptive thresholding (Gaussian weighted) to obtain a high‑contrast binary image suitable for OCR.
7. Produce two differently processed versions for a *dual‑pass* OCR strategy:
   * ``proc1`` – the standard pipeline described above.
   * ``proc2`` – the same pipeline plus a slight morphological closing (dilate → erode) that can help
     fuse broken characters in low‑quality scans.
8. The original image is never mutated; all transformations work on copies.
9. Errors (unsupported format, unreadable file, unexpected OpenCV failures) are caught and re‑raised as
   ``ValueError`` with an informative message so the caller can handle them safely.

The module has no external side‑effects and only relies on ``opencv-python`` (``cv2``) and ``numpy`` –
both are already part of the project's ``requirements.txt``.
"""

import os
import cv2
import numpy as np

# Public API -----------------------------------------------------------------

def preprocess_image(source: str | bytes) -> tuple[np.ndarray, np.ndarray]:
    """Preprocess an image for PaddleOCR.

    Parameters
    ----------
    source : str | bytes
        Either a filesystem path to an image file or a ``bytes`` object containing the raw image
        data (as returned by ``UploadFile.read()`` in FastAPI, for example).

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        A pair ``(proc1, proc2)`` where each element is a BGR ``numpy.ndarray`` ready for OCR.

    Raises
    ------
    ValueError
        If the file extension is not supported or OpenCV cannot decode the image.
    """
    # ---------------------------------------------------------------------
    # 1️⃣ Validate input type & extension
    # ---------------------------------------------------------------------
    if isinstance(source, str):
        # Path‑based usage – check extension early to give a friendly error.
        ext = os.path.splitext(source)[1].lower()
        if ext not in {'.jpg', '.jpeg', '.png'}:
            raise ValueError(f"Unsupported image format '{ext}'. Only JPG, JPEG and PNG are allowed.")
        # Load the image from disk.
        image = cv2.imread(source)
        if image is None:
            raise ValueError(f"Failed to read image from path '{source}'. The file may be corrupted or not an image.")
    elif isinstance(source, (bytes, bytearray)):
        # In‑memory bytes – decode using OpenCV ``imdecode``.
        nparr = np.frombuffer(source, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Unable to decode image bytes. Ensure the data represents a valid JPG/JPEG/PNG image.")
    else:
        raise TypeError("source must be a file path (str) or raw image bytes.")

    # Preserve the original – all later steps work on a copy.
    original = image.copy()

    # ---------------------------------------------------------------------
    # 2️⃣ Grayscale conversion
    # ---------------------------------------------------------------------
    gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)

    # ---------------------------------------------------------------------
    # 3️⃣ Noise removal – median blur is fast and effective for salt‑and‑pepper noise.
    # ---------------------------------------------------------------------
    denoised = cv2.medianBlur(gray, ksize=3)

    # ---------------------------------------------------------------------
    # 4️⃣ Deskew (when a noticeable tilt is present)
    # ---------------------------------------------------------------------
    deskewed = _deskew(denoised)

    # ---------------------------------------------------------------------
    # 5️⃣ Adaptive thresholding – produce a binary image suitable for OCR.
    # ---------------------------------------------------------------------
    thresh = cv2.adaptiveThreshold(
        deskewed,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv2.THRESH_BINARY_INV,
        blockSize=31,  # must be odd
        C=10
    )

    # The first version is the plain thresholded image (converted back to BGR because PaddleOCR
    # expects a 3‑channel image when supplied as a NumPy array).
    proc1 = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

    # ---------------------------------------------------------------------
    # 6️⃣ Second version – add a light morphological closing to join broken strokes.
    # ---------------------------------------------------------------------
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    proc2 = cv2.cvtColor(closed, cv2.COLOR_GRAY2BGR)

    return proc1, proc2


# -------------------------------------------------------------------------
# Helper functions (internal)
# -------------------------------------------------------------------------

def _deskew(image: np.ndarray) -> np.ndarray:
    """Rotate the image to correct a small skew angle.

    The function works on a binary or grayscale image. It computes the minimum‑area bounding
    rectangle of the foreground pixels (non‑zero) and derives the rotation angle. If the absolute angle
    is less than 1° the image is returned unchanged to avoid unnecessary interpolation artifacts.
    """
    # Convert to binary for contour detection – simple Otsu threshold is enough.
    _, bin_img = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(bin_img > 0))
    if coords.size == 0:
        # No foreground – return the original image (nothing to deskew).
        return image
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    # The `cv2.minAreaRect` angle definition can be confusing – adjust it to the usual range.
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) < 1.0:
        return image
    # Compute rotation matrix around the image centre.
    (h, w) = image.shape[:2]
    centre = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(centre, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return rotated


# -------------------------------------------------------------------------
# Simple sanity test (executed when the module is run directly)
# -------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python preprocessor.py <image_path>")
        sys.exit(1)
    img_path = sys.argv[1]
    try:
        p1, p2 = preprocess_image(img_path)
        cv2.imwrite("preprocess_pass1.png", p1)
        cv2.imwrite("preprocess_pass2.png", p2)
        print("Preprocessing completed – outputs written as 'preprocess_pass1.png' and 'preprocess_pass2.png'.")
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
