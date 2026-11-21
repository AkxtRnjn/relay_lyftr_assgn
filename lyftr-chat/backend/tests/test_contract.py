"""Contract tests using real SQLite, LiteLLM and a loopback provider."""
import json
import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from main import create_app


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.calls.append(body["messages"])
        token = self.headers["Authorization"]
        status = self.server.failures.get(token, 200)
        if status == 200:
            time.sleep(.04)
            turns = body["messages"]
            reply = "Received " + turns[-1]["content"]
            payload = {"id": "chat-test", "object": "chat.completion", "created": 1,
                       "model": body["model"], "choices": [{"index": 0, "finish_reason": "stop",
                       "message": {"role": "assistant", "content": reply}}],
                       "usage": {"prompt_tokens": len(turns)*5, "completion_tokens": 3, "total_tokens": len(turns)*5+3}}
        else:
            payload = {"error": {"message": "quota exhausted", "type": "insufficient_quota", "code": "insufficient_quota"}}
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())


class Contract(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        self.server.calls, self.server.failures = [], {}
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        env = patch.dict(os.environ, {"LLM_API_KEYS": "local-a,local-b", "LLM_MODEL": "openai/gpt-4o-mini",
            "DATABASE_URL": "sqlite:///" + str(Path(folder.name)/"app.db"),
            "ENABLE_FAILURE_SIMULATION": "true", "LLM_API_BASE": f"http://127.0.0.1:{self.server.server_port}/v1"})
        env.start()
        self.addCleanup(env.stop)
        self.client = self.enterContext(TestClient(create_app()))

    def chat(self, sid, msg, header=None, **extra):
        return self.client.post("/chat", json={"session_id":sid, "message":msg, **extra},
                                headers={"X-Simulate-Failure":header} if header else {})

    def test_cache_context_usage_and_restart(self):
        a = self.chat("one"," hello ").json()
        b = self.chat("two","hello").json()
        self.assertEqual(a["reply"], b["reply"])
        x, y = a["metadata"], b["metadata"]
        self.assertEqual(x["resolution_source"], "LIVE_INFERENCE")
        self.assertEqual(y["resolution_source"], "LLM_CACHE")
        self.assertEqual((y["key_id"], y["fallback_attempts"]), (None, 0))
        self.assertLess(y["latency_ms"], x["latency_ms"])
        self.assertEqual((x["input_tokens"], x["output_tokens"]), (y["input_tokens"], y["output_tokens"]))
        self.assertEqual(len(self.server.calls), 1)
        c = self.chat("one","next").json()
        self.assertEqual(c["metadata"]["input_tokens"], 20)
        self.assertEqual([m["content"] for m in self.server.calls[-1]][1:], ["hello", a["reply"], "next"])
        self.assertEqual(self.chat("three","different").json()["metadata"]["resolution_source"], "LIVE_INFERENCE")
        with TestClient(create_app()) as fresh:
            history = fresh.get("/sessions/one/messages").json()["messages"]
        self.assertEqual([m["role"] for m in history], ["user","assistant"]*2)
        self.assertEqual(history[-1]["metadata"], c["metadata"])

    def test_real_and_simulated_failover(self):
        for status in [429, 500]:
            self.server.failures = {"Bearer local-a":status}
            result = self.chat(str(status), f"actual {status}").json()
            self.assertEqual((result["metadata"]["key_id"], result["metadata"]["fallback_attempts"]), ("key_2", 1))
        self.server.failures = {}
        for status in [429,500,502,503]:
            result = self.chat(f"s{status}", "same", f"key_1={status}").json()
            self.assertEqual(result["metadata"]["key_id"], "key_2")
        for header in ["*=429", "key_1=429,key_2=500"]:
            r = self.chat("failed","same",header)
            self.assertEqual((r.status_code,r.json()), (503, {"detail":"all providers unavailable"}))
        self.assertEqual(self.client.get("/sessions/failed/messages").status_code, 404)
        self.assertEqual(self.chat("normal","fresh").json()["metadata"]["key_id"], "key_1")
        self.client.app.state.simulate = False
        self.assertEqual(self.chat("off","fresh again","*=429").status_code, 200)

    def test_prompt_and_rollback(self):
        self.chat("a","hello",system_prompt="terse")
        self.chat("a","ignored","*=429",system_prompt="bad")
        self.chat("a","more")
        self.assertEqual(self.server.calls[-1][0]["content"], "terse")
        self.assertEqual(len(self.server.calls[-1]), 4)
        result = self.chat("b","hello",system_prompt="verbose").json()
        self.assertEqual(result["metadata"]["resolution_source"], "LIVE_INFERENCE")

    def test_concurrent_session(self):
        with ThreadPoolExecutor(2) as pool:
            codes = list(pool.map(lambda msg: self.chat("one",msg).status_code, ["first","second"]))
        self.assertEqual(codes, [200,200])
        self.assertEqual([len(m) for m in self.server.calls], [2,4])

    def test_validation_health_and_routes(self):
        self.assertEqual(self.client.get("/health").json(), {"status":"ok","keys_configured":2,"cache_enabled":True})
        for sid, msg in [("", "hi"), (" "*2,"hi"), ("x"*129,"hi"), ("bad"," "), ("bad","a"*4001)]:
            self.assertEqual(self.chat(sid,msg).status_code, 422)
        for body in ["{}", "{"]:
            self.assertEqual(self.client.post("/chat", content=body, headers={"Content-Type":"application/json"}).status_code, 422)
        self.assertEqual(self.chat("bad","hi","key_1=abc").status_code, 422)
        self.assertEqual(self.client.get("/sessions/bad/messages").json(), {"detail":"session not found"})
        self.assertEqual(self.client.get("/openapi.json").status_code, 404)
