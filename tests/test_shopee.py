"""Shopee transport and mapping tests with synthetic API responses."""

import hashlib
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from radar.shopee import ENDPOINT, Shopee, ShopeeError


PRODUCT_URL = "https://shopee.com.br/product/123/456"
SHORT_LINK = "https://s.shopee.com.br/synthetic"


def node(item=456, **values):
    return {
        "shopId": 123,
        "itemId": item,
        "productName": "Produto de teste",
        "productLink": f"https://shopee.com.br/product/123/{item}",
        "imageUrl": "https://example.test/photo.jpg",
        "priceMin": "12.90",
        "priceMax": "24.90",
        "sales": 48,
        "ratingStar": "4.7",
        "commissionRate": "0.06",
        "shopName": "Loja de teste",
        "productCatIds": [100, 200, 0],
        **values,
    }


def page(nodes, more=False):
    return {"productOfferV2": {"nodes": nodes, "pageInfo": {"hasNextPage": more}}}


class ShopeeTests(unittest.TestCase):
    def setUp(self):
        self.client = Shopee("123456", "secret-test")

    def test_catalog_signs_exact_post_body_and_maps_documented_fields(self):
        response = {"data": page([node()])}
        with patch.object(self.client._opener, "open", return_value=io.BytesIO(json.dumps(response).encode())) as send:
            with patch("radar.shopee.time.time", return_value=1577836800):
                product, = self.client.products('Café "forte"', 1)
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, ENDPOINT)
        self.assertEqual(request.get_method(), "POST")
        factor = b"1234561577836800" + request.data + b"secret-test"
        digest = hashlib.sha256(factor).hexdigest()
        self.assertEqual(request.headers["Authorization"],
                         f"SHA256 Credential=123456, Timestamp=1577836800, Signature={digest}")
        self.assertNotIn(b"secret-test", request.data)
        self.assertIn(r'keyword: "Café \"forte\""', json.loads(request.data)["query"])
        self.assertEqual(product["id"], "123-456")
        self.assertEqual(product["price"], 12.90)
        self.assertEqual(product["max_price"], 24.90)
        self.assertEqual(product["sales"], 48)
        self.assertEqual(product["rating"], 4.7)
        self.assertEqual(product["commission_rate"], 0.06)
        self.assertEqual(product["category"], "100 / 200")
        self.assertTrue(all(product[key] is None for key in ("reviews", "views", "previous_price")))

    def test_paginated_catalog_deduplicates_and_stops_at_limit(self):
        with patch.object(self.client, "_query", side_effect=[
            page([node()], True), page([node(), node(457), node(458)], True)
        ]) as query:
            products = self.client.products("", 2)
        self.assertEqual([product["id"] for product in products], ["123-456", "123-457"])
        self.assertIn("page: 2", query.call_args.args[0])
        self.assertNotIn("keyword:", query.call_args.args[0])

    def test_no_results_and_unavailable_numeric_values(self):
        with patch.object(self.client, "_query", return_value=page([])):
            self.assertEqual(self.client.products("", 1), [])
        with patch.object(self.client, "_query", return_value=page([
            node(sales=True, ratingStar="5.5", priceMin="NaN", commissionRate="-0.01")
        ])):
            product, = self.client.products("", 1)
        self.assertTrue(all(product[key] is None for key in ("sales", "rating", "price", "commission_rate")))

    def test_mismatched_product_identity_fails_closed(self):
        with patch.object(self.client, "_query", return_value=page([node(productLink="https://shopee.com.br/product/123/999")])):
            with self.assertRaises(ShopeeError):
                self.client.products("", 1)

    def test_link_is_generated_for_the_selected_product(self):
        with patch.object(self.client, "_query", return_value={"generateShortLink": {"shortLink": SHORT_LINK}}) as query:
            self.assertEqual(self.client.link(PRODUCT_URL), SHORT_LINK)
            self.assertEqual(self.client.link("https://shopee.com.br/produto-i.123.456"), SHORT_LINK)
        self.assertIn(PRODUCT_URL, query.call_args_list[0].args[0])
        self.assertIn("generateShortLink", query.call_args.args[0])

    def test_link_rejects_generic_origin_and_foreign_result(self):
        with patch.object(self.client, "_query") as query:
            for url in ["https://shopee.com.br", "https://shopee.com.br/product/123.456",
                        "https://shopee.com.br@other.test/product/123/456"]:
                with self.subTest(url=url), self.assertRaises(ShopeeError):
                    self.client.link(url)
            query.assert_not_called()
        with patch.object(self.client, "_query", return_value={
            "generateShortLink": {"shortLink": "https://example.test/invalid"}
        }), self.assertRaises(ShopeeError):
            self.client.link(PRODUCT_URL)

    def test_rejects_missing_credentials_before_network_access(self):
        client = Shopee("", "")
        with patch.object(client._opener, "open") as send, self.assertRaises(ShopeeError):
            client.products("", 1)
        send.assert_not_called()

    def test_graphql_errors_are_safe_for_display(self):
        response = {"data": page([node()]), "errors": [{
            "message": "secret-test", "extensions": {"code": 10020}
        }]}
        with patch.object(self.client._opener, "open", return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaisesRegex(ShopeeError, "recusou a autenticação") as failure:
                self.client.products("", 1)
        self.assertNotIn("secret-test", str(failure.exception))

    def test_transport_failures_are_safe_for_display(self):
        cases = [
            (URLError("secret-test"), "Falha de conexão"),
            (HTTPError(ENDPOINT, 503, "secret-test", {}, None), "HTTP 503"),
        ]
        for error, message in cases:
            with self.subTest(error=type(error)), patch.object(self.client._opener, "open", side_effect=error):
                with self.assertRaisesRegex(ShopeeError, message) as failure:
                    self.client.products("", 1)
                self.assertNotIn("secret-test", str(failure.exception))


if __name__ == "__main__":
    unittest.main()
