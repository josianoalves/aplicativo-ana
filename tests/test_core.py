import unittest
import tempfile
from radar.analysis import analyze, script_for
from radar.store import Store


class CoreTests(unittest.TestCase):
    def test_sales_and_reviews_are_separate(self):
        result = analyze({"reviews": 2000})
        self.assertEqual(result["score"], 20)
        self.assertIn("Sem dados de vendas", result["reasons"][-1])

    def test_strong_product(self):
        result = analyze(dict(sales=100000, views=200000, trend=.3, rating=5, reviews=8000,
                              commission_rate=.3, price=60))
        self.assertEqual((result["score"], result["grade"]), (100, "A"))

    def test_script_variants(self):
        first, second = [script_for({"name": "Mesa"}, variant) for variant in (1, 2)]
        self.assertEqual(len(first["segments"]), 5)
        self.assertNotEqual(first["segments"], second["segments"])

    def test_database_and_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            store.save("products", [{"id": "1", "price": 20}], "first")
            store.save("products", [{"id": "1", "price": 25}], "second")
            self.assertEqual(store.rows("products"), [{"id": "1", "price": 25}])
            with store.connect() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM snapshots").fetchone()[0], 2)
            self.assertTrue(store.backup().is_file())

