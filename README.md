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
claude-open notes --tmux --teams --prompt "/plan"   # agent teams on for this session only
claude-fork --name "try another way"         # inside a session: fork it
claude-desk --list                           # macOS: desktop app sessions
```

## Install

In Claude Code:

```
/plugin marketplace add lucas-saldanha-werneck/claude-plugins
/plugin install remote-sessions@lucas-plugins
```

The plugin puts `claude-open`, `claude-fork` and `claude-desk` on Claude's PATH. To use them in your own terminal too:

```
git clone https://github.com/lucas-saldanha-werneck/remote-sessions
cd remote-sessions && ./install.sh          # symlinks into ~/.local/bin (--prefix DIR, --dry-run)
```

`install.sh` never replaces a file it did not install (unless `--force`). On macOS with the Swift compiler it also builds the small `ax-press` helper that `claude-desk` uses; otherwise `claude-desk` builds it on first use.

## Settings

Your settings are in `~/.config/remote-sessions/config` (or `$REMOTE_SESSIONS_CONFIG`; `$XDG_CONFIG_HOME` is
respected), as `KEY=value` lines with the keys below minus the `REMOTE_SESSIONS_` prefix. Environment
variables with the full names work too.

You do not have to create it: the first time the plugin starts a session, or `claude-open`, `claude-fork`
or `claude-desk` really runs (`--help` and `--dry-run` write nothing), it is created from
[`config.example`](config.example), which lists every option with its default, commented out, so it
changes nothing until you edit a line. A file that already exists is never changed.

**Your settings survive updates.** The config file is outside the plugin folder, which Claude Code replaces on every plugin update, and outside the git clone that `install.sh` links to, so neither an update nor a `git pull` touches it. The plugin's `userConfig` (`/config` in Claude Code) could not carry these: it only reaches the plugin's hooks and MCP servers, while `claude-open` also runs from your shell, from scripts and from launchd jobs.

| Variable | Default | What |
|---|---|---|
| `REMOTE_SESSIONS_ROOT` | `~/Projects` | folder that holds your projects; lists and names are relative to it |
| `REMOTE_SESSIONS_TERMINAL` | `auto` | `iterm`, `terminal` (Terminal.app), `tmux` (detached) or `auto` (macOS: iTerm if installed, else Terminal; elsewhere: tmux) |
| `REMOTE_SESSIONS_CLAUDE` | `claude` | command that starts Claude Code (for example a wrapper that loads secrets) |
| `REMOTE_SESSIONS_PRECHECK` | none | shell command that must succeed before a session starts |
| `REMOTE_SESSIONS_PRECHECK_TIMEOUT` | `15` | seconds the precheck may take; a timeout counts as a failure |
| `REMOTE_SESSIONS_PRECHECK_FAIL_ENV` | none | `KEY=VALUE` pairs added when the precheck fails |
| `REMOTE_SESSIONS_PRECHECK_IN_TMUX` | off | `1`: for tmux sessions, run the precheck inside the tmux server (`tmux run-shell`), where the session will run. On macOS a launchd job may be denied files (privacy/TCC permissions) that a tmux server started from your terminal can read |
| `REMOTE_SESSIONS_TMUX_SERVER_VIA_TERMINAL` | off | `1` (macOS): when no tmux server is running, start it from a short-lived terminal window first, so it gets the terminal's permissions instead of the caller's. The window may take focus for a moment |
| `REMOTE_SESSIONS_RUN_SHELL` | `/bin/sh -c` | shell that runs the session command, in windows and in tmux. `/bin/zsh -lic` loads your `~/.zshrc`, so a `claude` alias or wrapper function (for example an auto-retry wrapper) applies |
| `REMOTE_SESSIONS_TEAMS_ENV` | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` | `KEY=VALUE` pairs `--teams` adds |
| `REMOTE_SESSIONS_TMUX_ENV` | none | `KEY=VALUE` pairs added to every tmux session (sessions nobody is watching) |
| `REMOTE_SESSIONS_TITLE_CMD` | none | command that names new sessions. It gets the folder path and the `--name` text (maybe empty); its first output line becomes the title. Empty output or an error keeps `<folder> · <name>` |
| `REMOTE_SESSIONS_KEEP_ENV` | none | session variables to keep (see below) |
| `REMOTE_SESSIONS_DROP_ENV` | none | extra variables removed from the new session (space separated; `NAME_*` removes a whole prefix), e.g. a wrapper's "already active" flag |
| `CLAUDE_CONFIG_DIR` | `~/.claude` | where Claude Code keeps sessions (`projects/`) |

Example config:

```
ROOT=~/code
TERMINAL=iterm
# a wrapper that waits for a password manager would hang when you are away; skip its secrets instead
CLAUDE=my-claude-wrapper
PRECHECK=my-claude-wrapper --check
PRECHECK_FAIL_ENV=MY_WRAPPER_SKIP=1
# called from launchd on macOS: check and run inside the tmux server, which the terminal started
PRECHECK_IN_TMUX=1
TMUX_SERVER_VIA_TERMINAL=1
# zsh functions apply (e.g. an auto-retry `claude` wrapper); drop its flag so it starts fresh
RUN_SHELL=/bin/zsh -lic
DROP_ENV=MY_RETRY_*
TEAMS_ENV=CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 CLAUDE_CODE_ENABLE_TODO_TOOLS=1
TMUX_ENV=CLAUDE_CODE_DISABLE_NOTIFICATION_PRESENCE_CHECK=1
TITLE_CMD=~/bin/my-session-title
```

Command settings are split like a shell line (quotes work); unbalanced quotes stop `claude-open` with a message naming the setting, and words that are not `KEY=VALUE` in an `_ENV` setting are ignored with a warning. The precheck runs with `/bin/sh -c`, so it may use pipes.

How the file is read: `KEY=value` lines, `#` starts a comment (also after a value, when preceded by a space and outside quotes). Quotes around the value are removed only when the whole value is one quoted word, so `TEAMS_ENV='A=x y' 'B=z'` keeps both pairs. The file is read once per run. `DROP_ENV` never removes `REMOTE_SESSIONS_*` variables; an entry that would is ignored with a warning.

Details of the tmux options: with `PRECHECK_IN_TMUX=1` and no tmux server running yet, the precheck runs in this process instead (a server is started first when `TMUX_SERVER_VIA_TERMINAL=1`). `TMUX_SERVER_VIA_TERMINAL` opens its window in the terminal `REMOTE_SESSIONS_TERMINAL` names; if that window cannot be opened (screen locked, automation not allowed) tmux starts from this process with a warning, and the short-lived `remote-sessions-keepalive` session is closed as soon as the real session exists. `TITLE_CMD` is not run by `--dry-run`, which shows the built-in title.

The new session's environment is cleaned of the variables a running Claude session sets for its children (`CLAUDECODE`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_ENTRYPOINT` and similar). Without that, a session started from inside another one, or from a terminal app that was itself started by the desktop app, may not save its transcript. Your own settings such as `CLAUDE_CODE_USE_BEDROCK` are left alone.

The command typed into the new window runs under `/bin/sh` by default, so it works the same in zsh, bash or fish, but shell aliases and functions are not available there. If `claude` is an alias or function in your shell, set `REMOTE_SESSIONS_RUN_SHELL` (e.g. `/bin/zsh -lic`) or point `REMOTE_SESSIONS_CLAUDE` at a real command.

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
/plugin uninstall remote-sessions@lucas-plugins
./install.sh --uninstall                     # removes only the links it created and the built helper
```

Your config in `~/.config/remote-sessions/` is left in place.

## License

MIT

Built with Claude Code
