import copy
import csv
import io
import json
import tempfile
import unittest
import zipfile
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from epoint_csv.core import (Catalog, Product, Settings, Store, ValidationError, calculate_prices,
    cell_text, export_products, make_products, mark_duplicates, money, now, read_table,
    sheet_names, suggest_mapping, valid_ean, validate_product)


def product(**kwargs):
    p = Product(name="TEST — Četka čćšžđ X100", sku="TEST-001", regular="125.00", vpc="100", brand="Test", category="Dom > Testovi",
                short='Kratki opis s "navodnicima", zarezom i čćšžđ.', description="Prvi odlomak.\n\nDrugi redak. <script>tekst</script>",
                images=["https://example.com/test.png"], checked_images=["https://example.com/test.png"], image_checked_at=now())
    for k, v in kwargs.items():
        setattr(p, k, v)
    p.approve()
    return p


def xlsx_fixture(path):
    # Minimal OOXML fixture tests real reader behavior without an Excel dependency.
    files = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Cjenik" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Naziv</t></is></c><c r="B1" t="inlineStr"><is><t>VPC</t></is></c><c r="C1" t="inlineStr"><is><t>SKU</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>Četka X100</t></is></c><c r="B2"><f>50+50</f><v>100</v></c><c r="C2" t="inlineStr"><is><t>00123</t></is></c></row><row r="3"><c r="A3" t="inlineStr"><is><t>Četka X200</t></is></c><c r="B3"><f>50+70</f></c></row></sheetData></worksheet>',
    }
    with zipfile.ZipFile(path, "w") as file:
        for name, contents in files.items():
            file.writestr(name, contents.encode("utf-8"))


