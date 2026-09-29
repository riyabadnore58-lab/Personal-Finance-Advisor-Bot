import os
import re
import json
import logging
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import requests

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key_finance_advisor')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///finance_advisor.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SQLAlchemy Database Model
class FinancialRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    income = db.Column(db.Float, nullable=False)
    expenses_json = db.Column(db.Text, nullable=False)
    goal = db.Column(db.String(100), nullable=False)
    budget_json = db.Column(db.Text, nullable=False)
    analysis_json = db.Column(db.Text, nullable=False)
    suggestions_json = db.Column(db.Text, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "income": self.income,
            "expenses": json.loads(self.expenses_json),
            "goal": self.goal,
            "budget": json.loads(self.budget_json),
            "analysis": json.loads(self.analysis_json),
            "suggestions": json.loads(self.suggestions_json)
        }

# Create database tables within application context
with app.app_context():
    db.create_all()

# Category Budgeting Thresholds and Guidance Tips
CATEGORY_TIPS = {
    "rent": "Housing/Rent should ideally not exceed 30% of your total monthly income.",
    "food": "Groceries and essential nutrition spending should stay under 15% of income.",
    "transport": "Commute and transportation costs should remain within 10% of monthly income.",
    "dining": "Dining out and food delivery should be capped around 5% to 8% of income.",
    "entertainment": "Entertainment and discretionary leisure should stay between 5% and 8%.",
    "utilities": "Essential utilities (electricity, water, gas, internet) should stay around 5% to 10%.",
    "savings": "Dedicated savings and emergency allocation should be at least 20% of monthly income."
}

# Financial Goal Descriptions
GOAL_DESCRIPTIONS = {
    "emergency_fund": "Build a liquid cash buffer covering 3 to 6 months of essential living expenses.",
    "vacation": "Save dedicated funds for planned travel without taking on high-interest debt.",
    "gadget": "Set aside funds for planned tech hardware or equipment upgrades.",
    "investment": "Allocate surplus wealth into inflation-beating long-term growth assets (mutual funds, stocks, index funds)."
}

def extract_json(text):
    """
    Robust JSON parser that tries multiple extraction strategies:
    1. Direct JSON parse
    2. Markdown block extraction (```json ... ```)
    3. Regex matching for outermost JSON object {...}
    """
    if not text:
        return None

    text = text.strip()
    
    # Strategy 1: Direct JSON parsing
    try:
        return json.loads(text)
    except Exception:
        pass

    # Strategy 2: Strip markdown code fences
    markdown_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    match = re.search(markdown_pattern, text, re.IGNORECASE)
    if match:
        extracted = match.group(1).strip()
        try:
            return json.loads(extracted)
        except Exception:
            pass

    # Strategy 3: Regex match outermost brace block {...}
    brace_pattern = r'\{[\s\S]*\}'
    match = re.search(brace_pattern, text)
    if match:
        extracted = match.group(0).strip()
        try:
            return json.loads(extracted)
        except Exception:
            pass

    return None

def build_prompt(income, expenses, goal):
    """
    Assembles a structured prompt for Gemini API incorporating category tips and goal descriptions.
    """
    goal_desc = GOAL_DESCRIPTIONS.get(goal.lower().replace(" ", "_"), f"Achieve goal: {goal}")
    
    prompt = f"""
You are an expert AI Personal Finance Advisor.
Analyze the following user's monthly income, expenses across categories, and financial goal.

User Financial Profile:
- Monthly Income: ₹{income:,.2f}
- Expenses Breakdown: {json.dumps(expenses, indent=2)}
- Financial Goal: {goal} ({goal_desc})

Category Guidelines for Context:
{json.dumps(CATEGORY_TIPS, indent=2)}

Instructions:
Generate a personalized financial advice plan. You MUST respond with ONLY a valid JSON object matching this exact schema:

{{
  "summary": "Short 2-3 sentence overview of the user's financial health, spending vs income ratio, and savings status.",
  "budget": {{
    "rent": {{ "recommended": number, "percentage": number, "status": "on_track" | "overspending" }},
    "food": {{ "recommended": number, "percentage": number, "status": "on_track" | "overspending" }},
    "transport": {{ "recommended": number, "percentage": number, "status": "on_track" | "overspending" }},
    "dining": {{ "recommended": number, "percentage": number, "status": "on_track" | "overspending" }},
    "entertainment": {{ "recommended": number, "percentage": number, "status": "on_track" | "overspending" }},
    "utilities": {{ "recommended": number, "percentage": number, "status": "on_track" | "overspending" }},
    "savings": {{ "recommended": number, "percentage": number, "status": "on_track" | "needs_improvement" }}
  }},
  "analysis": [
    {{
      "category": "Category Name",
      "spent": number,
      "pct_of_income": number,
      "status": "overspending" | "on_track",
      "tip": "Actionable advice based on category thresholds."
    }}
  ],
  "suggestions": [
    "Reduce dining expenses by ₹3,000 and redirect to your emergency fund.",
    "Actionable suggestion 2 with specific rupee amounts...",
    "Actionable suggestion 3 with specific rupee amounts...",
    "Actionable suggestion 4 with specific rupee amounts..."
  ]
}}

Do NOT include any text outside the JSON object. Return strictly valid JSON.
"""
    return prompt

