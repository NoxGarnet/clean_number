# Experiment manifest

The public candidate uses an explicit `experiment.yaml` manifest to connect
filename condition tokens with stable group and factor metadata. Keep the
manifest beside the input directory or pass its path with `analyze.py
--config`.

The supported manifest sections are:

- `project`: identifier and optional `kind` (`compression` or `flexural`);
- `factors`: named categorical or numeric factors;
- `mixes`: registered condition/mix identifiers;
- `condition_mapping`: required condition-to-group mapping, labels and factor
  values;
- `display` and `comparison`: optional presentation/comparison metadata.

Unknown conditions are rejected. The manifest does not make an unsupported
method, unit, geometry or standard valid; those require an independent
validation decision and code path.
