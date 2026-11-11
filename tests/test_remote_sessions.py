#!/usr/bin/env python3
"""Tests for claude-open, claude-fork and claude-desk. Nothing real is opened: the projects root, the
Claude config folder and the desktop app folder are temporary, and `claude`, `osascript` and `tmux` are
fakes that only record their arguments. Tests that need POSIX fake binaries skip on Windows.

Run: python3 tests/test_remote_sessions.py -v"""
import json, os, shlex, shutil, stat, subprocess, sys, tempfile, time, unittest, unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
sys.path.insert(0, os.path.join(ROOT, "lib"))
import remote_sessions as rs  # noqa: E402

WINDOWS = os.name == "nt"
POSIX_ONLY = unittest.skipIf(WINDOWS, "needs POSIX shell fakes (osascript/tmux), not available on Windows")
PY = sys.executable.replace("\\", "/")

FAKE_CLAUDE = r'''import json, os, sys
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f:
    f.write("claude " + " ".join(sys.argv[1:]) + "\n")
if sys.argv[1:3] == ["agents", "--json"]:
    print(json.dumps([{"sessionId": s, "pid": 123} for s in os.environ.get("FAKE_OPEN", "").split()]))
'''

FAKE_RECORDER = '''#!/bin/sh
# records its name and each argument on its own line, then a separator
{ echo "== $(basename "$0")"; for a in "$@"; do printf '%s\\n' "$a"; done; } >> "$FAKE_LOG"
exit 0
'''


