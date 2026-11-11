"""Shared code for claude-open, claude-fork and claude-desk.

Configuration (environment variable wins over the config file):

  REMOTE_SESSIONS_CONFIG   config file path (default ~/.config/remote-sessions/config)
  REMOTE_SESSIONS_ROOT     projects root folder            (file key: ROOT, default ~/Projects)
  REMOTE_SESSIONS_TERMINAL auto | iterm | terminal | tmux  (file key: TERMINAL, default auto)
  REMOTE_SESSIONS_CLAUDE   claude command to run           (file key: CLAUDE, default claude)
  REMOTE_SESSIONS_PRECHECK shell command that must succeed within 15 s before a session starts
                           (file key: PRECHECK; for example a check that a secrets wrapper is unlocked)
  REMOTE_SESSIONS_PRECHECK_FAIL_ENV
                           KEY=VALUE pairs added to the session when the precheck fails
                           (file key: PRECHECK_FAIL_ENV)
  REMOTE_SESSIONS_KEEP_ENV names that must NOT be removed from the new session's environment
                           (file key: KEEP_ENV, space separated)
  REMOTE_SESSIONS_DROP_ENV extra names removed from the new session's environment (file key: DROP_ENV,
                           space separated; NAME_* removes every name with that prefix)
  REMOTE_SESSIONS_PRECHECK_TIMEOUT
                           seconds the precheck may take (file key: PRECHECK_TIMEOUT, default 15)
  REMOTE_SESSIONS_PRECHECK_IN_TMUX
                           1 = for --tmux sessions, run the precheck inside the tmux server with
                           `tmux run-shell`, where the session itself will run (file key: PRECHECK_IN_TMUX).
                           On macOS a launchd job may lack file permissions (TCC) that the tmux server,
                           started from a terminal, has.
  REMOTE_SESSIONS_TMUX_SERVER_VIA_TERMINAL
                           1 = on macOS, when no tmux server runs, start it from a terminal window first
                           (file key: TMUX_SERVER_VIA_TERMINAL), so it inherits the terminal's permissions
  REMOTE_SESSIONS_RUN_SHELL
                           shell that runs the session command (file key: RUN_SHELL, default `/bin/sh -c`).
                           `/bin/zsh -lic` makes shell functions and aliases from ~/.zshrc apply, such as a
                           `claude` wrapper function
  REMOTE_SESSIONS_TEAMS_ENV
                           KEY=VALUE pairs that --teams adds (file key: TEAMS_ENV,
                           default CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1)
  REMOTE_SESSIONS_TMUX_ENV KEY=VALUE pairs added to every --tmux session (file key: TMUX_ENV)
  REMOTE_SESSIONS_TITLE_CMD
                           command that names new sessions (file key: TITLE_CMD). It gets the folder path
                           and the --name text (maybe empty) as two arguments; its first output line is the
                           title. Empty output or a failure keeps the built-in "<folder> · <name>"
  CLAUDE_CONFIG_DIR        Claude Code's config folder (default ~/.claude); sessions are read from
                           its projects/ subfolder
"""
import datetime, difflib, glob, json, os, re, shlex, shutil, subprocess, sys, time, unicodedata

SKIP = re.compile(r"^(\.|node_modules$|__pycache__$)")
DATE_FMT = "%Y-%m-%d %H:%M"

# Variables a Claude Code session (terminal or desktop app) sets for its own children. A session started
# from inside another one inherits them and then, for example, does not save its transcript. They are
# removed from the new session's environment (REMOTE_SESSIONS_KEEP_ENV keeps any of them).
SESSION_ENV = [
    "CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_PLUGIN_DATA", "CLAUDE_PLUGIN_ROOT",
    "CLAUDE_PROJECT_DIR", "CLAUDE_ENV_FILE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_BRIDGE_SESSION_ID", "CLAUDE_CODE_HOST_SESSION_ID",
    "CLAUDE_CODE_EXECPATH", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
    "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_SSE_PORT", "NO_COLOR", "FORCE_COLOR",
]
SESSION_ENV_PREFIXES = ("CLAUDE_AGENT_SDK_", "CLAUDE_PREVIEW_")


OWN = "REMOTE_SESSIONS_"          # our own settings: never removed by DROP_ENV
KEEPALIVE = "remote-sessions-keepalive"


class Fail(Exception):
    """A user-facing error: printed as one line, exit code 1."""


# ---------------------------------------------------------------- configuration

