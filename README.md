# clean_number

`clean_number` is a bounded data-processing pipeline for instrument exports.
The current public candidate supports two explicitly selected methods:

| Method | Required measurement columns | Result |
| --- | --- | --- |
| `compression` | stress and strain | peak supplied stress and a configurable diagnostic chord modulus |
| `flexural` | force and displacement | peak flexural stress and an optional diagnostic modulus |

The flexural calculation currently uses fixed three-point-bending geometry
defaults that can be overridden in `experiment.yaml`. This is an
implementation scope, not a claim of general standards compliance. Other
methods, units, geometries and instrument conventions are outside the supported
matrix until separately validated. See [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md)
and [METHOD_VALIDATION.md](METHOD_VALIDATION.md) for the reviewed mechanics,
measurement assumptions and differences from standardized laboratory methods.

## Install the core pipeline

The verified environment is Windows with Python 3.14.2. From the repository
root, create a local environment and install the core requirements:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The version lower bounds are dependency declarations, not a tested compatibility
matrix. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) records the reviewed
versions and dependency scope. Report export is optional and is outside the
verified first-release workflow.

## Run the synthetic example

The example data are generated, non-experimental fixtures. From this
directory:

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv\Scripts\python.exe analyze.py `
  --dir examples/synthetic/input/compression `
  --config examples/synthetic/experiment.yaml `
  --kind compression `
  --output run-output/compression `
  --phase2-only
& .\.venv\Scripts\python.exe analyze.py `
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

Each completed run also writes `processing_manifest.json` below the explicit
output directory. It binds the logical input filenames and raw hashes to the
effective configuration, per-file processing status, and output hashes. A
failed input is kept in the manifest and makes the CLI exit non-zero; it is not
silently hidden by a successful batch summary.

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

The manifest may also declare method settings under `methods`. The public
candidate currently accepts only `compression` and `flexural`. Required
measurement columns, chord-modulus fractions, and rectangular three-point
bending geometry are explicit there. Missing required columns, unknown units,
or duplicate semantic columns fail closed instead of being guessed.

Raw files are never rewritten. Processing overrides, when needed, are
explicit, file-specific and auditable in `processing_overrides.yaml` beside
the project manifest. Duplicate content is marked in the ledger and is not
silently removed.

## Development status

As reviewed on 2026-09-25, this is an independent local candidate with a bounded
CLI, configurable compression/flexural calculations, synthetic regression tests
and versioned processing manifests. A separate mining-research-kernel adapter
has been implemented and historically tested for manifest inspection and
registration; installing this tool does not require that kernel.

A bounded private comparison was completed separately. Its data, configuration,
results and ledger are not public fixtures and do not establish method validity.
The public examples remain synthetic-only.

The method/source review and dependency inventory are available in
[METHOD_VALIDATION.md](METHOD_VALIDATION.md), [PROVENANCE.md](PROVENANCE.md)
and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). See
[RELEASE_NOTES.md](RELEASE_NOTES.md) for the unpublished candidate changes.
The project license and source-rights confirmation remain undecided. No remote
publication or standards-compliance approval is implied by this candidate.
Do not redistribute until the owner has resolved those publication gates.
