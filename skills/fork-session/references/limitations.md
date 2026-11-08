# Known limitations of fork-session

- **Phantom tasks (cosmetic):** if the original session ran background agents, the copy may show "N running tasks" that never finish. Nothing actually runs. This is a Claude Code server-side issue (the task registry gets the "started" event but not the "finished" one), not something the fork causes or can prevent; see anthropics/claude-code issues #75085, #65925 and #73605. Ignore the badges or dismiss them in the app.
- The copy inherits up to the last turn already written to the transcript; the turn in progress may be left out.
- Always fork with `--fork-session`: resuming the SAME session id twice at the same time is not a supported setup.
- The Claude mobile app has no fork, branch or rewind command; this skill is the workaround.
- The copy is a new process on the computer. To end it: exit it normally, or `tmux kill-session -t fork-HHMMSS`.
- A copy opened as a tab instead of a window is easy to confuse with the original. That is why `claude-fork` opens a separate window and gives the copy its own name.
