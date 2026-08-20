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

Hardened after review by permafrost-bidding (2026-08-20): `to` may be a real
JSON list (not only a comma/space string), and `data`/`handoff`/`ack` may be
malformed (a non-dict), which must NOT raise - an exception here would crash the
monitor and deafen the seat. Coerce on TYPE, never on truthiness.
"""


def _recips(v):
    if isinstance(v, (list, tuple)):
        return [str(t).strip() for t in v if str(t).strip()]
    return str(v or "").replace(",", " ").split()


def _dict(v):
    return v if isinstance(v, dict) else {}


def handoff_line(peer, mine, me):
    pdata = _dict(peer.get("data"))
    ho = _dict(pdata.get("handoff"))
    ak = _dict(pdata.get("ack"))
    mdata = _dict(mine.get("data"))
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
    mdata = _dict(mine.get("data"))
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
