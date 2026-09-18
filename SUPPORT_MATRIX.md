# Support matrix

This candidate supports only the methods below. The matrix describes implemented
behavior and fail-closed cases; it is not a standards-compliance claim.

## Implemented methods

| Method | Required columns | Configurable parameters | Implemented result |
| --- | --- | --- | --- |
| `compression` | `stress_MPa`, `strain_pct` | chord-modulus lower/upper stress fractions | peak stress and chord modulus |
| `flexural` | `force_kN`, `deform_mm` | rectangular three-point-bending span, width, depth, and chord-modulus lower/upper force fractions | recalculated flexural stress and diagnostic flexural modulus |

The public fixture manifest records these settings under `methods` in
`examples/synthetic/experiment.yaml`.

## Column and unit boundary

Input columns are intentionally narrow. A supported source must expose units in
the column labels:

| Internal column | Accepted unit signal |
| --- | --- |
| `force_kN` | `kN` or `千牛` |
| `stress_MPa` | `MPa` or `兆帕` |
| `strain_pct` | `%`, `pct`, or `百分` |
| `deform_mm` | `mm` or `毫米` |
| `time_s` | `s` or `秒` |

Missing required columns, unsupported or omitted units, and duplicate columns
that map to the same internal measurement fail closed.

## Explicit non-support examples

The current candidate does not support these cases:

- unknown test methods or a directory whose method cannot be explicitly
  resolved;
- force units other than kN, stress units other than MPa, displacement units
  other than mm, or strain units other than percent;
- flexural geometries other than rectangular three-point bending;
- automatic conversion from crosshead displacement to specimen strain;
- automatic deletion or exclusion of anomalous raw data;
- treating the quality score or a successful run as a scientific conclusion.

## Source status

The implemented flexural equation is the configured rectangular three-point
bending calculation:

```text
stress_MPa = 3 * force_kN * 1000 * span_mm / (2 * width_mm * depth_mm^2)
modulus_GPa = span_mm^3 / (4 * width_mm * depth_mm^3) * dF_kN / ddelta_mm
```

These equations and the compression chord-modulus interval are implementation
contracts for the synthetic public candidate. Formal method authority, standard
version, specimen-shape applicability, and instrument-specific interpretation
remain pending review before any release or real-material claim.
