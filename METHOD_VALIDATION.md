# Method review and calculation boundaries

Reviewed 2026-09-25. This is a source-backed review of the implemented
calculations, not certification of a laboratory method or any material.

## Review outcome

The rectangular center-loaded beam equations have a traceable mechanics
basis. The default 10%-40% chord interval and origin detection are software
choices, not a verified standards procedure. Outputs remain diagnostic until
the experiment's geometry, measurement channels, calibration, loading history
and applicable method have been independently accepted.

The public examples are generated numerical fixtures. In particular, their
100 mm span and 40 mm depth give a span/depth ratio of 2.5; they establish
arithmetic regression, not slender-beam suitability or realistic material data.

## Compression

`process_single.extract_properties` takes the maximum supplied stress after
configured truncation and origin cropping. It does not calculate stress from
force and measured area or verify the instrument's area setting.

Before the first peak, the implementation selects the measured points nearest
the configured lower and upper fractions of peak stress (defaults 0.10 and
0.40). It uses actual selected stresses and strains, without interpolation,
cycle separation, curve fitting or an independent linearity check:

```text
E_GPa = (stress_upper_MPa - stress_lower_MPa)
        / ((strain_upper_pct - strain_lower_pct) / 100) / 1000
```

For the generated control curve, 10 MPa per 0.1 percentage-point strain gives
10 GPa. This is an independent unit/scale check; it does not validate the
physical origin of the strain channel. A percent label alone cannot establish
that the instrument measured specimen strain instead of converting crosshead
travel with an unsuitable gauge length.

ASTM's public [C469/C469M-22 catalogue][c469] describes concrete cylinders and
cores, and identifies a working range up to 40% of ultimate strength. Only the
catalogue scope was reviewed; the paid standard text was not obtained.

The University of Texas [FSEL procedure, revision 0][fsel], sections 5.8-5.10,
uses a seating cycle followed by two measurement cycles, a lower observation
near 50 microstrain and an upper observation near 40% of measured strength.
It references C469-10, not C469/C469M-22. Our comparison shows a substantive
difference from the program's default 10%-40% single-curve chord. It is not
evidence that the current ASTM standard has been implemented.

## Rectangular three-point bending

The boundary conditions are two simple supports and a central point load on a
rectangular section. With force F, span L, width b and depth h, statics gives
maximum moment FL/4. Using section inertia bh^3/12 and outer-fibre distance
h/2 in the flexure relation gives the implemented nominal stress:

```text
stress_MPa = 3 * F_kN * 1000 * L_mm / (2 * b_mm * h_mm^2)
```

The flexure relation and rectangular inertia are explained in [MIT mechanics
notes][mit-stress], PDF page 7. [MIT's beam discussion][mit-deflection], PDF
pages 6-7, supplies the central-load moment and homogeneous-beam deflection
F*L^3/(48*E*I). Substitution yields the diagnostic modulus used here:

```text
E_GPa = L_mm^3 / (4 * b_mm * h_mm^3) * delta_F_kN / delta_deflection_mm
```

The kN-to-N and MPa-to-GPa factors cancel in the second expression. For the
generated treated curve, the slope is 120 kN/mm. A 100-by-40-by-40 mm
span/width/depth gives 11.71875 GPa; changing only the span to 80 mm gives
6 GPa. Peak stresses are respectively 168.75 and 135 MPa. These constants
are asserted by the public tests without using the implementation to compute
their expected values.

This interpretation assumes small deflection, an appropriate elastic beam
regime, and specimen mid-span deflection relative to the supports. The code
does not correct machine compliance, support settlement, indentation or shear
deflection; nor does it verify these assumptions from a column labelled mm.
Crosshead movement alone is insufficient evidence of specimen deflection.

The chord uses the configured force fractions and nearest pre-peak samples.
An unavailable flexural modulus stays `None` (blank in CSV) and is omitted
from the plot. It never falls back to treating displacement as percent strain.
The log identifies insufficient pre-peak points, an unordered interval or a
displacement increment below 1e-6 mm as possible causes. A valid peak stress
can still be returned with file status `ok`; that status does not mean a
modulus was available or physically validated.

The [ASTM C293/C293M-16 catalogue][c293] identifies center-point loading,
states that it is not an alternative to C78/C78M, and marks it withdrawn in
2025 with no replacement. It is included here only to distinguish loading
methods and historical scope, not as a current compliance basis. Third-point
loading is outside this implementation.

## Processing and reporting limits

- Origin detection searches for a sustained positive strain/displacement
  segment, then can fall back to a force threshold. Cropping can change which
  peak survives; it is a processing heuristic, not a calibrated zero correction.
- Subtracting a constant strain/displacement offset leaves a chord difference
  unchanged, but does not correct machine compliance or a wrong gauge length.
- Sparse, noisy, cyclic or nonmonotone curves can select unsuitable chord
  endpoints. The code does not establish a material's elastic interval.
- Group statistics require a correct independent-specimen mapping. Processing
  success, duplicate marking and quality scores do not establish sample
  independence or scientific validity.
- DOCX/PDF report wording and layout are outside current acceptance. Use the
  documented `--phase2-only` commands; do not infer report certification.

## Remaining acceptance boundary

The mechanics/source review is complete for this bounded diagnostic scope.
A standards-conforming or material-valid result still requires an applicable
standard and version, specimen/geometry evidence, instrument-channel and
calibration evidence, and method-specific experimental acceptance. This review
does not change any historical private result or authorize publication.

## Sources actually consulted

All links were read on 2026-09-25. The descriptions above are summaries and
our derivations; no standard text or teaching figures are redistributed.

[c469]: https://store.astm.org/c0469_c0469m-22.html
[c293]: https://store.astm.org/c0293_c0293m-16.html
[fsel]: https://fsel.engr.utexas.edu/images/resources-pdfs/FSEL-MOE-Testing-Rev-00.pdf
[mit-stress]: https://web.mit.edu/course/3/3.11/www/pset03/Rec6.pdf
[mit-deflection]: https://ocw.mit.edu/courses/3-054-cellular-solids-structure-properties-and-applications-spring-2015/f6e2d069cbeff55c12152c92f92a5853_4zpQwirFsbk.pdf
