#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Render a SparkModelBench result without querying the endpoint."""
import argparse
import json
from pathlib import Path
from statistics import median


def number(value):
    return "—" if value is None else f"{value:,.2f}"


def render(result):
    lanes = result["lanes"]
    meta = result["appliance"]
    lines = [f"# {result['model']} · SparkModelBench", "",
             f"{meta['hardware']} · {meta['serving_engine']}", "",
             "Serving measurements and quality tasks by **Alex Ellis, OpenFaaS Ltd**. "
             "[RigMark](https://github.com/alexellis/rigmark) · "
             "[RigMark Quality](https://github.com/alexellis/rigmark-quality). "
             "Enntity adds the staggered four-request field guide.", "",
             f"Comparison `{result['comparison_id']}` · suite `{result['suite'][:12]}`", ""]
    if "quality" in lanes:
        lines.extend(["## RigMark Quality · task completion", "", "| Task | Checks passed | Finished | Seconds | Output tokens |",
                      "|---|---|---|---:|---:|"])
        for task, row in lanes["quality"].items():
            lines.append(f"| {task} | {row['passed']} | {row['finished']} | {number(row['wall_s'])} | "
                         f"{row['tokens'] if row['tokens'] is not None else '—'} |")
        lines.append("")
    if "decode" in lanes:
        lines.extend(["## RigMark · generation, median", "", "| Workload | Tok/s | Last output (s) | Output tokens | Gates |",
                      "|---|---:|---:|---:|---:|"])
        for name, r in lanes["decode"].items():
            gates = r["gate"]
            lines.append(f"| {name} | {number(r['tokens_s'])} | {number(r['last_s'])} | "
                         f"{median(r['output_tokens']):g} | {gates['passed']}/{gates['total']} |")
        lines.append("")
    if "c4" in lanes:
        lines.extend(["## SparkGLM · staggered C4", "", "| Round | Wall (s) | Stream TTFT (s) | Longest visible gap (s) | Full streams |",
                      "|---|---:|---|---:|---|"])
        valid = []
        for name, r in lanes["c4"].items():
            ttft = ", ".join(number(s["ttft_s"]) for s in r["streams"])
            gaps = [s["max_visible_gap_s"] for s in r["streams"] if s["max_visible_gap_s"] is not None]
            lines.append(f"| {name} | {number(r['wall_s'])} | {ttft} | {number(max(gaps, default=None))} | {r['complete']} |")
            if name != "warmup" and r["complete"]:
                valid.append(r["wall_s"])
        if len(valid) == result["protocol"]["c4"]["repetitions"]:
            lines.extend(["", f"Median measured wall time **{number(median(valid))} s**."])
        lines.append("")
    if "prefill" in lanes:
        lines.extend(["## RigMark · prefill", ""])
        if result["portable"]:
            lines.extend(["Skipped on this chat-only endpoint. Exact-depth prefill requires RigMark's token-ID completion path.", ""])
        else:
            lines.extend(["| Prompt tokens | First TTFT (s) | First tok/s | Replay TTFT (s) | Replay tok/s | First cache evidence |",
                          "|---:|---:|---:|---:|---:|---|"])
        skipped = []
        for depth, r in lanes["prefill"].items():
            if "skip" in r:
                skipped.append(str(depth))
            else:
                first, replay = r["cold"], r["warm_replay"]
                observed = first["cached_tokens"]
                verified = bool(observed) and all(n == 0 for n in observed)
                lines.append(f"| {depth} | {number(first['ttft_s'])} | {number(first['tokens_s'])} | "
                             f"{number(replay['ttft_s'])} | {number(replay['tokens_s'])} | "
                             f"{'zero cached tokens reported' if verified else 'unverified'} |")
        if skipped and not result["portable"]:
            lines.extend(["", "Outside the declared context limit including output reserve: " + ", ".join(skipped) + "."])
        lines.append("")
    for lane, error in result["errors"].items():
        lines.append(f"**{lane} harness error** — {error}")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    print(render(json.loads(args.result.read_text())), end="")
