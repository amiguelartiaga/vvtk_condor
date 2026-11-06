#!/usr/bin/env python3
"""Readable view of the HTCondor pool: nodes (CPU/RAM/GPU), running, idle and held jobs.

Used by the launchers `condor_qx` (your jobs) and `condor_qg` (all users).
Read-only (condor_q / condor_status); it never changes anything. Python >= 3.6, no dependencies.

Usage:  condor_view.py [-f/--full] [--user U | --all] [--wide] [--ram] [--no-color] [--ascii] [--nodes-only] [--jobs-only]
"""
import argparse
import getpass
import os
import re
import shutil
import subprocess
import sys
import time
import zlib
from collections import OrderedDict, defaultdict

os.environ["PATH"] = "/usr/local/condor/x86_64/bin:" + os.environ.get("PATH", "")


# ───────────────────────────── drawing helpers ─────────────────────────────
class Ui:
    def __init__(self, color, ascii_only):
        self.color = color
        self.ascii = ascii_only

    def c(self, txt, code):
        return "\033[%sm%s\033[0m" % (code, txt) if self.color else str(txt)

    def bold(self, t): return self.c(t, "1")
    def dim(self, t): return self.c(t, "2")
    def red(self, t): return self.c(t, "31")
    def green(self, t): return self.c(t, "32")
    def yellow(self, t): return self.c(t, "33")
    def blue(self, t): return self.c(t, "34")
    def cyan(self, t): return self.c(t, "36")

    def user(self, name, me):
        # stable color per user (hash); yours is bold, underlined and marked with ★.
        # Only cyan/magenta/blue/white: red, yellow and green are reserved for STATES (problem/warning/ok).
        pal = [36, 35, 34, 96, 95, 94, 1, 37]
        col = pal[zlib.crc32(name.encode()) % len(pal)]
        return self.c(("★" if not self.ascii else "*") + name if name == me else name, ("1;4;%d" if name == me else "%d") % col)

    def bar(self, used, total, width=12):
        """Usage bar: green (<60 %), yellow (<90 %), red (full)."""
        if total <= 0:
            return self.dim("-" * width)
        frac = max(0.0, min(1.0, used / float(total)))
        n = int(round(frac * width))
        full, empty = ("█", "░") if not self.ascii else ("#", ".")
        col = "32" if frac < .6 else ("33" if frac < .9 else "31")
        return self.c(full * n, col) + self.dim(empty * (width - n))

    def gpus(self, used, total):
        if total <= 0:
            return self.dim("no GPU")
        on, off = ("●", "○") if not self.ascii else ("X", "o")
        return self.c(on * used, "31") + self.c(off * (total - used), "32")


def nice_tag(ui, j):
    """nice_user: lowest priority; any other job can overtake it, so it may wait for a long time."""
    return ui.c("nice", "95") if str(j.get("NiceUser")).lower() == "true" else ui.dim("normal")


def vlen(s):
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def pad(s, n, right=False):
    gap = max(0, n - vlen(s))
    return (" " * gap + s) if right else (s + " " * gap)


def clip(s, n):
    s = str(s)
    return s if len(s) <= n else s[: max(0, n - 1)] + "…"


def human_dur(sec):
    sec = int(max(0, sec))
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return "%dd %02dh" % (d, h)
    if h:
        return "%dh %02dm" % (h, m)
    return "%dm" % m if m else "<1m"


def human_mem(mb):
    mb = float(mb)
    return ("%.0fG" % (mb / 1024)) if mb >= 1024 * 10 else (("%.1fG" % (mb / 1024)) if mb >= 1024 else "%dM" % mb)


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def short_host(h):
    return re.sub(r"^(slot[\w]*@)?", "", h or "").split(".")[0]


def short_dir(p):
    p = (p or "").replace("/automount/", "/extra/")
    p = re.sub(r"^/extra/scratch\d+/", "", p)
    p = re.sub(r"^/home/gtc/[^/]+/", "~/", p)
    parts = p.split("/")
    return p if len(parts) <= 4 else "…/" + "/".join(parts[-3:])


