"""Unit tests for the Guard — pure, no agent, no browser, no model, no credit.

    pytest test_guard.py    (or)    python -m pytest
"""

from __future__ import annotations

from guard import Guard, Policy


def _guard(save_dir: str = ".") -> Guard:
    return Guard(Policy(approved_domains=("wikipedia.org", "python.org"), save_dir=save_dir))


def test_visit_allows_approved_domain_and_subdomains():
    g = _guard()
    assert g.check_visit("https://wikipedia.org/wiki/Foo").allowed
    assert g.check_visit("https://en.wikipedia.org/wiki/Foo").allowed  # subdomain
    assert g.check_visit("https://docs.python.org/3/").allowed


def test_visit_blocks_everything_off_list():
    g = _guard()
    assert not g.check_visit("https://ads.doubleclick.net/x").allowed
    assert not g.check_visit("https://evil.example/steal").allowed
    # A lookalike that merely CONTAINS an approved domain must still be blocked.
    assert not g.check_visit("https://wikipedia.org.evil.com/x").allowed


def test_block_carries_a_reason():
    d = _guard().check_visit("https://tracker.example/beacon")
    assert not d.allowed and "approved" in d.reason


def test_save_only_inside_the_approved_folder(tmp_path):
    g = Guard(Policy(("x.com",), str(tmp_path)))
    assert g.allow_save(str(tmp_path / "brief.txt"))
    assert not g.allow_save(str(tmp_path / ".." / "escape.txt"))  # path traversal blocked
    assert not g.allow_save("/etc/passwd")


def test_every_decision_is_recorded_and_renders_a_feed_line():
    g = _guard()
    g.check_visit("https://en.wikipedia.org/a")  # allowed
    g.check_visit("https://bad.example/b")  # blocked
    assert g.summary() == {"total": 2, "allowed": 1, "blocked": 1}
    assert all(d.line() for d in g.decisions)  # each decision shows on the feed
    assert "BLOCKED" in g.decisions[1].line()


def test_on_event_and_audit_fire_for_each_decision(tmp_path):
    seen = []
    audit = tmp_path / "audit.log"
    g = Guard(Policy(("wikipedia.org",), str(tmp_path)),
              on_event=seen.append, audit_path=str(audit))
    g.check_visit("https://en.wikipedia.org/a")
    g.check_visit("https://bad.example/b")
    assert len(seen) == 2  # the live feed got both
    assert audit.read_text(encoding="utf-8").count("\n") == 2  # the receipt got both


if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
