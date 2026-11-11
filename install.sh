#!/bin/bash
# Installs the remote-sessions commands (claude-open, claude-fork, claude-desk) by symlinking them into
# a folder on your PATH, so they work in your own terminal too (the plugin already puts them on Claude's
# PATH). On macOS with the Swift compiler, it also builds the ax-press helper used by claude-desk.
#
#   ./install.sh [--prefix DIR] [--dry-run] [--force]   install (DIR default: ~/.local/bin)
#   ./install.sh --uninstall [--prefix DIR] [--dry-run]  remove what this script installed
#
# It never overwrites a file that is not its own symlink unless --force is given.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$HOME/.local/bin"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/remote-sessions"
DRY=0; FORCE=0; UNINSTALL=0
CMDS="claude-open claude-fork claude-desk switch-app-terminal"

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) [ $# -ge 2 ] || { echo "--prefix needs a folder" >&2; exit 2; }; PREFIX="$2"; shift ;;
    --dry-run) DRY=1 ;;
    --force) FORCE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

run() { if [ $DRY -eq 1 ]; then echo "would run: $*"; else "$@"; fi; }
ours() { [ -L "$1" ] && [ "$(readlink "$1")" = "$REPO/bin/$2" ]; }

if [ $UNINSTALL -eq 1 ]; then
  for c in $CMDS; do
    t="$PREFIX/$c"
    if ours "$t" "$c"; then run rm "$t"; echo "removed $t"
    elif [ -e "$t" ] || [ -L "$t" ]; then echo "kept $t (not installed by this script)"
    fi
  done
  if [ -e "$DATA/ax-press" ]; then run rm -f "$DATA/ax-press"; echo "removed $DATA/ax-press"; fi
  [ -d "$DATA" ] && [ $DRY -eq 0 ] && rmdir "$DATA" 2>/dev/null
  echo "uninstall done (your config in ~/.config/remote-sessions was left alone)"
  exit 0
fi

command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 || echo "warning: Python 3 not found; the commands need it"
run mkdir -p "$PREFIX" || exit 1
rc=0
for c in $CMDS; do
  t="$PREFIX/$c"
  if ours "$t" "$c"; then echo "ok $t (already installed)"; continue; fi
  if [ -e "$t" ] || [ -L "$t" ]; then
    if [ $FORCE -eq 0 ]; then echo "skipped $t: a different file exists there (use --force to replace it)"; rc=1; continue; fi
    run rm -f "$t"
  fi
  run chmod +x "$REPO/bin/$c"
  run ln -s "$REPO/bin/$c" "$t" && echo "installed $t -> $REPO/bin/$c"
done

if [ "$(uname -s)" = "Darwin" ]; then
  if command -v swiftc >/dev/null 2>&1; then
    run mkdir -p "$DATA" && run swiftc -O -o "$DATA/ax-press" "$REPO/tools/ax-press.swift" && echo "built $DATA/ax-press"
  else
    echo "note: swiftc not found; claude-desk will open sessions but not turn Remote Control on (xcode-select --install)"
  fi
fi
case ":$PATH:" in *":$PREFIX:"*) ;; *) echo "note: $PREFIX is not on your PATH; add it to use the commands in your terminal" ;; esac
exit $rc
