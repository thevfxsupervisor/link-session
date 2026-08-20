#!/usr/bin/env python3
"""Tests for handoff.py (monitor-time handoff_line + invocation-time unacked),
plus a drift guard that the exact source is embedded in the shipped skill.
Exit 0 iff every criterion passes.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import handoff as H

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print("  %-6s %s%s" % ("PASS" if cond else "FAIL", name, (" - " + detail) if detail and not cond else ""))


def ob(session, **data):
    return {"session": session, "status": "", "data": data}


def main():
    ME = "mint"

    # --- handoff_line: receiver side ---
    offer = ob("ws14", handoff={"id": "h1", "to": "mint", "task": "convert frontmatter", "detail": "ws14-HANDOFF-h1.md"})
    mine_none = ob("mint")
    line = H.handoff_line(offer, mine_none, ME)
    check("hl.offer-to-me-unacked", line and "HANDOFF from ws14" in line and "convert frontmatter" in line, repr(line))
    check("hl.offer-shows-detail", line and "ws14-HANDOFF-h1.md" in line, repr(line))

    mine_acked = ob("mint", ack={"id": "h1", "verdict": "accepted", "understood": "add type:bootstrap"})
    check("hl.offer-to-me-acked-silent", H.handoff_line(offer, mine_acked, ME) is None)

    offer_other = ob("ws14", handoff={"id": "h9", "to": "demoreel", "task": "x"})
    check("hl.offer-to-other-silent", H.handoff_line(offer_other, mine_none, ME) is None)

    # --- handoff_line: sender side (I offered, peer acks) ---
    my_offer = ob("ws14", handoff={"id": "h2", "to": "mint", "task": "do the thing"})
    peer_ack = ob("mint", ack={"id": "h2", "verdict": "accepted", "understood": "I will do the thing"})
    line2 = H.handoff_line(peer_ack, my_offer, "ws14")
    check("hl.peer-acks-my-offer", line2 and "mint ACKed your handoff [accepted]" in line2 and "I will do the thing" in line2, repr(line2))

    peer_decline = ob("mint", ack={"id": "h2", "verdict": "declined", "understood": "", "reason": "no GPU free"})
    line3 = H.handoff_line(peer_decline, my_offer, "ws14")
    check("hl.decline-shows-reason", line3 and "[declined]" in line3 and "no GPU free" in line3, repr(line3))

    ack_not_mine = ob("mint", ack={"id": "zzz", "verdict": "accepted"})
    check("hl.ack-not-mine-silent", H.handoff_line(ack_not_mine, my_offer, "ws14") is None)

    check("hl.nothing-silent", H.handoff_line(ob("ws14"), ob("mint"), ME) is None)

    # --- unacked: invocation sweep ---
    peers = [offer, ob("demoreel")]
    w = H.unacked(peers, mine_none, ME)
    check("un.receiver-unacked", any("UNACKED handoff from ws14" in x for x in w), repr(w))
    check("un.receiver-acked-clear", H.unacked(peers, mine_acked, ME) == [])

    my_ob = ob("ws14", handoff={"id": "h3", "to": "mint", "task": "later task"})
    peers2 = [ob("mint")]  # target present, not acked
    w2 = H.unacked(peers2, my_ob, "ws14")
    check("un.sender-unacked", any("your handoff to mint is UNACKED" in x for x in w2), repr(w2))

    peers3 = [ob("mint", ack={"id": "h3", "verdict": "accepted"})]
    check("un.sender-acked-clear", H.unacked(peers3, my_ob, "ws14") == [])

    # --- MALFORMED INPUT (the review by permafrost-bidding + macbook-wintermute). These must never
    # raise: an exception inside handoff_line runs in the monitor loop and would deafen the seat.
    # 1) `to` as a real JSON list must reach the seats it names (not stringify to garbage).
    offer_list = ob("ws14", handoff={"id": "hL", "to": ["mint", "demoreel"], "task": "list route"})
    ll = H.handoff_line(offer_list, mine_none, ME)
    check("mal.list-to-reaches", ll and "HANDOFF from ws14" in ll, repr(ll))
    check("mal.list-to-unacked-sweep", any("hL" for _ in [0]) and
          any("UNACKED handoff from ws14" in x for x in H.unacked([offer_list], mine_none, ME)))
    # 2) a non-dict handoff/ack must be ignored, not crash.
    try:
        r = H.handoff_line(ob("ws14", handoff="oops not a dict"), mine_none, ME)
        check("mal.nondict-handoff", r is None)
    except Exception as e:
        check("mal.nondict-handoff", False, "raised %r" % e)
    try:
        r = H.handoff_line(ob("mint", ack=["not", "a", "dict"]), my_offer, "ws14")
        check("mal.nondict-ack", r is None)
    except Exception as e:
        check("mal.nondict-ack", False, "raised %r" % e)
    # 3) a non-dict `data` on EITHER side (peer's, or my own) must not crash - macbook's third find.
    try:
        peer_baddata = {"session": "ws14", "status": "", "data": "not a dict"}
        check("mal.nondict-peer-data", H.handoff_line(peer_baddata, mine_none, ME) is None)
    except Exception as e:
        check("mal.nondict-peer-data", False, "raised %r" % e)
    try:
        my_baddata = {"session": "mint", "status": "", "data": 12345}
        check("mal.nondict-my-data", H.handoff_line(offer, my_baddata, ME) is not None)  # still surfaces
    except Exception as e:
        check("mal.nondict-my-data", False, "raised %r" % e)
    try:
        check("mal.unacked-nondict-data", H.unacked([{"session": "ws14", "data": "x"}], {"data": None}, ME) == [])
    except Exception as e:
        check("mal.unacked-nondict-data", False, "raised %r" % e)

    # --- drift guard: the exact source is embedded in the shipped skill ---
    skill = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "commands", "link-session.md")
    if os.path.exists(skill):
        md = open(skill, encoding="utf-8").read()
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "handoff.py"), encoding="utf-8").read()
        for fn in ("def _recips(", "def _dict(", "def handoff_line(", "def unacked("):
            body = src[src.index(fn):]
            # take up to the next top-level def after this one (or EOF)
            nxt = body.find("\ndef ", 1)
            body = body[:nxt] if nxt != -1 else body
            check("drift.%s" % fn.split("(")[0].split()[-1], body.strip() in md,
                  "function %s not embedded verbatim in skill - run build" % fn)
    else:
        check("drift.skill-present", False, "skill md not found")

    print("")
    passed = sum(1 for _, ok in results if ok)
    print("=== %d/%d criteria passed ===" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