def job_name(cmd, args):
    base = os.path.basename(cmd or "?")
    args = "" if args in (None, "undefined") else args
    return (base + " " + args).strip()


# ───────────────────────────── reading Condor ─────────────────────────────
def run(cmd, timeout=60):
    """Output of cmd, or "" if it fails or hangs (a stuck schedd or node must not freeze the view)."""
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, universal_newlines=True, timeout=timeout)
    except Exception:
        return ""


_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def safe(v):
    """Text that comes from Condor (job names, arguments, directories, hold reasons) is written by any user of
    the pool. Remove control characters so nobody can inject terminal escape sequences into your terminal."""
    return _CTRL.sub("?", v.replace("\t", " ")) if isinstance(v, str) else v


HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")


def gpu_label(ad):
    """GPU models of the node (they may differ from each other): «A10 22G + RTX 2080 Ti 11G»."""
    devs = []
    for i in range(8):
        n = ad.get("CUDA%dDeviceName" % i)
        if n:
            devs.append((n, num(ad.get("CUDA%dGlobalMemoryMb" % i))))
    if not devs and ad.get("CUDADeviceName"):
        devs.append((ad["CUDADeviceName"], num(ad.get("CUDAGlobalMemoryMb"))))
    if not devs and ad.get("OCLDeviceName"):  # no CUDA detected: use the OpenCL name as a hint
        devs.append((ad["OCLDeviceName"], num(ad.get("OCLGlobalMemoryMb"))))
    return " + ".join("%s %dG" % (re.sub(r"NVIDIA |GeForce |Server Edition", "", n).strip(), round(m / 1024)) if m else
                      re.sub(r"NVIDIA |GeForce ", "", n) for n, m in devs) or "-"


def read_nodes():
    """One row per node, taken from the partitionable slot (slot1@...), whose Cpus/Memory/GPUs are what is still FREE."""
    out = run(["condor_status", "-constraint", "PartitionableSlot =?= true", "-l"])
    nodes = OrderedDict()
    for block in out.split("\n\n"):
        ad = {}
        for line in block.splitlines():
            k, sep, v = line.partition(" = ")
            if sep:
                ad[k] = safe(v.strip().strip('"'))
        if "Machine" not in ad:
            continue
        name = short_host(ad["Machine"])
        nodes[name] = dict(name=name, cpus=num(ad.get("TotalSlotCpus")), cpus_free=num(ad.get("Cpus")),
                           mem=num(ad.get("TotalSlotMemory")), mem_free=num(ad.get("Memory")),
                           gpus=int(num(ad.get("TotalSlotGPUs"))), gpus_free=int(num(ad.get("GPUs"))),
                           gpu_name=gpu_label(ad), state=ad.get("State", ""))
    return OrderedDict(sorted(nodes.items()))


# Args goes LAST: it is the only field that may contain tabs, so everything after the last fixed field is Args.
FIELDS = ["Owner", "JobStatus", "RemoteHost", "JobCurrentStartDate", "QDate", "EnteredCurrentStatus",
          "RequestCpus", "RequestMemory", "RequestGpus", "MemoryUsage", "Cmd", "Iwd", "HoldReason", "NiceUser", "Args"]


def read_jobs():
    out = run(["condor_q", "-nobatch", "-g", "-allusers", "-af:jt"] + FIELDS)
    jobs = []
    for line in out.splitlines():
        f = line.split("\t")
        if len(f) < len(FIELDS) + 1:
            continue
        f = f[:len(FIELDS)] + ["\t".join(f[len(FIELDS):])]
        d = dict(zip(["id"] + FIELDS, [safe(x) for x in f]))
        d["status"] = int(num(d["JobStatus"], 0))
        d["node"] = short_host(d["RemoteHost"]) if d["RemoteHost"] != "undefined" else None
        for k in ("RequestCpus", "RequestMemory", "RequestGpus", "MemoryUsage"):
            d[k] = num(d[k])
        d["start"] = num(d["JobCurrentStartDate"], num(d.get("QDate")))
        jobs.append(d)
    return jobs


