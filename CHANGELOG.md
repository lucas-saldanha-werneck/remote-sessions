# Changelog

Versions are the `version` in `.claude-plugin/plugin.json`. Newest first.

## 0.5.5 (2026-11-13)

- Skill schema and score: add version and tags, a Purpose section, Prerequisites, Limitations and Troubleshooting to both skills; add SkillEvaluator badges.

## 0.5.4 (2026-11-13)

- Add author metadata, Instructions and Examples to SKILL.md; bump to 0.5.4.

## 0.5.3 (2026-11-12)

- Maintenance.

## 0.5.2 (2026-11-12)

- Fix audit findings: tmux names, pane-only stop, rollback, locks, focus guard.

## 0.5.1 (2026-11-11)

- Close tmux sessions on clean exit.

## 0.5.0 (2026-11-11)

- Claude-desk: set the permission mode, send a first turn, exit 3 without Remote Control.

## 0.4.4 (2026-11-11)

- Switch-app-terminal: wait for Remote Control in the app.

## 0.4.3 (2026-11-11)

- Add the /switch-app-terminal command.
- Add commands/switch-app-terminal.md.

## 0.4.2 (2026-11-11)

- Point to the catalog repo's new name, lucas-tools.

## 0.4.1 (2026-11-11)

- Switch-app-terminal: pick the copy it runs in.

## 0.4.0 (2026-11-11)

- Add switch-app-terminal.

## 0.3.2 (2026-11-11)

- Rename the marketplace to lucas-tools.

## 0.3.1 (2026-11-11)

- Claude-open: accept a full path under the projects root.

## 0.3.0 (2026-11-10)

- Open-session: ask app or terminal; claude-desk resume opens a session by its terminal id.

## 0.2.1 (2026-11-09)

- Polish: short description, catalog install, settings headings.

## 0.2.0 (2026-11-08)

- Config: --teams, run shell, precheck in tmux, title command, extra env.
- Claude-open: a --tmux dry run shows the tmux env even where tmux is missing (Windows CI).
- Review fixes: precheck in tmux, settings parsing, tmux server, dry run.
- Create the config file on first run: SessionStart hook and the commands seed ~/.config/remote-sessions/config from config.example, never changing an existing file.

## 0.1.0 (2026-11-08)

- Open, resume and fork Claude Code sessions from the phone.

