"""Shopee Brasil Affiliate Open API catalog and short-link client."""

import hashlib
import json
import math
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ENDPOINT = "https://open-api.affiliate.shopee.com.br/graphql"
_CATALOG_FIELDS = """
    nodes {
        shopId itemId productName imageUrl priceMin priceMax sales ratingStar
        commissionRate shopName productCatIds productLink offerLink
    }
    pageInfo { hasNextPage }
"""
_PRODUCT_PATH = re.compile(r"/product/([0-9]+)/([0-9]+)/?")
_PRODUCT_SLUG = re.compile(r"/[^/]*-i\.([0-9]+)\.([0-9]+)/?")


class ShopeeError(RuntimeError):
    """Safe-to-display failure from the Shopee integration."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _https_url(value, domains=None):
    if not isinstance(value, str) or re.search(r"[\s\\]", value):
        return None
    try:
        url = urlsplit(value)
        host = url.hostname
        if (url.scheme == "https" and host and not url.username and not url.password
                and url.port in (None, 443) and (domains is None or host in domains)):
            return value
    except ValueError:
        pass
    return None


def _product_url(value):
    if not _https_url(value, {"shopee.com.br", "www.shopee.com.br"}):
        return None
    path = urlsplit(value).path
    return _PRODUCT_PATH.fullmatch(path) or _PRODUCT_SLUG.fullmatch(path)


def _number(value, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        value = float(value)
    except (ValueError, OverflowError):
        return None
    if math.isfinite(value) and value >= 0 and (maximum is None or value <= maximum):
        return value
    return None


def _product(node):
    if not isinstance(node, dict):
        raise ShopeeError("A Shopee retornou uma oferta em formato inválido.")
    shop_id, item_id = str(node.get("shopId")), str(node.get("itemId"))
    name = node.get("productName")
    url = node.get("productLink")
    url_product = _product_url(url)
    if (not re.fullmatch(r"[1-9][0-9]*", shop_id) or not re.fullmatch(r"[1-9][0-9]*", item_id)
            or not isinstance(name, str) or not name.strip()
            or not url_product or url_product.groups() != (shop_id, item_id)):
        raise ShopeeError("A Shopee retornou uma oferta sem identificação ou link de produto válido.")
    categories = node.get("productCatIds")
    categories = [str(n) for n in categories if type(n) is int and n > 0] if isinstance(categories, list) else []
    shop = node.get("shopName")
    shop = shop.strip() if isinstance(shop, str) else None
    return {
        "id": f"{shop_id}-{item_id}",
        "shop_id": shop_id,
        "item_id": item_id,
        "name": name.strip(),
        "image": _https_url(node.get("imageUrl")),
        "price": _number(node.get("priceMin")),
        "max_price": _number(node.get("priceMax")),
        "previous_price": None,
        "sales": node["sales"] if type(node.get("sales")) is int and node["sales"] >= 0 else None,
        "views": None,
        "rating": _number(node.get("ratingStar"), 5),
        "reviews": None,
        "commission_rate": _number(node.get("commissionRate"), 1),
        "shop": shop or None,
        "category": " / ".join(categories) or None,
        "url": url,
        "offer_link": _https_url(node.get("offerLink"), {"s.shopee.com.br", "shope.ee"}),
    }


class Shopee:
    def __init__(self, app_id, secret):
        self.app_id = (app_id or "").strip()
        self._secret = (secret or "").strip()
        self._opener = build_opener(_NoRedirect())

    def _query(self, query):
        if not re.fullmatch(r"[0-9]+", self.app_id) or not self._secret:
            raise ShopeeError("Configure o App ID e o Secret da API de afiliados Shopee.")
        payload = json.dumps({"query": query}, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(time.time()))
        factor = (self.app_id + timestamp).encode("utf-8") + payload + self._secret.encode("utf-8")
        signature = hashlib.sha256(factor).hexdigest()
        auth = f"SHA256 Credential={self.app_id}, Timestamp={timestamp}, Signature={signature}"
        request = Request(ENDPOINT, data=payload, headers={
            "Authorization": auth,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with self._opener.open(request, timeout=25) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ShopeeError("A resposta da Shopee ultrapassou o tamanho esperado.")
            result = json.loads(raw)
        except HTTPError as error:
            raise ShopeeError(f"A API Shopee retornou HTTP {error.code}.") from None
        except (URLError, OSError):
            raise ShopeeError("Falha de conexão com a API Shopee.") from None
        except (ValueError, UnicodeError):
            raise ShopeeError("A API Shopee retornou uma resposta inválida.") from None
        if not isinstance(result, dict):
            raise ShopeeError("A API Shopee retornou uma resposta inválida.")
        if result.get("errors"):
            errors = result["errors"]
            first = errors[0] if isinstance(errors, list) and errors else None
            details = first.get("extensions") if isinstance(first, dict) else None
            code = details.get("code") if isinstance(details, dict) else None
            if code in (10020, "10020"):
                raise ShopeeError("A API Shopee recusou a autenticação. Confira as chaves, a permissão e o relógio do Windows.")
            if code in (10030, "10030"):
                raise ShopeeError("A API Shopee atingiu o limite de requisições.")
            raise ShopeeError("A API Shopee rejeitou a operação. Confira as permissões no portal de afiliados.")
        data = result.get("data")
        if not isinstance(data, dict):
            raise ShopeeError("A API Shopee retornou uma resposta sem dados.")
        return data

    def products(self, keyword, limit):
        """Research distinct offers, ordered by the documented sales count."""
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("O limite de pesquisa deve ser um inteiro entre 1 e 500.")
        keyword = (keyword or "").strip()
        if len(keyword) > 200:
            raise ValueError("A palavra-chave pode ter até 200 caracteres.")
        keyword_arg = f", keyword: {json.dumps(keyword, ensure_ascii=False)}" if keyword else ""
        page_size = min(limit, 20)
        products = {}
        # Bound pagination even when the service returns repeated or short pages.
        for page in range(1, 51):
            query = (
                f"query {{ productOfferV2(page: {page}, limit: {page_size}, sortType: 2"
                f"{keyword_arg}) {{ {_CATALOG_FIELDS} }} }}"
            )
            offer = self._query(query).get("productOfferV2")
            nodes = offer.get("nodes") if isinstance(offer, dict) else None
            info = offer.get("pageInfo") if isinstance(offer, dict) else None
            if not isinstance(nodes, list) or not isinstance(info, dict) or type(info.get("hasNextPage")) is not bool:
                raise ShopeeError("A Shopee retornou um catálogo em formato inválido.")
            for node in nodes:
                product = _product(node)
                products.setdefault(product["id"], product)
                if len(products) == limit:
                    return list(products.values())
            if not info["hasNextPage"]:
                return list(products.values())
        raise ShopeeError("A pesquisa da Shopee excedeu o limite seguro de páginas.")

    def link(self, url):
        """Ask Shopee to convert an individual product URL for this affiliate."""
        if not _product_url(url):
            raise ShopeeError("Informe o endereço de um produto específico da Shopee Brasil.")
        origin = json.dumps(url, ensure_ascii=False)
        query = f'mutation {{ generateShortLink(input: {{originUrl: {origin}, subIds: ["radar"]}}) {{ shortLink }} }}'
        result = self._query(query).get("generateShortLink")
        short = result.get("shortLink") if isinstance(result, dict) else None
        if not _https_url(short, {"s.shopee.com.br", "shope.ee"}) or urlsplit(short).path in ("", "/"):
            raise ShopeeError("A Shopee não retornou um link de afiliado válido para o produto.")
        return short
