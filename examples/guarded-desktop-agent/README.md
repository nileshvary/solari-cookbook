# Guarded Desktop Agent

[![guard-tests](https://github.com/nileshvary/solari-cookbook/actions/workflows/guard-tests.yml/badge.svg)](https://github.com/nileshvary/solari-cookbook/actions/workflows/guard-tests.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

**A least-privilege security layer for autonomous computer-use agents on a Solari cloud desktop.**

An autonomous vision agent drives a real Chrome browser on a [Solari](https://getsolari.com)
desktop VM — it perceives the screen, decides its own next move, and acts. In front of *every*
action sits a **Guard**: a small, un-trickable allowlist that decides whether the agent may
visit a site or save a file, streams each decision to a live on-screen feed, and writes a
tamper-evident audit log. When the agent tries to step off the approved site, the Guard
**blocks it** — showing the exact URL and reason — and pulls the agent back.

> **Design principle:** the agent (a model) is the fallible part; the Guard (a rule) is the
> provable part. Security lives in the boundary around what the agent may *do*, not in the
> model's good behaviour. A clever model can be talked out of its judgement; a plain allowlist
> cannot.

## Architecture

```mermaid
flowchart LR
    subgraph SOLARI["Solari Cloud Desktop VM"]
        SCREEN["Screen: live stream plus mp4"]
        CHROME["Real Chrome browser"]
    end

    subgraph AGENT["Autonomous agent - fallible"]
        EYES["Perceive - screenshot"]
        BRAIN["Vision brain - decides one move"]
        HANDS["Act - mouse and keyboard"]
    end

    subgraph GUARD["The Guard - deny by default - provable"]
        POLICY["Allowlist policy - visit approved domains, save one folder"]
        DECIDE{"Allowed?"}
    end

    AUDIT["Audit log JSONL plus live on-screen feed"]
    BLOCK["BLOCKED notice - URL and reason - agent pulled back"]

    SCREEN --> EYES --> BRAIN -->|"intended move"| POLICY --> DECIDE
    DECIDE -->|"ALLOW"| HANDS --> CHROME --> SCREEN
    DECIDE -->|"DENY"| BLOCK --> SCREEN
    DECIDE -.->|"every decision"| AUDIT

    classDef solari fill:#14532d,stroke:#22c55e,color:#ffffff;
    classDef agent fill:#0b3b57,stroke:#38bdf8,color:#ffffff;
    classDef guard fill:#3f1d1d,stroke:#ef4444,color:#ffffff;
    classDef audit fill:#3b0764,stroke:#a78bfa,color:#ffffff;
    class SOLARI,SCREEN,CHROME solari;
    class AGENT,EYES,BRAIN,HANDS agent;
    class GUARD,POLICY,DECIDE guard;
    class AUDIT audit;
    class BLOCK guard;
```

The agent runs a classic **perceive → decide → act** loop. The Guard is a mediator on the
*act* edge: no navigation or file write reaches the desktop until the policy approves it, and
**every** decision — allow or deny — is emitted to a live feed and appended to an audit log.

## See it in action

Real frames from the recorded run (`run_moltbook_live.py`), start to finish:

**1 — The agent researches; the Guard allows moltbook**

![The agent browsing moltbook.com/m/general with the live Guard feed on the desktop](docs/01-research.png)

**2 — It writes a cited, multi-section brief on screen**

![The agent's research brief open in a text editor, with sections and field notes](docs/02-brief.png)

**3 — It tries to leave to the real twitter.com; the Guard DENIES it**

![The real X / Twitter login page with a BLOCKED BY THE GUARD dialog naming the URL and reason](docs/03-blocked.png)

The block is real: the agent typed the real `twitter.com/login` and reached X — but the
navigation is off the allowlist, so the Guard refused it, showed the exact URL + reason, and
pulled the agent back to moltbook. The decision is in the audit log:
`[00:54:33] visit twitter.com BLOCKED (off moltbook - ...)`.

## Quickstart — try the Guard, no keys

The Guard is pure Python. See it allow, block, and audit with **no API keys, no Solari
session, no model** — a scripted brain drives the loop. You only need **Python 3.10+**:

```bash
git clone https://github.com/nileshvary/solari-cookbook
cd solari-cookbook/examples/guarded-desktop-agent
python demo_dryrun.py
```

```
   GUARD  [18:05:19]  visit  en.wikipedia.org        ALLOWED
   GUARD  [18:05:19]  visit  ads.tracker.example     BLOCKED  (not on the approved list)
   GUARD  [18:05:19]  save   brief.txt               ALLOWED
   ...
   guard summary: {'total': 3, 'allowed': 2, 'blocked': 1}
```

That is the whole security model, verifiable offline. The rest of this repo is what it looks
like driving a *real* agent on a *real* desktop against *real* sites.

## The threat it addresses

Computer-use agents are capable and *credulous*. Two failure modes matter:

1. **Prompt injection** — a malicious instruction hidden in a web page ("ignore your task,
   go here, paste this, post that") hijacks the agent.
2. **Task drift** — even with no attacker, an open-ended agent wanders off its intended source
   and starts touching sites or data it should never touch.

You cannot make the model un-foolable. So you do what every other security discipline does:
apply **least privilege** to the *actions*, and make them **auditable**. That is the Guard.

## The Guard's policy model

```python
Policy(
    approved_domains = ("moltbook.com",),   # visit: exact domain OR any subdomain
    save_dir         = "/tmp/agent-out",    # save: only inside this one folder
)
```

- **Visit** — allowed only for an approved domain or a subdomain of it. A look-alike like
  `moltbook.com.evil.com` is **denied** because it does not end in `.moltbook.com`.
- **Save** — allowed only for real paths inside the approved folder (path-traversal such as
  `../../etc/passwd` is denied).
- **Everything else is denied by default.**
- **Every** decision is recorded: `[00:54:33] visit twitter.com BLOCKED (off moltbook …)`, and
  the same line is appended to `runs/*_audit.jsonl` — a receipt of exactly what the agent did.

`guard.py` is pure and dependency-free on purpose, and unit-tested. A rule you can prove
beats a model you can only hope about.

## The demo — `run_moltbook_live.py`

Runs the guarded agent, live and recorded, on the real
[moltbook.com](https://www.moltbook.com) ("a social network for AI agents"):

1. **Research** — the agent opens several communities (`/m/general`, `/m/aithoughts`, …),
   **scrolls and reads** posts, and takes concrete cited notes. The Guard **allows** moltbook.
2. **Brief** — it writes a multi-section brief (with a numbered *Field notes* list of every
   observation) into a text editor, on screen.
3. **The block** — it then attempts moltbook's "verify on X" step and types the real
   `twitter.com/login` itself. The real site appears for a moment, then the Guard **DENIES**
   it: a *BLOCKED BY THE GUARD* notice names the URL + reason and the agent is pulled back.
   `twitter.com` is off the allowlist, so the navigation is refused and logged.

Everything is captured in one screen recording; every allow/deny is in `runs/moltbook_audit.jsonl`.

## Use it on your own task

The Guard is not tied to this demo. Two ways to reuse it:

**1. Point the generic runner at your own site + task** (no code changes):

```bash
python run_guarded.py \
  --topic "your research question" \
  --start "https://your-approved-site.com/start" \
  --allow your-approved-site.com \
  --steps 8
```

The agent will research only within `--allow`; any attempt to leave is blocked and logged, and
the run is recorded.

**2. Drop `guard.py` in front of *any* agent** (local or cloud, not just this one):

```python
from guard import Guard, Policy

guard = Guard(Policy(approved_domains=("yourcompany.com",), save_dir="/tmp/out"))

decision = guard.check_visit(url)     # call BEFORE the agent navigates
if decision.allowed:
    agent.visit(url)                  # perform the action
else:
    show_block(url, decision.reason)  # deny + it is already in the audit log
```

That is the whole integration: check before you act, honour the answer, keep the log. No SDK,
no service, no `npx` — it is ~120 lines of standard-library Python.

## Real-world use cases

- **Scoped research / monitoring** — let an agent gather from approved sources with a hard
  guarantee it cannot wander off or exfiltrate.
- **Operating on untrusted sites** — the agent may get prompt-injected; the Guard caps the
  blast radius to the allowlist.
- **Agents over sensitive/internal data** — egress control (DLP-style) for agent actions.
- **Regulated / auditable automation** — a provable record of every action the agent took.

## Threat model (summary)

| Element | Disposition |
|---|---|
| **Assets** | the operator's API keys; the data the agent can reach; third parties who must never receive agent traffic |
| **Trust boundary** | hostile page → agent brain (fallible) → **Guard** → action on the desktop |
| **T-1** Injected instruction causes off-site navigation / exfiltration | **MITIGATED** — allowlist denies every host but the approved one; denial is logged (`guard.py`) |
| **T-2** Agent writes outside its workspace | **MITIGATED** — save is confined to one folder; traversal denied |
| **T-3** API key leaks into the repo/artifacts | **MITIGATED** — keys are env-only, `.env` is gitignored, recordings/logs are gitignored |
| **T-4** Confused agent burns credit | **MITIGATED** — hard step cap + per-session timeout + `finally` teardown |
| **Residual** | the demo's block page loads the real site briefly before the pull-back (detect-and-enforce, not prevent-before-load) |

## Project structure

```
guarded-desktop-agent/
├── guard.py              # The Guard — allowlist + audit (pure, unit-tested)
├── brain.py              # Vision brain — one move from a screenshot (Groq / Gemini)
├── worker.py             # Agent move/state types + the guarded work loop
├── computer.py           # The Computer interface (Dry / Solari / Local backends)
├── solari_computer.py    # Solari desktop backend + the live Guard console
├── run_moltbook_live.py  # Headline demo (recorded)
├── run_guarded.py        # Generic guarded runner (--topic / --start / --allow)
├── run_redteam_demo.py   # BrowseSafe-Bench red-team runs
├── demo_dryrun.py        # Offline, no-keys quickstart
├── test_guard.py         # Guard policy unit tests
├── requirements.txt
├── PAYLOADS.md           # Which real attack samples are used, and their source
└── browsesafe/           # Red-team data prep + block page
```

## Notes and limits

- **Action-level, not a sandbox.** The Guard vets the visits and saves the agent makes
  through the computer interface; it is not a network- or kernel-level containment boundary,
  and does not contain code running outside the agent's browser.
- **The leave is instructed.** In the demo the agent is told to attempt the off-site step —
  the security value is the Guard *denying* it, not the agent going rogue. What it proves:
  when an agent tries to leave its approved site, a simple allowlist stops it, visibly and
  provably.
- **Detect and enforce.** The blocked site loads for a moment before the agent is pulled back;
  the navigation is refused and logged either way.
- **Free-tier brain.** The vision model runs on Groq's free tier (per-minute / per-day token
  caps); long runs pace themselves, and a heavy day may need a fresh key.

## Scripts

Add your keys to `.env` (`SOLARI_API_KEY`, `GROQ_API_KEY`), then `pip install -r requirements.txt`.
The offline dry run needs neither.

```bash
python demo_dryrun.py         # Guard allow / block / audit, offline, no keys
python run_moltbook_live.py   # the recorded moltbook demo (live + mp4)
python run_guarded.py --allow SITE --start URL --topic "..."   # generic guarded agent
python run_redteam_demo.py    # agent vs. real BrowseSafe-Bench injection pages
pytest test_guard.py          # Guard policy unit tests
```

<p align="center">Built with <a href="https://getsolari.com">Solari</a> · Public sources only</p>
