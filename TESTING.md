# Verification

The public regression suite is self-contained. It must not discover or read
private workspace projects.

## Environment

Create an isolated environment outside the repository if dependencies are not
already installed:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Optional report export:
& .\.venv\Scripts\python.exe -m pip install -r requirements-report.txt
```

The current local acceptance run uses Python 3.14.2. This is a tested
interpreter, not a compatibility guarantee for all Python versions.

## Checks

```powershell
python examples/generate_synthetic_data.py
python -m unittest discover -s tests -v
```

The tests cover manifest mapping, unknown-method fail-closed behavior,
compression strength and modulus regression, flexural recalculation, input
hash preservation, independent-specimen aggregation, and output containment.

The two bounded CLI smoke runs are:

```powershell
python analyze.py --dir examples/synthetic/input/compression `
  --config examples/synthetic/experiment.yaml --kind compression `
  --output run-output/compression --phase2-only
python analyze.py --dir examples/synthetic/input/flexural `
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
