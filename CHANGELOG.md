# Changelog

Versions are the `version` in `.claude-plugin/plugin.json`. Newest first.

## 0.5.5 (2026-11-13)

- Skills: add version and tags, a Purpose section, Prerequisites, Limitations and Troubleshooting; SkillEvaluator badges in the README.
- README: demo GIF and badges; add SECURITY.md and this CHANGELOG.

## 0.5.4 (2026-11-13)

- Skills: add author metadata, Instructions and Examples sections (docs only).

## 0.5.3 (2026-11-12)

- Tests no longer reach the real `open` or `osascript` (a test run had started the desktop app).

## 0.5.2 (2026-11-12)

- tmux session names keep their unique suffix; duplicate names retry.
- switch-app-terminal stops only the pane, reopens the source on a failed move, one move per session.
- claude-desk presses nothing unless the app shows the session; relative names with `..` cannot leave the projects root.
- Config file created 0600; `claude-open --resume --prompt` no longer uses the prompt as the Remote Control name.

## 0.5.1 (2026-11-11)

- Close tmux sessions on clean exit.

## 0.5.0 (2026-11-11)

- claude-desk: set the permission mode, send a first turn, exit 3 without Remote Control.

## 0.4.4 (2026-11-11)

- Add the `/switch-app-terminal` command file.
- switch-app-terminal: wait up to 10 minutes for Remote Control in the app instead of failing.

## 0.4.3 (2026-11-11)

- README: list the `/switch-app-terminal` command (the command file shipped in 0.4.4).

## 0.4.2 (2026-11-11)

- Point to the catalog repo's new name, `lucas-tools`.

## 0.4.1 (2026-11-11)

- switch-app-terminal: pick the copy it runs in.

## 0.4.0 (2026-11-11)

- Add switch-app-terminal: move the current conversation between the desktop app and a terminal, keeping Remote Control on.

## 0.3.2 (2026-11-11)

- Catalog renamed to `lucas-tools`.

## 0.3.1 (2026-11-11)

- claude-open: accept a full path under the projects root.

## 0.3.0 (2026-11-10)

- open-session: ask app or terminal; `claude-desk resume` opens a session by its terminal id.

## 0.2.1 (2026-11-09)

- Short description, catalog install steps, settings headings in the README.

## 0.2.0 (2026-11-08)

- Config: `--teams`, run shell, precheck in tmux, title command, extra env.
- Create the config file on first run (SessionStart hook and the commands seed it from `config.example`, never changing an existing file); `--help` and `--dry-run` do not create it.
- Review fixes: precheck in tmux, settings parsing, tmux server, dry run.
- `claude-open --tmux` dry run shows the tmux env even where tmux is missing.

## 0.1.0 (2026-11-08)

- Open, resume and fork Claude Code sessions from the phone.
