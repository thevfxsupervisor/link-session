#!/usr/bin/env python3
"""Self-contained tests for bootstrap.py. Builds fixture templates in a temp
dir, exercises discover/parse/validate/checkenv, and asserts each planned
criterion. Exit 0 iff every criterion passes.

Run:  python test_bootstrap.py
"""
import os, sys, re, tempfile, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bootstrap as B

FIXTURES = {
    # valid, full
    "valid_seat.md": """---
type: bootstrap
title: Example render seat
description: A generic worked example, used only in tests. No private content.
tags: [example, test]
workspace: /example/workspace
role_hint: render
boot_sequence:
  - knowledge/example-pipeline.md
  - knowledge/example-tools.md
mounts:
  - {path: /example/scratch, label: scratch space}
tools:
  - {name: ExampleTool, detect: /example/bin/tool, get: https://example.com}
---

# Example render seat

Generic example. No private content.

## Starter CLAUDE.md

```markdown
# CLAUDE.md - example render seat
Read the boot sequence, then run /link-session.
```
""",
    # valid, minimal (only the required pieces)
    "minimal_seat.md": """---
type: bootstrap
title: Minimal seat
description: The smallest valid bootstrap, required fields plus a CLAUDE.md block.
---

```markdown
# CLAUDE.md - minimal seat
```
""",
    # not a bootstrap at all
    "not_a_bootstrap.md": """---
type: reference
title: Some reference doc
description: Should never appear in discovery.
---

Body.
""",
    # type: bootstrap but no CLAUDE.md block
    "invalid_no_claude.md": """---
type: bootstrap
title: No claude block
description: Missing the required markdown block.
---

Just prose, no fenced markdown block.
""",
    # type: bootstrap but a mount entry has no path
    "invalid_bad_mount.md": """---
type: bootstrap
title: Bad mount
description: A mount entry with no path.
mounts:
  - {label: has a label but no path}
---

```markdown
# CLAUDE.md
```
""",
    # type: bootstrap but no title
    "invalid_no_title.md": """---
type: bootstrap
description: Missing the title.
---

```markdown
# CLAUDE.md
```
""",
}

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print("  %-6s %s%s" % ("PASS" if cond else "FAIL", name, (" - " + detail) if detail and not cond else ""))


def main():
    repo = tempfile.mkdtemp(prefix="bootstrap_test_")
    try:
        for fn, content in FIXTURES.items():
            with open(os.path.join(repo, fn), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)

        # Criterion 1: discovery finds exactly the VALID bootstraps, ignoring
        # non-bootstrap docs and malformed bootstraps.
        found = B.discover(repo)
        keys = sorted(b["key"] for b in found)
        check("1.discover-count", len(found) == 2, "got %d: %s" % (len(found), keys))
        check("1.discover-keys", keys == ["minimal_seat", "valid_seat"], "got %s" % keys)
        check("1.menu-shape",
              all(set(b) == {"key", "title", "description", "path"} for b in found),
              "menu entries must be key/title/description/path only")

        # Criterion 2: a valid template parses into every contract field.
        v = B.parse(os.path.join(repo, "valid_seat.md"))
        check("2.parse-title", v["title"] == "Example render seat")
        check("2.parse-desc", bool(v["description"]))
        check("2.parse-bootseq", v["boot_sequence"] == ["knowledge/example-pipeline.md", "knowledge/example-tools.md"])
        check("2.parse-mounts", v["mounts"] and v["mounts"][0]["path"] == "/example/scratch")
        check("2.parse-tools", v["tools"] and v["tools"][0]["name"] == "ExampleTool")
        check("2.parse-claudemd", v["claude_md"] and "CLAUDE.md - example render seat" in v["claude_md"])
        check("2.parse-claudemd-clean", v["claude_md"] and "```" not in v["claude_md"],
              "extracted CLAUDE.md must not include fence markers")

        # Criterion 3: valid templates validate clean.
        check("3.valid-full", B.validate(os.path.join(repo, "valid_seat.md")) == [])
        check("3.valid-minimal", B.validate(os.path.join(repo, "minimal_seat.md")) == [])

        # Criterion 4: malformed templates are rejected, each for the right reason.
        e_claude = " ".join(B.validate(os.path.join(repo, "invalid_no_claude.md")))
        check("4.reject-no-claude", "CLAUDE.md" in e_claude, e_claude)
        e_mount = " ".join(B.validate(os.path.join(repo, "invalid_bad_mount.md")))
        check("4.reject-bad-mount", "mounts[0]" in e_mount, e_mount)
        e_title = " ".join(B.validate(os.path.join(repo, "invalid_no_title.md")))
        check("4.reject-no-title", "title" in e_title, e_title)
        e_type = " ".join(B.validate(os.path.join(repo, "not_a_bootstrap.md")))
        check("4.reject-not-bootstrap", "type" in e_type, e_type)

        # Criterion 5: checkenv reports mount/tool presence on THIS box, read-only.
        # Build a template with one path that exists (the temp dir) and one that does not.
        envdoc = os.path.join(repo, "env_seat.md")
        with open(envdoc, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("---\ntype: bootstrap\ntitle: Env seat\ndescription: env test\n"
                     "mounts:\n  - {path: %s, label: exists}\n  - {path: %s, label: missing}\n"
                     "tools:\n  - {name: RealDir, detect: %s, get: n/a}\n"
                     "  - {name: Nope, detect: /definitely/not/here/xyz, get: n/a}\n---\n\n"
                     "```markdown\n# CLAUDE.md\n```\n"
                     % (repo.replace("\\", "/"), "/definitely/not/here/xyz", repo.replace("\\", "/")))
        env = B.checkenv(envdoc)
        check("5.mount-present", env["mounts"][0]["present"] is True)
        check("5.mount-missing", env["mounts"][1]["present"] is False)
        check("5.missing-mounts-list", env["missing_mounts"] == ["/definitely/not/here/xyz"])
        check("5.tool-present", env["tools"][0]["present"] is True)
        check("5.tool-missing", env["tools"][1]["present"] is False)
        check("5.missing-tools-list", env["missing_tools"] == ["Nope"])

        # Criterion 6: the engine embedded in the shipped skill matches the
        # canonical source byte-for-byte (no paste drift; what ships is tested).
        skill = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", ".claude", "commands", "link-session.md")
        if os.path.exists(skill):
            md = open(skill, encoding="utf-8").read()
            m = re.search(r"````python\n(.*?)````", md, re.S)
            src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bootstrap.py"),
                       encoding="utf-8").read()
            check("6.embedded-present", m is not None, "no embedded engine found in skill md")
            check("6.embedded-matches", bool(m) and m.group(1) == src,
                  "embedded engine differs from bootstrap.py - run build_skill.py")
        else:
            check("6.skill-present", False, "skill md not found at %s" % skill)

        print("")
        passed = sum(1 for _, ok, _ in results if ok)
        total = len(results)
        print("=== %d/%d criteria passed ===" % (passed, total))
        return 0 if passed == total else 1
    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
