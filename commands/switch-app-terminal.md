---
description: Move this session between the desktop app and a terminal window, with Remote Control on
argument-hint: "[--to app|terminal] [--tmux]"
allowed-tools: Bash(switch-app-terminal:*)
---

Move this conversation to the other place (desktop app ↔ terminal window) with `switch-app-terminal`.

1. Run, exactly: `switch-app-terminal $ARGUMENTS`
2. Reply in one or two short lines, in the user's language: where it goes (from its "started:" line), and that it
   moves once this turn ends. If it printed an error, show it and stop.
3. Then end the turn at once. Do nothing else: the move waits until this session is idle.

Do not archive this session in the desktop app: when it is the conversation's Remote Control view, archiving it
disconnects Remote Control in the terminal too. After the move, `switch-app-terminal last` (run in the new place)
prints the result.
