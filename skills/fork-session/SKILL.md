---
name: fork-session
description: Fork the current Claude Code session into an independent copy (new session id, the original untouched) that starts connected to Remote Control in its own window. Built for the phone, where the Claude app has no fork button. Use when the user says "/fork-session", "fork this session", "fork it", "duplicate the session", "open a copy of this session", or "I want to try another direction without losing this one". Accepts an optional name ("fork as try-redis").
version: "0.5.5"
metadata:
  author: Lucas Saldanha Werneck <lucas@2olhares.com>
  tags: [fork, remote-control, sessions]
---

# fork-session

## Purpose

Fork the current session into an independent copy from the phone, where the Claude app has no fork button, and keep the original untouched.

Creates a COPY of the current session without stopping or changing the original. The copy gets a new session id and inherits all context up to the last completed turn. It starts with `--remote-control`, so it shows up in the Claude app's session list within seconds: this is how you fork from a phone, by asking here.

## Instructions

1. Take the current session id and a name for the copy.
2. Run `claude-fork --name "<name>"` from this session's folder.
3. Wait about 15 seconds and verify the copy is alive before saying it worked.
4. Report the copy's name; to discard it, kill its tmux session.

## Steps

1. **Session id** = this session's id: `$CLAUDE_CODE_SESSION_ID` when set (`claude-fork` uses it by default); otherwise the UUID in this session's transcript or scratchpad path.
2. **Name of the copy**: the one the user gave; otherwise `fork <short topic of this session>`. Only letters, digits, spaces and hyphens.
3. **Launch** from this session's folder:

   ```bash
   claude-fork --name "<name>"            # or: claude-fork <session-id> --name "<name>"
   ```

   The copy must be easy to tell apart from the original at a glance: its own window and its own name. With tmux installed it gets its own tmux session (`fork-HHMMSS`) and, on macOS, a new iTerm or Terminal window attached to it. Without tmux, macOS opens a window running the copy directly. On Linux without a desktop terminal it stays a detached tmux session; tell the user.
4. **Verify before claiming** (wait about 15 seconds, polling with a deadline):
   - process alive: `pgrep -fl -- --fork-session`
   - with tmux: `tmux capture-pane -p -t fork-HHMMSS`; a good start shows the "/remote-control is active" line and the idle prompt.
   - if available: `claude agents --json` lists the new session.
5. **Report**: the copy's name + "it should appear in your app list shortly". If the process died, paste the captured output; do NOT say it worked.
6. **To discard a copy**: `tmux kill-session -t fork-HHMMSS` (the attached window closes by itself; confirm with `pgrep -fl -- --fork-session`), or exit the copy normally.

Known limitations (phantom tasks, last turn missing): see `references/limitations.md`.

## Prerequisites

- Claude Code with the `--fork-session` and `--remote-control` flags, and Python 3.8+.
- `claude-fork` (installed by the plugin or the repo installer). tmux is optional on macOS and needed on Linux.

## Limitations

See `references/limitations.md`: phantom "running tasks" in the copy (cosmetic), and the turn in progress may be missing from the copy.

## Troubleshooting

- The copy did not start: paste the output of `tmux capture-pane -p -t fork-HHMMSS` and say it failed; do not claim it worked.
- No terminal window opened on Linux without a desktop terminal: the copy stays a detached tmux session; attach with `tmux attach -t fork-HHMMSS`.

## Examples

- User: "/fork-session". Claude runs `claude-fork` with a name like `fork <topic>`, checks the copy is running and says it should appear in the app list shortly.
- User: "fork it as try-redis". Claude runs `claude-fork --name "try-redis"`.
- User: "I want to try another direction without losing this one". Same as a fork request.
