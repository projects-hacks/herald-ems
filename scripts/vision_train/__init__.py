"""Training photos for Herald's vision model (docs/MODEL_PLAN.md §2a "Vision training set").

Separate from the test photos in eval/photos/ by design: its own renderers, layouts and text, and a
decontamination check (decontam.py) against eval/photos/gold.jsonl. Build: `python scripts/vision_train/make.py`.
"""
