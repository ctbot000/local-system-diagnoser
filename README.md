# Local System Diagnoser

A local web UI that shows what is using this machine's resources. It starts
with memory: how physical RAM and swap break down, and which apps and
processes occupy them.

macOS only for now. Python 3.9+ standard library, no dependencies.

## Run

```bash
python3 -m diagnoser
```

Opens <http://127.0.0.1:8765/>, refreshing every 5 seconds. Options:
`--port N`, `--no-browser`, `--json` (print one snapshot and exit).

## Memory

- **Physical memory**: App memory, Wired, Compressed, Cached files, Other and
  Free, computed the way Activity Monitor does from `vm_stat` and `sysctl`.
- **Swap**: used and free swap, compressor size, swap-ins and swap-outs.
- **What occupies it**: every process's footprint split into the part
  resident in RAM and the part compressed or swapped out (`top`), grouped by
  `.app` bundle, sortable and filterable.

macOS does not report swap usage per process. The per-process
"Compressed / swap" figure counts the process's compressed pages, including
those the compressor has moved out to swap.

psutil is not used because on macOS it exposes neither the compressor, the
app/cached split, nor per-process compressed memory.

## Test

```bash
python3 -m unittest discover -s tests -t .
```
