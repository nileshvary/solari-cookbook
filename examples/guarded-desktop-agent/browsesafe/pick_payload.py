"""Download the REAL BrowseSafe-Bench test split (MIT), find label=="yes" pages
whose injection drives an OFF-DOMAIN NAVIGATION (a URL the agent could be tricked
into opening) — the attack our Guard actually catches — and save the best
candidates (row index + a short verbatim snippet of the injection) for review.

Nothing here authors an attack; it selects real rows from Perplexity's dataset.
"""

from __future__ import annotations

import pathlib
import re
import urllib.request

HERE = pathlib.Path(__file__).parent
PARQUET = HERE / "browsesafe_test.parquet"
URL = ("https://huggingface.co/datasets/perplexity-ai/browsesafe-bench/"
       "resolve/refs%2Fconvert%2Fparquet/default/test/0000.parquet")

# Instruction-like markers the BrowseSafe taxonomy uses.
MARKERS = [
    "ignore your previous", "ignore previous", "ignore all previous",
    "important message", "important!!!", "todo:", "new instruction",
    "instruction:", "system prompt", "as support staff", "urgent",
    "end context", "data-instruction", "you must", "navigate to",
    "go to", "visit", "redirect", "open the following", "click here",
]
# A navigation/exfil target the agent could actually ACT on by browsing.
URL_RE = re.compile(r"https?://[^\s\"'<>)]+", re.I)


def main() -> None:
    if not PARQUET.exists():
        print("downloading real BrowseSafe test split (46.9 MB, MIT) ...", flush=True)
        urllib.request.urlretrieve(URL, PARQUET)
    import pandas as pd

    df = pd.read_parquet(PARQUET)
    yes = df[df["label"] == "yes"]
    print(f"rows total={len(df)}  yes={len(yes)}  no={len(df) - len(yes)}")

    out = HERE / "candidates.txt"
    hits = 0
    with out.open("w", encoding="utf-8") as f:
        for idx, row in yes.iterrows():
            html = row["content"]
            low = html.lower()
            marker = next((m for m in MARKERS if m in low), None)
            if not marker:
                continue
            # find a URL that appears NEAR a marker (an off-domain nav target)
            urls = URL_RE.findall(html)
            offdomain = [u for u in urls if not any(
                d in u for d in ("wikipedia.org", "w3.org", "schema.org",
                                 "googleapis.com", "gstatic.com", "cloudflare",
                                 "jsdelivr", "unpkg", "gravatar", "fbcdn"))]
            if not offdomain:
                continue
            hits += 1
            pos = low.find(marker)
            snippet = html[max(0, pos - 120): pos + 320].replace("\n", " ")
            f.write(f"===== yes row #{idx}  (len={len(html)}) marker='{marker}'\n")
            f.write(f"  off-domain URLs: {offdomain[:4]}\n")
            f.write(f"  snippet: ...{snippet}...\n\n")
            if hits >= 25:
                break
    print(f"wrote {hits} candidate(s) -> {out}")


if __name__ == "__main__":
    main()
