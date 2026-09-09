import copy
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from epoint_csv.core import Product, Settings, ValidationError
from epoint_csv.research import (ApiFatal, Cancelled, Fetcher, OpenAIResearch,
    ResearchCache, direct_research, domain_list, identity_check, on_domains, public_url)


URL = "https://manufacturer.example.com/x100"
IMAGE = "https://manufacturer.example.com/x100.png"


def page_fixture():
    return {"url": URL, "title": "Test X100", "text": "Test X100 product. Exact model X100. Power 650 W. Original test product information, enough text to verify a real source. " * 2,
            "images": [IMAGE], "structured": [{"@type": "Product", "name": "Test X100", "mpn": "X100", "brand": {"name": "Test"}, "description": "Izvorni opis. Druga rečenica.", "image": [IMAGE]}]}


def api_result():
    data = {"matched": True, "reason": "Potvrđen model na proizvođačkom izvoru.", "source_url": URL, "official_manufacturer": True,
            "brand": "Test", "model": "X100", "ean": "", "category": "Testovi", "short": "Kratki opis.", "description": "Dugi opis.",
            "identity_quote": "Exact model X100", "images": [IMAGE], "specs": [{"name": "Snaga", "value": "650 W", "quote": "Power 650 W"}]}
    return {"status": "completed", "usage": {"input_tokens": 100, "output_tokens": 150}, "output": [
        {"type": "web_search_call", "action": {"sources": [{"url": URL}]}},
        {"type": "message", "content": [{"type": "output_text", "text": json.dumps(data)}]}]}


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.cancel = threading.Event()
        self.p = Product(name="Test X100", model="X100", brand="Test", vpc="999.99", source_url=URL, sku="S1")
        self.fetcher = MagicMock()
        self.fetcher.page.return_value = page_fixture()
        self.fetcher.image.side_effect = lambda url: url
        self.provider = OpenAIResearch("synthetic-test-key", Settings(), self.cancel, self.fetcher)

    def test_payload_does_not_send_prices_or_sku(self):
        payload = self.provider.payload(self.p)
        data = json.loads(payload["input"])
        self.assertNotIn("vpc", data)
        self.assertNotIn("sku", data)
        self.assertNotIn("999.99", payload["input"])
        self.assertFalse(payload["store"])
        self.assertEqual(payload["max_tool_calls"], 4)

    def test_manufacturer_filter(self):
        self.provider.settings.domains = "manufacturer.example.com"
        self.assertEqual(self.provider.payload(self.p)["tools"][0]["filters"]["allowed_domains"], ["manufacturer.example.com"])

    def test_grounded_research_pending_review(self):
        with patch.object(self.provider, "request", return_value=api_result()):
            result = self.provider.research(self.p)
        self.assertEqual(result.name, self.p.name)
        self.assertEqual(result.status, "Za pregled")
        self.assertFalse(result.approved)
        self.assertEqual(result.vpc, "999.99")
        self.assertEqual(result.checked_images, [IMAGE])
        self.assertEqual(self.p.description, "")

    def test_source_not_consulted_rejected(self):
        body = api_result()
        body["output"][0]["action"]["sources"] = []
        with patch.object(self.provider, "request", return_value=body):
            with self.assertRaisesRegex(ValidationError, "stvarno korištenim"):
                self.provider.research(self.p)

    def test_fabricated_spec_quote_rejected(self):
        self.fetcher.page.return_value["text"] = "Test X100. Exact model X100. No power mentioned."
        with patch.object(self.provider, "request", return_value=api_result()):
            with self.assertRaisesRegex(ValidationError, "Specifikacija"):
                self.provider.research(self.p)

    def test_invented_image_rejected(self):
        self.fetcher.page.return_value["images"] = []
        with patch.object(self.provider, "request", return_value=api_result()):
            with self.assertRaisesRegex(ValidationError, "slike"):
                self.provider.research(self.p)

    def test_identity_nearby_model_rejected(self):
        with self.assertRaises(ValidationError):
            identity_check(self.p, {"text": "Test X1000 product"}, "X1000")

    def test_all_numeric_variant_anchors_required(self):
        p = Product(name="Test S26 256GB")
        with self.assertRaises(ValidationError):
            identity_check(p, {"text": "Test S26 128GB"})

    def test_name_only_requires_review(self):
        with self.assertRaises(ValidationError):
            identity_check(Product(name="Test četka"), {"text": "Test četka"})

    def test_wrong_ean_rejected(self):
        with self.assertRaises(ValidationError):
            identity_check(Product(name="X100", ean="4006381333931"), page_fixture(), matched_ean="1234567890128")

    def test_no_key_fails_before_network(self):
        self.provider.key = ""
        with patch.object(self.provider.session, "post") as post:
            with self.assertRaises(ApiFatal):
                self.provider.request({})
            post.assert_not_called()

    def test_api_401_fatal_no_retry(self):
        response = MagicMock(status_code=401)
        with patch.object(self.provider.session, "post", return_value=response) as post:
            with self.assertRaises(ApiFatal):
                self.provider.request({})
            self.assertEqual(post.call_count, 1)

    def test_uncertain_api_post_not_retried(self):
        with patch.object(self.provider.session, "post", side_effect=requests.Timeout) as post:
            with self.assertRaises(ApiFatal):
                self.provider.request({})
            self.assertEqual(post.call_count, 1)

    def test_incomplete_response_rejected(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"status": "incomplete", "output": []}
        with patch.object(self.provider.session, "post", return_value=response):
            with self.assertRaisesRegex(ValidationError, "dovršen"):
                self.provider.request({})

    def test_cancel_before_paid_call(self):
        self.cancel.set()
        with patch.object(self.provider.session, "post") as post:
            with self.assertRaises(Cancelled):
                self.provider.request({})
            post.assert_not_called()

    def test_direct_jsonld(self):
        result = direct_research(self.p, self.fetcher)
        self.assertEqual(result.description, "Izvorni opis. Druga rečenica.")
        self.assertEqual(result.short, "Izvorni opis.")
        self.assertEqual(result.images, [IMAGE])
        self.assertEqual(result.status, "Za pregled")

    def test_direct_ambiguous_product_rejected(self):
        page = page_fixture()
        page["structured"].append(copy.deepcopy(page["structured"][0]))
        self.fetcher.page.return_value = page
        with self.assertRaisesRegex(ValidationError, "nedvosmislen"):
            direct_research(self.p, self.fetcher)

    def test_cache_does_not_reuse_prices_or_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ResearchCache(Path(directory) / "cache.sqlite")
            key = cache.key(self.p, Settings(), "ai")
            researched = copy.deepcopy(self.p)
            researched.description = "Cache opis"
            researched.regular = "999.00"
            researched.approval = "old"
            cache.put(key, researched)
            self.p.regular = "120.00"
            result = cache.get(key, self.p)
            self.assertEqual(result.regular, "120.00")
            self.assertEqual(result.description, "Cache opis")
            self.assertFalse(result.approved)

    def test_domain_boundary(self):
        domains = domain_list("www.example.com, manufacturer.hr")
        self.assertTrue(on_domains("https://shop.example.com/product", domains))
        self.assertFalse(on_domains("https://example.com.attacker.net/product", domains))

    def test_private_network_url_rejected(self):
        with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
            with self.assertRaises(ValidationError):
                public_url("https://localhost/private")

    def test_credentials_and_non_http_rejected(self):
        for url in ["file:///c:/data", "https://user:secret@example.com", "javascript:alert(1)"]:
            with self.assertRaises(ValidationError):
                public_url(url)

    def test_image_content_sniff(self):
        fetcher = Fetcher(self.cancel)
        response = MagicMock()
        response.status_code, response.is_redirect = 200, False
        response.headers = {"Content-Type": "image/png"}
        response.iter_content.return_value = [b"<html>Not an image</html>"]
        response.__enter__.return_value = response
        with patch("epoint_csv.research.public_url", side_effect=lambda url: url), patch.object(fetcher.session, "get", return_value=response):
            with self.assertRaisesRegex(ValidationError, "Sadržaj"):
                fetcher.image(IMAGE)

    def test_blocked_host_cached(self):
        fetcher = Fetcher(self.cancel)
        response = MagicMock(status_code=403)
        response.__enter__.return_value = response
        with patch("epoint_csv.research.public_url", side_effect=lambda url: url), patch.object(fetcher.session, "get", return_value=response) as get:
            for _ in range(2):
                with self.assertRaises(ValidationError):
                    fetcher._request(URL)
            self.assertEqual(get.call_count, 1)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_windows_encrypted_key_roundtrip(self):
        from epoint_csv.secrets import protect
        secret = b"synthetic-key-for-test-only"
        encrypted = protect(secret)
        self.assertNotIn(secret, encrypted)
        self.assertEqual(protect(encrypted, decrypt=True), secret)


if __name__ == "__main__":
    unittest.main()

