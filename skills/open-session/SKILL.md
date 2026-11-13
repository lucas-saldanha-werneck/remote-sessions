---
name: open-session
description: Open or resume a Claude Code session of another project folder on this computer, in a new terminal window or in the Claude desktop app, with Remote Control on, picking project, folder and session from numbered lists. Built for use from the phone through Remote Control, where only already-open sessions show up and /resume does not work. Use when the user says "/open-session", "open the project X", "open a session in X", "resume the X session", "continue that conversation in X", or asks to open or resume Claude in a folder that has no open session.
argument-hint: "[folder] [last|id] [app|terminal]"
metadata:
  author: Lucas Saldanha Werneck <lucas@2olhares.com>
---

# open-session: open or resume a session in another folder

Why: in the Claude mobile app, Remote Control only lists sessions that are already running, and `/resume` is not available there. This skill runs from any open session and starts, on this computer, the chosen session with Remote Control on, so it appears in the app's Code tab. It opens either in a new terminal window (iTerm, Terminal.app, or a detached tmux session) or in the Claude desktop app (macOS). The permission mode is whatever the user's settings say.

Finding folders and sessions goes through `claude-open`. It prints JSON; never read `~/.claude/projects/` by hand. Opening in the desktop app goes through `claude-desk`:

| Command | What it does |
|---|---|
| `claude-desk resume <id>` | opens the session in the desktop app: the app session that holds that id, or else it imports the terminal session into the app first. Then it turns Remote Control on. `--dry-run` only says which |
| `claude-desk new <folder>` | starts a new session in the desktop app in that folder (creates the folder if missing) and turns Remote Control on |
| `switch-app-terminal` | run inside a session: moves it to the other place (app → terminal, terminal → app), keeps Remote Control on and checks it. Returns at once; `switch-app-terminal last` prints the result. Archive only app sessions the result lists under `archive` |

| Command | What it does |
|---|---|
| `claude-open --projects [folder]` | one level of the tree: the folder itself plus children with sessions in or below them. Fields: `folder`, `sessions` (its own), `subfolders` (how many below have sessions), `last` |
| `claude-open <folder> --list [N]` | N recent sessions of the folder: `id`, `when`, `title`, `open` |
| `claude-open <folder> --resume <id\|last>` | opens a window resuming the session |
| `claude-open <folder>` | opens a window with a new session |
| `claude-open <parent> --new "<name>"` | creates `<parent>/<name>` (exact name; refuses if it exists, has `/` or quotes, or starts with `.`) and opens a new session there |

`<folder>` accepts an approximate name ("invntory" finds `client/inventory-app`); `.` is the projects root. Add `--tmux` when the user wants no window (nothing steals focus on the computer).

If `claude-open` says the projects root was not found, ask the user which folder holds their projects and offer to write `ROOT=<folder>` to `~/.config/remote-sessions/config`.

## Instructions

1. Find the folder with `claude-open --projects` (numbered lists; skip steps the argument answers).
2. Pick a session with `claude-open <folder> --list 10`, or start a new one.
3. Ask where to open it (desktop app or terminal) unless already said.
4. Open it with `claude-open` or `claude-desk`, then verify it started and that Remote Control is on.

## Flow

Skip the steps the argument already answers: `/open-session inventory` goes straight to step 3; `/open-session inventory last` goes straight to step 4.

**Choices are a numbered list in plain text, not a multiple-choice question tool.** Those tools usually cap the options at a few items. Show the whole list, **end your turn**, and wait. The user answers with a number, or with a name that goes straight to `claude-open` (approximate match also finds deep folders).

Format (short, one line per item, no table, it is read on a phone):

```
client — reply with a number:
0. right here (client) · 12 sessions · 2026-01-25 21:28
1. inventory-app · 7 sessions · 2026-01-25 21:36
2. website ▸ · 15 sessions · 2026-01-15 15:37
3. + new folder here
```

- `0. right here (<folder>)` is the folder itself; show it **whenever it has `sessions` > 0**, also at the top ("right here (<root name>)").
- Children are numbered from 1, in the order `claude-open` returned them (most recent first). Show all of them.
- `▸` = has subfolders with sessions (`subfolders` > 0): choosing it **goes down one level** (new list). Without `▸`, choosing it goes to the session list.
- An item with `sessions: 0` shows only "▸ · last <date>" (it is only a path).
- **The last number of every folder list is `+ new folder here`** (at the top it creates directly in the root). If chosen: ask only "Name of the new folder?", end your turn, and with the answer go to step 4 (where) and open it there: `claude-open <current-folder> --new "<name>"` or `claude-desk new <current-folder>/<name>` (no step 3: a new folder has no old session). Use the name as typed; if `claude-open` refuses (already exists etc.), show the message and ask again.

