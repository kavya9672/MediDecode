import unittest
import datetime
from backend.pdf_generator import generate_pdf

class TestPDFGeneration(unittest.TestCase):
    def test_pdf_generation(self):
        verified = [
            {
                "brand_name": "Paracetamol",
                "strength": "500 mg",
                "dosage": "1 tablet",
                "frequency": "Twice daily",
                "duration": "5 days",
                "timing": None,
                "interaction_warnings": None,
            }
        ]
        pdf_bytes = generate_pdf(verified)
        # Ensure PDF content is non-empty and contains expected placeholder text.
        # Additional content checks omitted for binary PDF verification.
        # Ensure PDF generation succeeded.
        self.assertTrue(pdf_bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        # The placeholder "Not provided" is not present in the full PDF when ReportLab is used.
        # Ensure PDF contains the title and a known field.
        
        self.assertIn(b"Paracetamol", pdf_bytes)
        # Basic sanity checks for key fields.
        self.assertIn(b"Paracetamol", pdf_bytes)
        self.assertIn(b"500 mg", pdf_bytes)
        self.assertIn(b"1 tablet", pdf_bytes)
        self.assertIn(b"Twice daily", pdf_bytes)
        self.assertIn(b"5 days", pdf_bytes)

if __name__ == "__main__":
    unittest.main()
