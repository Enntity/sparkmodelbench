#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Run the versioned suite against a serving endpoint."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

from card import render
from field_guide import capture

ROOT = Path(__file__).resolve().parent
PERF = ROOT / "upstream/rigmark"
QUALITY = ROOT / "upstream/rigmark-quality"
PLAN = json.loads((ROOT / "protocol.json").read_text())


def write(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def revision(path):
    return subprocess.check_output(["git", "-C", path, "rev-parse", "HEAD"], text=True).strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--metadata", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--comparison-id", default="sparkmodelbench-v1")
    p.add_argument("--trial", help="fresh shared text salt for a matched comparison")
    p.add_argument("--effort", choices=["low", "medium", "xhigh", "default"], default="low")
    p.add_argument("--portable", action="store_true", help="chat-only endpoint: skip exact prefill and use standard C4 chat fields")
    p.add_argument("--lanes", nargs="+", choices=["decode", "prefill", "c4", "quality"],
                   default=["decode", "prefill", "c4", "quality"])
    args = p.parse_args()
    dirty = subprocess.check_output(["git", "-C", ROOT, "diff", "--name-only", "HEAD", "--",
                                     "run.py", "protocol.json", "field_guide.py"])
    if dirty:
        p.error("commit changes to measured workload files before starting a run")
    if len(args.lanes) != len(set(args.lanes)):
        p.error("each lane can be requested once")
    pins = {}
    for path in (PERF, QUALITY):
        pin = subprocess.check_output(["git", "-C", ROOT, "rev-parse",
                                       "HEAD:" + str(path.relative_to(ROOT))], text=True).strip()
        if revision(path) != pin or subprocess.check_output(["git", "-C", path, "status", "--porcelain"]):
            p.error(f"restore the pinned clean submodule at {path}")
        pins[path.name] = pin
    sys.path.insert(0, str(PERF))
    import bench
    meta = bench.load_metadata(args.metadata)
    base = bench.validate_base_url(args.base_url)
    key = os.getenv("OPENAI_API_KEY", "")
    client = bench.Client(base, key, 1800)
    prompts, _ = bench.load_prompts(PERF / "prompts.json")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    trial = args.trial or secrets.token_hex(12)
    result = {"suite": revision(ROOT), "protocol": PLAN, "upstreams": pins,
              "model": args.model, "appliance": meta, "trial": trial,
              "comparison_id": args.comparison_id, "effort": args.effort, "portable": args.portable,
              "requested": args.lanes, "lanes": {}, "errors": {}}
    summary = out / "result.json"
    write(summary, result)
    for lane in args.lanes:
        print(f"Starting {lane}", flush=True)
        try:
            if lane == "decode":
                cmd = [PERF / "rigmark", "bench", "--model", args.model, "--base-url", base,
                       "--metadata", args.metadata.resolve(), "--label", "decode",
                       "--comparison-id", args.comparison_id, "--runs", str(PLAN["decode_runs"]),
                       "--decode-tokens", str(PLAN["decode_cap"]), "--skip-concurrency",
                       "--skip-prefill", "--output", out / "rigmark.json"]
                if args.effort != "default":
                    cmd.extend(["--extra-body", json.dumps({"reasoning_effort": args.effort})])
                subprocess.run(cmd, check=True)
                data = json.loads((out / "rigmark.json").read_text())["decode"]
                result["lanes"][lane] = {name: {"tokens_s": row["decode_tokens_per_second"]["median"],
                                                "last_s": row["time_to_last_output_seconds"]["median"],
                                                "output_tokens": [r["completion_tokens"] for r in row["runs"]],
                                                "gate": row["completion_gate"]}
                                         for name, row in data.items()}
            elif lane == "prefill":
                curve = result["lanes"][lane] = {}
                for depth in PLAN["prefill_depths"]:
                    if args.portable:
                        curve[depth] = {"skip": "chat-only mode; RigMark exact prefill requires token-ID completions"}
                        continue
                    if depth + 8 > meta["context_limit"]:
                        curve[depth] = {"skip": "context limit including output reserve"}
                        continue
                    record = bench.run_prefill(client, args.model, prompts, [depth],
                                               PLAN["prefill_pairs"], args.comparison_id)[str(depth)]
                    curve[depth] = {k: {"ttft_s": v["ttft_seconds"]["median"],
                                        "tokens_s": v["effective_prefill_tokens_per_second"]["median"],
                                        "cached_tokens": [r["cached_prompt_tokens"] for r in v["runs"]]}
                                    for k,v in record.items()}
                    write(out / f"prefill-{depth}.json", record)
                    write(summary, result)
            elif lane == "c4":
                rounds = result["lanes"][lane] = {}
                transport_errors = []
                for i in range(PLAN["c4"]["repetitions"] + 1):
                    record = capture(base, args.model, key, f"{trial}-{i}", PLAN["c4"], args.portable)
                    write(out / f"c4-{i}.json", record)
                    for r in record["requests"]:
                        if r.get("error") or not r["done"] or not r["usage"]:
                            transport_errors.append(f"round {i} stream {r['stream']}: " +
                                                    (r.get("error") or "missing DONE/usage"))
                    rounds["warmup" if i == 0 else str(i)] = {
                        "complete": record["complete"], "wall_s": record["wall_s"],
                        "streams": [{k: r[k] for k in ("ttft_s","max_visible_gap_s","usage")}
                                    for r in record["requests"]]}
                    write(summary, result)
                if transport_errors:
                    raise RuntimeError("; ".join(transport_errors))
            else:
                cmd = [QUALITY / "rigmark", "quality", "run", "--model", args.model, "--endpoint",
                       base + "/v1", "--output", out / "quality", "--seconds", str(PLAN["task_seconds"]),
                       "--max-output-tokens", str(PLAN["task_output_cap"])]
                for task in PLAN["quality_tasks"]:
                    cmd.extend(["--task", task])
                if args.effort != "default":
                    cmd.extend(["--reasoning-effort", args.effort])
                if key:
                    cmd.extend(["--api-key-env", "OPENAI_API_KEY"])
                subprocess.run(cmd, check=True)
                tasks = result["lanes"][lane] = {}
                for task in PLAN["quality_tasks"]:
                    r = json.loads((out / "quality" / f"{args.model.replace('/', '-')}-{task}.json").read_text())
                    usage = [e.get("usage") or {} for e in r["events"]]
                    tasks[task] = {"passed": r["artefact_passed"], "finished": r["conversation_finished"],
                                   "wall_s": r["elapsed_seconds"], "failure": r["failure"],
                                   "tokens": sum(u["completion_tokens"] for u in usage)
                                   if usage and all(isinstance(u.get("completion_tokens"), int) for u in usage)
                                   else None}
        except (RuntimeError, ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
            result["errors"][lane] = str(exc)
            print(f"{lane} failed: {exc}", file=sys.stderr, flush=True)
        write(summary, result)
    (out / "CARD.md").write_text(render(result))
    files = sorted(f for f in out.rglob("*") if f.is_file())
    (out / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(out)}\n" for f in files))
    print(summary)
    return int(bool(result["errors"]))


if __name__ == "__main__":
    sys.exit(main())