# ───────────────────────────── real RAM (optional, over ssh) ─────────────────────────────
def measure_rss(jobs):
    """REAL RAM (sum of the RSS of the process tree) of each running job, reading `ps` on its node over ssh.
    Condor 8.6 only fills MemoryUsage now and then (many jobs show «undefined»), but every job hangs from its
    `condor_starter -a slotX_Y`: adding up its descendants gives the memory of THAT job, even when the same user
    has many jobs on the node. Returns {job_id: MB}. Nodes without passwordless ssh are skipped."""
    from concurrent.futures import ThreadPoolExecutor
    bynode = defaultdict(list)
    for j in jobs:
        if j["status"] == 2 and j["node"] and j["RemoteHost"] != "undefined" and HOST_RE.match(j["node"]):
            bynode[j["node"]].append(j)

    def one(node):
        try:
            return one_node(node)
        except Exception:
            NODE_FAIL.append(node)
            return {}

    def one_node(node):
        out = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4", node,
                   "grep -E '^(MemTotal|MemAvailable):' /proc/meminfo | sed 's/^/MEM /'; ps -eo pid=,ppid=,rss=,args="], timeout=20)
        if not out:
            NODE_FAIL.append(node)
            return {}
        procs, kids = {}, defaultdict(list)
        mem = {}
        for ln in out.splitlines():
            if ln.startswith("MEM "):
                k, v = ln.split()[1].rstrip(":"), float(ln.split()[2]) / 1024.0
                mem[k] = v
                continue
            f = ln.split(None, 3)
            if len(f) == 4 and f[0].isdigit():
                procs[int(f[0])] = (int(f[2]), f[3])
                kids[int(f[1])].append(int(f[0]))
        if "MemTotal" in mem and "MemAvailable" in mem:
            NODE_MEM[node] = (mem["MemTotal"] - mem["MemAvailable"], mem["MemTotal"])
        starters = {}
        for pid, (rss, args) in procs.items():
            m = re.match(r"condor_starter\b.*?-a (slot[\w]+)", args)
            if m:
                starters[m.group(1)] = pid
        res = {}
        for j in bynode[node]:
            slot = j["RemoteHost"].split("@")[0]
            if slot in starters:
                tot, stack = 0, list(kids[starters[slot]])
                while stack:
                    q = stack.pop()
                    tot += procs[q][0]
                    stack.extend(kids[q])
                res[j["id"]] = tot / 1024.0
        return res

    out = {}
    if bynode:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for r in ex.map(one, list(bynode)):
                out.update(r)
    return out


# ───────────────────────────── hints for held jobs ─────────────────────────────
HOLD_HINTS = [
    (r"Exec format error", "the script does not start with «#!/bin/bash» (or is not executable)"),
    (r"Failed to open .* as standard (output|error)", "the log directory (.condor/) does not exist or is not writable"),
    (r"Failed to open .* as standard input", "the input file is missing"),
    (r"Failed to execute", "the program could not be run: check its path and permissions (chmod +x)"),
    (r"Disk quota|No space left", "out of disk space / disk quota exceeded"),
    (r"memory|Memory", "the job used more memory than requested: raise --memory"),
    (r"SYSTEM_PERIODIC_HOLD|PeriodicHold|periodic", "held by a periodic rule (time or resources exceeded)"),
]


def hold_hint(reason):
    for pat, hint in HOLD_HINTS:
        if re.search(pat, reason or ""):
            return hint
    return None


def hold_summary(reason):
    r = re.sub(r"^Error from \S+: ", "", reason or "")
    r = re.sub(r"'[^']*/([^'/]+)'", r"'…/\1'", r)  # long paths -> file name only
    return r


