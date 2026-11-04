"""A stand-in for the Anthropic API (just enough for Claude Code): every request logged, each answered 'OK'."""
import json, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
LOG = sys.argv[2]
lock = threading.Lock()


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def note(self, method, raw):
        with lock, open(LOG, "a") as f:
            f.write(json.dumps({"method": method, "path": self.path, "body": raw.decode("utf-8", "replace")}) + "\n")

    def send_json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.note("GET", b"")
        if self.path.startswith("/v1/models"):
            return self.send_json(200, {"data": [], "has_more": False})
        self.send_json(404, {"type": "error", "error": {"type": "not_found_error", "message": "no"}})

    def do_HEAD(self):
        self.send_response(200); self.send_header("Content-Length", "0"); self.end_headers()

    def do_POST(self):
        raw = self.body()
        self.note("POST", raw)
        path = self.path.split("?")[0]
        if path.endswith("/count_tokens"):
            return self.send_json(200, {"input_tokens": 12})
        if not path.endswith("/v1/messages"):
            return self.send_json(404, {"type": "error", "error": {"type": "not_found_error", "message": "no"}})
        try:
            req = json.loads(raw)
        except ValueError:
            req = {}
        model = req.get("model", "claude-test")
        msg = {"id": "msg_1", "type": "message", "role": "assistant", "model": model,
               "content": [{"type": "text", "text": "OK"}], "stop_reason": "end_turn", "stop_sequence": None,
               "usage": {"input_tokens": 12, "output_tokens": 1}}
        if not req.get("stream"):
            return self.send_json(200, msg)
        events = [("message_start", {"type": "message_start", "message": dict(msg, content=[], stop_reason=None)}),
                  ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
                  ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "OK"}}),
                  ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                  ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 1}}),
                  ("message_stop", {"type": "message_stop"})]
        data = "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in events).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


srv = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H)
srv.serve_forever()
