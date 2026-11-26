# SPDX-License-Identifier: AGPL-3.0-only
"""SparkGLM field-guide workload, derived from bench/four_stream_video.py at b83e250."""
import concurrent.futures
import hashlib
import json
import threading
import time
import urllib.request

TOPICS = ("distributed systems engineering", "surprising facts about the solar system",
          "deep-ocean science and exploration", "practical robotics and embodied AI")


def capture(base, model, key, salt, settings, portable):
    epoch = []
    barrier = threading.Barrier(len(TOPICS), action=lambda: epoch.append(time.monotonic()))

    def request(index):
        facts = "\n".join(f"context-{index}-{i}: alpha beta gamma delta"
                          for i in range(settings["depth"] // 12))
        prompt = (f"Benchmark salt: {salt}\nRead the unique reference context below before "
                  f"answering the final request.\n{facts}\n\nFinal request:\n"
                  f"Write a dense numbered field guide containing concise facts about {TOPICS[index]}. "
                  "Start immediately with item 1. Use one short item per line, no introduction, "
                  "no conclusion, and continue until the response limit.")
        body = dict(model=model, messages=[{"role": "user", "content": prompt}], stream=True,
                    stream_options={"include_usage": True}, temperature=0, top_p=1,
                    max_tokens=settings["output"])
        if not portable:
            body.update(ignore_eos=True, chat_template_kwargs={"enable_thinking": False})
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        req = urllib.request.Request(base + "/v1/chat/completions",
                                     json.dumps(body).encode(), headers=headers)
        barrier.wait()
        zero = epoch[0]
        target = index * settings["interval_s"]
        time.sleep(max(0, zero + target - time.monotonic()))
        start = time.monotonic() - zero
        row = dict(stream=index, scheduled_s=target, start_s=start, events=[], usage={},
                   done=False, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
        try:
            with urllib.request.urlopen(req, timeout=900) as response:
                for raw in response:
                    if not raw.startswith(b"data:"):
                        continue
                    value = raw[5:].strip()
                    if value == b"[DONE]":
                        row["done"] = True
                        break
                    chunk = json.loads(value)
                    if chunk.get("error"):
                        raise ValueError(str(chunk["error"]))
                    if chunk.get("usage"):
                        row["usage"] = chunk["usage"]
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        if delta.get("content") or delta.get("reasoning_content"):
                            row["events"].append({"s": time.monotonic() - zero,
                                                  "visible": bool(delta.get("content"))})
                        if choice.get("finish_reason"):
                            row["finish_reason"] = choice["finish_reason"]
        except (OSError, ValueError) as exc:
            row["error"] = str(exc)
        row["end_s"] = time.monotonic() - zero
        times = [event["s"] for event in row["events"]]
        visible = [event["s"] for event in row["events"] if event["visible"]]
        row["ttft_s"] = times[0] - start if times else None
        row["max_visible_gap_s"] = max((b - a for a, b in zip(visible, visible[1:])), default=None)
        row["complete"] = bool(row["done"] and visible and not row.get("error")
                               and row["usage"].get("prompt_tokens", 0) > 0
                               and row.get("finish_reason") in ("stop", "length")
                               and row["usage"].get("completion_tokens") == settings["output"])
        return row

    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        rows = list(pool.map(request, range(4)))
    return {"requests": rows, "salt": salt, "portable": portable,
            "complete": all(row["complete"] for row in rows),
            "wall_s": max(row["end_s"] for row in rows) - min(row["start_s"] for row in rows)}
