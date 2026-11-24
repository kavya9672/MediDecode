import sys, pathlib, os
sys.path.append(r'C:/Users/kavya/OneDrive/Desktop/Automated medicine prescription decoder')
from backend.ocr_engine import run_dual_pass_ocr
import numpy as np

# Create a simple black image (no text) – shape must be HxWx3
dummy_img = np.zeros((100, 300, 3), dtype=np.uint8)
# Use the same dummy for both passes
res = run_dual_pass_ocr(dummy_img, dummy_img)
print('Result keys:', list(res.keys()))
print('Pass1 lines count:', len(res['pass1']['lines']))
print('Pass2 lines count:', len(res['pass2']['lines']))
print('Issues:', res['issues'])
