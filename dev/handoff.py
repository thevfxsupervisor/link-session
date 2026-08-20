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
- unacked(peers, mine, me): the invocation-time sweep. Warns about handoffs to
  me I have not acked, and my own offer that its target has not acked. This is
  what keeps a pending handoff VISIBLE rather than firing once and vanishing.
"""


def _recips(v):
    return str(v or "").replace(",", " ").split()


def handoff_line(peer, mine, me):
    pdata = peer.get("data") or {}
    ho = pdata.get("handoff") or {}
    ak = pdata.get("ack") or {}
    mdata = mine.get("data") or {}
    my_ho = mdata.get("handoff") or {}
    my_ak = mdata.get("ack") or {}
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
    mdata = mine.get("data") or {}
    my_ho = mdata.get("handoff") or {}
    my_ak = mdata.get("ack") or {}
    for p in peers:
        ho = (p.get("data") or {}).get("handoff") or {}
        if ho.get("id") and me in _recips(ho.get("to")) and my_ak.get("id") != ho.get("id"):
            warns.append("UNACKED handoff from %s: %s"
                         % (p.get("session"), str(ho.get("task") or "")[:80]))
    if my_ho.get("id"):
        target = _recips(my_ho.get("to"))
        acked = any((p.get("data") or {}).get("ack", {}).get("id") == my_ho["id"]
                    for p in peers if p.get("session") in target)
        if not acked:
            warns.append("your handoff to %s is UNACKED: %s"
                         % (my_ho.get("to"), str(my_ho.get("task") or "")[:80]))
    return warns
