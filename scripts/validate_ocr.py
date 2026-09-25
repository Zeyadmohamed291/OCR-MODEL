import os
import sys

# Auto-relaunch inside virtualenv if executed with global python
_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_venv_python = os.path.join(_root_dir, "venv", "Scripts", "python.exe")
if os.path.exists(_venv_python) and os.path.abspath(sys.executable).lower() != os.path.abspath(_venv_python).lower():
    import subprocess
    sys.exit(subprocess.run([_venv_python] + sys.argv).returncode)

import json

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
import cv2

def run_validation():
    print("Initializing EasyOCR Engine...")
    engine = EasyOCREngine()
    
    test_dir = os.path.join(_root_dir, 'tests')
    images = ['ENGLISH.webp', 'ARABIC.jpg', 'arabic3.jpeg', 'test_id.jpg']
    
    for img_name in images:
        img_path = os.path.join(test_dir, img_name)
        if not os.path.exists(img_path):
            print(f"Skipping {img_name}: File not found.")
            continue
            
        print(f"\n{'='*50}\nTesting Image: {img_name}\n{'='*50}")
        image = cv2.imread(img_path)
        if image is None:
            print(f"Failed to read image {img_name}")
            continue
            
        result = engine.process_image(image)
        
        # We need to test the extraction logic as well
        from app.services.structured_extraction import extract_id_fields
        text_str = "\n".join([b.text for b in result.blocks])
        fields = extract_id_fields(text_str)
        
        print(f"Found {len(result.blocks)} text blocks.")
        print(f"Average Confidence: {result.average_confidence:.4f}")
        print(f"Total Time: {result.total_time_ms:.2f} ms")
        
        print("\nExtracted Fields:")
        print(json.dumps(fields, indent=2, ensure_ascii=False))
        
        print("\nText Blocks:")
        for idx, b in enumerate(result.blocks):
            print(f"  [{idx}] {b.text} (Conf: {b.confidence:.2f})")

if __name__ == "__main__":
    run_validation()
