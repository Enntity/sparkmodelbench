# SparkSplitTime

Measure generation speed, prefill over a context sweep, four staggered requests, and elapsed time and tokens to a checked result. Runs against a single OpenAI-compatible endpoint. Python 3.10+, Git and Docker are required for the complete suite.

    git clone --recurse-submodules https://github.com/Enntity/sparksplittime
    cd sparksplittime
    docker build -t rigmark-quality-runtime:0.4 upstream/rigmark-quality/quality_suite
    cp upstream/rigmark/metadata.example.json appliance.json
    # Fill in the appliance metadata before running.
    python3 run.py --base-url http://localhost:8000 --model MODEL --metadata appliance.json --out runs/first

The submodule commits pin upstream RigMark protocol 1.3.0 and RigMark Quality v0.0.2. The suite settings are in [protocol.json](protocol.json). The field-guide prompts, scheduling and request settings come from [SparkGLM](https://github.com/Enntity/sparkglm/blob/b83e250/bench/four_stream_video.py). The C4 capture retains client stream timing, server usage and actual start times. Round zero warms the engine and is excluded from the three measured rounds. Each round changes the first prompt line.

Read `result.json` alongside the upstream decode card and raw JSON files. Quality records separate a passing artifact from a finished conversation. Wall seconds and tokens cover every turn, and elapsed time includes local grading. A 180-second agent budget can be followed by grading time. A timeout, incomplete stream or missing usage stays visible. A nonzero runner exit signals a harness error. Model failures remain valid observations.

The standard sweep uses exact RigMark token IDs and three first/replay pairs per supported depth. The eight-token output reserve must fit. Treat the first request as cold only when the server reports zero cached tokens. Use `--extended` for the 512K and near-1M points. For chat-only servers, use `--portable --effort default` on both contenders. Portable depth labels count repeated text units, and receipts carry observed prompt counts and latency. Portable C4 permits natural stops and reports whether each stream delivered 400 tokens.

Use the same fresh `--trial` on both contenders, the same comparison ID, sampling, workload controls and placement. Match checkpoint, tokenizer and quantization for engine comparisons. Use an idle endpoint and record hardware, version, speculation, context limit and client network placement. Across different tokenizers compare wall time on the same correctly finished tasks. Report failed tasks alongside those comparisons. Set OPENAI_API_KEY when required. Use a new output directory for each run and `--lanes` to isolate individual measurements. Check the receipts from their directory with `sha256sum -c SHA256SUMS`.