def _config_file():
    return os.environ.get("REMOTE_SESSIONS_CONFIG") or os.path.join(
        os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"),
        "remote-sessions", "config")


def _strip_comment(v):
    """Drops a trailing ` # comment` (a # after whitespace, outside quotes)."""
    quote = None
    for i, c in enumerate(v):
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "#" and (i == 0 or v[i - 1].isspace()):
            return v[:i].rstrip()
    return v


def _unquote(v):
    """Removes the surrounding quotes only when the whole value is ONE quoted token: `'a b'` -> `a b`, but
    `'A=x y' 'B=z'` stays as written (it is two tokens for the setting that splits it)."""
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" and v[0] not in v[1:-1]:
        return v[1:-1]
    return v


def _read_config():
    out = {}
    try:
        with open(_config_file(), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = _unquote(_strip_comment(v.strip()))
    except OSError:
        pass
    return out


# The starter config: config.example at the plugin / repo root (install.sh links to the clone, so it is there too).
STARTER = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "config.example")


def seed_for_run(argv, empty_is_help=False):
    """The commands' first real run creates the config (seed_config). --help, -h and --dry-run write nothing,
    nor does no argument at all where that only prints the help (empty_is_help)."""
    if (argv or not empty_is_help) and not {"-h", "--help", "--dry-run"} & set(argv):
        seed_config()


def seed_config(dest=None, starter=None):
    """First run: copy the starter to the config file when that file does not exist, creating its folder.
    Never overwrites or changes an existing file, never raises, prints nothing. Returns the path it wrote,
    else None. The starter has every option commented out, so it behaves exactly like no file."""
    try:
        dest = dest or _config_file()
        starter = starter or STARTER
        if os.path.lexists(dest) or not os.path.isfile(starter):
            return None
        with open(starter, "rb") as fh:
            data = fh.read()
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        # O_EXCL: a file that appears between the check and here is left alone
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
        except Exception:
            try:
                os.remove(dest)   # created by us a moment ago: do not leave half a file
            except OSError:
                pass
            return None
        return dest
    except Exception:
        return None


_CONFIG = None


def _config():
    """The config file, read once per process."""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = _read_config()
    return _CONFIG


def setting(key, default=None):
    v = os.environ.get("REMOTE_SESSIONS_" + key)
    if v is None:
        v = _config().get(key)
    return default if v in (None, "") else v


def number(key, default):
    """A numeric setting; anything that is not a positive number falls back to `default` with a warning."""
    raw = setting(key)
    if raw is None:
        return default
    try:
        v = float(raw)
        if v > 0:
            return v
    except ValueError:
        pass
    print(f"warning: REMOTE_SESSIONS_{key}={raw!r} is not a positive number; using {default:g}", file=sys.stderr)
    return default


def split_setting(key, default=""):
    """A setting split like a shell line. Unbalanced quotes are a clear error, not a traceback."""
    raw = setting(key, default) or ""
    try:
        return shlex.split(raw)
    except ValueError as e:
        raise Fail(f"REMOTE_SESSIONS_{key} ({raw!r}) cannot be split like a shell line: {e}")


def expand(p):
    return os.path.abspath(os.path.expanduser(os.path.expandvars(p)))


def projects_root(must_exist=True):
    root = expand(setting("ROOT", "~/Projects"))
    if must_exist and not os.path.isdir(root):
        raise Fail(f"projects root not found: {root}. Set REMOTE_SESSIONS_ROOT, or ROOT=<folder> in "
                   f"{_config_file()}, to the folder that holds your projects.")
    return root.rstrip("/\\") or root


def claude_dir():
    return expand(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")


def sessions_store():
    return os.path.join(claude_dir(), "projects")


def claude_cmd():
    return setting("CLAUDE", "claude")


def keep_env():
    return set((setting("KEEP_ENV", "") or "").split())


def when(ts):
    return datetime.datetime.fromtimestamp(ts).strftime(DATE_FMT)


def print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


for _s in (sys.stdout, sys.stderr):  # titles may hold any character; Windows consoles default to cp1252
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


# ---------------------------------------------------------------- environment hygiene

def drop_lists():
    """(names, prefixes) to remove from a new session: the built-in lists plus REMOTE_SESSIONS_DROP_ENV
    (space separated; a name ending in * is a prefix, e.g. MY_WRAPPER_*)."""
    extra = []
    for n in (setting("DROP_ENV", "") or "").split():
        base = n[:-1] if n.endswith("*") else n
        # a name or prefix that would cover REMOTE_SESSIONS_* would delete our settings before they are read
        if base.startswith(OWN) or (n.endswith("*") and OWN.startswith(base)):
            print(f"warning: REMOTE_SESSIONS_DROP_ENV entry {n!r} is ignored: it would remove REMOTE_SESSIONS_ "
                  f"settings", file=sys.stderr)
            continue
        extra.append(n)
    names = SESSION_ENV + [n for n in extra if not n.endswith("*") and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n)]
    prefixes = SESSION_ENV_PREFIXES + tuple(n[:-1] for n in extra
                                            if n.endswith("*") and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n[:-1]))
    return names, prefixes


