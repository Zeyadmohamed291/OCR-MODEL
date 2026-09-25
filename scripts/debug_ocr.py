import os
import sys

# Auto-relaunch inside virtualenv if executed with global python
_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_venv_python = os.path.join(_root_dir, "venv", "Scripts", "python.exe")
if os.path.exists(_venv_python) and os.path.abspath(sys.executable).lower() != os.path.abspath(_venv_python).lower():
    import subprocess
    sys.exit(subprocess.run([_venv_python] + sys.argv).returncode)

import cv2

# Fix Windows console UTF-8 encoding for Arabic characters
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure app can be imported
sys.path.append(_root_dir)

from app.infrastructure.ocr.easyocr_engine import EasyOCREngine

print("--- EasyOCR Engine Initialization Debug ---")
try:
    engine = EasyOCREngine()
    print("Engine initialized successfully.")
    print("Reader languages:", getattr(engine.reader, "lang_list", ["ar", "en"]))
    print("Device used (CPU/GPU):", getattr(engine.reader, "device", "cpu"))
except Exception as e:
    print("Error initializing EasyOCR engine:", e)
    sys.exit(1)

print("\n--- Running OCR on test images ---")
test_images = [
    os.path.join(_root_dir, "tests", "ARABIC.jpg"),
    os.path.join(_root_dir, "tests", "ENGLISH.webp"),
    os.path.join(_root_dir, "tests", "test_id.jpg"),
]

for image_path in test_images:
    if not os.path.exists(image_path):
        print(f"Skipping {image_path}: File not found.")
        continue

    print(f"\nProcessing: {os.path.basename(image_path)}")
    image = cv2.imread(image_path)
    if image is None:
        print(f"Error: Could not read image {image_path}")
        continue

    result = engine.process_image(image)
    print(f"Detected {len(result.blocks)} blocks in {result.total_time_ms:.2f} ms (Avg Conf: {result.average_confidence:.4f})")
    for idx, block in enumerate(result.blocks):
        print(f"  [{idx}] Text=\"{block.text}\" | Conf={block.confidence:.4f}")
