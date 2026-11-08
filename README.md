# remote-sessions

Open, resume and fork Claude Code sessions on your computer while you are away from it, from the Claude app on your phone.

In the mobile app, Remote Control only lists sessions that are already running, and `/resume` and fork are not available. This plugin works from any session you already have open: ask it to open another project, and it starts a new terminal window on the computer with that session and Remote Control on, so it shows up in the app a few seconds later.

- **`open-session` skill + `claude-open`**: pick project, folder and session from short numbered lists (made for a phone screen), then open a new or a past session in a new window.
- **`fork-session` skill + `claude-fork`**: fork the current session into an independent copy, in its own window, with Remote Control on.
- **`claude-desk`** (macOS): reopen a Claude desktop app session and switch its Remote Control on.

## Example

From the phone, in any open session:

```
you:    /open-session
Claude: Projects — reply with a number:
        0. right here (Projects) · 3 sessions · 2026-01-25 21:28
        1. client ▸ · 12 sessions · 2026-01-25 21:36
        2. notes · 4 sessions · 2026-01-20 09:10
        3. + new folder here
you:    1
Claude: client — reply with a number: ...
you:    inventory last
Claude: Opened client/inventory-app, session "fix the parser". It is running; open it from the app's Code tab.
```

The same from a terminal:

```
claude-open --projects                       # JSON: folders that have sessions
claude-open invntory --list 5                # JSON: recent sessions (approximate names work)
claude-open inventory --resume last          # new window, resumed, Remote Control on
claude-open client --new website             # create client/website and start a session there
claude-open notes --tmux --name "weekly"     # detached tmux session, no window
claude-fork --name "try another way"         # inside a session: fork it
claude-desk --list                           # macOS: desktop app sessions
```

## Install

In Claude Code:

```
/plugin marketplace add lucas-saldanha-werneck/remote-sessions
/plugin install remote-sessions@remote-sessions
```

The plugin puts `claude-open`, `claude-fork` and `claude-desk` on Claude's PATH. To use them in your own terminal too:

```
git clone https://github.com/lucas-saldanha-werneck/remote-sessions
cd remote-sessions && ./install.sh          # symlinks into ~/.local/bin (--prefix DIR, --dry-run)
```

`install.sh` never replaces a file it did not install (unless `--force`). On macOS with the Swift compiler it also builds the small `ax-press` helper that `claude-desk` uses; otherwise `claude-desk` builds it on first use.

## Configuration

Environment variables, or the same keys without the `REMOTE_SESSIONS_` prefix in `~/.config/remote-sessions/config` (`KEY=value` lines):

| Variable | Default | What |
|---|---|---|
| `REMOTE_SESSIONS_ROOT` | `~/Projects` | folder that holds your projects; lists and names are relative to it |
| `REMOTE_SESSIONS_TERMINAL` | `auto` | `iterm`, `terminal` (Terminal.app), `tmux` (detached) or `auto` (macOS: iTerm if installed, else Terminal; elsewhere: tmux) |
| `REMOTE_SESSIONS_CLAUDE` | `claude` | command that starts Claude Code (for example a wrapper that loads secrets) |
| `REMOTE_SESSIONS_PRECHECK` | none | shell command that must succeed within 15 s before a session starts |
| `REMOTE_SESSIONS_PRECHECK_FAIL_ENV` | none | `KEY=VALUE` pairs added when the precheck fails |
| `REMOTE_SESSIONS_KEEP_ENV` | none | session variables to keep (see below) |
| `CLAUDE_CONFIG_DIR` | `~/.claude` | where Claude Code keeps sessions (`projects/`) |

Example config:

```
ROOT=~/code
TERMINAL=iterm
# a wrapper that waits for a password manager would hang when you are away; skip its secrets instead
CLAUDE=my-claude-wrapper
PRECHECK=my-claude-wrapper --check
PRECHECK_FAIL_ENV=MY_WRAPPER_SKIP=1
```

The new session's environment is cleaned of the variables a running Claude session sets for its children (`CLAUDECODE`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_ENTRYPOINT` and similar). Without that, a session started from inside another one, or from a terminal app that was itself started by the desktop app, may not save its transcript. Your own settings such as `CLAUDE_CODE_USE_BEDROCK` are left alone.

The command typed into the new window runs under `/bin/sh`, so it works the same in zsh, bash or fish, but shell aliases and functions are not available there. If `claude` is an alias or function in your shell, point `REMOTE_SESSIONS_CLAUDE` at a real command.

## Requirements

- Claude Code with Remote Control (the `--remote-control` and `--fork-session` flags) and Python 3.8+.
- macOS: iTerm or Terminal.app. The first launch asks you, on the computer, to allow automation of the terminal app.
- Linux: tmux (sessions start detached; attach with `tmux attach -t <name>`).

### Optional requirements

| Optional | Used for | Without it |
|---|---|---|
| iTerm | new windows on macOS | Terminal.app is used |
| tmux | `--tmux`; forks get their own tmux session | `--tmux` is refused with a message; on macOS forks run directly in a new window |
| `claude agents --json` (recent Claude Code) | marking sessions as already open; refusing to open a second copy | every session shows as not open |
| Swift compiler (`xcode-select --install`) | builds `ax-press`, which flips the Remote Control switch for `claude-desk` | `claude-desk` opens the session; you turn Remote Control on in its panel |
| Accessibility permission for your terminal/Python | `ax-press` | as above |

## Platform

- `claude-open` and `claude-fork`: macOS (iTerm, Terminal.app or tmux) and Linux (tmux). Listing (`--projects`, `--list`) works everywhere, Windows included; opening windows on Windows is not supported.
- `claude-desk`: macOS only. It relies on undocumented Claude desktop app internals (the `claude://` deep links, log lines in `~/Library/Logs/Claude/main.log`, and the accessibility label of the Remote Control switch), so an app update can break it.

## Notes

- A session that is already running is not opened again: Remote Control does not attach to a second copy. `--force` overrides.
- A brand-new folder may show the "trust this folder?" prompt in the new window, which waits until someone answers on the computer, unless a parent folder is already trusted.
- A fork inherits up to the last completed turn. See `skills/fork-session/references/limitations.md`.

## Uninstall

```
/plugin uninstall remote-sessions@remote-sessions
./install.sh --uninstall                     # removes only the links it created and the built helper
```

Your config in `~/.config/remote-sessions/` is left in place.

## License

MIT

Built with Claude Code