def scrub_env():
    """Removes the parent session's variables from this process (they would reach the new window)."""
    keep = keep_env()
    names, prefixes = drop_lists()
    for k in list(os.environ):
        if k in keep or k.startswith(OWN):
            continue
        if k in names or k.startswith(prefixes):
            del os.environ[k]


def unset_snippet():
    """POSIX sh code that removes the same variables inside the new window. Needed because a terminal app
    that was itself started from a Claude session passes them to every new window."""
    keep = keep_env()
    all_names, prefixes = drop_lists()
    names = [n for n in all_names if n not in keep]
    pat = ";".join(f"s/^\\({p}[A-Za-z0-9_]*\\)=.*/\\1/p" for p in prefixes)
    out = f"unset {' '.join(names)} 2>/dev/null; " if names else ""
    keep_case = " ".join(sorted(keep))
    out += (f"for v in $(env | sed -n '{pat}'); do case \" {keep_case} \" in *\" $v \"*) ;; "
            f"*) unset \"$v\";; esac; done; ")
    return out


# ---------------------------------------------------------------- folder names

def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return re.sub(r"[^a-z0-9/]", "", "".join(c for c in s if not unicodedata.combining(c)))


def candidates(root):
    """Folders one and two levels below the root."""
    out = []
    for a in sorted(os.listdir(root)):
        pa = os.path.join(root, a)
        if SKIP.match(a) or not os.path.isdir(pa):
            continue
        out.append(a)
        try:
            subs = sorted(os.listdir(pa))
        except OSError:
            continue
        for b in subs:
            if not SKIP.match(b) and os.path.isdir(os.path.join(pa, b)):
                out.append(f"{a}/{b}")
    return out


def score(query, cand):
    q, c = norm(query).strip("/").split("/"), norm(cand).split("/")
    if len(q) == len(c):  # part by part: "client/invntory" vs "Client/Inventory-App"
        return sum(difflib.SequenceMatcher(None, x, y).ratio() for x, y in zip(q, c)) / len(q)
    if len(q) == 1:  # only the last name
        if q[0] == c[-1]:  # an exact name beats a prefix ("notes" -> notes, not notes-old)
            return 1.0
        if len(q[0]) >= 4 and c[-1].startswith(q[0]):  # "inventory" -> inventory-app
            return 0.9
        return difflib.SequenceMatcher(None, q[0], c[-1]).ratio() * 0.95
    return 0.0


def resolve(root, query, create=False, dry_run=False):
    """Approximate name -> path relative to the root ("." = the root). Fails when nothing is close
    or two names are equally close. A full path (/..., ~/...) under the root is taken as that folder."""
    full = os.path.expanduser(query.strip())
    if os.path.isabs(full):
        real, real_root = os.path.realpath(full), os.path.realpath(root)
        if real != real_root and not real.startswith(real_root + os.sep):
            raise Fail(f"'{query.strip()}' is outside the projects root ({root}). Give a folder under it.")
        query = os.path.relpath(real, real_root).replace(os.sep, "/")  # "." for the root itself; "/" as everywhere here
    query = query.strip().strip("/\\")
    if query in (".", ""):
        return "."
    exact = os.path.join(root, query)
    if os.path.isdir(exact):
        return query
    pool = set(candidates(root)) | (set(session_folders(root)) - {"."})  # + deeper folders with sessions
    ranked = sorted(((score(query, c), c) for c in pool), reverse=True)
    best = ranked[0] if ranked else (0, "")
    if best[0] < 0.75:
        if create:
            if not dry_run:
                os.makedirs(exact, exist_ok=True)
            print(f"created: {exact}" if not dry_run else f"would create: {exact}")
            return query
        near = ", ".join(c for _, c in ranked[:3]) or "(no folders)"
        raise Fail(f"nothing close to '{query}'. Closest: {near}. Use --create to create it.")
    if len(ranked) > 1 and ranked[1][0] > best[0] - 0.05:
        raise Fail(f"ambiguous: '{ranked[0][1]}' or '{ranked[1][1]}'? Run again with the exact name.")
    return best[1]


