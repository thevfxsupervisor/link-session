#!/usr/bin/env python3
"""Discover, validate and inspect session-bootstrap templates in a repo.

This is the engine behind `/link-session new <repo>`. It is deliberately
CONTENT-FREE: it knows the bootstrap CONTRACT (the field names), never any
particular repo's values. Point it at any repo and it acts on whatever that
repo's own `type: bootstrap` docs declare. Private repos keep their paths,
aliases and tool lists to themselves; this tool only reads a schema.

A bootstrap is any markdown file whose YAML frontmatter has `type: bootstrap`.
Beyond the OKF basics (title, description) it may declare, all optional except
where noted:

    ---
    type: bootstrap                 # REQUIRED, the discovery marker
    title: ...                      # REQUIRED, shown in the pick menu
    description: ...                # REQUIRED, shown in the pick menu
    workspace: <suggested path>     # optional hint, where this seat lives
    role_hint: <prefix>             # optional hint for the link-session role
    boot_sequence:                  # optional, files to read in order
      - knowledge/foo.md
    mounts:                         # optional, checkable required paths
      - {path: X:/scratch, label: what it is}
    tools:                          # optional, checkable recommended tools
      - {name: ComfyUI, detect: X:/ComfyUI, get: <url or note>}
    ---

The body must contain exactly one ```markdown fenced block: that block IS the
starter CLAUDE.md for the new seat. That is the one required piece of body.

Commands:
    discover <repo_dir>   -> JSON array of {key,title,description,path} for the menu
    show <doc>            -> JSON of the full parsed template
    validate <doc>       -> exit 0 if it satisfies the contract, else print errors, exit 1
    checkenv <doc>       -> JSON of mount/tool presence ON THIS BOX (read-only)
"""
import sys, os, json, re, glob
import yaml


def _split(path):
    t = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", t, re.S)
    if not m:
        return {}, t
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, m.group(2)


def _claude_md(body):
    """The one ```markdown fenced block in the body is the starter CLAUDE.md."""
    blocks = re.findall(r"```markdown\n(.*?)```", body, re.S)
    return blocks[0].rstrip("\n") if blocks else None


def is_bootstrap(path):
    fm, _ = _split(path)
    return fm.get("type") == "bootstrap"


def parse(path):
    fm, body = _split(path)
    return {
        "key": os.path.splitext(os.path.basename(path))[0],
        "path": path,
        "type": fm.get("type"),
        "title": fm.get("title"),
        "description": fm.get("description"),
        "workspace": fm.get("workspace"),
        "role_hint": fm.get("role_hint"),
        "boot_sequence": fm.get("boot_sequence") or [],
        "mounts": fm.get("mounts") or [],
        "tools": fm.get("tools") or [],
        "claude_md": _claude_md(body),
    }


def validate(path):
    """Return a list of human-readable problems; empty list means valid."""
    fm, body = _split(path)
    errs = []
    if fm.get("type") != "bootstrap":
        errs.append("frontmatter `type` is not `bootstrap` (this file is not a bootstrap)")
    for req in ("title", "description"):
        v = fm.get(req)
        if not (isinstance(v, str) and v.strip()):
            errs.append("missing or empty required frontmatter field: `%s`" % req)
    if _claude_md(body) is None:
        errs.append("no ```markdown fenced block found: a bootstrap must carry a starter CLAUDE.md")
    for i, m in enumerate(fm.get("boot_sequence") or []):
        if not isinstance(m, str):
            errs.append("boot_sequence[%d] must be a string path" % i)
    for i, m in enumerate(fm.get("mounts") or []):
        if not (isinstance(m, dict) and m.get("path")):
            errs.append("mounts[%d] must be a mapping with a `path`" % i)
    for i, t in enumerate(fm.get("tools") or []):
        if not (isinstance(t, dict) and t.get("name") and t.get("detect")):
            errs.append("tools[%d] must be a mapping with `name` and `detect`" % i)
    return errs


def discover(repo_dir):
    out = []
    for path in sorted(glob.glob(os.path.join(repo_dir, "**", "*.md"), recursive=True)):
        try:
            if not is_bootstrap(path):
                continue
        except (OSError, UnicodeDecodeError):
            continue
        if validate(path):
            continue  # skip malformed ones from the menu; `validate` reports why
        b = parse(path)
        out.append({"key": b["key"], "title": b["title"],
                    "description": b["description"], "path": path})
    return out


def _present(detect):
    """A detect string is a path if it looks like one, else a command on PATH."""
    if re.search(r"[\\/]|^[A-Za-z]:", str(detect)):
        return os.path.exists(os.path.expandvars(os.path.expanduser(str(detect))))
    from shutil import which
    return which(str(detect)) is not None


def checkenv(path):
    b = parse(path)
    mounts = [{"path": m.get("path"), "label": m.get("label"),
               "present": os.path.exists(os.path.expandvars(os.path.expanduser(str(m.get("path")))))}
              for m in b["mounts"]]
    tools = [{"name": t.get("name"), "detect": t.get("detect"), "get": t.get("get"),
              "present": _present(t.get("detect"))}
             for t in b["tools"]]
    return {"mounts": mounts, "tools": tools,
            "missing_mounts": [m["path"] for m in mounts if not m["present"]],
            "missing_tools": [t["name"] for t in tools if not t["present"]]}


def main(argv):
    if len(argv) < 3:
        sys.stderr.write(__doc__)
        return 2
    cmd, arg = argv[1], argv[2]
    if cmd == "discover":
        print(json.dumps(discover(arg), indent=2))
        return 0
    if cmd == "show":
        print(json.dumps(parse(arg), indent=2))
        return 0
    if cmd == "validate":
        errs = validate(arg)
        if errs:
            sys.stderr.write("INVALID bootstrap %s:\n  - %s\n" % (arg, "\n  - ".join(errs)))
            return 1
        print("valid bootstrap: %s" % arg)
        return 0
    if cmd == "checkenv":
        print(json.dumps(checkenv(arg), indent=2))
        return 0
    sys.stderr.write("unknown command: %s\n" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
