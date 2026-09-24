# Unpublished candidate changes

This is a release-note draft, not an announcement or a published version.
The processing-manifest tool version remains `0.2.0-candidate` until the owner
selects a release version. No project license has been granted by this file.

## Included

- Explicit input, configuration, output and method selection for the bounded
  compression and rectangular three-point-bending CLI.
- Configurable geometry and diagnostic chord intervals, strict required-column
  and unit checks, and synthetic examples generated from known numerical curves.
- Processing manifests with input/configuration/output hashes and per-file
  status, for inspection and registration by a separate kernel adapter.
- Mechanics references, standards differences, source provenance and a bounded
  dependency/notice review.

## Corrected during the method review

When an early peak leaves insufficient samples for the flexural modulus, the
old code could fall back to a generic stress/strain calculation with displacement
incorrectly treated as percent strain. That fallback is removed. The modulus
now remains missing in both the result and plot, while a valid peak stress can
still be reported. The synthetic regression suite covers this case and checks
normal flexural moduli at two spans.

Logging no longer asserts that every instrument stress channel is erroneous.
The configured beam formula is described as a recalculation, and compression
chord logging uses the configured interval. The unused WeasyPrint requirement
was removed from the optional report dependency list.

## Limits

Only synthetic fixtures are distributed. Results are diagnostic calculations,
not standards-conforming test reports or material-validity conclusions.
Instrument interpretation, specimen applicability and experimental acceptance
remain the user's laboratory responsibilities; see [METHOD_VALIDATION.md](METHOD_VALIDATION.md).
Optional DOCX/PDF export is not included in the validated release workflow.
Source-rights confirmation, project licensing and explicit publication
authorization remain open before release.
