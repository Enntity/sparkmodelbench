# SparkModelBench

**SparkModelBench runs Alex Ellis’s RigMark and RigMark Quality with the settings we use to compare Spark inference servers.** Alex Ellis and OpenFaaS Ltd publish both projects under the MIT license. The serving prompts, decode and prefill measurements, quality tasks, tools, graders and upstream receipts come from their work. [RigMark](https://github.com/alexellis/rigmark) · [RigMark Quality](https://github.com/alexellis/rigmark-quality)

**Enntity adds one test scenario**, the staggered four-request field guide from SparkGLM. RigMark starts the requests in a concurrency round together. Our field guide starts four long requests one second apart so we can observe the effect of arriving prefills on streams already in flight. The rest of this repository pins the upstream tools, selects parameters and prints their results together. [RigMark concurrency protocol](https://github.com/alexellis/rigmark/blob/946394fa/PROTOCOL.md#concurrency) · [Original SparkGLM scenario](https://github.com/Enntity/sparkglm/blob/b83e250/bench/four_stream_video.py)

## What runs

| Source | Settings and measurements |
|---|---|
| RigMark, protocol 1.3.0 | Five code, prose and structured-output samples each. 8,192-token cap, temperature zero, low reasoning effort by default. Record decode tok/s, time to last output and completion gates. |
| RigMark prefill | Its exact token-ID workload at 8K, 32K, 64K, 128K and 256K, three first/immediate-replay pairs per depth. Include the eight-token output reserve when checking the context limit. |
| RigMark Quality, v0.0.2 | Four unchanged tasks: `python-expiry`, `go-transfer-ledger`, `payment-recovery` and `evidence-revisions`. Each gets a 180-second agent budget and an 8,192-token cap per response. Report checks, conversation finish, seconds and output tokens across turns. Grading time is included in elapsed seconds. |
| Enntity’s staggered C4 | Four distinct field-guide prompts of approximately 16K tokens arrive at 0, 1, 2 and 3 seconds, each with a 400-token output budget. Discard one warm-up and retain all three measured rounds, including each stream’s actual start, first token and visible stalls. |

**Optional: RigMark concurrency.** `--lanes ... concurrency` adds RigMark's own concurrency sweep: 1, 2, 4 and 8 code requests released together through a barrier, 256 output tokens each, three rounds per level, at the same effort as the other lanes. It reports aggregate throughput (prefill and scheduling included), per-stream decode and per-stream time to first token, and keeps RigMark's raw rounds in `concurrency.json`. It is RigMark's workload, not an Enntity addition, and it is not in the default suite. Name it on both contenders when you compare.

The upstream checkouts and licenses are pinned in [upstream/rigmark](upstream/rigmark) and [upstream/rigmark-quality](upstream/rigmark-quality). Enntity’s parameter choices are in [protocol.json](protocol.json).

## Run

Python 3.10+, Git and Docker are required for the complete suite.

    git clone --recurse-submodules https://github.com/enntity/sparkmodelbench
    cd sparkmodelbench
    docker build -t rigmark-quality-runtime:0.4 upstream/rigmark-quality/quality_suite
    cp upstream/rigmark/metadata.example.json appliance.json
    # Fill in the appliance metadata before running.
    python3 run.py --base-url http://localhost:8000 --model MODEL --metadata appliance.json --out runs/first

Use the same fresh `--trial` on both contenders, the same comparison ID and the same request controls. Match checkpoint, tokenizer and quantization for engine comparisons. Record hardware, image, speculation, context limit and client placement. Set `OPENAI_API_KEY` for authenticated endpoints. Use a new output directory per run. The `--lanes` option selects individual measurements.

For chat-only endpoints use `--portable --effort default` on both contenders. The report marks RigMark’s exact-depth prefill as skipped when those interfaces are unavailable. Portable C4 permits natural stops and records the actual output counts.

## Read the result

Open `CARD.md` for the combined report. The original RigMark card, JSON and per-task RigMark Quality receipts sit beside it. Retain the raw repetitions and check them from the result directory with `sha256sum -c SHA256SUMS`. A zero cached-token count supports a cold prefill claim; missing cache evidence is labelled unverified. Compare wall time across different tokenizers on tasks both contenders finished correctly, and show the failed tasks alongside them. A nonzero runner exit signals a harness error. Model failures are recorded as outcomes.
