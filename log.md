# Decision log

## 2026-11-25: Evaluation as its own repo with committed HTML summaries
**Decision:** Evidence for Optiland/RayCrafter vs Zemax lives in this repo, one folder per design. A Python script generates each design's HTML summary and the landing page; the output is committed and served by GitHub Pages from the root.
**Why:** The two Claude Artifacts would pollute Rob's account as designs accumulate; the repo should hold the ground truth. Committed output means Pages needs no build step (as in RayCrafter-docs). Hand-written HTML rejected because numbers would drift from the data.