def generate_fallback_financial_plan(income, expenses, goal):
    """
    Algorithmic fallback financial advice generator used if external Gemini API is unreachable or unconfigured.
    """
    total_expenses = sum(float(val) for val in expenses.values())
    savings_current = float(expenses.get('savings', 0))
    net_savings = max(0, income - total_expenses + savings_current)
    savings_pct = round((net_savings / income) * 100, 1) if income > 0 else 0

    recommended_ratios = {
        'rent': 0.30,
        'food': 0.15,
        'transport': 0.10,
        'dining': 0.06,
        'entertainment': 0.06,
        'utilities': 0.08,
        'savings': 0.25
    }

    budget = {}
    analysis = []
    suggestions = []

    for cat, tip in CATEGORY_TIPS.items():
        spent = float(expenses.get(cat, 0))
        rec_pct = recommended_ratios.get(cat, 0.10)
        rec_amt = round(income * rec_pct, 2)
        pct_of_inc = round((spent / income) * 100, 1) if income > 0 else 0

        is_over = spent > rec_amt if cat != 'savings' else spent < rec_amt
        status = "overspending" if (cat != 'savings' and is_over) else ("needs_improvement" if (cat == 'savings' and is_over) else "on_track")

        budget[cat] = {
            "recommended": rec_amt,
            "percentage": round(rec_pct * 100, 1),
            "status": status
        }

        analysis.append({
            "category": cat.capitalize(),
            "spent": spent,
            "pct_of_income": pct_of_inc,
            "status": "overspending" if status in ["overspending", "needs_improvement"] else "on_track",
            "tip": tip if status != "on_track" else f"{cat.capitalize()} spending is well within recommended limits."
        })

        if is_over and cat != 'savings':
            excess = spent - rec_amt
            suggestions.append(f"Reduce {cat} expenses by ₹{excess:,.0f} per month and redirect the funds toward your {goal} goal.")

    if savings_pct < 20:
        shortfall = round(income * 0.20 - net_savings, 0)
        suggestions.append(f"Increase total monthly savings by ₹{shortfall:,.0f} to reach the benchmark 20% savings target.")

    goal_desc = GOAL_DESCRIPTIONS.get(goal.lower().replace(" ", "_"), goal)
    suggestions.append(f"Set up an automated recurring transfer on payday targeted specifically for: {goal_desc}")
    suggestions.append(f"Review subscription services and monthly non-essential recurring payments to free up additional discretionary cash.")

    summary = f"Your total monthly expenses are ₹{total_expenses:,.2f} ({round((total_expenses/income)*100, 1)}% of income). You are saving approximately {savings_pct}% of your income. Focusing on targeted reductions in discretionary spending will help accelerate your {goal} goal."

    return {
        "summary": summary,
        "budget": budget,
        "analysis": analysis,
        "suggestions": suggestions[:5]
    }