# ---------------------------------------------------------------- Claude Code session files

def encode(path):
    # Claude Code stores sessions in <config>/projects/<path with every non-alphanumeric char as "-">
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def session_dir(path):
    return os.path.join(sessions_store(), encode(path))


def is_conversation(f):
    """False for `claude -p` / Agent SDK sessions (entrypoint sdk-*): those are other tools' runs."""
    with open(f, errors="ignore", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            m = re.search(r'"entrypoint":\s*"([^"]*)"', line)
            if m:
                return not m.group(1).startswith("sdk")
            if i > 200:
                break
    return True


def session_title(f):
    custom = ai = first = None
    with open(f, errors="ignore", encoding="utf-8") as fh:
        for line in fh:
            if '"custom-title"' in line or '"ai-title"' in line:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                custom = d.get("customTitle") or custom
                ai = d.get("aiTitle") or ai
            elif first is None and re.search(r'"type":\s*"user"', line):
                try:
                    c = json.loads(line).get("message", {}).get("content")
                except ValueError:
                    continue
                if isinstance(c, list):
                    c = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
                if isinstance(c, str) and c.strip() and not c.lstrip().startswith("<"):
                    first = " ".join(c.split())
    title = custom or ai or first
    return title[:80] if title else None


def open_ids():
    """Session ids running right now in some terminal (`claude agents --json`; empty if unavailable)."""
    try:
        cmd = shlex.split(claude_cmd()) + ["agents", "--json"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
        return {s["sessionId"] for s in json.loads(out) if s.get("sessionId") and s.get("pid")}
    except Exception:
        return set()


def session_files(path):
    return sorted(glob.glob(os.path.join(session_dir(path), "*.jsonl")), key=os.path.getmtime, reverse=True)


def list_sessions(path, n):
    live, out = open_ids(), []
    for f in session_files(path):
        if not is_conversation(f):
            continue
        title = session_title(f)
        if not title:  # empty session (opened and closed without a message)
            continue
        sid = os.path.basename(f)[:-6]
        out.append({"id": sid, "when": when(os.path.getmtime(f)), "title": title, "open": sid in live})
        if len(out) >= n:
            break
    return out


def key_to_path(base, rest):
    """Undoes the session-folder key by walking the disk from `base`: at each level, finds the entry whose
    encoded name starts the key. Resolves ambiguous '-' (a-b-c = a-b/c or a/b-c) and dotted names."""
    try:
        entries = os.listdir(base)
    except OSError:
        return None
    for e in entries:
        k = encode(e)
        p = os.path.join(base, e)
        if rest == k and os.path.isdir(p):
            return p
        if rest.startswith(k + "-") and os.path.isdir(p):
            found = key_to_path(p, rest[len(k) + 1:])
            if found:
                return found
    return None


def session_folders(root):
    """{folder relative to the root: (number of sessions, last change)} for folders that exist under the
    root today and hold Claude Code conversations. Git worktrees under .claude/worktrees are left out."""
    prefix = encode(root)
    out = {}
    try:
        keys = os.listdir(sessions_store())
    except OSError:
        return out
    for d in keys:
        if d != prefix and not d.startswith(prefix + "-"):
            continue
        files = [f for f in glob.glob(os.path.join(sessions_store(), d, "*.jsonl")) if is_conversation(f)]
        if not files:
            continue
        path = root if d == prefix else key_to_path(root, d[len(prefix) + 1:])
        if not path:
            continue
        rel = "." if path == root else os.path.relpath(path, root).replace(os.sep, "/")
        if "/.claude/worktrees/" in "/" + rel + "/":
            continue
        out[rel] = (len(files), max(os.path.getmtime(f) for f in files))
    return out


def list_projects(root, prefix):
    """One level of the tree: the folder itself (if it has sessions) plus children that have sessions in
    them or below. 'subfolders' = how many folders with sessions sit below each item (>0 = can go down)."""
    folders = session_folders(root)
    prefix = (prefix or "").strip("/")
    if prefix and prefix != ".":
        prefix = resolve(root, prefix)
    if prefix == ".":
        prefix = ""
    nodes = {}
    for rel, (n, t) in folders.items():
        if prefix:
            if rel == prefix:
                node = rel
            elif rel.startswith(prefix + "/"):
                node = prefix + "/" + rel[len(prefix) + 1:].split("/")[0]
            else:
                continue
        else:
            node = rel.split("/")[0]
        x = nodes.setdefault(node, {"folder": node, "sessions": 0, "subfolders": 0, "_t": 0})
        if rel == node:
            x["sessions"] = n
        else:
            x["subfolders"] += 1
        x["_t"] = max(x["_t"], t)
    out = sorted(nodes.values(), key=lambda x: x["_t"], reverse=True)
    for x in out:
        x["last"] = when(x.pop("_t"))
    return out


# ---------------------------------------------------------------- precheck

def env_pairs(key, default=""):
    """KEY=VALUE pairs from a setting (shell-style quoting allowed), ready to put before a command."""
    out, dropped = [], []
    for a in split_setting(key, default):
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", a):
            k, v = a.split("=", 1)
            out.append(f"{k}={shlex.quote(v)}")
        else:
            dropped.append(a)
    if dropped:
        print(f"warning: REMOTE_SESSIONS_{key}: ignored {dropped} (not KEY=VALUE)", file=sys.stderr)
    return out


def flag(key):
    return (setting(key, "") or "").lower() in ("1", "true", "yes", "on")


def precheck_env(in_tmux=False):
    """Runs REMOTE_SESSIONS_PRECHECK (if set). Returns extra KEY=VALUE pairs for the session when it
    fails or times out, and prints a warning. Without a precheck, returns [].
    in_tmux: the session will run in tmux; with PRECHECK_IN_TMUX=1 the check runs there too."""
    cmd = setting("PRECHECK")
    if not cmd:
        return []
    timeout = number("PRECHECK_TIMEOUT", 15.0)
    argv = ["/bin/sh", "-c", cmd]
    if in_tmux and flag("PRECHECK_IN_TMUX") and tmux_bin():
        if tmux_server_running():
            # run-shell expands #{...} formats, so '#' is doubled; sh -c keeps a compound command whole
            inner = "sh -c " + shlex.quote(cmd) + " >/dev/null 2>&1"
            argv = [tmux_bin(), "run-shell", inner.replace("#", "##")]
        else:
            print("note: no tmux server is running, so the precheck runs here instead of inside tmux")
    try:
        ok = subprocess.run(argv, capture_output=True, timeout=timeout).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        ok = False
    if ok:
        return []
    extra = env_pairs("PRECHECK_FAIL_ENV")
    print(f"warning: the precheck `{cmd}` failed or took over {timeout:g} s; the session starts with "
          f"{' '.join(extra) if extra else 'no changes'}. Run the precheck yourself to see why.")
    return extra


# ---------------------------------------------------------------- terminals

def is_mac():
    return sys.platform == "darwin"


def iterm_installed():
    return any(os.path.isdir(p) for p in ("/Applications/iTerm.app",
                                         os.path.expanduser("~/Applications/iTerm.app")))


def which(name, fallback=None):
    return shutil.which(name) or (fallback if fallback and os.path.exists(fallback) else None)


def pick_terminal(force_tmux=False):
    """'iterm', 'terminal' or 'tmux'. Fails with a clear message when nothing fits."""
    want = "tmux" if force_tmux else (setting("TERMINAL", "auto") or "auto").lower()
    if want not in ("auto", "iterm", "terminal", "tmux"):
        raise Fail(f"unknown terminal '{want}' (use auto, iterm, terminal or tmux)")
    if want == "auto":
        if is_mac():
            want = "iterm" if iterm_installed() else "terminal"
        else:
            want = "tmux"
    if want in ("iterm", "terminal") and not osascript():
        raise Fail(f"terminal '{want}' needs macOS (osascript not found). Use --tmux, or set "
                   f"REMOTE_SESSIONS_TERMINAL=tmux.")
    if want == "tmux" and not tmux_bin():
        raise Fail("tmux not found. Install tmux, or on macOS set REMOTE_SESSIONS_TERMINAL to iterm or terminal.")
    return want


def osascript():
    return which("osascript", "/usr/bin/osascript")


def tmux_bin():
    return which("tmux", "/opt/homebrew/bin/tmux") or which("tmux", "/usr/local/bin/tmux")


def applescript_string(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def open_window(kind, line):
    """Opens a new iTerm or Terminal.app window and types `line` into its shell."""
    if kind == "iterm":
        osa = ('tell application "iTerm"\n'
               '  set w to (create window with default profile)\n'
               '  tell current session of w\n'
               f'    write text {applescript_string(line)}\n'
               '  end tell\n'
               'end tell')
    elif kind == "terminal":
        osa = ('tell application "Terminal"\n'
               f'  do script {applescript_string(line)}\n'
               '  activate\n'
               'end tell')
    else:
        raise Fail(f"open_window: bad kind {kind}")
    r = subprocess.run([osascript(), "-e", osa], capture_output=True, text=True)
    if r.returncode != 0:
        raise Fail(f"osascript failed ({r.returncode}): {(r.stderr or r.stdout).strip()[:300]}. "
                   f"Is the Mac awake and logged in? The first run may ask to allow automation of {kind}.")


def run_shell():
    """argv prefix of the shell that runs a session command (REMOTE_SESSIONS_RUN_SHELL)."""
    return split_setting("RUN_SHELL", "/bin/sh -c") or ["/bin/sh", "-c"]


def sh_line(script):
    """A line any interactive shell (zsh, bash, fish) runs the same way: the script goes to /bin/sh
    (or REMOTE_SESSIONS_RUN_SHELL)."""
    return " ".join(shlex.quote(a) for a in run_shell()) + " " + shlex.quote(script)


def new_session_title(path, name, default):
    """Title for a new session: REMOTE_SESSIONS_TITLE_CMD's first output line, else `default`."""
    cmd = setting("TITLE_CMD")
    if not cmd:
        return default
    try:
        argv = shlex.split(cmd)
        argv[0] = os.path.expanduser(argv[0])
        r = subprocess.run(argv + [path, name or ""], capture_output=True, text=True, timeout=10)
        line = (r.stdout or "").strip().splitlines()[0].strip() if r.returncode == 0 and (r.stdout or "").strip() else ""
    except (subprocess.TimeoutExpired, OSError, ValueError, IndexError):
        line = ""
    return line or default


def tmux_server_running():
    t = tmux_bin()
    return bool(t) and subprocess.run([t, "list-sessions"], capture_output=True).returncode == 0


def ensure_tmux_server():
    """With TMUX_SERVER_VIA_TERMINAL=1 on macOS: when no tmux server runs, start one from a terminal window
    (it then has the terminal's permissions, not those of the caller, e.g. a launchd job) and wait for it.
    The window runs in the terminal REMOTE_SESSIONS_TERMINAL names (auto: iTerm if installed, else Terminal).
    Returns True when it started the keepalive session, which drop_keepalive() removes once the real session
    exists. Any failure (screen locked, automation not allowed) only warns: tmux then starts from here."""
    if not flag("TMUX_SERVER_VIA_TERMINAL") or not osascript() or tmux_server_running():
        return False
    try:
        kind = pick_terminal(False)
    except Fail as e:
        print(f"warning: cannot start the tmux server from a terminal ({e}); starting it from here")
        return False
    if kind not in ("iterm", "terminal"):
        print("warning: REMOTE_SESSIONS_TERMINAL is tmux, so there is no terminal window to start the tmux "
              "server from; starting it from here")
        return False
    tmux = tmux_bin()
    try:
        open_window(kind, f"{shlex.quote(tmux)} new-session -d -s {KEEPALIVE}; exit")
    except Fail as e:
        print(f"warning: could not open a {kind} window for the tmux server ({e}); starting it from here")
        return False
    for _ in range(40):
        if tmux_server_running():
            return True
        time.sleep(0.25)
    print("warning: started a terminal window to bring up the tmux server, but it did not come up in 10 s")
    return False


def drop_keepalive():
    """Removes the keepalive session ensure_tmux_server() started; the real session now keeps the server up."""
    subprocess.run([tmux_bin(), "kill-session", "-t", KEEPALIVE], capture_output=True)


def tmux_session_name(base):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", base).strip("-")[:40] or "claude"


def start_tmux(session, path, script):
    """Detached tmux session running `script` with /bin/sh; the pane keeps a login shell afterwards."""
    keep_shell = 'exec "${SHELL:-/bin/sh}" -l'
    subprocess.run([tmux_bin(), "new-session", "-d", "-s", session, "-c", path] +
                   run_shell() + [script + "; " + keep_shell], check=True)


if __name__ == "__main__":   # the plugin's SessionStart hook: python3 lib/remote_sessions.py --seed
    if "--seed" in sys.argv[1:]:
        seed_config()
    sys.exit(0)