class MoneyTests(unittest.TestCase):
    def test_formats(self):
        for value in ["1.299,99 €", "1,299.99 EUR", "1299.99", "1 299,99", "1299,99"]:
            with self.subTest(value=value):
                self.assertEqual(money(value), Decimal("1299.99"))

    def test_bad_formats(self):
        for value in [0, "1.250", "1,250", "1.2.3", "1,23,45", "-12", "NaN", "Infinity", "0", "#DIV/0!", "1e6", "1.22,00", "=100"]:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    money(value)

    def test_priority(self):
        self.assertEqual(calculate_prices("100", "80", Settings()), ("100.00", "", "Akcija VPC"))

    def test_fallback(self):
        self.assertEqual(calculate_prices("100", "", Settings()), ("125.00", "", "VPC"))

    def test_bad_promo_does_not_fallback(self):
        with self.assertRaises(ValidationError):
            calculate_prices("100", "bad", Settings())

    def test_promo_only(self):
        self.assertEqual(calculate_prices("", "80", Settings(price_mode="sale"))[:2], ("100.00", ""))

    def test_sale_pair(self):
        self.assertEqual(calculate_prices("100", "80", Settings(price_mode="sale"))[:2], ("125.00", "100.00"))

    def test_sale_rejected_when_not_lower(self):
        for promo in ["100", "120"]:
            with self.assertRaises(ValidationError):
                calculate_prices("100", promo, Settings(price_mode="sale"))

    def test_gross_input_no_double_tax(self):
        self.assertEqual(calculate_prices("100", "80", Settings(input_gross=True))[0], "80.00")

    def test_rounding_half_up(self):
        self.assertEqual(calculate_prices("0.10", "", Settings())[0], "0.13")

    def test_bad_settings(self):
        for vat in ["NaN", "abc", "-1", "101"]:
            with self.assertRaises(ValidationError):
                Settings(vat=vat).validate()


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_xlsx_cached_formula_and_missing_formula(self):
        path = self.path / "fixture.xlsx"
        xlsx_fixture(path)
        self.assertEqual(sheet_names(path), ["Cjenik"])
        headers, rows = read_table(path, "Cjenik")
        products = make_products(path, "Cjenik", rows, suggest_mapping(headers), Settings())
        self.assertEqual(products[0].sku, "00123")
        self.assertEqual(products[0].regular, "125.00")
        self.assertEqual(products[1].status, "Preskočeno")
        self.assertIn("formulu", products[1].error)

    def test_semicolon_csv_header_offset(self):
        path = self.path / "data.csv"
        path.write_text('Dobavljač;\nNaziv;VPC\nČetka X100;"100,00"\n', encoding="utf-8-sig")
        headers, rows = read_table(path, header_row=2)
        self.assertEqual(headers, ["Naziv", "VPC"])
        self.assertEqual(rows, [(3, {"Naziv": "Četka X100", "VPC": "100,00"})])

    def test_header_aliases_and_ambiguity(self):
        result = suggest_mapping(["Naziv", "Akcijska VPC EUR", "VPC", "Šifra artikla"])
        self.assertEqual(result["promo_vpc"], "Akcijska VPC EUR")
        self.assertEqual(result["vpc"], "VPC")
        self.assertEqual(result["sku"], "Šifra artikla")
        self.assertNotIn("promo_vpc", suggest_mapping(["Akcija VPC", "VPC akcija"]))

    def test_duplicate_headers_rejected(self):
        path = self.path / "bad.csv"
        path.write_text("Naziv,VPC,VPC\nX,1,2", encoding="utf-8")
        with self.assertRaises(ValidationError):
            read_table(path)

    def test_ean_checksum(self):
        self.assertTrue(valid_ean("4006381333931"))
        self.assertFalse(valid_ean("4006381333932"))
        self.assertFalse(valid_ean("123.0"))

    def test_padding(self):
        self.assertEqual(cell_text(123, "000000"), "000123")

    def test_duplicates_all_blocked(self):
        a, b = product(), product()
        mark_duplicates([a, b])
        self.assertTrue(a.error and b.error)
        self.assertFalse(a.approved or b.approved)

    def test_deterministic_sku(self):
        args = ("book.xlsx", "List", [(2, {"Naziv": "Četka X100", "VPC": "10"})], {"name": "Naziv", "vpc": "VPC"}, Settings())
        self.assertEqual(make_products(*args)[0].sku, make_products(*args)[0].sku)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def read_records(self, folder, summary, delimiter=","):
        result = []
        for filename in summary["csv"]:
            with (folder / filename).open(encoding="utf-8-sig", newline="") as stream:
                result.extend(csv.DictReader(stream, delimiter=delimiter))
        return result

    def test_utf8_quotes_html_and_draft(self):
        folder, summary = export_products([product()], self.path, Settings())
        records = self.read_records(folder, summary)
        self.assertIn("čćšžđ", records[0]["Short description"])
        self.assertIn("&lt;script&gt;", records[0]["Description"])
        self.assertEqual(records[0]["Published"], "-1")
        self.assertEqual(records[0]["Regular price"], "125.00")
        self.assertNotIn("Stock", records[0])
        self.assertTrue((folder / summary["csv"][0]).read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_unapproved_and_bad_images_excluded(self):
        a = product()
        a.short = "Promijenjen opis"
        b = product(sku="B")
        b.checked_images = []
        folder, summary = export_products([a, b], self.path, Settings())
        self.assertEqual(summary["izvezeno"], 0)
        self.assertEqual(summary["preskoceno"], 2)
        self.assertTrue((folder / "log.txt").exists())

    def test_approval_invalidates_after_edit(self):
        p = product()
        p.regular = "100.00"
        self.assertFalse(p.approved)

    def test_excel_injection_blocked(self):
        with self.assertRaises(ValidationError):
            product(name="=HYPERLINK(\"bad\")")

    def test_update_preserves_state_and_absent_sale(self):
        catalog = Catalog([{"ID": "55", "SKU": "TEST-001", "Type": "simple"}])
        folder, summary = export_products([product()], self.path, Settings(export_mode="update"), catalog)
        row = self.read_records(folder, summary)[0]
        self.assertEqual(row["ID"], "55")
        for col in ("Published", "Type", "Sale price", "Stock", "GTIN, UPC, EAN, or ISBN"):
            self.assertNotIn(col, row)

    def test_update_matches_ean_and_keeps_existing_sku(self):
        p = product(sku="SupplierSKU", ean="4006381333931")
        catalog = Catalog([{"ID": "55", "SKU": "ShopSKU", "GTIN, UPC, EAN, or ISBN": p.ean}])
        folder, summary = export_products([p], self.path, Settings(export_mode="update"), catalog)
        self.assertEqual(self.read_records(folder, summary)[0]["SKU"], "ShopSKU")

    def test_conflicting_sku_and_ean(self):
        p = product(ean="4006381333931")
        catalog = Catalog([{"ID": "1", "SKU": p.sku}, {"ID": "2", "SKU": "OTHER", "GTIN, UPC, EAN, or ISBN": p.ean}])
        with self.assertRaises(ValidationError):
            catalog.match(p)

    def test_conflicting_ean_same_sku(self):
        p = product(ean="4006381333931")
        catalog = Catalog([{"SKU": p.sku, "GTIN, UPC, EAN, or ISBN": "1234567890128"}])
        with self.assertRaises(ValidationError):
            catalog.match(p)

    def test_update_requires_catalog(self):
        with self.assertRaises(ValidationError):
            export_products([product()], self.path, Settings(export_mode="update"))

    def test_split_new_and_update(self):
        a, b = product(), product(sku="NEW")
        catalog = Catalog([{"ID": "9", "SKU": a.sku}])
        folder, summary = export_products([a, b], self.path, Settings(export_mode="split"), catalog)
        self.assertEqual(summary["izvezeno"], 2)
        self.assertTrue(any(f.startswith("novi") for f in summary["csv"]))
        self.assertTrue(any(f.startswith("azuriranje") for f in summary["csv"]))

    def test_variation_skipped(self):
        p = product()
        catalog = Catalog([{"SKU": p.sku, "Type": "variation"}])
        _, summary = export_products([p], self.path, Settings(export_mode="update"), catalog)
        self.assertEqual(summary["preskoceno"], 1)

    def test_thousand_products_batches_reconcile(self):
        products = [product(sku=f"TEST-{i:04}", name=f"TEST Četka {i}") for i in range(1000)]
        folder, summary = export_products(products, self.path, Settings(batch_size=100, delimiter=";"))
        self.assertEqual(summary["izvezeno"], 1000)
        self.assertEqual(len(summary["csv"]), 10)
        self.assertEqual(len(self.read_records(folder, summary, ";")), 1000)
        self.assertEqual(summary["ulaz"], summary["izvezeno"] + summary["preskoceno"])

    def test_stale_image_check_blocks_export(self):
        p = product()
        p.image_checked_at = "2020-01-01T00:00:00+00:00"
        self.assertTrue(any("24 sata" in e for e in validate_product(p)))

    def test_repeated_exports_do_not_overwrite(self):
        one, _ = export_products([product()], self.path, Settings())
        two, _ = export_products([product()], self.path, Settings())
        self.assertNotEqual(one, two)
        self.assertTrue(one.exists() and two.exists())

    def test_persistence_and_project_backup(self):
        store = Store(self.path / "work.epcsv")
        p = product()
        store.put(p)
        store.set_setting("settings", asdict(Settings()))
        store.backup(self.path / "backup.epcsv")
        loaded = Store(self.path / "backup.epcsv").load()[0]
        self.assertEqual(asdict(loaded), asdict(p))
        self.assertTrue(loaded.approved)


if __name__ == "__main__":
    unittest.main()

