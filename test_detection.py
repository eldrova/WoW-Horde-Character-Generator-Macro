"""Detection tests on the reference screenshots. Run: python test_detection.py"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wow_finish_macro import analyze, annotate, fmt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = [  # (file, finish, okay, disconnected)
    ("samples/finish_active.webp", True, False, False),
    ("samples/okay_popup.webp", False, True, False),
    ("samples/disconnected.webp", False, False, True),
]

failed = 0
for rel, want_finish, want_okay, want_dc in CASES:
    img = np.asarray(Image.open(os.path.join(HERE, rel)).convert("RGB"))
    s = analyze(img)
    ok = s["finish"] == want_finish and s["okay"] == want_okay and s["disconnected"] == want_dc
    failed += not ok
    print(("PASS" if ok else "FAIL"), rel, "->", fmt(s))
    annotate(img, s, os.path.join(HERE, "samples", os.path.basename(rel).replace(".webp", "_annotated.png")))

sys.exit(1 if failed else 0)
