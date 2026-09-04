"""The Worker — one naive agent that does a real task on a real computer:
research a topic, then write a short brief and save it.

Deliberately simple and framework-free: look -> decide -> act, with a hard step
cap. The point of the whole project lives in one place — EVERY move that has a
side effect (visiting a site, saving a file) is routed through the Guard first,
so nothing happens that the Guard has not approved, and every decision is on the
record.

The model is INJECTED as `decide`, so the loop is testable with a scripted brain
(no credit) and swappable for a real vision model at record time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from computer import Computer
from guard import Decision, Guard


@dataclass
class Move:
    """The Worker's next step. Small on purpose: visit a page, jot a note, write
    the brief, or stop."""

    action: str  # "visit" | "note" | "write" | "done"
    reasoning: str = ""
    url: str = ""
    text: str = ""  # a note (for action == "note")
    filename: str = ""  # for action == "write"
    content: str = ""  # the brief text (for action == "write")


@dataclass
class WorkerState:
    """What the brain is given to decide the next Move."""

    topic: str
    screenshot: bytes
    page_text: str
    notes: list[str]
    history: list[str]


# The brain: given the state, choose the next Move. Async so a real model call
# fits naturally; the dry/scripted brain just returns the next canned Move.
Decide = Callable[[WorkerState], Awaitable[Move]]

# Optional async hook, awaited with each Guard Decision the moment it is made —
# the runner uses it to stream the yes/no onto an on-screen console in the VM.
Feed = Callable[[Decision], Awaitable[None]]


@dataclass
class WorkerResult:
    notes: list[str] = field(default_factory=list)
    brief_path: str | None = None
    brief_content: str = ""  # the brief text, kept so it survives the VM teardown
    completed: bool = False
    steps: int = 0
    blocked: int = 0  # how many of the Worker's moves the Guard denied


MAX_STEPS = 12


async def run(
    topic: str,
    computer: Computer,
    guard: Guard,
    decide: Decide,
    max_steps: int = MAX_STEPS,
    feed: Optional[Feed] = None,
) -> WorkerResult:
    notes: list[str] = []
    history: list[str] = []
    brief_path: str | None = None
    brief_content = ""
    completed = False
    blocked = 0
    step = 0

    async def gate(decision: Decision) -> bool:
        if feed is not None:
            await feed(decision)  # stream the yes/no to the on-screen console
        return decision.allowed

    for step in range(max_steps):
        shot = await computer.look()
        page_text = await computer.read_text()
        move = await decide(WorkerState(topic, shot, page_text, list(notes), list(history)))

        if move.action == "visit":
            if await gate(guard.check_visit(move.url)):  # <-- Guard decides before we act
                await computer.visit(move.url)
                history.append(f"visited {move.url}")
            else:
                blocked += 1
                history.append(f"BLOCKED visit {move.url}")

        elif move.action == "note":
            notes.append(move.text)
            history.append(f"noted: {move.text[:60]}")

        elif move.action == "write":
            if await gate(guard.check_save(move.filename)):  # <-- Guard decides before we save
                await computer.write_file(move.filename, move.content)
                brief_path = move.filename
                brief_content = move.content
                completed = True
                history.append(f"saved {move.filename}")
                break
            else:
                blocked += 1
                history.append(f"BLOCKED save {move.filename}")

        else:  # "done" or anything unrecognized
            completed = bool(brief_path)
            break

    return WorkerResult(
        notes=notes, brief_path=brief_path, brief_content=brief_content,
        completed=completed, steps=step + 1, blocked=blocked
    )
