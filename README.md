# clean_number

`clean_number` is a bounded data-processing pipeline for instrument exports.
The current public candidate supports two explicitly selected methods:

| Method | Required measurement columns | Result |
| --- | --- | --- |
| `compression` | force or stress, plus strain when modulus is required | peak stress and a 10%–40% chord modulus |
| `flexural` | force and displacement | peak flexural stress and an optional diagnostic modulus |

The flexural calculation currently uses fixed three-point-bending geometry
constants in `process_single.py`. This is an implementation scope, not a
claim of general standards compliance. Other methods, units, geometries and
instrument conventions are outside the supported matrix until separately
validated.

## Run the synthetic example

The example data are generated, non-experimental fixtures. From this
directory:

```powershell
python examples/generate_synthetic_data.py
python -m unittest discover -s tests -v
python analyze.py `
  --dir examples/synthetic/input/compression `
  --config examples/synthetic/experiment.yaml `
  --kind compression `
  --output run-output/compression `
  --phase2-only
python analyze.py `
  --dir examples/synthetic/input/flexural `
  --config examples/synthetic/experiment.yaml `
  --kind flexural `
  --output run-output/flexural `
  --phase2-only
```

Every run requires an explicit output directory. The command reads only the
requested input directory and writes its per-run ledger and tables below that
directory. It does not search sibling projects or create a cross-run summary.
Use `--no-plot` to omit figures. Report export is optional; install
`requirements-report.txt` when needed. Visual document QA is not part of this
candidate's acceptance claim.

## Input and configuration

The reader accepts ordinary Excel files when the corresponding engine is
installed. It also accepts the tab-separated text form used by the synthetic
fixtures: one metadata row, then a header row. Column matching is deliberately
limited to the documented measurement names (`力`, `应力`, `应变`, `变形`,
`时间` and their unit-bearing variants).

Use an `experiment.yaml` beside the input or pass `--config` explicitly.
Conditions must be registered in `condition_mapping`; unknown conditions fail
instead of falling back to a guessed group. The filename parser handles the
documented `d{age}{condition}{specimen}-{end}` compression form and the
corresponding flexural forms.

Raw files are never rewritten. Processing overrides, when needed, are
explicit, file-specific and auditable in `processing_overrides.yaml` beside
the project manifest. Duplicate content is marked in the ledger and is not
silently removed.

## Development status

This directory is an independent local candidate, not a published release.
The first implementation batch covers the public-boundary audit, isolated
synthetic regression and bounded CLI path. Mining-research-kernel registration,
private sample comparison, licensing, remote repository creation and release
publication are separate gates and are not performed by these commands.

The license is intentionally undecided in this candidate. Do not redistribute
it until a license and provenance review have been completed.