# ───────────────────────────── why a job is waiting (condor_q -better-analyze) ─────────────────────────────
_ANALYSIS = {}
MAX_ANALYZE = 25   # condor_q -better-analyze takes ~0.1 s; with hundreds of idle clusters the view would take minutes
REAL_RSS = {}   # {job_id: MB} measured over ssh (--ram)
NODE_MEM = {}   # {node: (used_MB, total_MB)} REAL node memory (/proc/meminfo)
NODE_FAIL = []  # nodes we could not reach over ssh


def analyze(jid):
    """Ask Condor (the negotiator) why the job does not start. This is the reliable source, because it takes the
    job's real Requirements into account (pinned node, exclusions, GPU, OS...), not only free CPU/RAM/GPU."""
    cluster = jid.split(".")[0]
    if cluster in _ANALYSIS:
        return _ANALYSIS[cluster]
    r = dict(ok=False, pinned=[], excluded=[], reason="", skipped=False)
    if len(_ANALYSIS) >= MAX_ANALYZE:
        r["skipped"] = True
        _ANALYSIS[cluster] = r
        return r
    txt = run(["condor_q", "-g", "-better-analyze", jid])
    pats = OrderedDict([("rej_req", r"(\d+) are rejected by your job's requirements"),
                        ("rej_theirs", r"(\d+) reject your job because of their own requirements"),
                        ("exhausted", r"(\d+) are exhausted partitionable slots"),
                        ("running_yours", r"(\d+) match and are already running your jobs"),
                        ("other_users", r"(\d+) match but are serving other users"),
                        ("available", r"(\d+) are available to run your job")])
    for k, pat in pats.items():
        m = re.search(pat, txt)
        r[k] = int(m.group(1)) if m else 0
        r["ok"] = r["ok"] or bool(m)
    m = re.search(r"Reason for last match failure: (.*)", txt)
    r["reason"] = m.group(1).strip() if m else ""
    req = txt.split("reduces to these conditions")[0]
    r["pinned"] = sorted(set(short_host(x) for x in re.findall(r'TARGET\.Machine == "([^"]+)"', req)))
    r["excluded"] = sorted(set(short_host(x) for x in re.findall(r'TARGET\.Machine != "([^"]+)"', req)))
    r["total"] = sum(r[k] for k in pats)
    _ANALYSIS[cluster] = r
    return r


def verdict(ui, j, nodes):
    """(level, short text): level is 'ok' | 'warn' | 'bad'."""
    waited = time.time() - num(j["QDate"])
    r = analyze(j["id"])
    if r["skipped"]:
        return "warn", "not analyzed (too many idle jobs): run  condor_q -better-analyze %s" % j["id"]
    if not r["ok"]:
        return "warn", "no data from the negotiator yet (just submitted?)"
    pin = ("pinned to " + ",".join(r["pinned"])) if r["pinned"] else ""
    exc = (" · excludes " + ",".join(r["excluded"])) if r["excluded"] else ""
    if r["available"] > 0:
        if waited > 600:
            return "warn", "%d matching slot(s) are free but it has waited %s: check priority or the negotiator cycle%s" % (
                r["available"], human_dur(waited), (" · " + pin) if pin else "")
        return "ok", "%d free slot(s) accept it: it should start in the next cycle (~1 min)%s" % (r["available"], (" · " + pin) if pin else "")
    if r["total"] and r["rej_req"] >= r["total"]:
        return "bad", "no node satisfies its Requirements%s%s" % ((" · " + pin) if pin else "", exc)
    base = []
    if pin:
        base.append(pin)
    if r["other_users"] or "priority" in r["reason"]:
        base.append("the matching slots are busy with other users (waiting for priority)")
    if r["exhausted"]:
        base.append("%d matching slot(s) have no free CPU/RAM/GPU" % r["exhausted"])
    if r["running_yours"]:
        base.append("%d matching slot(s) already run jobs of the same user" % r["running_yours"])
    if r["rej_theirs"]:
        base.append("%d slot(s) reject it (their own rules)" % r["rej_theirs"])
    return "warn", " · ".join(base) + exc if base else "waiting for its turn"


