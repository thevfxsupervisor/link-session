# link-session

A [Claude Code](https://claude.com/claude-code) skill for coordinating two or more live agent
sessions over shared files. No server, no daemon, no message bus: just JSON outboxes on a shared
folder and a lightweight file watcher, so agents on the same box or across machines can hand off
work, report progress, and stay out of each other's way.

I built this running a fleet of agents across Windows, macOS, and Linux boxes on the same project.
The sessions needed to coordinate (who owns which file, what changed, when a job finished) without
a heavyweight orchestration layer. A shared folder plus a simple contract turned out to be enough,
and it survives the things that usually break coordination: context compaction, a session restart,
and a flaky network mount.

## What it does

- Each session writes ONE JSON outbox (`<session>.json`) into a shared channel folder.
- A session's name is its ROLE in the coordination, not just its working directory.
- A file-watcher Monitor tails the other outboxes and surfaces their status and messages as they
  change, so you find out about a peer's progress without polling.
- A small set of rules keeps it safe: one writer per file, long payloads go in separate files (the
  outbox message is a single slot), and a stop protocol closes the channel cleanly.

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

- `status`: an always-current one-liner; update it on meaningful progress.
- `message`: a one-off note to peers; clear it once acknowledged. Long payloads go in a separate
  file in the channel, not here (this field is a single slot and overwrites).
- `to`: optional target session when the channel has three or more participants.
- `done` / `stop`: both true closes the channel.

## Monitoring

The skill includes ready-to-run watcher scripts for PowerShell (Windows) and bash (macOS / Linux),
in polling, adaptive-backoff, and event-driven variants. They emit a peer's status line whenever
its outbox changes, and (in the hardened form) warn loudly if the shared mount drops instead of
looping silently. See the skill file for the full patterns and the safety and stop protocols.

## Why files instead of a message bus

Because it is boring, portable, and durable. A shared folder works the same on every OS, needs no
service to be running, leaves a readable audit trail, and the state survives a session dying. The
whole design leans into that: the file is the source of truth, and the watcher is just a
convenience for not having to re-read it by hand.

## License

MIT. See [LICENSE](LICENSE).

Built by Geoffrey Hancock ([thevfxsupervisor](https://thevfxsupervisor.github.io/)).
