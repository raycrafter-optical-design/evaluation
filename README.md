# evaluation

How well do [Optiland](https://github.com/optiland/optiland) and
[RayCrafter](https://github.com/raycrafter-optical-design/raycrafter) reproduce Zemax OpticStudio?
One folder per design, one generated HTML summary per design, and a landing page that lists them.
The pages are served by GitHub Pages from the repository root.

```
designs/<name>/
  *.ZMX, *.ZDA             the design as exported by Zemax
  design.json              name, summary, wavelengths (feeds the landing page)
  comparison.json          rows of the Zemax-vs-Optiland verdict table, with tolerances
  Zemax_reference_output/  what Optiland must match (README inside)
  optiland_analysis/       our best attempt: png, csv, json, glb (README inside)
  HTML_summary/            template.html (design-specific text) and generated index.html
evaluation_tools/          analysis and page-building code
```

## Run

```
export UV_PROJECT_ENVIRONMENT=~/uv_venvs/evaluation_mac   # venv outside Dropbox
uv sync --extra dev
uv run python -m evaluation_tools.analyze designs/SMOD4.5      # about 2 minutes
uv run python -m evaluation_tools.build_summary                # all pages
python3 -m http.server                                         # preview at http://localhost:8000
```

The generated HTML is committed, so Pages needs no build step. See `CLAUDE.md` for conventions and
`optiland_issues_found.md` for the Optiland problems found so far.

## Visit the site
The [evaluation site lives here](https://raycrafter-optical-design.github.io/evaluation/)
