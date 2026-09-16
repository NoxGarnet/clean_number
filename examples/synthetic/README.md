# Synthetic demonstration data

These files are generated, non-experimental fixtures. They are intentionally
small and exist only to exercise the public read and calculation paths.

Regenerate them from the repository root with:

```powershell
python examples/generate_synthetic_data.py
```

The `.xls` suffix mirrors a common instrument export. The files contain
GBK-encoded tab-separated text with one metadata row followed by column names;
this is one of the reader paths supported by `process_single.py`.
