# Security

## Reporting a vulnerability

Please report security problems privately, not in a public issue. Open the repository's
[Security tab](https://github.com/lucas-saldanha-werneck/remote-sessions/security) and choose
"Report a vulnerability" (GitHub private vulnerability reporting).

## Supported versions

Only the latest release is supported. Fixes land there.

## What this plugin accesses

- Files: it lists session and project folders (`~/.claude/sessions`, `~/.claude/projects` and your projects root) to build the pick lists, reads `~/.config/remote-sessions/config`, and keeps small state files under `~/.local/share`.
- Processes: it starts `claude` (resume or fork) in a new terminal window or tmux session, using `osascript` on macOS.
- Desktop app (macOS): `claude-desk` and `switch-app-terminal` read the app log `~/Library/Logs/Claude/main.log` and use the Accessibility API to press controls in the app; this needs the Accessibility permission, which you grant yourself.
- Network: the plugin's own code makes no network requests, and it does not read secrets.

