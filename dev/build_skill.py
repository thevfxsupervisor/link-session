#!/usr/bin/env python3
"""Embed dev/bootstrap.py into the link-session skill as the `new` section.

The skill installs FLAT (only link-session.md is copied), so the engine cannot
ship as a sibling file: it must live inside the skill. dev/bootstrap.py stays
the canonical, tested source; this script embeds it verbatim between HTML-comment
markers so re-running replaces cleanly (idempotent) and test_bootstrap.py can
verify the embedded copy matches the source byte-for-byte.

Run after editing dev/bootstrap.py:  python build_skill.py
"""
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", ".claude", "commands", "link-session.md")
ENGINE = os.path.join(HERE, "bootstrap.py")

BEGIN = "<!-- BEGIN new-seat (generated from dev/bootstrap.py; edit there, then run dev/build_skill.py) -->"
END = "<!-- END new-seat -->"

PROSE = """## Starting a new seat: `/link-session new <repo>`

**`new` initializes THIS session, it does not spawn another.** Open a fresh Claude Code session in
whatever folder you want, then run `/link-session new <repo>` to turn that empty session into a
registered seat of a chosen type, pulling its starting context and `CLAUDE.md` from a repo you name.
The repo holds the templates; this skill stays generic and holds none of any one repo's private
detail.

### What a bootstrap template is (the contract)

A template is any markdown file in the repo whose YAML frontmatter says `type: bootstrap`. Its
`title` and `description` are what the picker shows. Optionally it declares the environment the seat
needs, so `new` can verify it before you start work:

```yaml
---
type: bootstrap                 # REQUIRED - the discovery marker
title: ...                      # REQUIRED - shown in the pick menu
description: ...                # REQUIRED - shown in the pick menu
workspace: <suggested path>     # optional - where this seat should live
role_hint: <prefix>             # optional - suggested link-session role
boot_sequence:                  # optional - files to read, in order
  - path/to/file.md
mounts:                         # optional - paths that must be reachable
  - {path: X:/scratch, label: what it is}
tools:                          # optional - tools/assets to check for
  - {name: ExampleTool, detect: X:/ExampleTool, get: <url or note>}
---
```

The body must contain exactly one ` ```markdown ` fenced block: that block IS the starter `CLAUDE.md`
for the seat. Keep secrets out of a template as you would any repo file; nothing here is a private
store.

### The flow

1. **Resolve + authorise the repo.** If a local clone exists, use it (offer a pull). Otherwise check
   you can reach it (`gh auth status`, or your git credentials) and clone a per-seat copy, one clone
   per seat, never share a working tree. No access -> say exactly what is missing (`gh auth login`, a
   deploy key, or a fine-grained token the principal installs) and stop. Never accept a credential
   in-band through the prompt.
2. **Discover + pick.** Run the engine below with `discover <repo_dir>`; it returns the valid
   templates as `{key,title,description}`. Zero -> say so and point at this format. One -> confirm it.
   Many -> show a numbered menu of title + description and let the user choose.
3. **Load context.** Read the chosen template's `boot_sequence` files, in order, into this session.
   That reading IS the inheritance: a fresh seat reconstructs its working state from durable files,
   not from another session's transcript.
4. **Import to `CLAUDE.md`.** Write the template's starter `CLAUDE.md` into the workspace. If a
   `CLAUDE.md` already exists, do NOT overwrite it: show the difference and append the section, or
   write `CLAUDE.local.md` alongside, and let the user decide.
5. **Verify the environment.** Run `checkenv <template>`. It reports which declared `mounts` are
   reachable and which `tools` are present ON THIS BOX. For anything missing, name it and either help
   mount it or ask for access. Tool checks are read-only: report what is missing and how to get it,
   never auto-install or download large assets.
6. **Join.** Fall through to the normal invocation above: claim a registered role (honour `role_hint`,
   but check for a live incumbent first), write your outbox, start exactly one monitor.

### The engine

Write this to a temp file and run it (`python bootstrap.py <cmd> <arg>`). It is content-free: it knows
the contract, never a repo's values. `discover <dir>` lists valid templates, `show <doc>` dumps one,
`validate <doc>` checks conformance (non-zero exit on problems), `checkenv <doc>` reports mount/tool
presence here.

````python
%s````"""


def render():
    engine = open(ENGINE, encoding="utf-8").read()
    return BEGIN + "\n" + (PROSE % engine) + "\n" + END


def main():
    t = open(SKILL, encoding="utf-8").read()
    block = render()
    if BEGIN in t and END in t:
        t = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block, t, flags=re.S)
    else:
        anchor = "## The pattern behind most failures here"
        t = t.replace("---\n\n" + anchor, block + "\n\n---\n\n" + anchor, 1)
    with open(SKILL, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(t)
    print("embedded new-seat section into", os.path.normpath(SKILL))


if __name__ == "__main__":
    main()
