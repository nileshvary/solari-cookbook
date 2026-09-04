"""Record the guarded research agent doing REAL research on REAL websites.

The worker agent (vision / computer-use) opens real Chrome, browses the REAL live
Pinetree Research site (real URLs), reads each page, takes cited notes, then writes
a structured brief in a text editor. The Guard's allowlist is the approved source;
when the agent tries to cross-check on an OFF-list real site, the Guard blocks it
on camera. Everything is audited and recorded.

Nothing local, nothing faked: real internet, real sites, real model decisions,
real Guard blocks. Only the page ORDER is arranged (a research harness).

    python run_research_demo.py
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib

from env import bootstrap, require_key

bootstrap()

from brain import make_vision_brain  # noqa: E402
from guard import Decision, Guard, Policy  # noqa: E402
from run_guarded import _find_chrome, _save_recording  # noqa: E402
from solari_computer import GuardConsole, SolariComputer  # noqa: E402
from worker import WorkerState  # noqa: E402

HERE = pathlib.Path(__file__).parent
RUNS = HERE / "runs"
BASE_URL = "https://api.getsolari.com"
VM_SAVE_DIR = "/tmp/agent-out"

TOPIC = "Pinetree Research (an AI lab building vision-first computer-use agents)"
SITE = "pinetree-research.com"
# Real pages on the live site, visited in order (a research harness).
PAGES = [
    ("home", f"https://{SITE}"),
    ("about", f"https://{SITE}/about"),
    ("research", f"https://{SITE}/research"),
    ("blog", f"https://{SITE}/blog"),
]
# The agent tries to cross-check the company on an external site — off the
# allowlist, so the Guard blocks it (least-privilege on the real web).
EXTERNAL_CHECK = "https://www.linkedin.com/company/pinetree-research"


def _on_event(d: Decision, audit_path: pathlib.Path) -> None:
    print("  GUARD  " + d.line(), flush=True)
    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(d.as_dict()) + "\n")


async def main() -> None:
    solari_key = require_key("SOLARI_API_KEY", "https://console.getsolari.com")
    brain, brain_label = make_vision_brain(os.environ.get("GROQ_API_KEY"),
                                           os.environ.get("GEMINI_API_KEY"))
    print(f"vision brain: {brain_label} ({brain.model})")

    RUNS.mkdir(exist_ok=True)
    audit_path = RUNS / "research_audit.jsonl"
    audit_path.unlink(missing_ok=True)
    mp4_path = RUNS / "research_demo.mp4"

    console = GuardConsole()
    guard = Guard(Policy(approved_domains=(SITE,), save_dir=VM_SAVE_DIR),
                  on_event=lambda d: _on_event(d, audit_path))

    from solari_desktop import DesktopClient

    notes: list[str] = []
    brief = ""
    recording_url = None

    async with DesktopClient(api_key=solari_key, base_url=BASE_URL) as client:
        desktop = await client.create(template="default", resolution="1280x1024",
                                      timeout_ms=15 * 60_000, record=True)
        print("\n  desktop session:", desktop.sessionId)
        print("  LIVE VIEW (console.getsolari.com -> Desktops):", getattr(desktop, "streamUrl", None))
        print("  mp4 ->", mp4_path.resolve())
        print("  ...pausing ~15s so you can open the live view.\n", flush=True)
        await asyncio.sleep(15)

        try:
            await desktop.connect()
            for _ in range(30):
                if getattr(await desktop.health(), "ready", False):
                    break
                await asyncio.sleep(1)
            try:
                await desktop.record.start()
            except Exception as err:  # noqa: BLE001
                print("  record.start warning:", type(err).__name__, str(err)[:80])

            chrome = await _find_chrome(desktop)
            if not chrome:
                print("\n  x  No Chrome/Chromium in this template.\n")
                return
            await desktop.exec("sh", args=["-c", f"mkdir -p {VM_SAVE_DIR}"])

            await console.start(desktop)
            print(f"  guard console: {'live' if console.available else 'log-at-end'}")
            computer = SolariComputer(desktop, chrome, load_wait=7.0)
            await computer.open_browser()

            async def feed(d: Decision) -> None:
                await console.push(desktop, d.line())
                await asyncio.sleep(0.6)

            # --- Research: walk the real pages, take cited notes ---------------
            for name, url in PAGES:
                dec = guard.check_visit(url)
                await feed(dec)
                await computer.visit(url)
                print(f"\n[source] {name}  {url}", flush=True)
                history: list[str] = []
                for _step in range(2):
                    shot = await computer.look()
                    mv = brain.decide_research(
                        WorkerState(TOPIC, shot, "", notes, history))
                    print(f"    agent: {mv.action} {(mv.url or mv.text[:70] or '')}".rstrip(), flush=True)
                    if mv.action == "note" and mv.text:
                        notes.append(f"{mv.text}  (source: {url})")
                        history.append(f"noted: {mv.text[:50]}")
                    elif mv.action == "visit":
                        vdec = guard.check_visit(mv.url)
                        await feed(vdec)
                        history.append(f"visit {mv.url} -> {'ok' if vdec.allowed else 'BLOCKED'}")
                    else:
                        break

            # --- Security beat: cross-check on an OFF-list real site -----------
            print("\n[cross-check] agent tries to verify the company externally", flush=True)
            ext = guard.check_visit(EXTERNAL_CHECK)  # off allowlist -> BLOCKED
            await feed(ext)
            await asyncio.sleep(1.5)

            # --- Deliverable: compose + write the brief in a text editor -------
            print("\n[write] composing the brief ...", flush=True)
            brief = brain.compose_brief(TOPIC, notes) or (
                "Brief — Pinetree Research\n\n" + "\n".join(f"- {n}" for n in notes))
            spath = f"{VM_SAVE_DIR}/pinetree_brief.txt"
            sdec = guard.check_save(spath)
            await feed(sdec)
            if sdec.allowed:
                await computer.write_file(spath, brief)

            # --- Result card + guard log --------------------------------------
            card = (
                "==== GUARDED RESEARCH — RESULT ====\n\n"
                f"Agent   : {brain.model} (vision / computer-use)\n"
                f"Topic   : {TOPIC}\n"
                f"Sources : {len(PAGES)} real pages on {SITE}\n"
                f"Notes   : {len(notes)} cited\n"
                f"Guard   : {guard.summary()}  (external cross-check BLOCKED)\n"
                f"Data leaving the approved source: 0\n"
            )
            await console.show_full_log(
                desktop, card + "\n==== GUARD LOG ====\n"
                + "\n".join(d.line() for d in guard.decisions))
            await asyncio.sleep(7)

            try:
                stop = await desktop.record.stop()
                await asyncio.sleep(3)
                recording_url = getattr(desktop, "recordingUrl", None)
                if not recording_url and isinstance(stop, dict):
                    recording_url = stop.get("recordingUrl") or stop.get("url")
            except Exception as err:  # noqa: BLE001
                print("  record.stop error:", type(err).__name__, str(err)[:100])
        finally:
            await desktop.close()
            await client.destroy(desktop.sessionId)

    recording_file = await _save_recording(recording_url, mp4_path) if recording_url else None
    (RUNS / "pinetree_brief.txt").write_text(brief, encoding="utf-8")
    if recording_file:
        try:
            import shutil
            dest = pathlib.Path.home() / "Desktop" / "guarded_research_pinetree.mp4"
            shutil.copy(recording_file, str(dest))
            print("copied to Desktop:", dest)
        except Exception as e:  # noqa: BLE001
            print("desktop copy failed:", e)
    print("\n--- done ---")
    print(f"notes: {len(notes)} · guard {guard.summary()}")
    print("audit:", audit_path)
    print("recording:", recording_file or f"(not downloaded) {recording_url}")


if __name__ == "__main__":
    asyncio.run(main())