# ───────────────────────────── sections ─────────────────────────────
def section(ui, title, width, note=None, col="36"):
    line = "━" if not ui.ascii else "="
    head = " %s " % title
    print()
    print(ui.c(head, "1;7;" + col if ui.color else col) + ui.c(line * max(0, width - len(head)), col))
    if note:
        print(ui.dim(note))


def render_nodes(ui, nodes, jobs, me, width):
    section(ui, "POOL NODES  ·  what is free right now", width,
            "Bars = USED part (green: plenty left · yellow: >60 % · red: almost full). GPU: ● busy  ○ free.")
    users_on = defaultdict(lambda: defaultdict(int))
    for j in jobs:
        if j["status"] == 2 and j["node"]:
            users_on[j["node"]][j["Owner"]] += 1
    print(ui.dim(pad("NODE", 7) + pad("GPU", 30) + pad("CPU used", 21) + pad("RAM used", 21) + pad("GPUs", 6) + "WHO IS USING IT"))
    for n in nodes.values():
        cu, mu, gu = n["cpus"] - n["cpus_free"], n["mem"] - n["mem_free"], n["gpus"] - n["gpus_free"]
        gname = n["gpu_name"] if n["gpus"] else "—"
        who = "  ".join("%s×%d" % (ui.user(u, me), c) for u, c in sorted(users_on[n["name"]].items())) or ui.dim("free")
        flag = ui.yellow(" (backfill)") if n["state"] == "Backfill" else ""
        print(pad(ui.bold(n["name"]), 7) + pad(clip(gname, 28), 30)
              + pad("%s %2d/%-2d" % (ui.bar(cu, n["cpus"], 10), cu, n["cpus"]), 21)
              + pad("%s %3s/%-3s" % (ui.bar(mu, n["mem"], 10), human_mem(mu), human_mem(n["mem"])), 21)
              + pad(ui.gpus(int(gu), n["gpus"]), 6) + who + flag)
    tc = sum(n["cpus"] for n in nodes.values())
    fc = sum(n["cpus_free"] for n in nodes.values())
    tg = sum(n["gpus"] for n in nodes.values())
    fg = sum(n["gpus_free"] for n in nodes.values())
    print(ui.dim("─" * width))
    print("Total free: %s CPU of %d  ·  %s GPU of %d" % (ui.green(int(fc)), tc, ui.green(fg), tg))


