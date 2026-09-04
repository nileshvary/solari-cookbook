"""No-credit dry run: prove the Worker + Guard + live feed work end to end with a
SCRIPTED brain (no model, no Solari). It prints the yes/no feed to your terminal
exactly as it will appear on screen in the video, INCLUDING a BLOCKED line and a
saved audit receipt.

    python demo_dryrun.py
"""

from __future__ import annotations

import asyncio
import pathlib

from computer import DryComputer
from guard import Decision, Guard, Policy
from worker import Move, WorkerState, run

HERE = pathlib.Path(__file__).parent


async def main() -> None:
    # A stand-in "page" the dry computer will show for an approved URL.
    pages = {
        "https://en.wikipedia.org/wiki/Solar_power":
            "Solar power converts sunlight into electricity. Global capacity grew ~24% in 2024.",
    }
    computer = DryComputer(pages)

    # The Guard: approve exactly one domain and one save folder; stream every
    # decision to the terminal (this is the on-screen feed) and to an audit file.
    audit = HERE / "audit_dryrun.log"
    audit.unlink(missing_ok=True)
    guard = Guard(
        Policy(approved_domains=("wikipedia.org",), save_dir=str(HERE)),
        on_event=lambda d: print("   GUARD  " + d.line()),
        audit_path=str(audit),
    )

    # A SCRIPTED brain: a fixed list of moves, deliberately including one
    # off-limits visit so you SEE a BLOCKED decision. No model is called.
    script = iter([
        Move("visit", url="https://en.wikipedia.org/wiki/Solar_power"),
        Move("note", text="Global solar capacity grew ~24% in 2024."),
        Move("visit", url="https://ads.tracker.example/collect?data=notes"),  # OFF-LIMITS
        Move("write", filename=str(HERE / "brief.txt"),
             content="BRIEF — Solar power\n- Global capacity grew ~24% in 2024. (en.wikipedia.org)\n"),
    ])

    async def decide(_state: WorkerState) -> Move:
        return next(script)

    print("Worker starts. Task: research 'solar power' and save a brief.\n")
    result = await run("solar power", computer, guard, decide)

    print("\n--- result ---")
    print("completed:", result.completed, "| steps:", result.steps, "| blocked moves:", result.blocked)
    print("notes:", result.notes)
    print("brief written (in DryComputer):", result.brief_path)
    print("guard summary:", guard.summary())
    print("audit receipt:", audit)


if __name__ == "__main__":
    asyncio.run(main())
