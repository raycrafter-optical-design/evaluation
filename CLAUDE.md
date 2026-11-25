# evaluation: instructions for coding agents (and humans)

This repository holds the evidence for how well Optiland, and then RayCrafter, reproduce Zemax
OpticStudio, one optical design at a time. It is a support repository for RayCrafter. The code
is written mainly by coding agents, but it must be readable and maintainable by people who use
little or no AI. The generated HTML summaries are served by GitHub Pages from the repo root.


# Layout

```
index.html, style.css      landing page (generated) and the shared style
evaluation_tools/          load_system.py, analyze.py, build_summary.py, repro_*.py
designs/<name>/
  *.ZMX, *.ZDA             the design exactly as exported by Zemax
  design.json              name, description, wavelengths, summary status (feeds the landing page)
  Zemax_reference_output/  what Optiland must match; ground truth; never edit
  optiland_analysis/       our best attempt to match it: png, csv, json, glb, with a README.md
  HTML_summary/index.html  generated page for this design
```


# Rules

- **Zemax reference files are ground truth.** Never edit or regenerate them. Values read off a
  plot (digitised) are labelled as such wherever they are shown.
- **Tables, charts and chips come from files** in `optiland_analysis/` or
  `Zemax_reference_output/`. Do not type results into them. Explanatory prose in a design's
  `template.html` may quote numbers; re-check them when the analysis is re-run. Status chips (match / partial /
  fail) are computed by `build_summary.py` from `comparison.json` tolerances.
- **Descriptive file names** in `optiland_analysis/`, and keep its README.md listing every file.
- **Generated HTML is committed.** After changing analysis output or the template, run
  `build_summary.py` and commit the result. CI does not build anything.
- **Optiland** is pinned to the same minor version as RayCrafter. Local workarounds live only in
  `load_system.py`, each with a comment linking the upstream issue. Every problem found goes in
  `optiland_issues_found.md`; RayCrafter's `optiland_fix.md` tracks fixes it waits for.
- **Adding a design:** make `designs/<name>/`, drop in the ZMX/ZDA and Zemax reference output,
  write `design.json`, run `analyze.py designs/<name>`, then `build_summary.py`.
- **RayCrafter** is pointed at a design folder here and compared with `Zemax_reference_output/`.
  Only designs that largely work in Optiland are worth processing in RayCrafter.
- The page style matches the original Artifacts (IBM Plex, teal accent, white figure plates,
  light and dark), not the RayCrafter docs site.
- Files under about 1000 lines.


# Code style

- Use descriptive variable names; avoid abbreviations that a newcomer would have to guess.
- Use white space well, including blank lines between functions and between logical blocks.
- Aim for lines of at most 100 chars. Up to 120 is allowed where it helps readability.
- Every public module, class and function gets a docstring in the NumPy style.
- Add type hints to public functions and methods.
- Where the intent of a piece of code is not obvious (physics, Optiland workarounds), explain it
  in a comment. Physical units go in names or comments (`_mm`, `_um`, degrees, waves).
- Once a feature is complete, remove any dead code.


# Tests

- Run them with `uv run pytest`. `tests/test_unit` uses small synthetic data and needs no Zemax
  files. A bug fix comes with a test that would have caught the bug.


# Workflow

- Work directly on `main`. Use a branch and pull request only for risky or experimental work.
- Before committing, run `uv run pre-commit run --all-files` and `uv run pytest`.
- Use GitHub issues for substantial bugs and design questions. Reference them in commits.
- Small changes may be committed and pushed without asking. Ask Rob before creating the GitHub
  repo, changing Pages settings, adding a design, or deleting anything published (including
  Claude Artifacts).
- Expect that people may have changed files you recently worked on. Re-read a file before
  modifying it.


# Environment

- Use `uv`. The virtual environment lives **outside Dropbox**, because a venv cannot be shared
  between machines or operating systems. On the Mac, run:
  `export UV_PROJECT_ENVIRONMENT=~/uv_venvs/evaluation_mac` and then `uv sync --extra dev`.
- `uv.lock` is committed so that every developer gets the same environment.
- `rm` and `mv` are aliased to interactive versions on Rob's machines, so use `rm -f` / `mv -f`.


# Decision log (`log.md`)

`log.md` records significant decisions and why they were made. Keep it short.

- **Before starting work**, search the log for the topic, e.g. `grep -n -i -A6 "strehl" log.md`.
- **Add an entry** for a decision someone might later ask "why?" about. Do not log routine work.
- **Append only.** If a decision is reversed, add an entry saying which one it supersedes.
- **Format.** Each entry is at most about 8 lines:

  ```
  ## YYYY-MM-DD: Short title
  **Decision:** what was decided.
  **Why:** the reason, including alternatives rejected.
  **Supersedes:** (optional) the date and title of the earlier entry.
  ```
- Ask Rob before logging a decision that he has not made or agreed to.
