import io
import json
import tempfile
import unittest
from unittest.mock import patch

from radar import whatsapp
from radar.pipeline import Pipeline
from radar.store import Store

CONFIG = {
    "RADAR_MODO_WHATSAPP": "1", "WHATSAPP_PHONE_ID": "123",
    "WHATSAPP_DESTINO": "5585999999999", "WHATSAPP_TOKEN": "sample-token",
}


class WhatsAppTests(unittest.TestCase):
    def test_meta_template_request(self):
        with patch.dict("os.environ", CONFIG, clear=True), patch(
            "radar.whatsapp.urllib.request.urlopen",
            return_value=io.BytesIO(b'{"messages":[{"id":"wamid.example"}]}'),
        ) as http:
            self.assertEqual(whatsapp.send(["one", "two", "three"]), "wamid.example")
        request = http.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/123/messages"))
        body = json.loads(request.data)
        self.assertEqual(body["to"], CONFIG["WHATSAPP_DESTINO"])
        self.assertEqual(body["template"]["language"]["code"], "pt_BR")
        self.assertEqual([p["text"] for p in body["template"]["components"][0]["parameters"]],
                         ["one", "two", "three"])

    def test_top_three_once_without_video(self):
        from unittest.mock import Mock
        client = Mock()
        client.products.return_value = [
            dict(id=str(index), name=f"Produto {index}", sales=sales, url=f"https://shopee.com.br/product/1/{index}")
            for index, sales in enumerate([10, 100, None, 50, 75], 1)
        ]
        client.link.side_effect = lambda url: f"https://s.shopee.com.br/{url.rsplit('/', 1)[1]}"
        render = Mock()
        with tempfile.TemporaryDirectory() as folder, patch.dict("os.environ", CONFIG, clear=True), patch(
            "radar.pipeline.whatsapp.send", return_value="wamid.example"
        ) as send:
            store = Store(folder)
            pipeline = Pipeline(store, lambda: client, render)
            pipeline.execute()
            self.assertEqual(store.get("last_run")["whatsapp"], "accepted")
            pipeline.execute()
            self.assertEqual(store.get("last_run")["status"], "ok")
            self.assertEqual({p["id"] for p in store.rows("products") if p["selected"]}, {"2", "4", "5"})
        send.assert_called_once_with([f"https://s.shopee.com.br/{index}" for index in (2, 5, 4)])
        render.assert_not_called()
