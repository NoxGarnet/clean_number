# Provenance and redistribution review

This document records the source review for the `clean_number` public candidate. It is a provenance record, not a legal opinion, a copyright determination, or a statement that redistribution is authorized.

## Scope and review basis

The review covered the three candidate commits listed below, the separate local Git history in which the original `clean_number` implementation was introduced, the candidate source tree, the two requirements files, and the imports used by the Python files. The review did not run the data pipeline, inspect private experimental material, alter source data, install packages, or publish anything.

The source provenance trace is reviewed through candidate commit `35c68219590af18b085e28b1bb8e84ae1c2facd8`. The method fixes and documentation updates from this review are recorded in subsequent Git history, including the commit containing this file, and can be verified from the repository history.

The candidate history is:

| Commit | Date | Review-relevant change |
| --- | --- | --- |
| `d3102aa77dc2a113e5f8c0a297ec38fad840cbf7` | 2026-09-16 | Added the bounded public candidate, synthetic fixtures, tests, and dependency declarations. |
| `44ba1e12e650aad5dee0621fe9e2f39df2beab3c` | 2026-09-18 | Generalized the selected compression and flexural methods and tightened the public support profile. |
| `35c68219590af18b085e28b1bb8e84ae1c2facd8` | 2026-09-18 | Added processing-manifest generation and related tests. |

The original implementation was found in a separate local Git history that introduced a `clean_number` source tree. No private baseline commit identifier or public upstream URL is asserted here. The local history is evidence of source relationship, not evidence that redistribution rights were granted.

The relationship is source derivation and adaptation, not a clean-room reimplementation. At review time, these candidate files were byte-identical to files in that original working tree: `analysis_units.py`, `md_to_pdf.py`, `processing_overrides.py`, `report_builder.py`, and `stats_plotter.py`. The other overlapping implementation files differed, reflecting public-boundary changes and later candidate work. The candidate also adds synthetic fixtures, tests, support documentation, and manifest code.

## Rights and source findings

No project `LICENSE`, `COPYING`, or `NOTICE` file was present in the candidate tree. No source-file copyright or license header was found during the review. The candidate README explicitly says that its license is undecided and that redistribution should wait for a provenance review.

The reviewed Git records identify the source history, but they do not by themselves prove that the person or organization with authority over the original implementation granted permission to redistribute the adapted candidate. The source author or rights holder must confirm the rights chain before publication. This remains unresolved.

The public candidate contains generated, non-experimental fixture files under `examples/synthetic/`; they are described in the repository documentation as generated fixtures. No private sample data or private experiment name is relied on by this provenance record. The repository contains no packaged `.dll`, `.pyd`, `.so`, `.dylib`, or `.exe` artifact at review time.

## Current first-release boundary

The intended first release contains only the core CLI source and synthetic fixtures. Users install the core dependencies themselves, and the project does not bundle wheels, native libraries, browsers, fonts, optional report dependencies, or other binary artifacts. Optional report support is outside the first-release acceptance scope and has not passed runtime acceptance. This boundary does not remove the source-rights or project-license block described below.

For a source-only release, publication remains blocked until the rights holder confirms the source rights and the responsible owner selects and applies a project license. The dependency records here support review but do not establish legal clearance.

Packaging binaries or enabling optional report export creates additional work. The release must then preserve notices for the exact locked wheels and their bundled native components, review platform libraries and fonts, and review the exact browser or document-export artifact used. Optional report dependencies must be pinned or otherwise identified and their official notices included, followed by runtime acceptance. Those requirements do not apply to the current core CLI plus synthetic-fixtures boundary, but they are required before a binary or report-enabled distribution is claimed ready.

## Public-release constraints

This candidate has no selected project license. The provenance review therefore does not choose one and does not grant any license. Do not describe the project as legally cleared or redistribute it until the rights holder confirms the source rights and a project license decision is made by the responsible owner.

The dependency notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) cover the declared Python dependencies and the installed dependency evidence available in the review environment. They are not a complete SBOM. A release built from a different lockfile, wheel set, operating-system package, browser, font, or other binary distribution needs a fresh notice review for those exact artifacts.

## Open items for the owner

1. Confirm the rights holder and written permission or other documented basis for redistributing the original implementation and this adaptation.
2. Decide and apply a project license after that rights confirmation; this review intentionally leaves the choice open.
3. If optional reports or binary artifacts are added later, identify the exact stack and record its versions and notices.
4. Recheck bundled binary and platform-level notices for those exact release artifacts, including any browser or font used by document export.
