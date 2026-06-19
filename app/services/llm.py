import json
import time
import google.generativeai as genai
from app.config import settings

# Configure the Gemini client once per process.
# This avoids re-instantiating the model for every request.
genai.configure(api_key=settings.gemini_api_key)
model = genai.GenerativeModel("gemini-2.5-flash-lite")


VALID_CATEGORIES = [
    "Food", "Shopping", "Travel", "Transport",
    "Utilities", "Cash Withdrawal", "Entertainment", "Other"
]

DOMESTIC_MERCHANTS = {
    "swiggy", "ola", "irctc", "zomato",
    "jio recharge", "bookmyshow", "hdfc atm",
}


def _call_with_retry(prompt: str, max_retries: int = 3) -> str | None:
    """
    Call Gemini with exponential backoff retry logic.
    Exponential backoff: wait 2s, then 4s, then 8s between retries.
    This avoids hammering the API when it's rate-limiting us.
    """
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"  LLM call failed after {max_retries} attempts: {e}")
                return None
            wait_time = 2 ** attempt  # 1s, 2s, 4s
            print(f"  LLM attempt {attempt + 1} failed, retrying in {wait_time}s...")
            time.sleep(wait_time)

    return None


def classify_transactions_batch(transactions: list[dict]) -> dict[str, str]:
    """
    Send a BATCH of uncategorised transactions to the LLM in one call.
    Returns a dict mapping txn_id → category.

    Why batch? The assignment explicitly says not to make one call per row.
    One call for 20 rows = 20x cheaper and faster.
    """
    if not transactions:
        return {}

    # Format the transactions as a numbered list for the LLM
    txn_lines = "\n".join([
        f"{i+1}. ID: {t.get('txn_id', f'row_{i}')}, "
        f"Merchant: {t['merchant']}, "
        f"Amount: {t['amount']} {t['currency']}, "
        f"Notes: {t.get('notes', '')}"
        for i, t in enumerate(transactions)
    ])

    prompt = f"""You are a financial transaction categorizer.
Categorize each transaction into EXACTLY one of these categories:
{', '.join(VALID_CATEGORIES)}

Transactions to categorize:
{txn_lines}

Respond with ONLY a JSON object mapping the transaction ID to its category.
Example format: {{"TXN001": "Food", "TXN002": "Shopping"}}
No explanation, no markdown, just the JSON object."""

    raw_response = _call_with_retry(prompt)

    if raw_response is None:
        # All retries failed — return empty dict, caller handles this
        return {}

    try:
        # Strip markdown code fences if the LLM added them
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]

        result = json.loads(cleaned)
        return result
    except json.JSONDecodeError as e:
        print(f"  Failed to parse LLM classification response: {e}")
        return {}


def generate_narrative_summary(stats: dict) -> dict | None:
    """
    Ask the LLM to write a human-readable summary of the transaction data.
    Returns a dict with narrative and risk_level, or None on failure.
    """

    prompt = f"""You are a financial analyst reviewing transaction data.

Here are the statistics:
- Total INR spend: ₹{stats['total_inr']:,.2f}
- Total USD spend: ${stats['total_usd']:,.2f}
- Total transactions: {stats['total_count']}
- Anomalies detected: {stats['anomaly_count']}
- Top merchants: {json.dumps(stats['top_merchants'])}
- Categories breakdown: {json.dumps(stats['category_breakdown'])}

Respond with ONLY a JSON object with these exact keys:
{{
  "narrative": "2-3 sentence spending summary here",
  "risk_level": "low" | "medium" | "high"
}}

Risk level guide:
- low: <2 anomalies, no suspicious patterns
- medium: 2-5 anomalies or moderate unusual spending
- high: 5+ anomalies or very large suspicious transactions

No markdown, no explanation. Just the JSON object."""

    raw_response = _call_with_retry(prompt)

    if raw_response is None:
        return None

    try:
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]

        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None