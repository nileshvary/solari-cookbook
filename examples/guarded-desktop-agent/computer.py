"""The Computer — the Worker's eyes and hands, behind ONE tiny interface so the
SAME Worker runs unchanged on a Solari cloud desktop (for the recording) or on
your own machine.

Backends:
  DryComputer    — records intended actions, no real machine (tests / dry run)
  SolariComputer — a Solari cloud desktop, driven by mouse + screenshots   [added at record time]
  LocalComputer  — your own desktop, via screenshots + input                [added for --local]

The interface is deliberately small — look, read_text, visit, write_file — and
the Worker routes every side-effecting call (visit, write_file) through the Guard
first. Backends never bypass the Guard; they just carry out an already-approved
action on whatever machine they drive.
"""

from __future__ import annotations

from typing import Protocol


class Computer(Protocol):
    async def look(self) -> bytes:
        """A screenshot of the screen, PNG bytes (the Worker's eyes)."""
        ...

    async def read_text(self) -> str:
        """The visible text of the current page (cheap perception for text models)."""
        ...

    async def visit(self, url: str) -> None:
        """Open a URL in the browser. Only called after the Guard approved it."""
        ...

    async def write_file(self, path: str, content: str) -> None:
        """Save text to a file. Only called after the Guard approved the path."""
        ...


class DryComputer:
    """No real machine. Records what it was asked to do, so the Worker + Guard
    plumbing (and the on-screen feed) can be exercised with zero credit and no
    Solari. `pages` maps url -> the visible text that url would show."""

    def __init__(self, pages: dict[str, str] | None = None) -> None:
        self.pages = pages or {}
        self.current = ""
        self.visited: list[str] = []
        self.files: dict[str, str] = {}

    async def look(self) -> bytes:
        return b"\x89PNG\r\n"  # placeholder; the dry brain reads text, not pixels

    async def read_text(self) -> str:
        return self.current

    async def visit(self, url: str) -> None:
        self.visited.append(url)
        self.current = self.pages.get(url, "")

    async def write_file(self, path: str, content: str) -> None:
        self.files[path] = content