def render_running(ui, jobs, nodes, me, width, wide):
    run_ = [j for j in jobs if j["status"] in (2, 6, 7)]
    section(ui, "▶ RUNNING (%d)" % len(run_), width, col="32", note=
            "Grouped by node. RAM = used/requested. «used»: «~12G» measured over ssh (--ram; sum of RSS, an UPPER BOUND: "
            "shared memory is counted more than once) · «12G» reported by Condor · «?» no data.")
    if not run_:
        print("  " + ui.dim("no running jobs"))
        return
    byn = defaultdict(list)
    for j in run_:
        byn[j["node"] or "?"].append(j)
    namew = max(20, width - 74)
    for node in sorted(byn):
        n = nodes.get(node)
        print()
        if n:
            gu, cu, mu = n["gpus"] - n["gpus_free"], n["cpus"] - n["cpus_free"], n["mem"] - n["mem_free"]
            nm = NODE_MEM.get(node)
            ram_real = ("  " + ui.cyan("real %s/%s" % (human_mem(nm[0]), human_mem(nm[1])))) if nm else ""
            print(ui.bold(ui.blue("┃ " if not ui.ascii else "| ")) + ui.bold(pad(node, 6)) + " "
                  + ui.bold(pad(clip(n["gpu_name"], 26), 27)) + "GPU " + ui.gpus(int(gu), n["gpus"]) + "   "
                  + "CPU " + ui.bar(cu, n["cpus"], 8) + " %d/%d   " % (cu, n["cpus"])
                  + "RAM " + ui.bar(mu, n["mem"], 8) + " %s/%s requested%s" % (human_mem(mu), human_mem(n["mem"]), ram_real))
        else:
            print(ui.bold(ui.blue("┃ " if not ui.ascii else "| ")) + ui.bold(node))
        print(ui.dim("   " + pad("ID", 8) + pad("USER", 11) + pad("PRIO", 7) + pad("FOR", 8) + pad("CPU", 4) + pad("GPU", 4)
                     + pad("RAM used/req.", 17) + "JOB · DIRECTORY"))
        for j in sorted(byn[node], key=lambda x: x["start"]):
            gp = int(j["RequestGpus"])
            if j["id"] in REAL_RSS:
                ram = ui.green("~%s" % human_mem(REAL_RSS[j["id"]])) + "/%s" % human_mem(j["RequestMemory"])
            elif j["MemoryUsage"]:
                ram = "%s/%s" % (human_mem(j["MemoryUsage"]), human_mem(j["RequestMemory"]))
            else:
                ram = ui.dim("?") + "/%s" % human_mem(j["RequestMemory"])
            st = {6: ui.yellow("↓"), 7: ui.yellow("⏸")}.get(j["status"], "")
            line = ("   " + pad(j["id"].replace(".0", ""), 8) + pad(ui.user(j["Owner"], me), 11) + pad(nice_tag(ui, j), 7)
                    + pad(human_dur(time.time() - j["start"]) + st, 8) + pad(str(int(j["RequestCpus"])), 4)
                    + pad(ui.cyan("●" if not ui.ascii else "G") if gp else ui.dim("-"), 4) + pad(ram, 17)
                    + clip(job_name(j["Cmd"], j["Args"]), namew if not wide else 200))
            print(line)
            print(ui.dim("   " + " " * 59 + "↳ " + short_dir(j["Iwd"])))


def render_idle(ui, jobs, nodes, me, width):
    idle = [j for j in jobs if j["status"] == 1]
    section(ui, "⏳ IDLE, WAITING IN THE QUEUE (%d)" % len(idle), width, col="33", note=
            "«Diagnosis» comes from condor_q -better-analyze (the job's real Requirements), not from a guess.")
    if not idle:
        print("  " + ui.dim("queue is empty"))
        return
    for j in sorted(idle, key=lambda x: x["QDate"]):
        lvl, why = verdict(ui, j, nodes)
        col = {"ok": ui.green, "warn": ui.yellow, "bad": ui.red}[lvl]
        print("   " + ui.bold(pad(j["id"].replace(".0", ""), 7)) + pad(ui.user(j["Owner"], me), 11)
              + pad(nice_tag(ui, j), 7) + pad("waiting " + human_dur(time.time() - num(j["QDate"])), 15)
              + "asks %dCPU %s %s" % (j["RequestCpus"], ("%dGPU" % j["RequestGpus"]) if j["RequestGpus"] else "no GPU", human_mem(j["RequestMemory"])))
        print("       " + ui.dim("job      : ") + clip(job_name(j["Cmd"], j["Args"]), width - 20))
        print("       " + ui.dim("directory: ") + short_dir(j["Iwd"]))
        print("       " + ui.dim("diagnosis: ") + col(why))
        r = analyze(j["id"])
        if r["ok"]:
            print("       " + ui.dim("slots    : %d matching and free · %d used by other users · %d without resources · "
                                     "%d running jobs of the same user · %d fail Requirements"
                                     % (r["available"], r["other_users"], r["exhausted"], r["running_yours"], r["rej_req"])))


