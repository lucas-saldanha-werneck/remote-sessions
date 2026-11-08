#!/bin/bash
# Runs every test: the Python suite, then install.sh against a temporary prefix (never your real ~/.local/bin).
T="$(cd "$(dirname "$0")" && pwd)"
R="$(dirname "$T")"
PY="${PYTHON:-$(command -v python3 || command -v python)}"
FAIL=0

echo "== Python tests"
"$PY" "$T/test_remote_sessions.py" -v || FAIL=1

echo "== install.sh"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) echo "SKIP: install.sh needs real symlinks (not available in Git Bash on Windows)" ;;
  *)
    W="$(mktemp -d "${TMPDIR:-/tmp}/remote-sessions-install.XXXXXX")"
    trap 'rm -rf "$W"' EXIT
    export HOME="$W/home" XDG_DATA_HOME="$W/data"; mkdir -p "$HOME"
    P="$W/bin"
    ok()  { echo "  PASS: $*"; }
    bad() { echo "  FAIL: $*"; FAIL=1; }
    bash "$R/install.sh" --prefix "$P" --dry-run >/dev/null
    [ ! -e "$P/claude-open" ] && ok "--dry-run changes nothing" || bad "--dry-run installed something"
    bash "$R/install.sh" --prefix "$P" >/dev/null || bad "install exit $?"
    for c in claude-open claude-fork claude-desk; do
      [ "$(readlink "$P/$c")" = "$R/bin/$c" ] && ok "$c linked" || bad "$c not linked"
    done
    "$P/claude-open" --help >/dev/null 2>&1 && ok "linked claude-open runs" || bad "linked claude-open does not run"
    bash "$R/install.sh" --prefix "$P" | grep -q "already installed" && ok "second install is a no-op" || bad "second install"
    rm "$P/claude-desk"; echo "mine" > "$P/claude-desk"
    bash "$R/install.sh" --prefix "$P" >/dev/null; rc=$?
    [ $rc -eq 1 ] && [ "$(cat "$P/claude-desk")" = "mine" ] && ok "foreign file kept (exit 1)" || bad "foreign file rc=$rc"
    bash "$R/install.sh" --prefix "$P" --uninstall >/dev/null
    [ ! -e "$P/claude-open" ] && [ ! -e "$P/claude-fork" ] && ok "uninstall removed the links" || bad "links left"
    [ "$(cat "$P/claude-desk")" = "mine" ] && ok "uninstall kept the foreign file" || bad "uninstall removed foreign file"
    ;;
esac

[ $FAIL -eq 0 ] && echo "ALL TESTS PASSED" || echo "SOME TESTS FAILED"
exit $FAIL
