"""The Solari backend — the Worker's eyes and hands on a real cloud desktop, plus
the on-screen Guard console that streams the live yes/no feed into the recording.

Mirrors the navigation approach proven in the cookbook's desktop example: open
Chrome with the stable open() API, then drive the address bar by COORDINATE CLICK
+ type (a keyboard chord to focus the omnibox leaks characters on this template).

The GuardConsole opens a terminal inside the VM that tails a feed file; the runner
appends one line per Guard decision, so you watch ALLOWED/BLOCKED scroll on screen
next to the browser. If the template has no terminal, the runner still shows the
full log at the end — the yes/no is never lost.
"""

from __future__ import annotations

import asyncio

FEED_PATH = "/tmp/guard_feed.log"
_TAIL_SCRIPT = "/tmp/tailguard.sh"

# Address-bar spot for the default template at 1280x1024 (proven in the desktop
# example): clicking here focuses the omnibox and selects its text, so a typed
# URL replaces whatever is there.
_OMNIBOX_XY = (660, 126)


class GuardConsole:
    """A terminal window in the VM that shows the Guard's decisions live."""

    def __init__(self) -> None:
        self.available = False

    async def start(self, desktop) -> None:
        # A tiny tail script (avoids nested shell quoting), then launch whatever
        # terminal the template has as a BOTTOM STRIP that stays ABOVE Chrome, so
        # it never covers the address bar and stays visible while the agent works.
        await desktop.fs.write(_TAIL_SCRIPT, "#!/bin/sh\ntail -n +1 -f " + FEED_PATH + "\n")
        await desktop.fs.write(FEED_PATH, "==== GUARD - live decisions (allow / block) ====\n")
        launch = (
            "chmod +x /tmp/tailguard.sh; "
            "if command -v xfce4-terminal >/dev/null 2>&1; then "
            "setsid xfce4-terminal --hide-menubar --hide-toolbar --hide-scrollbar "
            "--geometry=200x10-0-0 --title=GUARDFEED -e /tmp/tailguard.sh >/dev/null 2>&1 & "
            "elif command -v xterm >/dev/null 2>&1; then "
            "setsid xterm -geometry 200x10-0-0 -T GUARDFEED -e /tmp/tailguard.sh >/dev/null 2>&1 & "
            "else exit 7; fi; "
            "sleep 2; "
            "if command -v wmctrl >/dev/null 2>&1; then "
            "wmctrl -r GUARDFEED -b add,above >/dev/null 2>&1; "
            "wmctrl -r GUARDFEED -e 0,0,846,1280,178 >/dev/null 2>&1; "
            "fi; exit 0"
        )
        res = await desktop.exec("sh", args=["-c", launch])
        code = getattr(res, "exit_code", getattr(res, "exitCode", None))
        self.available = code in (0, None)

    async def push(self, desktop, line: str) -> None:
        # Append one line as a positional arg so no shell-quoting can break it.
        try:
            await desktop.exec(
                "sh", args=["-c", 'printf "%s\\n" "$1" >> ' + FEED_PATH, "sh", line]
            )
        except Exception:
            pass

    async def show_full_log(self, desktop, decisions_text: str) -> None:
        """Finale: drop the whole log into a text editor so the receipt is on
        screen even if no live terminal was available."""
        try:
            await desktop.fs.write("/tmp/guard_log.txt", decisions_text)
            await desktop.exec("sh", args=["-c", "setsid mousepad /tmp/guard_log.txt >/dev/null 2>&1 &"])
            await asyncio.sleep(2.5)
        except Exception:
            pass


