"""Research moltbook.com directly (read-only) and save the text of its key public
pages so we can summarize what the site is and what the agents are doing."""

from __future__ import annotations

import pathlib
from playwright.sync_api import sync_playwright

OUT = pathlib.Path(__file__).parent / "molt"
OUT.mkdir(exist_ok=True)

PAGES = {
    "home": "https://www.moltbook.com/",
    "communities": "https://www.moltbook.com/m",
    "m_agents": "https://www.moltbook.com/m/agents",
    "m_general": "https://www.moltbook.com/m/general",
    "m_aithoughts": "https://www.moltbook.com/m/aithoughts",
    "m_introductions": "https://www.moltbook.com/m/introductions",
    "m_announcements": "https://www.moltbook.com/m/announcements",
    "m_openclaw": "https://www.moltbook.com/m/openclaw-explorers",
    "post_1": "https://www.moltbook.com/post/04c4faf5-39d4-42f7-9bbd-2e8f3f6f255e",
    "post_2": "https://www.moltbook.com/post/1f9f1283-143a-42d7-a5ce-47ce196decf1",
    "post_3": "https://www.moltbook.com/post/2400e07a-674f-4bf6-bcd3-42b89032cbd4",
    "post_4": "https://www.moltbook.com/post/850f0699-2737-4594-829f-f634b7de0997",
    "post_5": "https://www.moltbook.com/post/a37dec7f-fe9b-4cf6-8a77-608381d6e0f9",
    "post_6": "https://www.moltbook.com/post/b73460a4-7334-43b1-8c8f-747d3eefffc8",
    "user_achi": "https://www.moltbook.com/u/Achi_AI",
    "user_aicli": "https://www.moltbook.com/u/AiiCLI",
    "skill_md": "https://www.moltbook.com/skill.md",
}


def main() -> None:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, url in PAGES.items():
            pg = b.new_page(viewport={"width": 1280, "height": 1200})
            try:
                r = pg.goto(url, wait_until="domcontentloaded", timeout=30000)
                pg.wait_for_timeout(3500)
                try:
                    text = pg.inner_text("body")
                except Exception:
                    text = pg.content()
                (OUT / f"{name}.txt").write_text(f"URL: {url}\n\n{text}", encoding="utf-8")
                print(f"{name:16} http={r.status if r else '?'} chars={len(text)}", flush=True)
            except Exception as e:
                print(f"{name:16} ERR {type(e).__name__}: {str(e)[:60]}", flush=True)
            pg.close()
        b.close()
    print("saved ->", OUT)


if __name__ == "__main__":
    main()
