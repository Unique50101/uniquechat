"""A loopback-only server for the bundled uniquechat interface."""
import base64
import json
import secrets
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path

from .engine import Engine, TEXT, VISION, read_turn

MAX_BODY = 36 * 1024**2
ASSETS = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/app.css": ("app.css", "text/css")}


def user_message(item, folder, vision):
    prompt = item["text"]
    attachments = item.get("files", [])
    if not isinstance(prompt, str) or len(prompt) > 64000 or len(attachments) > 3:
        raise ValueError("Shorten your message or choose at most three files.")
    paths = []
    for i, attachment in enumerate(attachments):
        name = attachment["name"]
        if not name or Path(name).name != name or name in {".", ".."} or "\\" in name:
            raise ValueError("Invalid filename.")
        directory = Path(folder) / str(i)
        directory.mkdir()
        path = directory / name
        path.write_bytes(base64.b64decode(attachment["data"], validate=True))
        paths.append(path)
    return read_turn(prompt, paths, vision)


class Session:
    def __init__(self, initial, offline):
        self.initial = initial
        self.offline = offline
        self.lock = threading.Lock()
        self.engine = None
        self.state = dict(phase="idle", model="", message="", vision=False)
        self.token = secrets.token_urlsafe(32)

    def load(self, repo):
        if not isinstance(repo, str) or not repo.strip() or len(repo) > 160:
            raise ValueError("Enter a Hugging Face model ID.")
        if not self.lock.acquire(blocking=False):
            raise ValueError("Another operation is running.")
        self.state = dict(phase="loading", model=repo, message="Checking local files…", vision=False)
        threading.Thread(target=self._load, args=(repo,), daemon=True).start()

    def _load(self, repo):
        try:
            self.engine = None
            try:
                engine = Engine(repo, cached=True)
            except OSError:
                if self.offline:
                    raise ValueError("Model files are missing. Load the model once while online.") from None
                self.state = {**self.state, "message": "Downloading model files and loading weights…"}
                engine = Engine(repo, cached=False)
            self.engine = engine
            self.state = dict(phase="ready", model=repo, message="Running locally", vision=engine.vision)
        except Exception as exc:
            self.state = dict(phase="error", model=repo, message=str(exc), vision=False)
        finally:
            self.lock.release()

    def reply(self, data):
        if not self.lock.acquire(blocking=False):
            raise ValueError("A model operation is already running.")
        try:
            if self.engine is None or data.get("model") != self.state["model"]:
                raise ValueError("Load the conversation's model first.")
            turns = data["turns"]
            if not isinstance(turns, list) or not 0 < len(turns) <= 101 or len(turns) % 2 != 1:
                raise ValueError("Start a new chat or send a user message.")
            messages = []
            for i, turn in enumerate(turns):
                if i % 2:
                    if turn["role"] != "assistant" or not isinstance(turn["text"], str):
                        raise ValueError("Invalid conversation.")
                    messages.append({"role": "assistant", "content": [{"type": "text", "text": turn["text"]}]})
                else:
                    if turn["role"] != "user":
                        raise ValueError("Invalid conversation.")
                    with tempfile.TemporaryDirectory() as folder:
                        messages.append(user_message(turn, folder, self.engine.vision))
            return self.engine.reply(messages)
        finally:
            self.lock.release()


def handler(session):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_body(self, code, body, mime):
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, code, value):
            self.send_body(code, json.dumps(value).encode(), "application/json")

        def local_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.local_host():
                return self.send_error(403)
            if self.path == "/api/config":
                return self.send_json(200, dict(initial=session.initial, offline=session.offline,
                    token=session.token, models=[TEXT, VISION]))
            if self.path == "/api/status":
                return self.send_json(200, session.state)
            if self.path not in ASSETS:
                return self.send_error(404)
            filename, mime = ASSETS[self.path]
            self.send_body(200, files("uniquechat").joinpath("static", filename).read_bytes(), mime)

        def do_POST(self):
            if not self.local_host() or self.headers.get("X-Uniquechat") != session.token:
                return self.send_error(403)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BODY:
                    return self.send_json(413, {"error": "Conversation too large. Start a new chat."})
                data = json.loads(self.rfile.read(size))
                if self.path == "/api/load":
                    session.load(data["model"])
                    return self.send_json(202, {"accepted": True})
                if self.path == "/api/chat":
                    return self.send_json(200, {"text": session.reply(data)})
                return self.send_error(404)
            except Exception as exc:
                self.send_json(400, {"error": str(exc)})
    return Handler


def serve(initial=None, *, offline=False, inbrowser=True, bind="127.0.0.1"):
    session = Session(initial, offline)
    # A stable origin lets the browser reopen its locally saved conversations.
    with ThreadingHTTPServer((bind, 7860), handler(session)) as http:
        url = "http://127.0.0.1:7860"
        print(f"uniquechat is running at {url}. Press Ctrl+C to stop.", flush=True)
        if inbrowser:
            webbrowser.open(url)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass
