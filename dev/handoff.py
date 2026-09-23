#!/usr/bin/env python3
"""Handoff correlation for link-session, pure and testable.

A handoff has a visible lifecycle so the silent failure link-session names as
its worst - "an unread request looks exactly like work in progress" - becomes a
visible PENDING state instead.

- The OFFERER sets `data.handoff = {id, to, task, detail}` in its own outbox
  (after writing the detail .md, doorbell order). One open handoff per outbox,
  single-slot like `message`.
- The RECEIVER acks in ITS OWN outbox (one-writer preserved):
  `data.ack = {id, verdict: accepted|declined, understood, reason?}`.
  `understood` restates the task in the receiver's own words - that restatement
  is the check that catches "received but misread".

Two views:
- handoff_line(peer, mine, me): the monitor's per-peer surface. A handoff to me
  that I have not acked PUSHES (even with no message); a peer's ack of MY offer
  pushes back. Returns a line or None.
- unacked(peers, mine, me): the invocation-time sweep that keeps a pending
  handoff VISIBLE rather than firing once and vanishing.

Hardened after review: `to` may be a real
JSON list (not only a comma/space string), and `data`/`handoff`/`ack` may be
malformed (a non-dict), which must NOT raise - an exception here would crash the
monitor and deafen the seat. Coerce on TYPE, never on truthiness.
"""


_SWEEP_LOUD = ('CORRECTION', 'RETRACT', 'SECURITY', 'HAZARD')
_SWEEP_SEEN_MAX = 200


def _sweep_seen(path):
    """Hashes of pending messages this seat has already surfaced. FAILS OPEN.

    **Why this exists, and it is a defect I shipped and then watched.** Surfacing pending
    messages at baseline (2026-09-23) fixed a silent drop and created a permanent nag: a
    message the sender never clears re-fires on EVERY monitor restart, and a monitor is
    restarted every thirty minutes by the harness. Measured within the hour: a `CORRECTION`
    from a seat that had not written for twelve hours, on another box, whose session may
    well be closed, so nothing will ever clear it. A handoff cannot do this because the
    receiver acks in its own outbox; a plain message has no ack, so the suppression has to
    be local.

    Per-seat local state, not channel content: dot-prefixed, and it carries no `session` or
    `status` key so the monitor's peer-shape filter ignores it.

    **Every failure path returns "nothing seen", which means emit.** A repeated line costs a
    glance; a swallowed one is the bug this whole sweep exists to prevent, so the degraded
    behaviour must be the noisy one."""
    if not path:
        return set()
    try:
        import json as _j
        with open(path) as fh:
            v = _j.load(fh)
        return set(v) if isinstance(v, list) else set()
    except Exception:
        return set()


def _sweep_remember(path, hashes):
    """Record what was surfaced. Best effort: failing to write must never lose a line."""
    if not path or not hashes:
        return
    try:
        import json as _j
        keep = list(_sweep_seen(path)) + list(hashes)
        with open(path, "w") as fh:
            _j.dump(keep[-_SWEEP_SEEN_MAX:], fh)
    except Exception:
        pass


def _sweep_key(sess, msg):
    import hashlib as _h
    return _h.md5(("%s\x00%s" % (sess, msg)).encode("utf-8")).hexdigest()[:16]


def _sweep_text(v):
    """Any shape -> a stripped string, for the same reason `_text` exists in the monitor."""
    if v is None:
        return ""
    if isinstance(v, (list, tuple, set)):
        return " ".join(str(x) for x in v).strip()
    return str(v).strip()


def _recips(v):
    if isinstance(v, (list, tuple)):
        return [str(t).strip() for t in v if str(t).strip()]
    return str(v or "").replace(",", " ").split()


def _dict(v):
    return v if isinstance(v, dict) else {}


def handoff_line(peer, mine, me):
    # YOUR OWN OUTBOX IS INPUT, NOT AN INVARIANT. It is a .json on a shared mount that a human, a
    # tool, or a half-finished edit can reshape, so it gets a stranger's validation. If `mine` ever
    # parses to a non-dict, `mine.get` raises AttributeError; the monitor's try/except then swallows
    # it and EVERY handoff addressed to you is dropped silently, forever, while the loop looks
    # healthy. That is the exact silent-handoff failure this feature exists to prevent.
    pdata = _dict(_dict(peer).get("data"))
    ho = _dict(pdata.get("handoff"))
    ak = _dict(pdata.get("ack"))
    mdata = _dict(_dict(mine).get("data"))
    my_ho = _dict(mdata.get("handoff"))
    my_ak = _dict(mdata.get("ack"))
    lines = []
    if ho.get("id") and me in _recips(ho.get("to")) and my_ak.get("id") != ho.get("id"):
        det = (" - see %s" % ho["detail"]) if ho.get("detail") else ""
        lines.append("HANDOFF from %s [NEEDS ACK]: %s%s"
                     % (peer.get("session"), str(ho.get("task") or "")[:120], det))
    if ak.get("id") and ak.get("id") == my_ho.get("id"):
        extra = str(ak.get("understood") or "")[:120]
        if ak.get("verdict") == "declined" and ak.get("reason"):
            extra = (extra + " - " + str(ak["reason"]))[:180]
        lines.append("%s ACKed your handoff [%s]: %s"
                     % (peer.get("session"), str(ak.get("verdict") or "?"), extra))
    return "\n".join(lines) if lines else None


def unacked(peers, mine, me):
    warns = []
    mdata = _dict(_dict(mine).get("data"))   # same reason as handoff_line: `mine` is untrusted
    my_ho = _dict(mdata.get("handoff"))
    my_ak = _dict(mdata.get("ack"))
    for p in peers:
        ho = _dict(_dict(p.get("data")).get("handoff"))
        if ho.get("id") and me in _recips(ho.get("to")) and my_ak.get("id") != ho.get("id"):
            warns.append("UNACKED handoff from %s: %s"
                         % (p.get("session"), str(ho.get("task") or "")[:80]))
    if my_ho.get("id"):
        target = _recips(my_ho.get("to"))
        acked = any(_dict(_dict(p.get("data")).get("ack")).get("id") == my_ho["id"]
                    for p in peers if p.get("session") in target)
        if not acked:
            warns.append("your handoff to %s is UNACKED: %s"
                         % (my_ho.get("to"), str(my_ho.get("task") or "")[:80]))
    return warns


def startup_sweep(peers, mine, me, seen_path=None):
    """One-shot on the monitor's baseline pass: pending HANDOFFS **and pending MESSAGES**.

    Baseline-never-replay is right for STATUS, which is progress you can read on demand. It
    is wrong for a handoff, and it is equally wrong for a MESSAGE addressed to you, which
    this function did not cover until 2026-09-23.

    **Measured, on a live channel.** `straylight-build` wrote a message at 09:08:30 pointing
    at a file it wanted read. `lx03-straylight`'s monitor started about ninety seconds later,
    recorded that outbox as baseline, and never emitted it. The seat found it by hand only
    because it was deciding whether to stop watching a channel it believed was silent, and a
    second one was hiding the same way on the fleet channel: a `CORRECTION` from
    `ws14-projects`, a LOUD marker, swallowed by the same baseline.

    **The window is exactly the case a restart creates**, which is the case link-session tells
    you to expect: re-invoke after a compaction or restart. So the message most likely to be
    lost is the one a peer sent while you were down, which is the one that mattered.

    The filter mirrors the monitor's push rule, so nothing surfaces here that would not have
    surfaced live: a message FOR me, a broadcast, or a loud marker."""
    out = []
    for p in peers:
        try:
            line = handoff_line(p, mine, me)
        except Exception:
            line = None
        if line:
            out.append(line)
    already = _sweep_seen(seen_path)
    fresh = []
    for p in peers:
        try:
            msg = _sweep_text(_dict(p).get("message"))
            if not msg:
                continue
            blob = (_sweep_text(_dict(p).get("status")) + " " + msg).upper()
            loud = any(k in blob for k in _SWEEP_LOUD)
            recips = _recips(_dict(p).get("to"))
            if recips and me not in recips and not loud:
                continue
            sess = _dict(p).get("session")
            # ONCE PER SEAT, NOT ONCE PER RESTART. Keyed on (sender, message) so an EDITED
            # message is a new one and surfaces again, which is what an edit means.
            key = _sweep_key(sess, msg)
            if key in already:
                continue
            fresh.append(key)
            out.append("PENDING AT STARTUP from %s%s: %s"
                       % (sess, "  [LOUD]" if loud else "", msg[:200]))
        except Exception:
            continue
    _sweep_remember(seen_path, fresh)
    return out
