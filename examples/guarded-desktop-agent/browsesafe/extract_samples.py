"""Save a few chosen label=='yes' rows from the REAL BrowseSafe test parquet to
standalone .html files, byte-for-byte (no edits), so we can render and inspect
the actual attack pages before recording."""

from __future__ import annotations

import pathlib

import pandas as pd

HERE = pathlib.Path(__file__).parent
SAMPLES = HERE / "samples"
SAMPLES.mkdir(exist_ok=True)
ROWS = [7, 25, 23, 20, 11]

df = pd.read_parquet(HERE / "browsesafe_test.parquet")
for idx in ROWS:
    html = df.loc[idx, "content"]
    label = df.loc[idx, "label"]
    (SAMPLES / f"row_{idx}.html").write_text(html, encoding="utf-8")
    print(f"row #{idx} label={label} len={len(html)} -> samples/row_{idx}.html")
