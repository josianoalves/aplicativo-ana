import http.client
import io
import json
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from contextlib import closing
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from radar.pipeline import Pipeline, TZ, settings_for
from radar.server import handler_for
from radar.store import DEFAULT, Store


class Catalog:
    def __init__(self):
        self.link_count = 0

    def products(self, keyword, limit):
        return [dict(id="1-2", name="Câmera", url="https://shopee.com.br/product/1/2",
                     price=60, sales=10000, rating=5, commission_rate=.2)]

    def link(self, url):
        self.link_count += 1
        return "https://s.shopee.com.br/test"


class AppTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(self.folder.name)
        self.catalog = Catalog()
        self.renders = []
        self.pipeline = Pipeline(self.store, lambda: self.catalog, self.render)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        self.host = f"127.0.0.1:{self.server.server_port}"
        self.server.RequestHandlerClass = handler_for(self.pipeline, "test-token", self.host)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def render(self, product, script, media, output, duration, variant, music, stop):
        self.assertEqual(media.read_bytes(), b"sample")
        self.assertEqual(len(script["segments"]), 5)
        self.renders.append(variant)
        output.write_bytes(b"test-render")

    def request(self, method, path, data=None, authorized=True):
        connection = http.client.HTTPConnection(self.host, timeout=3)
        self.addCleanup(connection.close)
        headers = {"Origin": f"http://{self.host}", "X-Radar-Token": "test-token"} if authorized else {}
        payload = json.dumps(data) if isinstance(data, dict) else data
        connection.request(method, path, payload, headers)
        response = connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw) if "application/json" in response.getheader("Content-Type", "") else raw

    def test_pipeline_to_publication_and_backup(self):
        self.assertEqual(self.request("GET", "/")[0], 200)
        self.assertEqual(self.request("GET", "/api/state")[1]["counts"]["products"], 0)
        self.assertEqual(self.request("POST", "/api/pause", authorized=False)[0], 403)
        self.assertEqual(self.request("POST", "/api/pause")[0], 200)
        self.assertFalse(self.pipeline.start())
        self.assertEqual(self.request("POST", "/api/resume")[0], 200)
        self.assertEqual(self.request("POST", "/api/settings", DEFAULT)[0], 200)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "SHOPEE_APP_ID": "test", "SHOPEE_SECRET": "test"}):
            self.assertEqual(self.request("POST", "/api/run")[0], 200)
            self.pipeline.worker.join(5)
            self.assertEqual(self.store.get("last_run")["status"], "ok")
            self.assertEqual(self.store.get("last_run")["videos"], 0)
            self.assertEqual(self.request("POST", "/api/media?id=1-2&name=cam.mov", b"sample")[0], 200)
            self.assertEqual(self.request("POST", "/api/run")[0], 200)
            self.pipeline.worker.join(5)
            self.assertEqual(self.request("POST", "/api/run")[0], 200)
            self.pipeline.worker.join(5)
        self.assertEqual(self.renders, [1, 2])
        self.assertEqual(self.catalog.link_count, 1)
        status = self.request("GET", "/api/state")[1]
        self.assertTrue(status["products"][0]["has_media"])
        self.assertEqual(status["counts"]["videos"], 2)
        video = status["videos"][0]["id"]
        self.assertEqual(self.request("GET", f"/api/video?id={video}"), (200, b"test-render"))
        code, payload = self.request("GET", f"/api/package?id={video}")
        self.assertEqual(code, 200)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertEqual(archive.namelist(), ["video.mp4", "legenda.txt", "produto.txt"])
            self.assertIn(b"/product/1/2", archive.read("produto.txt"))
        self.assertEqual(self.request("POST", "/api/published", {"id": video, "publication_id": "123"})[0], 200)
        self.assertEqual(self.request("POST", "/api/results", {"id": video, "confirmed_commission": 6.50})[0], 200)
        self.assertEqual(self.request("GET", "/api/state")[1]["counts"]["confirmed_commission"], 6.5)
        backup = Path(self.request("POST", "/api/backup")[1]["path"])
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM videos").fetchone()[0], 2)

    def test_invalid_settings(self):
        for change in ({"variants": 1}, {"keywords": "x" * 201}, {"times": {"research": "25:00"}}):
            with self.assertRaises(ValueError):
                settings_for({**DEFAULT, **change})
        self.assertEqual(self.request("POST", "/api/media?id=1-2&name=cam.exe", b"x")[0], 400)

    def test_scheduled_start_is_deduplicated_by_local_day(self):
        moment = datetime(2026, 11, 8, 8, 5, tzinfo=TZ)
        shutdown = threading.Event()
        with patch("radar.pipeline.now", return_value=moment), patch.object(self.pipeline, "execute"):
            self.assertTrue(self.pipeline.start(moment))
            self.pipeline.worker.join(3)
            self.assertEqual(self.store.get("schedule_day"), "2026-11-08")
            self.assertEqual(self.pipeline.next_run(), "2026-11-09T08:05:00-03:00")
            with patch.object(shutdown, "is_set", side_effect=[False, True]), patch.object(shutdown, "wait"), patch.object(self.pipeline, "start") as start:
                self.pipeline.schedule(shutdown)
                start.assert_not_called()

    def test_retries_are_bounded(self):
        calls = []

        def unavailable():
            calls.append(1)
            raise RuntimeError("Network failure")

        with patch.object(self.pipeline.stop, "wait", return_value=False):
            with self.assertRaises(RuntimeError):
                self.pipeline.retry("test", unavailable)
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.store.logs()[0]["status"], "retry")






