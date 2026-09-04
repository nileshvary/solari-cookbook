"""Minimal, SELF-CLEANING nav test: create one desktop, open Chrome, navigate to
a real page via SolariComputer.visit (F6), screenshot, and DESTROY the desktop in
a finally. No recording, ~1 minute, leaves no orphan session. Reviews whether the
real page actually loaded before we spend a full recorded take."""

from __future__ import annotations

import asyncio
import os
import pathlib

from env import bootstrap

bootstrap()

from solari_computer import SolariComputer  # noqa: E402

HERE = pathlib.Path(__file__).parent
BASE = "https://api.getsolari.com"


async def _find_chrome(d) -> str | None:
    p = await d.exec("sh", args=["-c",
        "for b in google-chrome google-chrome-stable chromium chromium-browser; do "
        "command -v $b >/dev/null 2>&1 && echo $b && break; done"])
    n = (getattr(p, "stdout", "") or "").strip().splitlines()
    return n[0].strip() if n else None


async def main() -> None:
    from solari_desktop import DesktopClient

    async with DesktopClient(api_key=os.environ["SOLARI_API_KEY"], base_url=BASE) as c:
        d = await c.create(template="default", resolution="1280x1024",
                           timeout_ms=5 * 60_000, record=False)
        print("navtest session:", d.sessionId[:40])
        try:
            await d.connect()
            for _ in range(30):
                if getattr(await d.health(), "ready", False):
                    break
                await asyncio.sleep(1)
            chrome = await _find_chrome(d)
            comp = SolariComputer(d, chrome)
            await comp.open_browser()
            await comp.visit("https://en.wikipedia.org/wiki/Solar_power")
            (HERE / "runs").mkdir(exist_ok=True)
            (HERE / "runs" / "_navtest.png").write_bytes(await d.screenshot(format="png"))
            print("navtest screenshot saved")
        finally:
            await d.close()
            await c.destroy(d.sessionId)
            print("cleaned up (session destroyed)")


if __name__ == "__main__":
    asyncio.run(main())
