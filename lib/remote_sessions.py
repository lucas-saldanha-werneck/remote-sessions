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
  CLAUDE_CONFIG_DIR        Claude Code's config folder (default ~/.claude); sessions are read from
                           its projects/ subfolder
"""
import datetime, difflib, glob, json, os, re, shlex, shutil, subprocess, sys, unicodedata

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


class Fail(Exception):
    """A user-facing error: printed as one line, exit code 1."""


# ---------------------------------------------------------------- configuration

def _config_file():
    return os.environ.get("REMOTE_SESSIONS_CONFIG") or os.path.join(
        os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"),
        "remote-sessions", "config")


def _read_config():
    out = {}
    try:
        with open(_config_file(), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                out[k.strip()] = v
    except OSError:
        pass
    return out


def setting(key, default=None):
    v = os.environ.get("REMOTE_SESSIONS_" + key)
    if v is None:
        v = _read_config().get(key)
    return default if v in (None, "") else v


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

def scrub_env():
    """Removes the parent session's variables from this process (they would reach the new window)."""
    keep = keep_env()
    for k in list(os.environ):
        if k in keep:
            continue
        if k in SESSION_ENV or k.startswith(SESSION_ENV_PREFIXES):
            del os.environ[k]


def unset_snippet():
    """POSIX sh code that removes the same variables inside the new window. Needed because a terminal app
    that was itself started from a Claude session passes them to every new window."""
    keep = keep_env()
    names = [n for n in SESSION_ENV if n not in keep]
    pat = ";".join(f"s/^\\({p}[A-Za-z0-9_]*\\)=.*/\\1/p" for p in SESSION_ENV_PREFIXES)
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
    or two names are equally close."""
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

def precheck_env():
    """Runs REMOTE_SESSIONS_PRECHECK (if set). Returns extra KEY=VALUE pairs for the session when it
    fails or times out, and prints a warning. Without a precheck, returns []."""
    cmd = setting("PRECHECK")
    if not cmd:
        return []
    try:
        ok = subprocess.run(["/bin/sh", "-c", cmd], capture_output=True, timeout=15).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        ok = False
    if ok:
        return []
    extra = (setting("PRECHECK_FAIL_ENV", "") or "").split()
    print(f"warning: the precheck `{cmd}` failed or took over 15 s; the session starts with "
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


def sh_line(script):
    """A line any interactive shell (zsh, bash, fish) runs the same way: the script goes to /bin/sh."""
    return "/bin/sh -c " + shlex.quote(script)


def tmux_session_name(base):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", base).strip("-")[:40] or "claude"


def start_tmux(session, path, script):
    """Detached tmux session running `script` with /bin/sh; the pane keeps a login shell afterwards."""
    keep_shell = 'exec "${SHELL:-/bin/sh}" -l'
    subprocess.run([tmux_bin(), "new-session", "-d", "-s", session, "-c", path,
                    "/bin/sh", "-c", script + "; " + keep_shell], check=True)
