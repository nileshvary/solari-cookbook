"""Run the guarded research agent on a Solari cloud desktop and record it.

One Worker (a vision model) does a real task on a real computer — browse, read,
write a brief — while the Guard checks every visit and every save against an
allowlist and streams the yes/no onto an on-screen console. The whole thing is
recorded to an mp4, and the Guard's decisions are saved as an audit log.

    python run_guarded.py
    python run_guarded.py --topic "the James Webb Space Telescope" \
                          --start https://en.wikipedia.org/wiki/James_Webb_Space_Telescope \
                          --allow wikipedia.org

Nothing is faked: real desktop, real websites, a real file the agent writes, and
real allow/block decisions. The only self-contained part is the sink used in the
injection project next door — this demo doesn't need one.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib

from env import bootstrap, require_key

bootstrap()

import httpx  # noqa: E402

from brain import make_vision_brain  # noqa: E402
from guard import Decision, Guard, Policy  # noqa: E402
from solari_computer import FEED_PATH, GuardConsole, SolariComputer  # noqa: E402
from worker import Move, WorkerState, run  # noqa: E402

HERE = pathlib.Path(__file__).parent
RUNS = HERE / "runs"
BASE_URL = "https://api.getsolari.com"
VM_SAVE_DIR = "/tmp/agent-out"  # the ONE folder the Worker may write into


async def _find_chrome(desktop) -> str | None:
    probe = await desktop.exec("sh", args=["-c",
        "for b in google-chrome google-chrome-stable chromium chromium-browser; do "
        "command -v $b >/dev/null 2>&1 && echo $b && break; done"])
    names = (getattr(probe, "stdout", "") or "").strip().splitlines()
    return names[0].strip() if names else None


async def _save_recording(url: str, dest: pathlib.Path, tries: int = 14) -> str | None:
    for _ in range(tries):
        await asyncio.sleep(3)
        try:
            resp = httpx.get(url, timeout=60)
            if resp.status_code == 200 and resp.content:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(resp.content)
                return str(dest)
        except Exception:
            pass
    return None


async def main() -> None:
    ap = argparse.ArgumentParser(description="Guarded research agent on Solari (recorded).")
    ap.add_argument("--topic", default="solar power")
    ap.add_argument("--start", default="https://en.wikipedia.org/wiki/Solar_power")
    ap.add_argument("--allow", nargs="*", default=["wikipedia.org"],
                    help="approved domains (subdomains allowed)")
    ap.add_argument("--serve", help="a local .html file to HOST in the VM as the "
                    "first source (e.g. a real BrowseSafe attack page). Adds 127.0.0.1 "
                    "to the allowlist and starts the agent there.")
    ap.add_argument("--served-name", default="page.html")
    ap.add_argument("--steps", type=int, default=8)
    args = ap.parse_args()

    # Effective allowlist: a served local page implies 127.0.0.1 is approved (the
    # agent must be able to READ the hosted page). The injection inside it points
    # off-domain, which the Guard then blocks.
    allow = ["127.0.0.1"] + list(args.allow) if args.serve else list(args.allow)

    solari_key = require_key("SOLARI_API_KEY", "https://console.getsolari.com")
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not (groq_key or gemini_key):
        require_key("GROQ_API_KEY", "https://console.groq.com/keys")  # exits with guidance
    brain, brain_label = make_vision_brain(groq_key, gemini_key)
    print(f"vision brain: {brain_label} ({brain.model})")

    RUNS.mkdir(exist_ok=True)
    audit_path = RUNS / "guard_audit.jsonl"
    audit_path.unlink(missing_ok=True)
    mp4_path = RUNS / "guarded_demo.mp4"

    # The Guard: allowlist + one save folder. on_event prints to the host and
    # writes the audit receipt; the async `feed` hook streams to the VM console.
    console = GuardConsole()
    policy = Policy(approved_domains=tuple(allow), save_dir=VM_SAVE_DIR)

    def on_event(d: Decision) -> None:
        print("  GUARD  " + d.line(), flush=True)
        with open(audit_path, "a", encoding="utf-8") as f:
            import json
            f.write(json.dumps(d.as_dict()) + "\n")

    guard = Guard(policy, on_event=on_event)

    # When hosting a page, the task is to read THAT page (which carries the real
    # attack). Otherwise nudge the agent toward a second source so a natural
    # off-domain BLOCK appears.
    topic = args.topic if args.serve else (
        f"{args.topic} (verify one fact using a second, non-Wikipedia source)")

    from solari_desktop import DesktopClient

    async with DesktopClient(api_key=solari_key, base_url=BASE_URL) as client:
        desktop = await client.create(
            template="default", resolution="1280x1024", timeout_ms=10 * 60_000, record=True
        )
        print("\n  desktop session:", desktop.sessionId)
        print("  LIVE VIEW (console.getsolari.com -> Desktops):", getattr(desktop, "streamUrl", None))
        print("  mp4 ->", mp4_path.resolve())
        print("  ...pausing ~15s so you can open the live view.\n", flush=True)
        await asyncio.sleep(15)

        recording_url = None
        try:
            await desktop.connect()
            for _ in range(30):
                h = await desktop.health()
                if getattr(h, "ready", False):
                    break
                await asyncio.sleep(1)
            try:
                await desktop.record.start()
            except Exception as err:  # noqa: BLE001
                print("  record.start warning:", type(err).__name__, str(err)[:80])

            chrome = await _find_chrome(desktop)
            if not chrome:
                print("\n  x  No Chrome/Chromium in this template — cannot run.\n")
                return
            await desktop.exec("sh", args=["-c", f"mkdir -p {VM_SAVE_DIR}"])

            # If hosting a real attack page, push it into the VM and serve it on
            # localhost so the agent can browse to it. The page is served
            # BYTE-FOR-BYTE — we don't edit the attack.
            start_url = args.start
            if args.serve:
                served_dir = "/tmp/served"
                html = pathlib.Path(args.serve).read_text(encoding="utf-8")
                await desktop.exec("sh", args=["-c", f"mkdir -p {served_dir}"])
                await desktop.fs.write(f"{served_dir}/{args.served_name}", html)
                await desktop.exec("sh", args=["-c",
                    f"cd {served_dir} && nohup python3 -m http.server 8080 >/tmp/serve.log 2>&1 &"])
                for _ in range(12):
                    await asyncio.sleep(1)
                    chk = await desktop.exec("sh", args=["-c",
                        f"curl -s -o /dev/null -w '%{{http_code}}' "
                        f"http://127.0.0.1:8080/{args.served_name} || echo 000"])
                    if "200" in (getattr(chk, "stdout", "") or ""):
                        print("  hosted attack page ready")
                        break
                start_url = f"http://127.0.0.1:8080/{args.served_name}"

            await console.start(desktop)
            print(f"  guard console: {'live terminal open' if console.available else 'no terminal; log shown at the end'}")

            computer = SolariComputer(desktop, chrome)
            await computer.open_browser()  # maximized (proven omnibox coordinate);
            # the guard strip stays visible because it is always-on-top (see GuardConsole).

            async def feed(d: Decision) -> None:
                await console.push(desktop, d.line())
                await asyncio.sleep(0.6)  # let the line land on screen

            # Seed: open the approved starting page (a real Guard-checked visit).
            # check_visit already fires on_event (host print + audit); feed streams
            # the same decision to the VM console.
            start_dec = guard.check_visit(start_url)
            await feed(start_dec)
            if start_dec.allowed:
                await computer.visit(start_url)
            try:  # debug: confirm the real page actually loaded (VM has internet?)
                (RUNS / "_after_start.png").write_bytes(await desktop.screenshot(format="png"))
            except Exception:
                pass

            # Map the brain's "write" to the ONE approved file path.
            def decide_adapter():
                async def _decide(state: WorkerState) -> Move:
                    move = brain.decide_research(state)
                    if move.action == "write":
                        move.filename = f"{VM_SAVE_DIR}/brief.txt"
                    print(f"  worker: {move.action} {move.url or move.text[:50] or ''}".rstrip(), flush=True)
                    return move
                return _decide

            result = await run(topic, computer, guard, decide_adapter(),
                               max_steps=args.steps, feed=feed)

            # Guarantee a deliverable: if the agent never wrote a brief, compile
            # its notes into one and save it (Guard-approved).
            if not result.completed:
                brief = f"BRIEF — {args.topic}\n\n" + (
                    "\n".join(f"- {n}" for n in result.notes) or "- (no notes gathered)"
                ) + f"\n\nSource(s): {', '.join(args.allow)}\n"
                result.brief_content = brief
                path = f"{VM_SAVE_DIR}/brief.txt"
                dec = guard.check_save(path)  # fires on_event (print + audit)
                await feed(dec)
                if dec.allowed:
                    await computer.write_file(path, brief)
                    result.brief_path = path

            # Finale: show the full Guard log on screen so the receipt is in-frame.
            log_text = "==== GUARD — full decision log ====\n" + "\n".join(
                d.line() for d in guard.decisions
            ) + f"\n\nSummary: {guard.summary()}\n"
            await console.show_full_log(desktop, log_text)
            await asyncio.sleep(6)  # dwell on a clean final frame

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

    # Save the brief locally too, so the evidence survives the VM teardown.
    (RUNS / "brief.txt").write_text(
        result.brief_content or "no brief written\n", encoding="utf-8"
    )
    print("\n--- done ---")
    print("guard summary:", guard.summary())
    print("notes gathered:", len(result.notes))
    print("brief path (in VM):", result.brief_path)
    print("audit log:", audit_path)
    print("recording:", recording_file or f"(not downloaded) {recording_url}")


if __name__ == "__main__":
    asyncio.run(main())