class SolariComputer:
    """Implements the Computer interface against a live Solari desktop handle."""

    def __init__(self, desktop, chrome_app: str, load_wait: float = 7.0) -> None:
        self._d = desktop
        self._chrome = chrome_app
        self._load_wait = load_wait

    async def open_browser(self) -> None:
        await self._d.open(self._chrome)
        await asyncio.sleep(4)

    async def position_browser(self) -> None:
        # Tile Chrome into the TOP region so the bottom guard strip stays visible
        # and nothing covers the address bar. No-op if wmctrl isn't present.
        try:
            await self._d.exec("sh", args=["-c",
                "if command -v wmctrl >/dev/null 2>&1; then "
                "wmctrl -r 'Google Chrome' -b remove,maximized_vert,maximized_horz >/dev/null 2>&1; "
                "wmctrl -r 'Google Chrome' -e 0,0,0,1280,840 >/dev/null 2>&1; fi"])
        except Exception:
            pass
        await asyncio.sleep(1.5)

    async def look(self) -> bytes:
        return await self._d.screenshot(format="png")

    async def scroll_down(self, times: int = 2) -> None:
        """Scroll the current page down so the agent reads FURTHER down it (and the
        video shows it working through the whole page, not just the top). Keyboard
        only — no click — so it can't accidentally follow a link and slip past the
        Guard, which only vets explicit visit() navigations."""
        for _ in range(times):
            await self._d.keyboard.press("Page_Down")
            await asyncio.sleep(0.7)

    async def read_text(self) -> str:
        return ""  # vision-only: the agent reads the screenshot, not the DOM

    async def visit(self, url: str) -> None:
        # Focus the Chrome window by clicking the page body (NOT the omnibox, which
        # would just place a cursor), then F6 to focus AND SELECT the address bar.
        # F6 is a function key: unlike ctrl+a / ctrl+l it can't leak a letter on
        # this template, and selecting means the typed URL replaces what's there.
        await self._d.mouse.click(660, 430, humanize=True)
        await asyncio.sleep(0.4)
        await self._d.keyboard.press("F6")
        await asyncio.sleep(0.4)
        await self._d.keyboard.type(url)
        await asyncio.sleep(0.6)
        await self._d.keyboard.press("Return")
        await asyncio.sleep(self._load_wait)  # let the real page load
        await self._d.keyboard.press("Escape")  # dismiss donation / cookie popups
        await asyncio.sleep(0.4)

    async def focus_browser(self) -> None:
        """Raise the real Chrome window (e.g. after a text editor covered it)."""
        try:
            await self._d.exec("sh", args=["-c",
                "command -v wmctrl >/dev/null 2>&1 && wmctrl -a 'Google Chrome' >/dev/null 2>&1; true"])
        except Exception:
            pass
        await asyncio.sleep(0.6)

    async def preview_url(self, url: str) -> None:
        """Type a URL into the REAL address bar so the true destination is visible
        on screen — but do NOT press Return. The Guard, not the browser, decides
        whether the navigation is allowed to happen."""
        await self._d.mouse.click(660, 430, humanize=True)
        await asyncio.sleep(0.3)
        await self._d.keyboard.press("F6")
        await asyncio.sleep(0.3)
        await self._d.keyboard.type(url)
        await asyncio.sleep(0.4)

    async def cancel_url(self) -> None:
        """Abandon a typed-but-not-navigated URL; the omnibox reverts to the page."""
        await self._d.keyboard.press("Escape")
        await asyncio.sleep(0.3)

    async def preview_and_go(self, url: str, dwell: float = 2.4) -> None:
        """The agent types the URL itself AND navigates, then waits `dwell` seconds
        so the REAL destination is briefly visible on screen — before the Guard's
        denial is enforced (the caller returns the agent to the approved site)."""
        await self._d.mouse.click(660, 430, humanize=True)
        await asyncio.sleep(0.3)
        await self._d.keyboard.press("F6")
        await asyncio.sleep(0.3)
        await self._d.keyboard.type(url)   # typed character by character, on screen
        await asyncio.sleep(0.5)
        await self._d.keyboard.press("Return")
        await asyncio.sleep(dwell)          # the real site shows for a moment

    async def write_file(self, path: str, content: str) -> None:
        # The real, guard-approved save (the file keeps its real newlines).
        await self._d.fs.write(path, content)
        # The visual: open a text editor and type the brief so it's seen on screen.
        # Type it LINE BY LINE, pressing Return between lines — keyboard.type does
        # not turn "\n" into a newline, so without this the whole brief lands on a
        # single row (which is exactly the "one line" bug).
        try:
            await self._d.open("mousepad")
            await asyncio.sleep(2.5)
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line:
                    await self._d.keyboard.type(line)
                if i < len(lines) - 1:
                    await self._d.keyboard.press("Return")
                await asyncio.sleep(0.05)
            await asyncio.sleep(1.5)
        except Exception:
            pass