def write(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    if mode:
        os.chmod(path, mode)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="remote-sessions-test-")
        self.root = os.path.join(self.tmp, "Projects")
        self.cfg = os.path.join(self.tmp, "claude")
        self.log = os.path.join(self.tmp, "calls.log")
        self.fakebin = os.path.join(self.tmp, "fakebin")
        os.makedirs(self.root)
        write(os.path.join(self.tmp, "fake_claude.py"), FAKE_CLAUDE)
        for name in ("osascript", "tmux"):
            write(os.path.join(self.fakebin, name), FAKE_RECORDER, 0o755)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("REMOTE_SESSIONS_", "CLAUDE")) and k not in ("TMUX", "XDG_CONFIG_HOME")}
        self.env.update({
            "HOME": self.tmp, "USERPROFILE": self.tmp,
            "REMOTE_SESSIONS_ROOT": self.root,
            "REMOTE_SESSIONS_CONFIG": os.path.join(self.tmp, "config"),
            "REMOTE_SESSIONS_CLAUDE": f'"{PY}" "{os.path.join(self.tmp, "fake_claude.py").replace(chr(92), "/")}"',
            "CLAUDE_CONFIG_DIR": self.cfg,
            "FAKE_LOG": self.log,
            "PATH": self.fakebin + os.pathsep + os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
        })
        self.t0 = time.time() - 10000

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def session(self, rel, sid, title=None, first=None, entry="cli", age=0, custom=None):
        """Writes a session transcript for folder `rel` (relative to the root)."""
        path = self.root if rel == "." else os.path.join(self.root, *rel.split("/"))
        os.makedirs(path, exist_ok=True)
        lines = [{"type": "system", "entrypoint": entry}]
        if first:
            lines.append({"type": "user", "message": {"content": first}})
        if title:
            lines.append({"type": "ai-title", "aiTitle": title})
        if custom:
            lines.append({"type": "custom-title", "customTitle": custom})
        f = os.path.join(self.cfg, "projects", rs.encode(path), sid + ".jsonl")
        write(f, "\n".join(json.dumps(x, separators=(",", ":")) for x in lines) + "\n")
        t = self.t0 + age
        os.utime(f, (t, t))
        return f

    def run_cmd(self, name, *args, env=None):
        e = dict(self.env, **(env or {}))
        return subprocess.run([sys.executable, os.path.join(BIN, name)] + list(args), env=e,
                              capture_output=True, text=True, encoding="utf-8", cwd=self.tmp)

    def calls(self):
        try:
            with open(self.log, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""


class TestOpen(Base):
    def tree(self):
        self.session("alpha", "a1111111-0000-0000-0000-000000000001", first="fix the parser", age=100)
        self.session("alpha", "a2222222-0000-0000-0000-000000000002", title="AI title", custom="My custom",
                     first="hello", age=300)
        self.session("alpha", "a3333333-0000-0000-0000-000000000003", age=50)                # empty: skipped
        self.session("alpha", "a4444444-0000-0000-0000-000000000004", first="robot", entry="sdk-cli", age=400)
        self.session("beta/sub", "b1111111-0000-0000-0000-000000000001", first="deep work", age=200)
        self.session("web-site/front", "c1111111-0000-0000-0000-000000000001", first="css", age=10)
        self.session("tools", "d1111111-0000-0000-0000-000000000001", first="x", entry="sdk-py", age=500)
        self.session("alpha/.claude/worktrees/wt1", "e1111111-0000-0000-0000-000000000001", first="wt", age=600)
        gone = self.session("deleted", "f1111111-0000-0000-0000-000000000001", first="old", age=700)
        shutil.rmtree(os.path.join(self.root, "deleted"))
        os.makedirs(os.path.join(self.root, "gamma-docs"))
        return gone

    def test_projects_top_level(self):
        self.tree()
        r = self.run_cmd("claude-open", "--projects")
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        names = [x["folder"] for x in got]
        self.assertEqual(names, ["alpha", "beta", "web-site"])  # newest first; no sdk-only, gone or doc-only
        alpha = got[0]
        self.assertEqual((alpha["sessions"], alpha["subfolders"]), (3, 0))  # sdk run not counted, worktree out
        self.assertEqual((got[1]["sessions"], got[1]["subfolders"]), (0, 1))

    def test_projects_one_level_down_and_dash_names(self):
        self.tree()
        r = self.run_cmd("claude-open", "--projects", "beta")
        self.assertEqual([x["folder"] for x in json.loads(r.stdout)], ["beta/sub"])
        r = self.run_cmd("claude-open", "--projects", "web-site")
        self.assertEqual([x["folder"] for x in json.loads(r.stdout)], ["web-site/front"])

    def test_list_titles_order_and_open_flag(self):
        self.tree()
        r = self.run_cmd("claude-open", "alpha", "--list", env={"FAKE_OPEN": "a1111111-0000-0000-0000-000000000001"})
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        self.assertEqual(got["folder"], "alpha")
        self.assertEqual([(s["title"], s["open"]) for s in got["sessions"]],
                         [("My custom", False), ("fix the parser", True)])

    def test_fuzzy_names(self):
        self.tree()
        r = self.run_cmd("claude-open", "alpah", "--list")
        self.assertEqual(json.loads(r.stdout)["folder"], "alpha")
        r = self.run_cmd("claude-open", "beta/sbu", "--list")
        self.assertEqual(json.loads(r.stdout)["folder"], "beta/sub")
        r = self.run_cmd("claude-open", "front", "--list")  # deep folder found through its sessions
        self.assertEqual(json.loads(r.stdout)["folder"], "web-site/front")
        r = self.run_cmd("claude-open", "zzzzqqq", "--list")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing close to 'zzzzqqq'", r.stderr)

    def test_full_path_under_the_root(self):
        self.tree()
        r = self.run_cmd("claude-open", os.path.join(self.root, "beta", "sub"), "--list")
        self.assertEqual(json.loads(r.stdout)["folder"], "beta/sub")   # a full path is that folder, not a name to guess
        r = self.run_cmd("claude-open", self.root + "/", "--list")
        self.assertEqual(json.loads(r.stdout)["folder"], ".")          # the root itself
        r = self.run_cmd("claude-open", os.path.join(self.root, "alpha"), "--tmux", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("folder: alpha\n", r.stdout)
        r = self.run_cmd("claude-open", self.tmp, "--list")            # a full path outside the root: a clear error
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is outside the projects root", r.stderr)
        r = self.run_cmd("claude-open", os.path.join(self.root, "zzzzqqq"), "--list")
        self.assertIn("nothing close to 'zzzzqqq'", r.stderr)          # under the root but missing: as before

    def test_ambiguous_name(self):
        os.makedirs(os.path.join(self.root, "notes-old"))
        os.makedirs(os.path.join(self.root, "notes-new"))
        r = self.run_cmd("claude-open", "notes", "--list")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ambiguous", r.stderr)

    def test_create(self):
        r = self.run_cmd("claude-open", "brand-new", "--create", "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isdir(os.path.join(self.root, "brand-new")))

    def test_new_subfolder(self):
        self.tree()
        r = self.run_cmd("claude-open", "beta", "--new", "fresh", "--dry-run")
        self.assertIn("would create: beta/fresh", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.root, "beta", "fresh")))
        r = self.run_cmd("claude-open", "beta", "--new", "sub", "--dry-run")
        self.assertIn("already exists", r.stderr)
        r = self.run_cmd("claude-open", "beta", "--new", "../x")
        self.assertIn("--new needs a folder name", r.stderr)

    def test_dry_run_new_session(self):
        self.tree()
        r = self.run_cmd("claude-open", "alpha", "--name", "parser", "--prompt", "start here", "--dry-run",
                         env={"REMOTE_SESSIONS_TERMINAL": "tmux"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("folder: alpha", r.stdout)
        self.assertIn("--remote-control 'alpha · parser' -n 'alpha · parser' 'start here'", r.stdout)
        self.assertIn("unset CLAUDECODE", r.stdout)
        self.assertIn("cd ", r.stdout)

    def test_resume_last_open_and_force(self):
        self.tree()
        r = self.run_cmd("claude-open", "alpha", "--resume", "last", "--dry-run")
        self.assertIn("--resume a2222222-0000-0000-0000-000000000002 --remote-control", r.stdout)  # newest conversation
        r = self.run_cmd("claude-open", "alpha", "--resume", "a1111111", "--dry-run",
                         env={"FAKE_OPEN": "a1111111-0000-0000-0000-000000000001"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already running", r.stderr)
        r = self.run_cmd("claude-open", "alpha", "--resume", "a1111111", "--force", "--dry-run",
                         env={"FAKE_OPEN": "a1111111-0000-0000-0000-000000000001"})
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.run_cmd("claude-open", "alpha", "--resume", "nope")
        self.assertIn("not found", r.stderr)

    def test_missing_root_and_config_file(self):
        missing = os.path.join(self.tmp, "nope")
        r = self.run_cmd("claude-open", "--projects", env={"REMOTE_SESSIONS_ROOT": missing})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("projects root not found", r.stderr)
        self.assertIn("REMOTE_SESSIONS_ROOT", r.stderr)
        other = os.path.join(self.tmp, "Work")
        os.makedirs(os.path.join(other, "proj"))
        write(self.env["REMOTE_SESSIONS_CONFIG"], f'# test\nROOT="{other}"\n')
        e = {k: v for k, v in self.env.items() if k != "REMOTE_SESSIONS_ROOT"}
        r = subprocess.run([sys.executable, os.path.join(BIN, "claude-open"), "proj", "--list"], env=e,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"folder": "proj", "sessions": []})

    @POSIX_ONLY
    def test_launch_iterm(self):
        self.tree()
        r = self.run_cmd("claude-open", "alpha", env={"REMOTE_SESSIONS_TERMINAL": "iterm"})
        self.assertEqual(r.returncode, 0, r.stderr)
        c = self.calls()
        self.assertIn("== osascript", c)
        self.assertIn('tell application "iTerm"', c)
        self.assertIn('write text "/bin/sh -c ', c)
        self.assertIn("window opened (iterm)", r.stdout)

    @POSIX_ONLY
    def test_launch_terminal_app(self):
        self.tree()
        r = self.run_cmd("claude-open", "alpha", env={"REMOTE_SESSIONS_TERMINAL": "terminal"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('tell application "Terminal"', self.calls())
        self.assertIn("do script", self.calls())

    @POSIX_ONLY
    def test_launch_tmux_with_failed_precheck(self):
        self.tree()
        r = self.run_cmd("claude-open", "alpha", "--tmux", env={"REMOTE_SESSIONS_PRECHECK": "exit 3",
                                                                "REMOTE_SESSIONS_PRECHECK_FAIL_ENV": "SKIP_SECRETS=1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("warning: the precheck", r.stdout)
        c = self.calls().split("\n")
        self.assertIn("== tmux", c)
        i = c.index("new-session")
        self.assertEqual(c[i + 1:i + 3], ["-d", "-s"])
        self.assertTrue(c[i + 3].startswith("claude-alpha-"))
        self.assertEqual(c[i + 4:i + 6], ["-c", os.path.join(self.root, "alpha")])
        self.assertEqual(c[i + 6:i + 8], ["/bin/sh", "-c"])
        self.assertIn("SKIP_SECRETS=1 ", c[i + 8])
        self.assertNotIn("osascript", self.calls())

    @POSIX_ONLY
    def test_tmux_keeps_shell_only_on_error(self):
        """Clean exit closes the tmux session; a failed command leaves a shell to read the error."""
        self.tree()
        self.run_cmd("claude-open", "alpha", "--tmux")
        c = self.calls().split("\n")
        tail = c[c.index("new-session") + 8].rsplit("; ", 3)
        tail = "; ".join(tail[-3:])
        self.assertTrue(tail.startswith('rc=$?; [ "$rc" -ne 0 ] && exec'), tail)
        probe = tail.replace('exec "${SHELL:-/bin/sh}" -l', "echo KEPT")
        for code, kept in ((0, False), (3, True)):
            out = subprocess.run(["/bin/sh", "-c", f"(exit {code}); {probe}"], capture_output=True, text=True)
            self.assertEqual(out.returncode, code)
            self.assertEqual("KEPT" in out.stdout, kept)

    def test_unknown_terminal(self):
        self.tree()
        r = self.run_cmd("claude-open", "alpha", env={"REMOTE_SESSIONS_TERMINAL": "kitty"})
        self.assertIn("unknown terminal 'kitty'", r.stderr)


class TestOptions(Base):
    """The settings that let a personal setup live outside the plugin: --teams/TEAMS_ENV, TMUX_ENV,
    RUN_SHELL, PRECHECK_IN_TMUX, TMUX_SERVER_VIA_TERMINAL, TITLE_CMD, DROP_ENV."""

    def setUp(self):
        super().setUp()
        self.session("alpha", "a1111111-0000-0000-0000-000000000001", first="fix the parser", age=100)

    def test_teams_default_and_custom_env(self):
        r = self.run_cmd("claude-open", "alpha", "--teams", "--tmux", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 ", r.stdout)
        r = self.run_cmd("claude-open", "alpha", "--resume", "last", "--teams", "--dry-run",
                         env={"REMOTE_SESSIONS_TEAMS_ENV": "TEAMS_A=1 'TEAMS_B=x y'"})
        self.assertIn("TEAMS_A=1 TEAMS_B='x y' ", r.stdout)
        self.assertIn("--resume a1111111", r.stdout)
        r = self.run_cmd("claude-open", "alpha", "--tmux", "--dry-run")
        self.assertNotIn("AGENT_TEAMS", r.stdout)

    def test_tmux_env_only_for_tmux(self):
        e = {"REMOTE_SESSIONS_TMUX_ENV": "UNATTENDED=1"}
        r = self.run_cmd("claude-open", "alpha", "--tmux", "--dry-run", env=e)
        self.assertIn("UNATTENDED=1 ", r.stdout)
        r = self.run_cmd("claude-open", "alpha", "--dry-run", env=dict(e, REMOTE_SESSIONS_TERMINAL="iterm"))
        self.assertNotIn("UNATTENDED", r.stdout)

    @POSIX_ONLY
    def test_run_shell_for_tmux_and_window(self):
        e = {"REMOTE_SESSIONS_RUN_SHELL": "/bin/bash -lc"}
        r = self.run_cmd("claude-open", "alpha", "--tmux", env=e)
        self.assertEqual(r.returncode, 0, r.stderr)
        c = self.calls().split("\n")
        i = c.index("new-session")
        self.assertEqual(c[i + 6:i + 8], ["/bin/bash", "-lc"])
        r = self.run_cmd("claude-open", "alpha", env=dict(e, REMOTE_SESSIONS_TERMINAL="iterm"))
        self.assertIn('write text "/bin/bash -lc ', self.calls())

    @POSIX_ONLY
    def test_precheck_in_tmux(self):
        marker = os.path.join(self.tmp, "precheck-ran")
        write(os.path.join(self.fakebin, "tmux"), FAKE_RECORDER.replace(
            "exit 0", '[ "$1" = run-shell ] && exit 3\nexit 0'), 0o755)
        e = {"REMOTE_SESSIONS_PRECHECK": f"touch '{marker}'", "REMOTE_SESSIONS_PRECHECK_FAIL_ENV": "NO_SECRETS=1",
             "REMOTE_SESSIONS_PRECHECK_IN_TMUX": "1"}
        r = self.run_cmd("claude-open", "alpha", "--tmux", env=e)
        self.assertEqual(r.returncode, 0, r.stderr)
        c = self.calls().split("\n")
        self.assertIn("run-shell", c)
        self.assertEqual(c[c.index("run-shell") + 1], "sh -c " + shlex.quote(f"touch '{marker}'") + " >/dev/null 2>&1")
        self.assertFalse(os.path.exists(marker))                 # ran in the (fake) tmux server, not here
        self.assertIn("NO_SECRETS=1 ", c[c.index("new-session") + 8])
        r = self.run_cmd("claude-open", "alpha", "--tmux", env=dict(e, REMOTE_SESSIONS_PRECHECK_IN_TMUX="0"))
        self.assertTrue(os.path.exists(marker))                  # off: runs with /bin/sh in this process

    @POSIX_ONLY
    def test_tmux_server_via_terminal(self):
        up = os.path.join(self.tmp, "server-up")
        write(os.path.join(self.fakebin, "tmux"), FAKE_RECORDER.replace(
            "exit 0", f'[ "$1" = list-sessions ] && [ ! -e "{up}" ] && exit 1\nexit 0'), 0o755)
        write(os.path.join(self.fakebin, "osascript"), FAKE_RECORDER.replace("exit 0", f'touch "{up}"\nexit 0'), 0o755)
        e = {"REMOTE_SESSIONS_TMUX_SERVER_VIA_TERMINAL": "1", "REMOTE_SESSIONS_TERMINAL": "terminal"}
        r = self.run_cmd("claude-open", "alpha", "--tmux", env=e)
        self.assertEqual(r.returncode, 0, r.stderr)
        c = self.calls()
        self.assertIn("new-session -d -s remote-sessions-keepalive; exit", c)
        self.assertLess(c.index("== osascript"), c.index("\nnew-session\n"))
        os.remove(self.log)
        r = self.run_cmd("claude-open", "alpha", "--tmux", env=e)   # server up now: no window
        self.assertNotIn("osascript", self.calls())
        os.remove(up)
        os.remove(self.log)
        r = self.run_cmd("claude-open", "alpha", "--tmux")          # option off: no window either
        self.assertNotIn("osascript", self.calls())

    @POSIX_ONLY
    def test_title_command(self):
        script = os.path.join(self.tmp, "title.py").replace("\\", "/")
        write(script, "import os, sys\nprint('T:' + os.path.basename(sys.argv[1]) + ':' + sys.argv[2])\n")
        e = {"REMOTE_SESSIONS_TITLE_CMD": f'"{PY}" "{script}"'}
        r = self.run_cmd("claude-open", "alpha", "--name", "parser", "--tmux", env=e)
        self.assertIn("--remote-control T:alpha:parser -n T:alpha:parser", r.stdout)
        r = self.run_cmd("claude-open", "alpha", "--tmux", env=e)
        self.assertIn("--remote-control T:alpha:", r.stdout)
        r = self.run_cmd("claude-open", "alpha", "--name", "parser", "--tmux",
                         env={"REMOTE_SESSIONS_TITLE_CMD": f'"{PY}" -c "import sys; sys.exit(1)"'})
        self.assertIn("--remote-control 'alpha · parser'", r.stdout)   # failure: built-in title

    # ---- review fixes (each test failed on the code before the fix) ----

    @POSIX_ONLY
    def test_r1_precheck_in_tmux_without_server_runs_here(self):
        marker = os.path.join(self.tmp, "precheck-ran")
        write(os.path.join(self.fakebin, "tmux"), FAKE_RECORDER.replace(
            "exit 0", '[ "$1" = list-sessions ] && exit 1\n[ "$1" = run-shell ] && exit 1\nexit 0'), 0o755)
        r = self.run_cmd("claude-open", "alpha", "--tmux", env={
            "REMOTE_SESSIONS_PRECHECK": f"touch '{marker}'", "REMOTE_SESSIONS_PRECHECK_IN_TMUX": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("warning: the precheck", r.stdout)
        self.assertIn("no tmux server is running", r.stdout)
        self.assertTrue(os.path.exists(marker))
        self.assertNotIn("run-shell", self.calls())

    @POSIX_ONLY
    def test_r2_precheck_in_tmux_is_quoted_and_hash_escaped(self):
        cmd = "test -n '#{pane_id}' && exit 0"
        r = self.run_cmd("claude-open", "alpha", "--tmux", env={
            "REMOTE_SESSIONS_PRECHECK": cmd, "REMOTE_SESSIONS_PRECHECK_IN_TMUX": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        c = self.calls().split("\n")
        arg = c[c.index("run-shell") + 1]
        self.assertEqual(arg, ("sh -c " + shlex.quote(cmd) + " >/dev/null 2>&1").replace("#", "##"))

    def test_r3_bad_env_settings_fail_cleanly(self):
        for key in ("REMOTE_SESSIONS_TEAMS_ENV", "REMOTE_SESSIONS_RUN_SHELL"):
            r = self.run_cmd("claude-open", "alpha", "--teams", "--tmux", "--dry-run", env={key: "'unbalanced"})
            self.assertNotEqual(r.returncode, 0)
            self.assertNotIn("Traceback", r.stderr)
            self.assertIn(f"claude-open: {key}", r.stderr)
        r = self.run_cmd("claude-open", "alpha", "--tmux", "--dry-run",
                         env={"REMOTE_SESSIONS_TMUX_ENV": "GOOD=1 junk"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("GOOD=1 ", r.stdout)
        self.assertIn("REMOTE_SESSIONS_TMUX_ENV: ignored ['junk']", r.stderr)

    @POSIX_ONLY
    def test_r4_bad_timeout_and_inline_comment(self):
        write(self.env["REMOTE_SESSIONS_CONFIG"], "PRECHECK=true\nPRECHECK_TIMEOUT=soon\nTERMINAL=tmux   # detached\n")
        r = self.run_cmd("claude-open", "alpha")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("REMOTE_SESSIONS_PRECHECK_TIMEOUT='soon' is not a positive number; using 15", r.stderr)
        self.assertIn("new-session", self.calls())                 # TERMINAL=tmux, the comment dropped

    def test_r4_comment_rules(self):
        self.assertEqual(rs._strip_comment("tmux  # c"), "tmux")
        self.assertEqual(rs._strip_comment("a#b"), "a#b")
        self.assertEqual(rs._strip_comment("'x # y' # z"), "'x # y'")

    @POSIX_ONLY
    def test_r5_osascript_failure_falls_back(self):
        write(os.path.join(self.fakebin, "tmux"), FAKE_RECORDER.replace(
            "exit 0", '[ "$1" = list-sessions ] && exit 1\nexit 0'), 0o755)
        write(os.path.join(self.fakebin, "osascript"), FAKE_RECORDER.replace("exit 0", "exit 1"), 0o755)
        r = self.run_cmd("claude-open", "alpha", "--tmux", env={"REMOTE_SESSIONS_TMUX_SERVER_VIA_TERMINAL": "1",
                                                                "REMOTE_SESSIONS_TERMINAL": "terminal"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("could not open a terminal window for the tmux server", r.stdout)
        self.assertIn("starting it from here", r.stdout)
        self.assertIn("\nnew-session\n", self.calls())

    @POSIX_ONLY
    def test_r6_terminal_setting_and_keepalive_removed(self):
        up = os.path.join(self.tmp, "server-up")
        write(os.path.join(self.fakebin, "tmux"), FAKE_RECORDER.replace(
            "exit 0", f'[ "$1" = list-sessions ] && [ ! -e "{up}" ] && exit 1\nexit 0'), 0o755)
        write(os.path.join(self.fakebin, "osascript"), FAKE_RECORDER.replace("exit 0", f'touch "{up}"\nexit 0'), 0o755)
        r = self.run_cmd("claude-open", "alpha", "--tmux", env={"REMOTE_SESSIONS_TMUX_SERVER_VIA_TERMINAL": "1",
                                                                "REMOTE_SESSIONS_TERMINAL": "iterm"})
        self.assertEqual(r.returncode, 0, r.stderr)
        c = self.calls()
        self.assertIn('tell application "iTerm"', c)              # TERMINAL honored, not "iTerm installed?"
        self.assertLess(c.index("\nnew-session\n"), c.index("\nkill-session\n-t\nremote-sessions-keepalive"))

    def test_r7_dry_run_does_not_run_title_command(self):
        marker = os.path.join(self.tmp, "title-ran").replace("\\", "/")
        script = os.path.join(self.tmp, "title2.py").replace("\\", "/")
        write(script, f"open({marker!r}, 'w').close()\nprint('T')\n")
        r = self.run_cmd("claude-open", "alpha", "--name", "x", "--tmux", "--dry-run",
                         env={"REMOTE_SESSIONS_TITLE_CMD": f'"{PY}" "{script}"'})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(marker))

    def test_r8_multi_token_value_keeps_its_quotes(self):
        write(self.env["REMOTE_SESSIONS_CONFIG"], "TEAMS_ENV='A=x y' 'B=z'\nCLAUDE_ONE='one value'\n")
        r = self.run_cmd("claude-open", "alpha", "--teams", "--tmux", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("A='x y' B=z ", r.stdout)
        self.assertEqual(rs._unquote("'one value'"), "one value")

    def test_r9_drop_env_cannot_remove_own_settings(self):
        r = self.run_cmd("claude-open", "alpha", "--list", env={"REMOTE_SESSIONS_DROP_ENV": "REMOTE_SESSIONS_* REMOTE_*"})
        self.assertEqual(r.returncode, 0, r.stderr)                # ROOT still read: the folder is found
        self.assertEqual(json.loads(r.stdout)["folder"], "alpha")
        self.assertIn("is ignored: it would remove REMOTE_SESSIONS_ settings", r.stderr)

    def test_r10_config_read_once(self):
        old = dict(os.environ)
        try:
            path = os.path.join(self.tmp, "cfg-once")
            write(path, "TERMINAL=tmux\n")
            os.environ["REMOTE_SESSIONS_CONFIG"] = path
            rs._CONFIG = None
            calls = []
            real = rs._read_config
            with unittest.mock.patch.object(rs, "_read_config", lambda: calls.append(1) or real()):
                for _ in range(5):
                    self.assertEqual(rs.setting("TERMINAL"), "tmux")
            self.assertEqual(len(calls), 1)
        finally:
            rs._CONFIG = None
            os.environ.clear()
            os.environ.update(old)

    def test_drop_env(self):
        old = dict(os.environ)
        try:
            os.environ.update({"REMOTE_SESSIONS_DROP_ENV": "WRAP_ACTIVE MYTOOL_* bad-name",
                               "WRAP_ACTIVE": "1", "MYTOOL_X": "1", "OTHER": "1"})
            snippet = rs.unset_snippet()
            self.assertIn(" WRAP_ACTIVE ", snippet + " ")
            self.assertIn("MYTOOL_", snippet)
            self.assertNotIn("bad-name", snippet)
            rs.scrub_env()
            self.assertNotIn("WRAP_ACTIVE", os.environ)
            self.assertNotIn("MYTOOL_X", os.environ)
            self.assertIn("OTHER", os.environ)
        finally:
            os.environ.clear()
            os.environ.update(old)


class TestLib(unittest.TestCase):
    def test_applescript_escaping(self):
        self.assertEqual(rs.applescript_string('a "b" \\c'), '"a \\"b\\" \\\\c"')

    def test_encode(self):
        self.assertEqual(rs.encode("/home/u/my.app"), "-home-u-my-app")

    @POSIX_ONLY
    def test_unset_snippet_runs_in_sh(self):
        env = dict(os.environ, CLAUDECODE="1", CLAUDE_CODE_CHILD_SESSION="1", CLAUDE_PREVIEW_X="1",
                   CLAUDE_AGENT_SDK_Y="1", CLAUDE_CODE_USE_BEDROCK="1", REMOTE_SESSIONS_KEEP_ENV="CLAUDE_PREVIEW_X")
        os.environ["REMOTE_SESSIONS_KEEP_ENV"] = "CLAUDE_PREVIEW_X"
        try:
            snippet = rs.unset_snippet()
        finally:
            del os.environ["REMOTE_SESSIONS_KEEP_ENV"]
        out = subprocess.run(["/bin/sh", "-c", snippet + "env"], env=env, capture_output=True, text=True).stdout
        names = {line.split("=", 1)[0] for line in out.splitlines()}
        self.assertNotIn("CLAUDECODE", names)
        self.assertNotIn("CLAUDE_CODE_CHILD_SESSION", names)
        self.assertNotIn("CLAUDE_AGENT_SDK_Y", names)
        self.assertIn("CLAUDE_PREVIEW_X", names)        # kept on request
        self.assertIn("CLAUDE_CODE_USE_BEDROCK", names)  # user settings are not session variables


class TestFork(Base):
    SID = "12345678-aaaa-bbbb-cccc-1234567890ab"

    def test_dry_run_uses_own_session_id(self):
        r = self.run_cmd("claude-fork", "--name", "try other way", "--dry-run",
                         env={"CLAUDE_CODE_SESSION_ID": self.SID, "REMOTE_SESSIONS_TERMINAL": "tmux"})
        if "needs tmux" in r.stderr:
            self.skipTest("tmux fake not usable on this platform")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"--resume {self.SID} --fork-session --remote-control 'try other way' -n 'try other way'",
                      r.stdout)
        self.assertIn("unset CLAUDECODE", r.stdout)

    def test_errors(self):
        r = self.run_cmd("claude-fork", "--dry-run")
        self.assertIn("no session id given", r.stderr)
        r = self.run_cmd("claude-fork", "not-an-id!", "--dry-run")
        self.assertIn("does not look like a session id", r.stderr)
        r = self.run_cmd("claude-fork", self.SID, "--name", "bad'name", "--dry-run")
        self.assertIn("--name may only have", r.stderr)

    @POSIX_ONLY
    def test_launch_tmux_and_window(self):
        r = self.run_cmd("claude-fork", self.SID, env={"REMOTE_SESSIONS_TERMINAL": "iterm"})
        self.assertEqual(r.returncode, 0, r.stderr)
        c = self.calls()
        self.assertIn("== tmux", c)
        self.assertIn("--fork-session", c)
        self.assertIn("--remote-control 'fork 12345678'", c)
        self.assertIn("== osascript", c)
        self.assertRegex(c, r"attach -t fork-\d{6}")

    @POSIX_ONLY
    def test_detached_only(self):
        r = self.run_cmd("claude-fork", self.SID, env={"REMOTE_SESSIONS_TERMINAL": "tmux"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no window (detached)", r.stdout)
        self.assertNotIn("osascript", self.calls())


class TestDesk(Base):
    def setUp(self):
        super().setUp()
        self.desk = os.path.join(self.tmp, "desk")
        self.env["REMOTE_SESSIONS_DESKTOP_SESSIONS"] = self.desk
        self.env["REMOTE_SESSIONS_DESKTOP_LOG"] = os.path.join(self.tmp, "main.log")
        for i, (title, archived, rc) in enumerate([("Old", False, False), ("Newest", False, True),
                                                   ("Archived", True, False)]):
            write(os.path.join(self.desk, "acct", "org", f"local_{i}.json"), json.dumps({
                "sessionId": f"local_0000000{i}-0000-0000-0000-000000000000", "title": title,
                "cwd": os.path.join(self.tmp, "Projects", title.lower()), "lastActivityAt": (1000 + i) * 1000,
                "isArchived": archived, "remoteControlUserEnabled": rc,
                "cliSessionId": f"c11{i}0000-0000-0000-0000-000000000000"}))

    def test_resume_dry_run(self):
        # by the terminal session id the app keeps for it, by the local id, and one the app does not hold
        for cli, want in (("c1100000-0000-0000-0000-000000000000", "would open local_00000000-"),
                          ("00000001-0000-0000-0000-000000000000", "would open local_00000001-"),
                          ("c1120000-0000-0000-0000-000000000000", "would import CLI session c1120000-"),
                          ("aaaaaaaa-0000-0000-0000-000000000000", "would import CLI session aaaaaaaa-")):
            r = self.run_cmd("claude-desk", "resume", cli, "--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(want, r.stdout, cli)

    def test_resume_needs_an_id(self):
        r = self.run_cmd("claude-desk", "resume", "inventory")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usage: claude-desk resume", r.stderr)

    def test_list(self):
        r = self.run_cmd("claude-desk", "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        self.assertEqual([(d["title"], d["rc"]) for d in got], [("Newest", True), ("Old", False)])
        self.assertTrue(got[0]["folder"].startswith("~"))

    def test_open_needs_mac_or_match(self):
        r = self.run_cmd("claude-desk", "no-such-session-text")
        self.assertNotEqual(r.returncode, 0)
        if sys.platform == "darwin":
            self.assertIn("no desktop session matches", r.stderr)
        else:
            self.assertIn("macOS only", r.stderr)


class SeedConfig(Base):
    """The first run creates ~/.config/remote-sessions/config from config.example, and never touches a file
    that already exists."""
    STARTER = os.path.join(ROOT, "config.example")

    def setUp(self):
        super().setUp()
        del self.env["REMOTE_SESSIONS_CONFIG"]
        self.dest = os.path.join(self.tmp, ".config", "remote-sessions", "config")

    def seed(self, **env):
        return subprocess.run([sys.executable, os.path.join(ROOT, "lib", "remote_sessions.py"), "--seed"],
                              capture_output=True, text=True, env=dict(self.env, **env))

    def bytes(self, p):
        with open(p, "rb") as f:
            return f.read()

    def test_missing_config_is_created_with_the_defaults(self):
        r = self.seed()
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(self.bytes(self.dest), self.bytes(self.STARTER))

    def test_each_command_seeds_on_first_use(self):
        # claude-fork with a bad id: a real run that stops before opening anything
        for cmd, args in (("claude-open", ["--projects"]), ("claude-fork", ["not-an-id"]), ("claude-desk", ["--list"])):
            if os.path.exists(self.dest):
                os.remove(self.dest)
            self.run_cmd(cmd, *args)
            self.assertEqual(self.bytes(self.dest), self.bytes(self.STARTER), cmd)

    def test_seed_uses_the_file_that_was_read_even_if_drop_env_removes_xdg(self):
        # DROP_ENV may remove XDG_CONFIG_HOME before the new window opens; the seed must still look where
        # the settings were read from, not create a second file under ~/.config.
        xdg = os.path.join(self.tmp, "xdg")
        os.makedirs(os.path.join(xdg, "remote-sessions"))
        with open(os.path.join(xdg, "remote-sessions", "config"), "w") as f:
            f.write("# mine\n")
        for cmd, args in (("claude-open", ["--projects"]), ("claude-fork", ["not-an-id"]), ("claude-desk", ["--list"])):
            self.run_cmd(cmd, *args, env={"XDG_CONFIG_HOME": xdg, "REMOTE_SESSIONS_DROP_ENV": "XDG_CONFIG_HOME"})
            self.assertFalse(os.path.exists(self.dest), cmd)

    def test_help_and_dry_run_leave_a_missing_config_missing(self):
        self.session("acme/api", "11111111-0000-4000-8000-000000000001", title="t")
        runs = [("claude-open", []), ("claude-open", ["--help"]), ("claude-open", ["-h"]),
                ("claude-open", ["acme/api", "--dry-run", "--tmux"]),
                ("claude-fork", ["--help"]), ("claude-fork", ["11111111-0000-4000-8000-000000000001", "--dry-run"]),
                ("claude-desk", []), ("claude-desk", ["--help"])]
        for cmd, args in runs:
            self.run_cmd(cmd, *args)
            self.assertFalse(os.path.exists(os.path.join(self.tmp, ".config")), (cmd, args))

    def test_existing_config_is_never_changed(self):
        os.makedirs(os.path.dirname(self.dest))
        with open(self.dest, "wb") as f:
            f.write(b"TERMINAL=tmux\r\n")
        os.utime(self.dest, (1000000000, 1000000000))
        for _ in range(2):
            self.assertEqual(self.seed().returncode, 0)
            self.run_cmd("claude-open", "--projects")
        self.assertEqual(self.bytes(self.dest), b"TERMINAL=tmux\r\n")
        self.assertEqual(os.stat(self.dest).st_mtime, 1000000000)

    def test_env_overrides_are_respected(self):
        alt = os.path.join(self.tmp, "alt", "rs.conf")
        x = os.path.join(self.tmp, "x")
        self.assertEqual(self.seed(REMOTE_SESSIONS_CONFIG=alt, XDG_CONFIG_HOME=x).returncode, 0)
        self.assertEqual(self.bytes(alt), self.bytes(self.STARTER))
        self.assertFalse(os.path.exists(x))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".config")))
        xdg = os.path.join(self.tmp, "xdg")
        self.assertEqual(self.seed(XDG_CONFIG_HOME=xdg).returncode, 0)
        self.assertEqual(self.bytes(os.path.join(xdg, "remote-sessions", "config")), self.bytes(self.STARTER))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".config")))

    def test_unwritable_place_does_not_crash(self):
        write(os.path.join(self.tmp, ".config"), "x")   # a file where the folder should be
        r = self.seed()
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        r = self.run_cmd("claude-open", "--projects")
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "read-only folders are not enforced for Windows or root")
    def test_read_only_folder_does_not_crash(self):
        cfgdir = os.path.join(self.tmp, ".config")
        os.makedirs(cfgdir)
        os.chmod(cfgdir, 0o500)
        try:
            r = self.seed()
            self.assertEqual((r.returncode, r.stderr), (0, ""))
            self.assertEqual(os.listdir(cfgdir), [])
        finally:
            os.chmod(cfgdir, 0o700)

    def test_seeded_config_behaves_like_no_config(self):
        """The starter sets nothing: every key listed in it resolves to the same value as with no file, and a
        whole dry run prints the same."""
        code = ("import json,sys; sys.path.insert(0, sys.argv[1]); import remote_sessions as rs; "
                "keys = sorted(l[2:].split('=')[0] for l in open(sys.argv[2]) "
                "if l.startswith('# ') and '=' in l and l[2:].split('=')[0].isupper()); "
                "print(json.dumps([rs._config(), {k: rs.setting(k, 'DEFAULT') for k in keys}]))")
        env = {k: v for k, v in self.env.items() if not k.startswith("REMOTE_SESSIONS_")}
        self.session("acme/api", "11111111-0000-4000-8000-000000000001", title="t")
        outs = []
        for seeded in (False, True):
            if seeded:
                self.assertEqual(self.seed().returncode, 0)
                self.assertTrue(os.path.isfile(self.dest))
            else:
                self.assertFalse(os.path.exists(self.dest))
            r = subprocess.run([sys.executable, "-c", code, os.path.join(ROOT, "lib"), self.STARTER],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            # a whole dry run with no config (path blocked, so nothing is seeded) and with the seeded file
            blocked = os.path.join(self.tmp, "blocker")
            write(blocked, "x")
            cfg = self.dest if seeded else os.path.join(blocked, "config")
            dry = self.run_cmd("claude-open", "acme/api", "--dry-run", "--tmux", env={"REMOTE_SESSIONS_CONFIG": cfg})
            outs.append((json.loads(r.stdout), dry.returncode, dry.stdout, dry.stderr))
        self.assertEqual(outs[0][0][0], {})
        self.assertEqual(outs[0][1], 0, outs[0][3])
        self.assertIn("api", outs[0][2])
        self.assertEqual(outs[0], outs[1])
        self.assertGreater(len(outs[0][0][1]), 15)   # every key of the starter was checked


def load_switch():
    """bin/switch-app-terminal has no .py suffix: load it as a module (main() does not run)."""
    import importlib.machinery, importlib.util
    path = os.path.join(BIN, "switch-app-terminal")
    loader = importlib.machinery.SourceFileLoader("switch_app_terminal", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class TestSwitch(unittest.TestCase):
    """switch-app-terminal: where a copy runs, which way to move, Remote Control, and the app record."""

    @classmethod
    def setUpClass(cls):
        cls.m = load_switch()

    def test_place_of(self):
        app = ("/Users/x/Library/Application Support/Claude/claude-code/2.1/abc/claude.app/Contents/MacOS/claude "
               "--output-format stream-json --verbose")
        self.assertEqual(self.m.place_of("??", app), "app")
        self.assertEqual(self.m.place_of("ttys010", "/usr/local/bin/claude --resume x --remote-control"), "terminal")
        self.assertEqual(self.m.place_of("??", "/usr/local/bin/claude -p hi"), "other")

    def test_target_for(self):
        self.assertEqual(self.m.target_for({"app"}, None), "terminal")
        self.assertEqual(self.m.target_for({"terminal"}, None), "app")
        self.assertEqual(self.m.target_for({"terminal"}, "terminal"), "terminal")
        for places in (set(), {"app", "terminal"}):
            with self.assertRaises(rs.Fail):
                self.m.target_for(places, None)
        with self.assertRaises(rs.Fail):
            self.m.target_for({"app"}, "phone")

    def test_main_copy(self):
        term = {"pid": 10, "place": "terminal", "remote_control": True}
        app = {"pid": 20, "place": "app", "remote_control": False}   # the app's own idle restart
        self.assertIsNone(self.m.main_copy([]))
        self.assertEqual(self.m.main_copy([app]), app)
        self.assertEqual(self.m.main_copy([term, app], mine=[99, 20, 1]), app)    # runs inside the app copy
        self.assertEqual(self.m.main_copy([term, app], mine=[99, 98]), term)      # outside: the Remote Control one
        self.assertIsNone(self.m.main_copy([dict(term, remote_control=False), app], mine=[99]))

    def test_rc_on_reads_the_pid_record(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "11.json"), json.dumps({"pid": 11, "bridgeSessionId": "session_01abc"}))
            write(os.path.join(d, "12.json"), json.dumps({"pid": 12, "bridgeSessionId": None}))
            with unittest.mock.patch.object(self.m, "SESSIONS", d):
                self.assertTrue(self.m.rc_on(11))
                self.assertFalse(self.m.rc_on(12))
                self.assertFalse(self.m.rc_on(13))  # no record

    def test_app_verdict(self):
        row = {"sessionId": "local_a", "isArchived": False, "bridgeSessionIds": ["session_01x", "session_01y"]}
        self.assertEqual(self.m.app_verdict(row, "session_01y"), "view")       # shares Remote Control: keep
        self.assertEqual(self.m.app_verdict(row, "session_01z"), "separate")   # its own session: archive
        self.assertEqual(self.m.app_verdict(row, None), "separate")
        self.assertIsNone(self.m.app_verdict(dict(row, isArchived=True), "session_01y"))
        self.assertIsNone(self.m.app_verdict(None, "session_01y"))

    def test_app_row_matches_the_cli_session(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "acct", "org", "local_aaa.json"),
                  json.dumps({"sessionId": "local_aaa", "cliSessionId": "1111-cli"}))
            write(os.path.join(d, "acct", "org", "local_bbb.json"), "not json")
            with unittest.mock.patch.object(self.m, "DESK", d):
                self.assertEqual(self.m.app_row("1111-cli")["sessionId"], "local_aaa")
                self.assertIsNone(self.m.app_row("2222-cli"))

    def test_copies_skips_other_sessions_and_dead_pids(self):
        live = [{"sessionId": "s1", "pid": 1, "status": "idle", "cwd": "/p"},
                {"sessionId": "s2", "pid": 2, "status": "busy", "cwd": "/q"},
                {"sessionId": "s1", "pid": 3, "status": "idle", "cwd": "/p"}]
        procs = {1: ("ttys001", "claude --resume s1"), 3: None}
        with unittest.mock.patch.object(self.m, "proc", lambda pid: procs.get(pid)), \
                unittest.mock.patch.object(self.m, "rc_on", lambda pid: True):
            out = self.m.copies("s1", live)
        self.assertEqual([(c["pid"], c["place"], c["remote_control"]) for c in out], [(1, "terminal", True)])

    def test_help_and_no_session(self):
        r = subprocess.run([PY, os.path.join(BIN, "switch-app-terminal"), "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("bridgeSessionIds", r.stdout)
        env = dict(os.environ)
        env.pop("CLAUDE_CODE_SESSION_ID", None)
        r = subprocess.run([PY, os.path.join(BIN, "switch-app-terminal"), "status"], capture_output=True, text=True,
                           env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no session", r.stderr)


def load_desk():
    """bin/claude-desk as a module (main() does not run)."""
    import importlib.machinery, importlib.util
    loader = importlib.machinery.SourceFileLoader("claude_desk", os.path.join(BIN, "claude-desk"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class TestDeskApp(unittest.TestCase):
    """claude-desk inside the app: permission mode, the first turn, Remote Control. ax-press and the app log
    are faked; nothing real is pressed."""

    SID = "local_11111111-2222-3333-4444-555555555555"

    @classmethod
    def setUpClass(cls):
        cls.m = load_desk()

    def setUp(self):
        self.log = ""
        self.calls = []
        self.ui = {"mode": "Manual", "rc": 0, "prompt": "", "turns": 0, "focused": True}
        p = unittest.mock.patch
        for name, fn in (("log_since", lambda pos: self.log), ("log_size", lambda: 0),
                         ("ax", self.fake_ax), ("app_pid", lambda: "1"),
                         ("wait_log", lambda pos, needle, t: needle in self.log)):
            patcher = p.object(self.m, name, fn)
            patcher.start()
            self.addCleanup(patcher.stop)
        sleeper = p.object(self.m.time, "sleep", lambda s: None)
        sleeper.start()
        self.addCleanup(sleeper.stop)
        if self.ui["focused"]:
            self.log += f"setFocusedSession: sessionId={self.SID}\n"

    def fake_ax(self, axbin, role, title, *act):
        self.calls.append((role, title) + act)
        names = [t[:-1] if t.endswith("$") else t for t in title.split("|")]
        if role == "AXPopUpButton":
            if self.ui["mode"] not in names:
                return 2, "NOT FOUND"
            if act and act[0] == "pick":
                self.ui["mode"] = act[1]
                self.log += f"setPermissionMode: sessionId={self.SID}, mode=x\n"
            return 0, f"found: {self.ui['mode']} value: nil"
        if role == "AXCheckBox":
            if act:
                if self.ui["turns"] == 0:
                    return 0, "press result: 0"          # ignored: no turn in the app yet
                self.ui["rc"] = 1
                self.log += f"toggleRemoteControl: sessionId={self.SID} enable=true\nRemote control enabled \"https://x/y\"\n"
            return 0, f"found: Remote Control value: {self.ui['rc']}"
        if role == "AXTextArea":
            if act and act[0] == "set":
                self.ui["prompt"] = act[1]
            return 0, f"found: Prompt value: {self.ui['prompt'] or ' '}"
        if role == "AXButton" and names == ["Send"]:
            self.ui["turns"] += 1
            self.ui["prompt"] = ""
            self.log += f"sendMessage: sessionId={self.SID}\nQuery completed for session {self.SID}\n"
            return 0, "press result: 0"
        return 2, "NOT FOUND"

    def test_wanted_mode(self):
        self.assertEqual(self.m.wanted_mode(["--mode", "bypassPermissions"]), "Bypass permissions")
        self.assertEqual(self.m.wanted_mode(["--mode", "accept edits"]), "Accept edits")
        self.assertEqual(self.m.wanted_mode(["--mode", "default"]), "Manual")
        self.assertIsNone(self.m.wanted_mode(["--mode", "plan", "--no-mode"]))
        with unittest.mock.patch.dict(os.environ, {"REMOTE_SESSIONS_APP_PERMISSION_MODE": "Bypass permissions"}):
            self.assertEqual(self.m.wanted_mode([]), "Bypass permissions")
        with unittest.mock.patch.dict(os.environ, {"REMOTE_SESSIONS_APP_PERMISSION_MODE": ""}):
            self.assertIsNone(self.m.wanted_mode([]))
        with self.assertRaises(rs.Fail):
            self.m.wanted_mode(["--mode", "yolo"])

    def test_set_mode_picks_from_the_menu(self):
        self.assertTrue(self.m.set_mode("ax", "Bypass permissions"))
        self.assertEqual(self.ui["mode"], "Bypass permissions")
        self.assertTrue(self.m.set_mode("ax", "Bypass permissions"))   # already: no second pick
        self.assertEqual(sum(1 for c in self.calls if "pick" in c), 1)

    def test_first_turn_then_remote_control(self):
        self.m.rc_on("ax", self.SID, 0)
        self.assertEqual(self.ui["turns"], 1)
        self.assertEqual(self.ui["rc"], 1)

    def test_no_turn_over_a_draft(self):
        self.ui["prompt"] = "half-typed text"
        with self.assertRaises(self.m.NoRC) as e:
            self.m.rc_on("ax", self.SID, 0)
        self.assertIn("draft", str(e.exception))
        self.assertEqual(self.ui["prompt"], "half-typed text")
        self.assertEqual(self.ui["turns"], 0)

    def test_no_turn_when_another_session_is_shown(self):
        self.log = "setFocusedSession: sessionId=local_other\n"
        with self.assertRaises(self.m.NoRC):
            self.m.rc_on("ax", self.SID, 0)
        self.assertEqual(self.ui["turns"], 0)

    def test_already_on_is_left_alone(self):
        self.ui.update(rc=1, turns=1)
        self.m.rc_on("ax", self.SID, 0)
        self.assertFalse(any(c[0] == "AXCheckBox" and c[2:] for c in self.calls))

    def test_no_rc_exits_3(self):
        """NoRC is caught before the generic failure (exit 1) and exits 3."""
        self.assertTrue(issubclass(self.m.NoRC, rs.Fail))
        self.assertEqual(self.m.EXIT_NO_RC, 3)
        src = open(os.path.join(BIN, "claude-desk"), encoding="utf-8").read()
        self.assertLess(src.index("except NoRC"), src.index("except rs.Fail"))


if __name__ == "__main__":
    unittest.main()
