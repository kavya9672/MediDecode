import unittest
import os
import json

# Attempt to import requests; if unavailable, define a dummy placeholder.
try:
    import requests
except ImportError:
    requests = None  # offline mode

BASE_URL = 'http://127.0.0.1:8000'

# Helper to conditionally skip tests that require network.
skip_if_no_requests = unittest.skipIf(requests is None, "requests library not available; skipping integration tests.")

# try:\n    import requests\nexcept ImportError:\n    requests = None  # offline mode  # disabled for offline testing

BASE_URL = 'http://127.0.0.1:8000'

def write_test_png():
    data = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mP8z8BQDwADhgG9W5G2fQAAAABJRU5ErkJggg==')
    path = os.path.join('frontend', 'test.png')
    with open(path, 'wb') as f:
        f.write(data)
    return path

def upload_image(path):
    with open(path, 'rb') as f:
        files = {'file': (os.path.basename(path), f, 'image/png')}
        r = requests.post(f'{BASE_URL}/api/upload', files=files)
    return r

def upload_invalid():
    # upload a .txt file
    txt_path = os.path.join('frontend', 'dummy.txt')
    with open(txt_path, 'w') as f:
        f.write('not an image')
    with open(txt_path, 'rb') as f:
        files = {'file': (os.path.basename(txt_path), f, 'text/plain')}
        r = requests.post(f'{BASE_URL}/api/upload', files=files)
    return r

def start_process(job_id):
    r = requests.post(f'{BASE_URL}/api/process', json={'job_id': job_id})
    return r

def poll_progress(job_id, timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f'{BASE_URL}/api/progress/{job_id}')
        if r.status_code != 200:
            return r
        data = r.json()
        if data.get('status') in ('completed', 'error'):
            return r
        time.sleep(2)
    return None

def verify(job_id, payload):
    r = requests.post(f'{BASE_URL}/api/verify', json=payload)
    return r

def analyze(job_id):
    r = requests.post(f'{BASE_URL}/api/analyze', json={'job_id': job_id})
    return r

def compare(job_id):
    r = requests.post(f'{BASE_URL}/api/compare', json={'job_id': job_id})
    return r

def report(job_id):
    r = requests.post(f'{BASE_URL}/api/report', json={'job_id': job_id})
    return r

def main():
    results = {}
    # 1. valid upload
    png_path = write_test_png()
    r = upload_image(png_path)
    results['valid_upload'] = {'status': r.status_code, 'json': r.json() if r.ok else r.text}
    if not r.ok:
        print('Valid upload failed, aborting')
        return
    job_id = r.json()['job_id']
    # 2. invalid upload
    r2 = upload_invalid()
    results['invalid_upload'] = {'status': r2.status_code, 'text': r2.text}
    # 3. start processing
    r3 = start_process(job_id)
    results['start_process'] = {'status': r3.status_code, 'json': r3.json() if r3.ok else r3.text}
    # 4. poll progress
    prog = poll_progress(job_id)
    if prog is None:
        results['poll'] = {'error': 'timeout'}
    else:
        results['poll'] = {'status': prog.status_code, 'json': prog.json()}
    # 5. verify without confirmed flag
    r5 = verify(job_id, {'job_id': job_id, 'medicines': []})
    results['verify_missing_flag'] = {'status': r5.status_code, 'text': r5.text}
    # 6. proper verify (empty list accepted)
    r6 = verify(job_id, {'job_id': job_id, 'confirmed': True, 'medicines': []})
    results['verify_ok'] = {'status': r6.status_code, 'json': r6.json() if r6.ok else r6.text}
    # 7. analyze with no verified meds
    r7 = analyze(job_id)
    results['analyze_no_verified'] = {'status': r7.status_code, 'text': r7.text}
    # 8. compare with no verified meds
    r8 = compare(job_id)
    results['compare_no_verified'] = {'status': r8.status_code, 'text': r8.text}
    # 9. report with no verified meds
    r9 = report(job_id)
    results['report_no_verified'] = {'status': r9.status_code, 'text': r9.text}
    # 10. invalid job id for each endpoint
    fake = 'nonexistent123'
    results['invalid_job_upload'] = 'N/A'  # upload always new
    r10 = start_process(fake)
    results['process_invalid_job'] = {'status': r10.status_code, 'text': r10.text}
    r11 = analyze(fake)
    results['analyze_invalid_job'] = {'status': r11.status_code, 'text': r11.text}
    r12 = compare(fake)
    results['compare_invalid_job'] = {'status': r12.status_code, 'text': r12.text}
    r13 = report(fake)
    results['report_invalid_job'] = {'status': r13.status_code, 'text': r13.text}

    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()
