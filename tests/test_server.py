import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from uniquechat.server import Session, handler


class LocalHTTP(unittest.TestCase):
    def setUp(self):
        self.session = Session(None, True)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.session))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_assets(self):
        for path in ("/", "/app.js", "/app.css", "/api/config"):
            with urlopen(self.origin + path) as resp:
                self.assertGreater(len(resp.read()), 50)

    def test_post_requires_token(self):
        with self.assertRaises(HTTPError) as raised:
            urlopen(Request(self.origin + "/api/load", data=b"{}"))
        self.assertEqual(raised.exception.code, 403)

    def test_offline_cache_miss(self):
        with patch("uniquechat.server.Engine", side_effect=OSError("missing")) as factory:
            self.session.lock.acquire()
            self.session._load("a/b")
            factory.assert_called_once_with("a/b", cached=True)
            self.assertEqual(self.session.state["phase"], "error")

    def test_chat_route(self):
        class Fixture:
            vision = False
            def reply(self, messages):
                return messages[-1]["content"][0]["text"]
        self.session.engine = Fixture()
        self.session.state.update(model="a/b", phase="ready")
        data = {"model":"a/b", "turns":[{"role":"user", "text":"hello", "files":[]}]}
        req = Request(self.origin + "/api/chat", data=json.dumps(data).encode(),
                      headers={"X-Uniquechat":self.session.token})
        with urlopen(req) as reply:
            self.assertEqual(json.load(reply)["text"], "hello")
