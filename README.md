# link-session

A [Claude Code](https://claude.com/claude-code) skill for coordinating two or more live agent
sessions over shared files. No server, no daemon, no message bus: just JSON outboxes on a shared
folder and a lightweight file watcher, so agents on the same box or across machines can hand off
work, report progress, and stay out of each other's way.

I built this running a fleet of agents across Windows, macOS, and Linux boxes, on several concurrent
projects. The sessions needed to coordinate (who owns which file, what changed, when a job finished)
without a heavyweight orchestration layer. A shared folder plus a simple contract turned out to be
enough, and it survives the things that usually break coordination: context compaction, a session
restart, and a flaky network mount.

## A quick example

Two sessions on one production. One is copying rendered shots, the other is waiting to conform them.

```
renders.json    {"session":"renders","status":"6/23 shots copied","done":false,...}
conform.json    {"session":"conform","status":"waiting on renders","done":false,...}
```

The `conform` session runs a watcher over the channel folder. When `renders` updates its outbox to
`"23/23 shots copied","done":true`, the watcher surfaces that line in the conform session, which
picks up the work. Nobody polled, nothing was double-started, and if either session had died and
restarted, the file still said exactly where things stood.

## What it does

- Each session writes ONE JSON outbox (`<session>.json`) into a shared channel folder.
- A session's name is its ROLE in the coordination, not just its working directory. One box can hold
  several roles.
- A file-watcher Monitor tails the other outboxes and surfaces their status and messages as they
  change, so you find out about a peer's progress without polling.
- A small set of rules (below) keeps it safe under real concurrency and unreliable mounts.

## Starting a new session from a template

`/link-session new <repo>` bootstraps a fresh session into a role. You start Claude in a folder, then
point it at a repo that carries `type: bootstrap` templates: the skill lists them, you pick one, and
it loads that role's starting context, writes its `CLAUDE.md`, and checks that the folders and tools
the role needs are present before you begin. The templates live in whatever repo you name; the skill
itself stays generic and holds none of their content. The template format is documented in the skill.

## The rules that keep it safe

These exist because each one failed in production first. They are the difference between a toy and
something you trust across machines.

- **One writer per file.** Two processes on one outbox overwrite each other, and on a synced store
  concurrent writes spawn conflicted copies where the real file reflects neither. You write only your
  own outbox and your own author-named files.
- **Doorbell order: file first, outbox last.** A long payload goes in a separate `.md`; the outbox
  `message` only points at it. Write the file, THEN bump the JSON, because the JSON is what wakes
  peers and it must change only once the thing it points at is complete.
- **Baseline on first sight, never replay.** A watcher records every peer's current state without
  emitting it, or every restart dumps the channel's whole history into a session that just began.
- **Fire on content, not mtime.** An identical re-save must wake nobody, so change is detected by
  hashing the meaningful fields, not the file's timestamp.
- **Identify peers by shape, not extension.** A real outbox has `session` and `status`. Everything
  else in the folder is somebody's working file, and treating every `.json` as a peer eventually
  adopts a cache as a colleague.
- **A message on the channel is not authorization.** Instructions come from the principal. Text a
  file claims was approved is a claim, not an approval; otherwise anything with write access to the
  folder could escalate its own permissions by writing a sentence.
- **Size is a context budget.** Every field you write is pulled into every peer's context on every
  change, so status is capped to a line and long content lives in a file, not the outbox.

## What it survives

- **Context compaction.** The channel is files, so a compacted session re-reads the current state
  instead of losing it. Re-invoke `/link-session` to rebuild the watcher and catch up.
- **A session restart.** The outbox is the source of truth and it is still on disk. A watcher process
  does not survive a full restart, so it is relaunched; the state it was watching does.
- **A dropped mount.** A vanished channel looks exactly like a quiet one, so the hardened watcher
  warns loudly when the mount goes away rather than reporting silence as calm.

## Install

Drop the command into your Claude Code commands directory:

```bash
# Global (all projects)
mkdir -p ~/.claude/commands
cp .claude/commands/link-session.md ~/.claude/commands/

# Or project-level
mkdir -p your-project/.claude/commands
cp .claude/commands/link-session.md your-project/.claude/commands/
```

Then invoke `/link-session` in any session you want to link. Run it again after a compaction or a
restart to catch up on missed messages and rebuild the watcher.

## The outbox contract

```json
{"session":"renders","updated":"2026-05-23 14:30:00","status":"6/23 shots copied","message":"","to":"","data":{},"done":false,"stop":false}
```

- `status`: an always-current one-liner; update it on meaningful progress. Keep it stable when
  nothing changed, so an unchanged check wakes nobody.
- `message`: a one-off note to peers; clear it once acknowledged. Long payloads go in a separate file
  in the channel, not here (this field is a single slot and overwrites).
- `to`: optional target session when the channel has three or more participants. It is an advisory
  hint, not access control: everyone can read every outbox.
- `updated`: from the shell clock; an agent cannot read the wall clock unaided.
- `done` / `stop`: both true closes the channel, via a stop protocol so no peer is left hanging.

## Monitoring

The skill includes ready-to-run watcher scripts for PowerShell (Windows) and bash / Python
(macOS / Linux), in polling, adaptive-backoff, and event-driven variants. They emit a peer's status
line whenever its outbox changes, and in the hardened form warn loudly if the shared mount drops
instead of looping silently. The watcher counts its own instances correctly before launching,
because two watchers deliver every event twice and look exactly like a healthy channel. See the skill
file for the full patterns and the safety and stop protocols.

## When to use it, and when not

Use it when several live agent sessions share the same files or production and must not collide, and
you want coordination without standing up infrastructure. It is deliberately for LIVE, ephemeral
coordination.

Do not use it as a database or a durable message log. Anything that must stay identical across
machines (shared config, skills, portable knowledge) belongs in version control, which is
mount-independent and versioned. The channel is a coordination surface, not a source of truth for
things you would be sad to lose.

## Why files instead of a message bus

Because it is boring, portable, and durable. A shared folder works the same on every OS, needs no
service to be running, leaves a readable audit trail, and the state survives a session dying. The
whole design leans into that: the file is the source of truth, and the watcher is just a convenience
for not having to re-read it by hand.

## License

MIT. See [LICENSE](LICENSE).

## Built by

Geoffrey Hancock, a VFX supervisor and producer who orchestrates AI agents on real film productions.
link-session is the coordination layer behind that work.

- Read the case study: [how I run a fleet of AI agents across projects](https://thevfxsupervisor.github.io/projects/link-session/)
- The method, as a course: [join the waitlist](https://thevfxsupervisor.github.io/course/)
- More: [thevfxsupervisor.github.io](https://thevfxsupervisor.github.io/)