def render_held(ui, jobs, me, width):
    held = [j for j in jobs if j["status"] == 5]
    section(ui, "✖ HELD (%d)  ·  stopped by an error, they will not continue on their own" % len(held), width, col="31", note=
            "Fix the cause and run  condor_release ID  (or  condor_rm ID  to remove it).")
    if not held:
        print("  " + ui.green("none ✔"))
        return
    for j in sorted(held, key=lambda x: num(x["EnteredCurrentStatus"])):
        age = human_dur(time.time() - num(j["EnteredCurrentStatus"]))
        print("   " + ui.red("✖ " if not ui.ascii else "x ") + ui.bold(j["id"].replace(".0", "")) + "  " + ui.user(j["Owner"], me) + " " + nice_tag(ui, j)
              + ui.dim("  held for " + age + "  ·  " + clip(job_name(j["Cmd"], j["Args"]), 50)))
        print("       " + ui.yellow("reason: ") + clip(hold_summary(j["HoldReason"]), width - 18))
        hint = hold_hint(j["HoldReason"])
        if hint:
            print("       " + ui.green("hint  : ") + hint)


def render_summary(ui, jobs, me, who, width):
    c = defaultdict(int)
    for j in jobs:
        c[j["status"]] += 1
    print()
    print(ui.bold("condor · " + time.strftime("%Y-%m-%d %H:%M")) + "   " + ui.dim("view: " + who)
          + "   " + ui.green("▶ %d running" % (c[2] + c[6] + c[7])) + "   " + ui.yellow("⏳ %d idle" % c[1])
          + "   " + (ui.red("✖ %d held" % c[5]) if c[5] else ui.dim("0 held")))


def render_simple_nodes(ui, nodes):
    """One line per node: what is still free."""
    print()
    print(ui.dim("Nodes: what is still FREE (of the total)"))
    for n in nodes.values():
        free_gpu = (ui.green if n["gpus_free"] else ui.red)("%d/%d GPU" % (n["gpus_free"], n["gpus"]))
        print("  " + pad(ui.bold(n["name"]), 7) + pad(clip(n["gpu_name"], 26), 28) + pad(free_gpu, 10)
              + pad("%d/%d CPU" % (n["cpus_free"], n["cpus"]), 11) + "%s RAM" % human_mem(n["mem_free"]))


def render_simple_jobs(ui, nodes, jobs, me, width):
    """One line per job. Just enough to know what is going on."""
    print()
    if not jobs:
        print(ui.dim("No jobs in this view."))
        return
    print(ui.dim("Jobs:"))
    order = {2: 0, 6: 0, 7: 0, 1: 1, 5: 2}
    for j in sorted(jobs, key=lambda x: (order.get(x["status"], 3), x["start"])):
        jid = j["id"].replace(".0", "")
        name = clip(job_name(j["Cmd"], j["Args"]), max(20, width - 62))
        if j["status"] in (2, 6, 7):
            t = human_dur(time.time() - j["start"])
            print("  " + ui.green("▶ " if not ui.ascii else "R ") + pad(jid, 6) + pad(ui.user(j["Owner"], me), 11) + pad(nice_tag(ui, j), 7)
                  + pad("on " + (j["node"] or "?"), 9) + pad(t, 8)
                  + (pad("%s/%s" % (human_mem(REAL_RSS[j["id"]]), human_mem(j["RequestMemory"])), 11) if j["id"] in REAL_RSS else "") + name)
        elif j["status"] == 1:
            lvl, why = verdict(ui, j, nodes)
            col = {"ok": ui.green, "warn": ui.yellow, "bad": ui.red}[lvl]
            print("  " + ui.yellow("⏳" if not ui.ascii else "I ") + pad(jid, 6) + pad(ui.user(j["Owner"], me), 11) + pad(nice_tag(ui, j), 7)
                  + pad("idle", 9) + pad(human_dur(time.time() - num(j["QDate"])), 8) + name)
            print("      " + col("↳ " + clip(why, width - 10)))
        elif j["status"] == 5:
            hint = hold_hint(j["HoldReason"]) or clip(hold_summary(j["HoldReason"]), width - 20)
            print("  " + ui.red("✖ " if not ui.ascii else "H ") + pad(jid, 6) + pad(ui.user(j["Owner"], me), 11) + pad(nice_tag(ui, j), 7)
                  + pad("HELD", 9) + pad(human_dur(time.time() - num(j["EnteredCurrentStatus"])), 8) + name)
            print("      " + ui.red("↳ " + hint))
    print()
    marks = ("▶", "⏳", "✖") if not ui.ascii else ("R", "I", "H")
    print(ui.dim("%s running · %s idle · %s held.  Details: -f (or condor_qxf / condor_qgf) · real RAM of running jobs: --ram." % marks))


