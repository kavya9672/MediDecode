import sys, pathlib, os, json
sys.path.append(r'C:/Users/kavya/OneDrive/Desktop/Automated medicine prescription decoder')

from backend.main import _JOBS, _store_upload, _run_pipeline
from backend.preprocessor import preprocess_image
from backend.ocr_engine import run_dual_pass_ocr
from backend.parser_matcher import parse_prescription

# Create a dummy prescription image with text similar to the mock example
import numpy as np, cv2
img_path = r'C:/Users/kavya/OneDrive/Desktop/Automated medicine prescription decoder/tmp_presc.png'
img = np.zeros((200, 600, 3), dtype=np.uint8)
cv2.putText(img, 'Paracetamol 500 mg Tablet 1 tablet twice daily for 5 days', (5,50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
cv2.imwrite(img_path, img)

# Simulate upload – read file bytes and store
with open(img_path, 'rb') as f:
    content = f.read()
stored_path = _store_upload(content, 'tmp_presc.png')
job_id = 'testjob123'
_JOBS[job_id] = {
    'file_path': stored_path,
    'status': 'uploaded',
    'ocr_result': None,
    'parse_result': None,
    'issues': [],
}
print('Job created')

# Run pipeline directly (synchronous) – this mimics background processing
_run_pipeline(job_id)
print('Job after pipeline:', json.dumps(_JOBS[job_id], indent=2, default=str))

# Extract parsing results
if _JOBS[job_id]['ocr_result']:
    parsed = parse_prescription(_JOBS[job_id]['ocr_result'])
    print('Parsed medicine entries:', parsed)
else:
    print('OCR result missing')

# Cleanup
os.remove(img_path)
