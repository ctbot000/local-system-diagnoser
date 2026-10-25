"""Memory diagnoser for macOS.

Reads the same kernel counters Activity Monitor uses (vm_stat, sysctl, top) and
breaks physical memory and swap down by category and by process.

psutil is not used: on macOS it exposes neither the compressor, the
app/cached split, nor per-process compressed memory, which are the point here.
"""

import os
import re
import subprocess
import time

_UNITS = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


def _run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def parse_size(text):
    """Parse a top/sysctl size such as '1375M', '7552K+', '4096.00M' to bytes."""
    m = re.fullmatch(r"([\d.]+)([BKMGT])?[+-]?", text.strip())
    if not m:
        raise ValueError(f"unrecognised size: {text!r}")
    return int(float(m.group(1)) * _UNITS[m.group(2) or "B"])


def parse_vm_stat(text):
    """Return (page_size, {counter name: page count}) from `vm_stat` output."""
    page_size = int(re.search(r"page size of (\d+) bytes", text).group(1))
    counters = {}
    for line in text.splitlines()[1:]:
        name, sep, value = line.rpartition(":")
        if sep and value.strip().rstrip(".").isdigit():
            counters[name.strip().strip('"')] = int(value.strip().rstrip("."))
    return page_size, counters


def parse_swapusage(text):
    """Return {'total', 'used', 'free'} in bytes from `sysctl vm.swapusage`."""
    fields = dict(re.findall(r"(total|used|free) = ([\d.]+[BKMGT])", text))
    return {k: parse_size(v) for k, v in fields.items()}


def parse_top(text):
    """Return {pid: {'footprint', 'compressed', 'purgeable'}} from top output
    run with `-stats pid,mem,cmprs,purg`."""
    rows = {}
    in_table = False
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "PID":
            in_table = True
            continue
        if in_table and len(parts) >= 4 and parts[0].isdigit():
            rows[int(parts[0])] = {
                "footprint": parse_size(parts[1]),
                "compressed": parse_size(parts[2]),
                "purgeable": parse_size(parts[3]),
            }
    return rows


def parse_ps(text):
    """Return {pid: {'user', 'path'}} from `ps -axo pid=,user=,comm=`."""
    procs = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3 and parts[0].isdigit():
            procs[int(parts[0])] = {"user": parts[1], "path": parts[2]}
    return procs


def app_name(path):
    """Name of the outermost .app bundle in path, else the executable name."""
    for part in path.split("/"):
        if part.endswith(".app"):
            return part[: -len(".app")]
    return os.path.basename(path) or path


def breakdown(total, page_size, vm):
    """Split physical memory into Activity Monitor's categories, in bytes."""
    purgeable = vm.get("Pages purgeable", 0)
    internal = vm.get("pageable_internal", vm.get("Anonymous pages", 0))
    parts = {
        "app": max(internal - purgeable, 0) * page_size,
        "wired": vm.get("Pages wired down", 0) * page_size,
        "compressed": vm.get("Pages occupied by compressor", 0) * page_size,
        "cached": (vm.get("File-backed pages", 0) + purgeable) * page_size,
        "free": (vm.get("Pages free", 0) + vm.get("Pages speculative", 0)) * page_size,
    }
    parts["other"] = max(total - sum(parts.values()), 0)
    return parts


_PRESSURE = {1: "normal", 2: "warning", 4: "critical"}


def snapshot():
    total = int(_run("sysctl", "-n", "hw.memsize"))
    page_size, vm = parse_vm_stat(_run("vm_stat"))
    vm["pageable_internal"] = int(_run("sysctl", "-n", "vm.page_pageable_internal_count"))
    swap = parse_swapusage(_run("sysctl", "vm.swapusage"))
    pressure = int(_run("sysctl", "-n", "kern.memorystatus_vm_pressure_level"))
    top = parse_top(_run("top", "-l", "1", "-o", "mem", "-stats", "pid,mem,cmprs,purg"))
    ps = parse_ps(_run("ps", "-axo", "pid=,user=,comm="))

    processes = []
    for pid, mem in top.items():
        info = ps.get(pid)
        if info is None:  # exited between the two samples
            continue
        processes.append({
            "pid": pid,
            "name": os.path.basename(info["path"]),
            "app": app_name(info["path"]),
            "user": info["user"],
            **mem,
        })
    processes.sort(key=lambda p: p["footprint"], reverse=True)

    parts = breakdown(total, page_size, vm)
    return {
        "timestamp": time.time(),
        "total": total,
        "used": parts["app"] + parts["wired"] + parts["compressed"],
        "breakdown": parts,
        "compressor": {
            "stored": vm.get("Pages stored in compressor", 0) * page_size,
            "occupied": parts["compressed"],
        },
        "swap": {
            **swap,
            "swapins": vm.get("Swapins", 0),
            "swapouts": vm.get("Swapouts", 0),
        },
        "pressure": _PRESSURE.get(pressure, str(pressure)),
        "processes": processes,
    }