def render_legend(ui, width):
    print()
    print(ui.dim("─" * width))
    print(ui.dim("Colors: USER NAMES get their own color only to tell them apart (never a state) · ★ = you. ")
          + ui.green("green") + ui.dim("=ok/free · ") + ui.yellow("yellow") + ui.dim("=warning/almost full · ") + ui.red("red") + ui.dim("=problem/full."))
    print(ui.dim("Priority: ") + ui.c("nice", "95") + ui.dim(" = nice_user (anyone can overtake it; it may wait a long time) · normal = standard priority."))
    print(ui.dim("States: ▶ running (R) · ⏳ idle (I) · ✖ held (H).  More about one job: ") + "condor_q -better-analyze ID")
    print(ui.dim("Actions: condor_rm ID (remove) · condor_release ID (resume a held job) · condor_stop (remove from any machine) · "
                 "condor_qx (your jobs) · condor_qg (everyone)"))


def main():
    ap = argparse.ArgumentParser(prog=os.environ.get("CONDOR_VIEW_PROG"), description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("-u", "--user", help="only the jobs of this user (default: you)")
    g.add_argument("-a", "--all", action="store_true", help="all users")
    ap.add_argument("-f", "--full", action="store_true", help="full view: usage bars, directories, detailed queue diagnosis")
    ap.add_argument("-w", "--wide", action="store_true", help="do not clip job names")
    ap.add_argument("--no-color", action="store_true", help="plain text, no colors")
    ap.add_argument("--ascii", action="store_true", help="no Unicode characters")
    ap.add_argument("-m", "--ram", action="store_true", help="measure the REAL RAM of each running job (ssh + ps on each node; takes a few seconds)")
    ap.add_argument("--default-all", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--nodes-only", action="store_true", help="show only the nodes")
    ap.add_argument("--jobs-only", action="store_true", help="show only the jobs")
    a = ap.parse_args()

    me = getpass.getuser()
    color = sys.stdout.isatty() and not a.no_color and "NO_COLOR" not in os.environ
    if os.environ.get("FORCE_COLOR"):
        color = not a.no_color
    enc = (sys.stdout.encoding or "").lower()
    ui = Ui(color, a.ascii or "utf" not in enc)
    width = max(90, min(shutil.get_terminal_size((130, 40)).columns, 160))

    nodes, alljobs = read_nodes(), read_jobs()
    if not nodes and not alljobs:
        sys.exit("Could not read Condor (are you on a node with condor_q/condor_status in the PATH?)")
    if a.all or (a.default_all and not a.user):
        jobs, who = alljobs, "all users"
    else:
        u = a.user or me
        jobs, who = [j for j in alljobs if j["Owner"] == u], "user " + u

    if a.ram:
        REAL_RSS.update(measure_rss(jobs))
    render_summary(ui, jobs, me, who, width)
    if a.ram and NODE_FAIL:
        print(ui.yellow("  (--ram) no ssh access to: %s -> run «ssh NODE» once to accept its host key and try again" % ", ".join(sorted(NODE_FAIL))))
    if not a.full:
        if not a.jobs_only:
            render_simple_nodes(ui, nodes)
        if not a.nodes_only:
            render_simple_jobs(ui, nodes, jobs, me, width)
        return
    if not a.jobs_only:
        render_nodes(ui, nodes, alljobs, me, width)
    if not a.nodes_only:
        render_running(ui, jobs, nodes, me, width, a.wide)
        render_idle(ui, jobs, nodes, me, width)
        render_held(ui, jobs, me, width)
    render_legend(ui, width)


if __name__ == "__main__":
    main()
