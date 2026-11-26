# SPDX-License-Identifier: AGPL-3.0-only
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock

from card import render
from field_guide import capture
from run import fixed_text


class ProtocolTest(unittest.TestCase):
    def test_c4_preserves_partial_stream_and_all_other_lanes(self):
        class Endpoint(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                prompt = body["messages"][0]["content"]
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n')
                footer = {"choices": [{"delta": {}, "finish_reason": "length"}],
                          "usage": {"prompt_tokens": 16, "completion_tokens": 400}}
                self.wfile.write(b"data: " + json.dumps(footer).encode() + b"\n\n")
                if "deep-ocean" not in prompt:
                    self.wfile.write(b"data: [DONE]\n\n")

            def log_message(self, *args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Endpoint) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                data = capture(f"http://127.0.0.1:{server.server_port}", "test", "", "salt",
                               dict(depth=16, interval_s=0.01, output=400), True)
            finally:
                server.shutdown()
                thread.join()
        self.assertFalse(data["complete"])
        self.assertEqual([r["complete"] for r in data["requests"]], [True, True, False, True])
        self.assertEqual(len({r["prompt_sha256"] for r in data["requests"]}), 4)
        self.assertTrue(all(r["start_s"] >= r["scheduled_s"] for r in data["requests"]))

    def test_fixed_text_replays_identical_request_only_within_pair(self):
        client = Mock()
        client.stream.side_effect = lambda *_: {"prompt_tokens": 27}
        runs = fixed_text(client, "test", 8, "shared", 2)["runs"]
        hashes = [r["prompt_sha256"] for r in runs]
        self.assertEqual(hashes[::2], hashes[1::2])
        self.assertNotEqual(hashes[0], hashes[2])

    def test_missing_cache_evidence_stays_unverified(self):
        row = dict(ttft_s=1.2, tokens_s=123, cached_tokens=[None, None, None])
        result = dict(model="test", appliance=dict(hardware="cpu", serving_engine="fixture"),
                      suite="abc", comparison_id="one", portable=False, errors={},
                      lanes={"prefill": {"128": {"cold": row, "warm_replay": row}}})
        self.assertIn("unverified", render(result))
        self.assertNotIn("zero cached tokens reported", render(result))


if __name__ == "__main__":
    unittest.main()
