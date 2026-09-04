"""The Guard — a simple, un-trickable rule-checker in front of every Worker action.

It does NOT judge whether a website is "genuine" or "fake" (nobody can do that
reliably). It enforces an ALLOWLIST the operator sets up front:

  * the Worker may VISIT only approved domains, and
  * the Worker may SAVE only inside one approved folder.

Everything else is denied by default. Every decision — allow OR deny — is emitted
live (for the on-screen feed you watch in the video) and appended to an audit log,
so what the agent did is provable afterward.

Pure and dependency-free on purpose: a simple rule can't be talked out of its
answer the way a clever model can, and the policy unit-tests with no agent,
no browser, and no model.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Policy:
    """What the Worker is allowed to do. Written by the operator, up front."""

    approved_domains: tuple[str, ...]  # e.g. ("en.wikipedia.org", "python.org")
    save_dir: str  # the ONE folder the Worker may write files into
    deny_reason: str = "not on the approved list"  # shown when a visit is blocked


@dataclass
class Decision:
    """One yes/no about one intended action. This is exactly what the on-screen
    feed shows and what the audit log stores."""

    allowed: bool
    kind: str  # "visit" | "save"
    target: str  # the domain or filename in question
    reason: str = ""
    at: str = field(default_factory=lambda: dt.datetime.now().strftime("%H:%M:%S"))

    def line(self) -> str:
        """One human-readable feed line, e.g.
        [10:02:19]  visit  ads.tracker.example   BLOCKED  (not on the approved list)"""
        verdict = "ALLOWED" if self.allowed else "BLOCKED"
        tail = "" if self.allowed else f"  ({self.reason})"
        return f"[{self.at}]  {self.kind:5}  {self.target[:44]:44}  {verdict}{tail}"

    def as_dict(self) -> dict:
        return {
            "at": self.at, "kind": self.kind, "target": self.target,
            "allowed": self.allowed, "reason": self.reason,
        }


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _domain_ok(host: str, approved: tuple[str, ...]) -> bool:
    """Allow an exact domain or any of its subdomains; nothing else. So
    'en.wikipedia.org' is allowed by approving 'wikipedia.org', but a lookalike
    like 'wikipedia.org.evil.com' is NOT (it doesn't end in '.wikipedia.org')."""
    return any(host == d or host.endswith("." + d) for d in approved)


class Guard:
    """Checks each intended action against the Policy, records the decision, and
    (optionally) streams it to a live feed and an audit file."""

    def __init__(
        self,
        policy: Policy,
        on_event: Optional[Callable[[Decision], None]] = None,
        audit_path: Optional[str] = None,
    ) -> None:
        self.policy = policy
        self._on_event = on_event
        self._audit_path = audit_path
        self.decisions: list[Decision] = []

    def check_visit(self, url: str) -> Decision:
        host = _host(url)
        ok = _domain_ok(host, self.policy.approved_domains)
        return self._record(
            Decision(ok, "visit", host or url, "" if ok else self.policy.deny_reason)
        )

    def check_save(self, path: str) -> Decision:
        root = os.path.realpath(self.policy.save_dir)
        full = os.path.realpath(path)
        inside = full == root or full.startswith(root + os.sep)
        name = os.path.basename(path) or path
        return self._record(
            Decision(inside, "save", name, "" if inside else "outside the approved folder")
        )

    # Convenience booleans for the Worker's call sites.
    def allow_visit(self, url: str) -> bool:
        return self.check_visit(url).allowed

    def allow_save(self, path: str) -> bool:
        return self.check_save(path).allowed

    def _record(self, d: Decision) -> Decision:
        self.decisions.append(d)
        if self._on_event is not None:
            self._on_event(d)  # the live on-screen feed
        if self._audit_path is not None:
            with open(self._audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(d.as_dict()) + "\n")  # the saved receipt
        return d

    def summary(self) -> dict:
        allowed = sum(1 for d in self.decisions if d.allowed)
        return {"total": len(self.decisions), "allowed": allowed,
                "blocked": len(self.decisions) - allowed}
