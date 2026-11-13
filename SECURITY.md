# Security

## Reporting a vulnerability

Please report security problems privately, not in a public issue. Open the repository's
[Security tab](https://github.com/lucas-saldanha-werneck/remote-sessions/security) and choose
"Report a vulnerability" (GitHub private vulnerability reporting).

## Supported versions

Only the latest release is supported. Fixes land there.

## What this plugin accesses

- Files: it reads session transcripts under `~/.claude/projects` (titles and first messages, for the pick lists), `~/.claude/sessions`, your projects root, and on macOS the desktop app's session records (`~/Library/Application Support/Claude/claude-code-sessions`) and log (`~/Library/Logs/Claude/main.log`). It creates `~/.config/remote-sessions/config` at session start if missing, keeps move logs and results in `~/.local/state/remote-sessions`, builds its `ax-press` helper into `~/.local/share/remote-sessions` with `swiftc`, and can create project folders you name.
- Sessions: it starts `claude` (new, resume, fork, or `claude -p` for a new app session) with Remote Control on, so the session can be reached from your other devices. It runs `claude agents --json` and `ps` to see which sessions run.
- Terminals: it opens iTerm or Terminal windows with `osascript` and types the start command into them, or starts tmux sessions. `switch-app-terminal` stops the moved session's process (SIGTERM) and its tmux pane, reads tmux screen content, and with `--hello` types a line into the new session.
- Desktop app (macOS): `claude-desk` and `switch-app-terminal` open `claude://` links and use the Accessibility API (permission you grant yourself) to press the Remote Control switch, type and send a short first message in a session's prompt box (only when it is empty), and set the permission mode you ask for, including Bypass permissions, confirming the app's question for that folder.
- Commands you configure: `PRECHECK`, `TITLE_CMD`, `NOTIFY`, `RUN_SHELL` and `CLAUDE` in the config file are run as given.
- Network: the plugin's own code makes no network requests and does not read secrets; the `claude` sessions it starts connect to Anthropic as usual.
