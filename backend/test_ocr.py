import sys, pathlib, os
sys.path.append(r'C:/Users/kavya/OneDrive/Desktop/Automated medicine prescription decoder')
from backend.preprocessor import preprocess_image
from backend.ocr_engine import run_dual_pass_ocr
import numpy as np, cv2

# create a simple image with text
img_path = r'C:/Users/kavya/OneDrive/Desktop/Automated medicine prescription decoder/tmp_test.png'
img = np.zeros((100,300,3), dtype=np.uint8)
cv2.putText(img, 'RX 10MG', (5,50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
cv2.imwrite(img_path, img)

p1, p2 = preprocess_image(img_path)
res = run_dual_pass_ocr(p1, p2)
print('Result keys:', list(res.keys()))
print('Pass1 lines (first 3):', res['pass1']['lines'][:3])
print('Pass2 lines (first 3):', res['pass2']['lines'][:3])
print('Issues (first 5):', res['issues'][:5])
# cleanup
os.remove(img_path)
