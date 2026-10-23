# Verification

The public regression suite is self-contained. It must not discover or read
private workspace projects.

## Environment

Create an isolated environment in the ignored `.venv/` directory if dependencies
are not already installed:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Optional report export:
& .\.venv\Scripts\python.exe -m pip install -r requirements-report.txt
```

The rc.2 local source-archive acceptance uses an existing Windows Python 3.14.2
environment with the core dependencies. It checks the extracted archive rather
than relying on untracked files in a developer checkout. This is not a fresh
dependency installation or a compatibility guarantee for all Python versions.

## Checks

```powershell
& .\.venv\Scripts\python.exe examples/generate_synthetic_data.py
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover manifest mapping, processing-manifest generation,
unknown-method fail-closed behavior, compression strength and modulus
regression, configurable flexural geometry, missing-column and unit fail-closed
cases, millisecond-vs-second unit handling, duplicate semantic column detection,
input hash preservation, independent-specimen aggregation, and output
containment. The core suite also checks independently calculated flexural
moduli for two spans and an early-peak curve whose unavailable modulus must
stay missing in both the result and plot inputs.

The eight input-validation tests in `tests/test_input_validation.py` check
case-insensitive file discovery, exclusion of suffix-matching directories from
processing and grouping, rejection of empty inputs before writing output,
preservation of previous output even with `--overwrite`, and bounded CLI
processing with a matching processing manifest. These tests use only synthetic
fixtures and temporary directories.

The local workbench adds 10 tests in `tests/test_local_ui.py`: input inspection,
neutral condition mapping for a new folder, lossless preset configuration,
invalid numeric settings, protected output locations, compression/flexural CLI
end-to-end runs, per-file failure visibility, cancellation, and HTTP session/
origin enforcement. The HTTP test needs permission to connect to loopback.
All inputs remain synthetic and all outputs use temporary directories.

Browser acceptance separately exercises folder/config browsing, presets,
form edits, run status, result tables, plots, history, and narrow layouts.
The earlier browser layout acceptance is historical. Source-archive acceptance
checks the launcher, local API, shared version and synthetic CLI outputs;
it does not imply a new visual review of every browser interaction.

To check a downloaded source archive, extract it to a new directory, create
`.venv` there (or select an existing environment with the core requirements),
then run the tests and examples from that directory. For a launcher check
without opening the browser:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-CleanNumber.ps1 `
  -Python (Resolve-Path .\.venv\Scripts\python.exe).Path -NoBrowser
# Run again to check reuse of the same local service, then stop it:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Stop-CleanNumber.ps1
```

The scripts do not install packages, and stopping the service preserves outputs.

The two bounded CLI smoke runs are:

```powershell
& .\.venv\Scripts\python.exe analyze.py --dir examples/synthetic/input/compression `
  --config examples/synthetic/experiment.yaml --kind compression `
  --output run-output/compression --phase2-only
& .\.venv\Scripts\python.exe analyze.py --dir examples/synthetic/input/flexural `
  --config examples/synthetic/experiment.yaml --kind flexural `
  --output run-output/flexural --phase2-only
```

Inspect `summary.csv`, `tables/`, and `experiment_manifest.sha256` below each
output directory. Do not point these commands at private data as part of the
public regression suite, and do not use the old private test commands from the
archived candidate baseline.

## Acceptance boundary

Passing these checks demonstrates that the candidate runs in the tested local
environment and that the documented synthetic calculations are reproducible.
It does not establish method validity, standards compliance, statistical
adequacy, engineering safety, real-sample equivalence, kernel integration or
publication readiness.
