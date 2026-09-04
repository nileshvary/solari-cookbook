"""Render candidate REAL websites to PNGs so we can confirm they load readably for
a screenshot-reading agent BEFORE spending a recording. Real internet, real sites."""

from __future__ import annotations

import pathlib

from playwright.sync_api import sync_playwright

OUT = pathlib.Path(__file__).parent / "site_check"
OUT.mkdir(exist_ok=True)

SITES = {
    "arxiv_browsesafe": "https://arxiv.org/abs/2511.20597",
    "perplexity_blog": "https://www.perplexity.ai/hub/blog/building-safer-ai-browsers-with-browsesafe",
    "wikipedia_prompt_injection": "https://en.wikipedia.org/wiki/Prompt_injection",
    "pinetree": "https://pinetree-research.com",
    "hf_browsesafe": "https://huggingface.co/datasets/perplexity-ai/browsesafe-bench",
    "anthropic": "https://www.anthropic.com/research",
}


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, url in SITES.items():
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            status = "ok"
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(2500)  # let JS paint
                code = resp.status if resp else "?"
            except Exception as e:
                code = f"ERR:{type(e).__name__}"
                status = "load-failed"
            try:
                page.screenshot(path=str(OUT / f"{name}.png"))
            except Exception:
                status = "shot-failed"
            text = ""
            try:
                text = page.inner_text("body")[:180].replace("\n", " ")
            except Exception:
                pass
            print(f"{name:28} http={code!s:12} {status:12} text: {text}", flush=True)
            page.close()
        browser.close()
    print("\nscreenshots ->", OUT)


if __name__ == "__main__":
    main()
