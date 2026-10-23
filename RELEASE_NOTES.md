# v0.2.0-rc.2 — release notes

This candidate adds a Chinese local browser workbench to the existing bounded
compression and rectangular three-point-bending CLI. The processing manifest
and workbench report the same tool version, `0.2.0-rc.2`. The source is licensed
under [MIT](LICENSE).

## Added

- Windows launch and stop scripts, folder and YAML selection, editable method
  parameters and condition labels, and reusable local presets.
- Isolated background analyses, cancellation, logs, history, result tables,
  plot browsing and output downloads. Runs use the existing CLI with a copied
  configuration and a new output directory.
- Per-file error messages in `summary.csv` so failed inputs remain visible in
  the workbench as well as in processing records.

The service uses Python's standard library and the frontend uses local HTML,
CSS and JavaScript. There are no new dependencies. Install the core requirements
before using the launcher; see the [workbench guide](docs/LOCAL_UI.md).

## Fixed

- Empty input folders now produce a clear error before any output is written.
  Earlier output stays intact even when `--overwrite` is supplied.
- Directories whose names end in `.xls` or `.xlsx` are no longer treated as
  data files or specimens. Supported file extensions remain case-insensitive.
- The displayed workbench version now follows the processing-manifest version.
- The launcher uses an explicit interpreter, the source directory's `.venv`,
  or system Python, without depending on a private workspace layout.

Calculation formulas, default numerical settings and the processing-manifest
schema are unchanged from rc.1. The new `error_msg` summary column is additive.

## Verification and scope

The synthetic suite covers the existing numerical cases, input discovery,
configuration preservation, workbench runs, cancellation and local HTTP access.
Acceptance uses an extracted source archive with an existing Windows Python
3.14.2 environment; no dependency installation is implied. See
[TESTING.md](TESTING.md) for commands and boundaries.

The archive contains source, documentation and synthetic examples. It excludes
virtual environments, local presets, run history, logs and private experimental
data. Local workbench state is stored in the ignored `.local-ui/` directory.

Results remain diagnostic calculations. Synthetic acceptance does not establish
standards compliance or experimental validity. Optional Word/PDF export remains
outside the validated workflow.

This file describes a local source candidate. Remote publication is recorded
separately; a candidate version is not evidence of a published tag or release.

## Previous candidate

rc.1 introduced bounded CLI selection, configurable flexural geometry, strict
column/unit checks, synthetic examples and hashed processing manifests. It also
removed the invalid stress/strain fallback when a flexural modulus is unavailable.
Those behaviors and their existing numerical regression cases are retained.
