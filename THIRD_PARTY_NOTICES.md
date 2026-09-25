# Third-party notices

This file records the dependency and notice review for the current `clean_number` candidate. It is an evidence-based inventory for review and release preparation. It is not a complete SBOM, a legal opinion, or a declaration that project redistribution is compliant.

The project source uses the [MIT License](LICENSE), selected by the maintainer on 2026-09-25. Dependencies retain their own licenses; the project license does not replace their terms.

## Review method

Reviewed 2026-09-25. Direct dependencies were mapped from imports in the candidate Python files to `requirements.txt` and `requirements-report.txt`. Installed versions and package metadata were read locally with `importlib.metadata` from the designated isolated environment. Absent optional packages were checked against official PyPI metadata, without installation or runtime acceptance. License names below reproduce the package metadata classifier, SPDX expression, or the package's included license file where the available evidence supported that label.

## Declared direct dependencies

| Package | Use in this repository | Declared requirement | Installed version in review environment | Latest published version checked | License evidence | Unverified or boundary item |
| --- | --- | --- | --- | --- | --- | --- |
| NumPy | Numeric arrays and calculations | `numpy>=1.24` | 2.5.3 | Not checked as a new web release | `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` in installed metadata | The expression covers bundled components; exact release wheel still needs review. |
| pandas | Tabular input, transformation, and output | `pandas>=2.0` | 3.0.6 | Not checked as a new web release | BSD License classifier and installed `LICENSE` file | Exact bundled components are environment-specific. |
| Matplotlib | Plotting and figure output | `matplotlib>=3.7` | 3.11.2 | Not checked as a new web release | Matplotlib License classifier and installed `LICENSE` file | The package license includes additional bundled notices; preserve the package notice for redistribution. |
| SciPy | Statistical calculations | `scipy>=1.10` | 1.18.1 | Not checked as a new web release | BSD License classifier and installed `LICENSE.txt` file | Compiled and bundled components need review for the exact wheel. |
| PyYAML | YAML configuration and manifest parsing | `PyYAML>=6.0` | 6.0.3 | Not checked as a new web release | MIT License classifier in installed metadata | No standalone license file was found in the inspected dist-info directory. |
| openpyxl | XLSX reading and report tables | `openpyxl>=3.1` | 3.1.5 | Not checked as a new web release | MIT License classifier in installed metadata | `et-xmlfile` is an installed transitive dependency. |
| xlrd | Legacy XLS reading | `xlrd>=2.0` | 2.0.2 | Not checked as a new web release | BSD License classifier and installed `LICENSE` file | None identified from the local package evidence. |
| Python-Markdown | Markdown to HTML in optional report export | `markdown>=3.5` | Not installed | [3.10.3](https://pypi.org/project/Markdown/) | BSD-3-Clause in official PyPI metadata | Official metadata and published release checked only; not installed or run. |
| python-docx | Optional DOCX report export | `python-docx>=1.1` | Not installed | [1.2.0](https://pypi.org/project/python-docx/) | MIT License in official PyPI metadata | Official metadata and published release checked only; not installed or run. |
| ReportLab | Optional PDF report export | `reportlab>=4.0` | Not installed | [5.0.1](https://pypi.org/project/reportlab/) | BSD License; PyPI points to the package `license.txt` | Official metadata and published release checked only; not installed or run. |
| lxml | Optional DOCX XML handling | `lxml>=4.9` | Not installed | [6.1.3](https://pypi.org/project/lxml/) | BSD-3-Clause in official PyPI metadata | Official metadata and published release checked only; not installed or run. Native libxml2/libxslt notices remain artifact-specific. |

The core imports map to the seven core requirements. The report imports map to Markdown, python-docx, ReportLab, and lxml. Standard-library imports and the repository's own modules do not require third-party notices. `weasyprint` was previously the sole repository reference and has now been removed from `requirements-report.txt` as an unused dependency. It is not part of this dependency inventory.

## Installed transitive packages observed

These packages were present in the designated review environment as dependencies of the installed stack. This is a bounded notice list, not a claim that it describes every possible installation or every dependency of every optional extra.

| Package | Observed version | License evidence | Relationship |
| --- | --- | --- | --- |
| contourpy | 1.4.0 | BSD-3-Clause in metadata | Matplotlib dependency |
| cycler | 0.12.1 | BSD License classifier | Matplotlib dependency |
| et-xmlfile | 2.0.0 | MIT License classifier | openpyxl dependency |
| fonttools | 4.65.0 | Package-internal `licenses/LICENSE` is MIT; `licenses/LICENSE.external` records SIL Open Font License 1.1 test fonts | Matplotlib dependency; preserve both package license files when redistributing the exact package artifact |
| kiwisolver | 1.5.1 | BSD License classifier | Matplotlib dependency |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause in metadata | Matplotlib dependency |
| Pillow | 12.3.0 | MIT-CMU in metadata | Matplotlib dependency |
| pyparsing | 3.3.2 | MIT in metadata | Matplotlib dependency |
| python-dateutil | 2.9.0.post0 | BSD License classifier | pandas and Matplotlib dependency |
| six | 1.17.0 | MIT License classifier | python-dateutil dependency |
| tzdata | 2026.4 | Apache-2.0 in metadata | pandas dependency on Windows |

The installed environment also contained compiled package payloads such as NumPy, pandas, and SciPy native libraries. No such binary payload is committed in this candidate. Their notices are governed by the exact package distributions and build artifacts used for a release; this document does not attempt to enumerate every bundled system library, font, browser, or operating-system component.

## Official sources checked for optional dependencies

The following official PyPI project pages were checked for the latest published version and license metadata. These checks are source and official-metadata checks only; the packages were not installed or run in this review: [Python-Markdown](https://pypi.org/project/Markdown/), [python-docx](https://pypi.org/project/python-docx/), [ReportLab](https://pypi.org/project/reportlab/), and [lxml](https://pypi.org/project/lxml/).

## Required follow-up before publication

- Preserve the project license and source attribution; see [PROVENANCE.md](PROVENANCE.md).
- Preserve the license and notice files for every exact dependency artifact selected for release, including transitive and bundled components.
- The source-only first-release boundary does not require installing or running the optional report stack. Optional report support has not passed runtime acceptance. If report export is enabled later, pin or identify the exact stack and preserve its notices.
- `weasyprint` was removed from `requirements-report.txt` after repository-wide review found no code or subprocess use. It is excluded from the current dependency set.
- Regenerate this notice record from the final locked environment or release artifacts. The versions observed here are evidence for the review environment, not a lockfile.
