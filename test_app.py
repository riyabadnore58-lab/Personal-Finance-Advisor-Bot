import json
import unittest
from app import app, db, FinancialRecord, extract_json, build_prompt, generate_fallback_financial_plan

class PersonalFinanceAdvisorTestCase(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.client = app.test_client()
        with app.app_context():
            db.create_all()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_home_route(self):
        """Test home page loads successfully with 200 OK status"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Personal Finance Advisor Bot', response.data)

    def test_analyse_valid_salaried_scenario(self):
        """Test /analyse POST endpoint with valid salaried professional input"""
        payload = {
            "income": 85000,
            "expenses": {
                "rent": 28000,
                "food": 14000,
                "transport": 8500,
                "dining": 10000,
                "entertainment": 7500,
                "utilities": 5000,
                "savings": 12000
            },
            "goal": "Emergency Fund"
        }
        response = self.client.post('/analyse', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get('success'))
        self.assertIn('summary', data)
        self.assertIn('budget', data)
        self.assertIn('analysis', data)
        self.assertIn('suggestions', data)
        self.assertGreaterEqual(len(data['suggestions']), 3)

    def test_analyse_input_validation_missing_income(self):
        """Test /analyse fails when monthly income is missing or <= 0"""
        payload = {
            "income": 0,
            "expenses": {"rent": 10000},
            "goal": "Emergency Fund"
        }
        response = self.client.post('/analyse', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data.get('success'))
        self.assertIn("Monthly income must be greater than zero.", data.get('error'))

    def test_analyse_input_validation_empty_expenses(self):
        """Test /analyse fails when no expense category is logged"""
        payload = {
            "income": 50000,
            "expenses": {},
            "goal": "Vacation"
        }
        response = self.client.post('/analyse', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data.get('success'))
        self.assertIn("Please provide at least one expense category entry.", data.get('error'))

    def test_generate_endpoint_valid(self):
        """Test /generate POST endpoint with valid product_info"""
        payload = {
            "product_info": "Smart Automated Savings Tracker App",
            "platform": "LinkedIn",
            "tone": "Professional"
        }
        response = self.client.post('/generate', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get('success'))
        self.assertIn('content', data)

    def test_generate_endpoint_validation_empty(self):
        """Test /generate POST endpoint fails with empty product_info"""
        payload = {
            "product_info": "   ",
            "platform": "Twitter",
            "tone": "Casual"
        }
        response = self.client.post('/generate', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data.get('success'))

    def test_extract_json_helper(self):
        """Test robust JSON parser with direct, markdown code block, and raw brace text"""
        # Strategy 1: Direct JSON
        raw1 = '{"key": "value"}'
        self.assertEqual(extract_json(raw1), {"key": "value"})

        # Strategy 2: Markdown code fence
        raw2 = '```json\n{"key": "value"}\n```'
        self.assertEqual(extract_json(raw2), {"key": "value"})

        # Strategy 3: Text with markdown and comments
        raw3 = 'Here is the JSON response:\n{\n  "summary": "Great budget"\n}\nHope this helps!'
        self.assertEqual(extract_json(raw3), {"summary": "Great budget"})

if __name__ == '__main__':
    unittest.main()