def call_gemini_api(prompt, income, expenses, goal):
    """
    Invokes Google Gemini API with fallback to rules engine if API Key is not set or API fails.
    Configured model: gemini-2.0-flash, temperature: 0.7, max_output_tokens: 2048.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key or api_key == "your_gemini_api_key_here":
        logger.info("Using smart rule-based financial engine fallback (GEMINI_API_KEY unconfigured).")
        return generate_fallback_financial_plan(income, expenses, goal)

    # Attempt GenAI / Gemini API invocation
    try:
        # Try new google.genai SDK first
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=2048
                )
            )
            parsed = extract_json(response.text)
            if parsed and all(k in parsed for k in ["budget", "analysis", "suggestions"]):
                return parsed
        except Exception as e_genai:
            logger.warning(f"google.genai SDK call failed/unavailable: {e_genai}. Trying google.generativeai...")

        # Try google.generativeai SDK
        try:
            import google.generativeai as ggi
            ggi.configure(api_key=api_key)
            model = ggi.GenerativeModel('gemini-2.0-flash')
            generation_config = ggi.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=2048
            )
            response = model.generate_content(prompt, generation_config=generation_config)
            parsed = extract_json(response.text)
            if parsed and all(k in parsed for k in ["budget", "analysis", "suggestions"]):
                return parsed
        except Exception as e_ggi:
            logger.warning(f"google.generativeai SDK call failed: {e_ggi}. Trying direct REST API...")

        # Fallback to direct REST API call
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048
            }
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            resp_json = resp.json()
            candidates = resp_json.get("candidates", [])
            if candidates:
                text_out = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                parsed = extract_json(text_out)
                if parsed and all(k in parsed for k in ["budget", "analysis", "suggestions"]):
                    return parsed

    except Exception as exc:
        logger.error(f"Gemini API request exception: {exc}")

    # Fallback if API fails or returns unparseable content
    return generate_fallback_financial_plan(income, expenses, goal)


# --- ROUTE HANDLERS ---

@app.route('/')
def home():
    """Renders the main single-page interface index.html"""
    return render_template('index.html')


@app.route('/analyse', methods=['POST'])
def analyse():
    """
    POST endpoint for financial data analysis.
    Accepts JSON body with income, expenses breakdown, and financial goal.
    Returns structured budget plan, spending analysis, and saving suggestions.
    """
    data = request.get_json() or {}
    
    # Input Retrieval and Validation
    income = data.get('income')
    expenses = data.get('expenses', {})
    goal = data.get('goal', 'Emergency Fund')

    # Convert numeric fields
    try:
        income = float(income)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid or missing monthly income value."}), 400

    if income <= 0:
        return jsonify({"success": False, "error": "Monthly income must be greater than zero."}), 400

    if not isinstance(expenses, dict) or not expenses:
        return jsonify({"success": False, "error": "Please provide at least one expense category entry."}), 400

    total_expense = 0
    clean_expenses = {}
    for cat, val in expenses.items():
        try:
            val_f = float(val)
            if val_f >= 0:
                clean_expenses[cat.lower()] = val_f
                total_expense += val_f
        except (ValueError, TypeError):
            continue

    if total_expense <= 0 and not clean_expenses:
        return jsonify({"success": False, "error": "At least one expense category must contain a valid positive amount."}), 400

    # Build Prompt and Call AI Engine
    prompt = build_prompt(income, clean_expenses, goal)
    result = call_gemini_api(prompt, income, clean_expenses, goal)

    # Persist in Database
    try:
        record = FinancialRecord(
            income=income,
            expenses_json=json.dumps(clean_expenses),
            goal=goal,
            budget_json=json.dumps(result.get('budget', {})),
            analysis_json=json.dumps(result.get('analysis', [])),
            suggestions_json=json.dumps(result.get('suggestions', []))
        )
        db.session.add(record)
        db.session.commit()
    except Exception as db_err:
        logger.error(f"Failed to persist financial record to database: {db_err}")
        db.session.rollback()

    return jsonify({
        "success": True,
        "summary": result.get("summary", ""),
        "budget": result.get("budget", {}),
        "analysis": result.get("analysis", []),
        "suggestions": result.get("suggestions", [])
    })


@app.route('/generate', methods=['POST'])
def generate():
    """
    POST endpoint for content/ad generation.
    Accepts JSON body: { product_info, platform, tone }.
    Validates that product_info is non-empty and <= 2000 characters.
    """
    data = request.get_json() or {}
    product_info = data.get('product_info', '').strip()
    platform = data.get('platform', 'General').strip()
    tone = data.get('tone', 'Professional').strip()

    # Input Validation
    if not product_info:
        return jsonify({"success": False, "error": "Product information is required."}), 400

    if len(product_info) > 2000:
        return jsonify({"success": False, "error": "Product information must not exceed 2000 characters."}), 400

    prompt = f"""
Generate an engaging marketing copy and financial planning post for a product/service.
Product Details: {product_info}
Target Platform: {platform}
Tone of Voice: {tone}

Instructions:
Provide a compelling headline, 2-3 body paragraphs highlighting value propositions, key call to action, and relevant hashtags.
"""

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    content = ""

    if api_key and api_key != "your_gemini_api_key_here":
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            res = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            content = res.text
        except Exception:
            pass

    if not content:
        content = f"🚀 **{platform} Exclusive Offer ({tone} Tone)**\n\n{product_info}\n\nTake control of your personal finances today with our smart automated tools! #FinancialFreedom #SmartBudgeting #FinanceAdvisor"

    return jsonify({
        "success": True,
        "content": content
    })


if __name__ == '__main__':
    # Local development server execution
    app.run(host='0.0.0.0', port=5000, debug=True)