The list shows only folders that **have Claude Code conversations** in them or below. Folders with only documents do not appear; `claude -p` / Agent SDK runs do not count; git worktrees and folders that no longer exist are left out.

1. **Top.** Run `claude-open --projects` and show the list (title "<root name> — reply with a number:"; the `.` item becomes `0. right here`).
2. **Go down.** For the chosen item: if it is "right here" or has no `▸`, go to step 3 with it. Otherwise run `claude-open --projects <chosen>` and show its list the same way (the item equal to the folder itself becomes `0.`). Repeat until it stops. **"back" or "menu"** = show the list one level up (at the top, show the top again); do not treat it as free text.
3. **Session.** Run `claude-open <folder> --list 10` and show:

   ```
   <folder> — reply with a number:
   0. new session
   1. <title> · <when>
   2. <title> · <when> · already open
   ```
   "already open" when `open: true`. If the user asks for "more", run with a larger N and keep the numbering.
4. **Where.** Session with `open: true`: **do not open it again** (in either place). Say it is already in the app's Code tab under that title. Use `--force` only if the user insists (Remote Control does not attach to the second copy). Otherwise ask, as a numbered list, and end your turn:

   ```
   Open where? Reply with a number:
   1. desktop app
   2. terminal
   ```
   Skip the question when the request already said it ("in the app", "in the terminal", `/open-session inventory last app`), and when `claude-desk` is missing or this is not macOS (then it is the terminal; say so in one line).
5. **Open.**
   - Terminal: `claude-open <folder> --resume <id>` (or `claude-open <folder>` for a new one; `--new "<name>"` for a new folder). A brand-new folder may show the "trust this folder?" prompt in the new window, unless a parent folder is already trusted. If it does, the session waits there until someone answers on the computer.
   - Desktop app: `claude-desk resume <id>` (or `claude-desk new <folder>` for a new one; for a new folder, `claude-desk new <folder>/<name>` with the same name rules as `--new`). The app must be running and the computer unlocked; the app comes to the front on the computer. A new session gets a short first turn (`claude -p`), which takes a few seconds.
6. **Check, do not trust "window opened".**
   - Terminal: wait about 10 seconds (a polling loop with a deadline, not a bare sleep) and run `claude agents --json`: there must be an `interactive` entry with that `sessionId` and a `pid`. If it does not show up, say it did not start and paste what `claude-open` printed. If `claude agents` is not available in this Claude Code version, say you could not confirm it.
   - Desktop app: `claude-desk` prints `opened:` or `imported into the app:` with the app session id (`local_…`), then `Remote Control on:`. Opening works with the screen locked, but the Remote Control switch is then hidden ("switch not found"). If the Remote Control step failed and you have a tool that turns Remote Control on for a desktop session (`set_remote_control` in the app's session tools), call it with that `local_…` id and report the state it returns. Otherwise tell the user to turn on the Remote Control switch in that session's panel. The app session starts its process only when it gets a message, so "not running" right after opening is normal.
7. **Answer briefly:** which folder, which session (title), where it opened, whether Remote Control is on, and "open it from the app's Code tab, name: <title>".

## Pitfalls

- **Precheck warning:** if `claude-open` prints `warning: the precheck ... failed`, pass it on in one line (the session started in the fallback mode the user configured, for example without secrets from a password manager).
- iTerm or Terminal must be usable on the computer with a logged-in user (`claude-open` drives them with AppleScript). A sleeping computer fails; say so instead of retrying. The first run may show a macOS "allow automation" prompt on the computer.
- A resumed session keeps its title; do not pass `--name` with `--resume`.
- Sessions with no user message are skipped by `--list` (opened and closed empty).

## Examples

- User: "/open-session". Claude shows a numbered list of project folders, then sessions, then where to open it.
- User: "/open-session inventory last app". Claude resumes the latest session of the matching folder in the desktop app and checks Remote Control.
- User: "open a session in client in the terminal". Claude opens a new terminal window with Remote Control on and confirms with `claude agents --json`.
