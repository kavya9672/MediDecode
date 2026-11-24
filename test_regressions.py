import unittest
import datetime
from backend.generic_matcher import compare_generics
from backend.database import get_connection, insert_medicine, delete_medicine

class TestGenericMatcherRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = get_connection()
        # Base medicine (verified)
        cls.base_med = {
            "brand_name": "ExactBrand",
            "active_ingredient": "Paracetamol",
            "strength": "500 mg",
            "dosage_form": "Tablet",
            "route": "Oral",
            "manufacturer": "PharmaA",
            "price": 5.0,
            "price_source": "test",
            "verification_date": datetime.date.today().isoformat(),
            "verification_status": "verified",
        }
        # Insert base medicine
        cls.base_id = insert_medicine(cls.conn, cls.base_med)
        # Create alternatives with one mismatched attribute each
        cls.alts = []
        mismatches = [
            ("IngredientMismatch", {"active_ingredient": "Ibuprofen"}),
            ("StrengthMismatch", {"strength": "650 mg"}),
            ("FormMismatch", {"dosage_form": "Capsule"}),
            ("RouteMismatch", {"route": "IV"}),
        ]
        for brand, changes in mismatches:
            med = cls.base_med.copy()
            med["brand_name"] = brand
            med.update(changes)
            med_id = insert_medicine(cls.conn, med)
            cls.alts.append(med_id)
        # Exact match alternative
        exact_alt = cls.base_med.copy()
        exact_alt["brand_name"] = "ExactAlt"
        cls.exact_alt_id = insert_medicine(cls.conn, exact_alt)

    @classmethod
    def tearDownClass(cls):
        # Clean up inserted records
        delete_medicine(cls.conn, cls.base_id)
        for aid in cls.alts:
            delete_medicine(cls.conn, aid)
        delete_medicine(cls.conn, cls.exact_alt_id)
        cls.conn.close()

    def test_exact_match_only(self):
        # Should return only the exact alternative (ExactAlt)
        result = compare_generics(["ExactBrand"])
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        alt = result[0]
        self.assertEqual(alt.get("alternative_brand"), "ExactAlt")

if __name__ == "__main__":
    unittest.main()
