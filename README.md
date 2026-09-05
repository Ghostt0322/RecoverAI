# RecoverAI

RecoverAI is a prototype AI-powered revenue recovery decision agent for merchants.

## What it demonstrates

- Detects failed payments and calculates revenue at risk
- Scores recovery likelihood using an explainable decision engine
- Uses Gemini when `GEMINI_API_KEY` is configured
- Recommends bounded recovery actions
- Requires approval for simulated recovery actions
- Records an audit trail
- Measures simulated recovered revenue

## Important

This prototype uses synthetic data. It does not execute real payments and does not claim real money was recovered.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Optional Gemini setup:

```powershell
$env:GEMINI_API_KEY="YOUR_KEY"
streamlit run app.py
```

Google's current Gemini Python SDK is `google-genai`; the app uses the current `client.models.generate_content(...)` interface. See the official Gemini API docs for current models and API-key setup.

## Demo flow

1. Open Overview and show revenue at risk.
2. Select a failed payment.
3. Click Analyze with RecoverAI.
4. Explain the confidence and recommended action.
5. Approve the simulated action.
6. Show the recovered amount and audit trail.

## Architecture

Synthetic payment data -> risk scoring -> AI decision layer -> bounded action -> audit trail -> recovery metrics.

## Future production work

- Razorpay Test Mode integration
- Real payment webhooks
- Merchant authentication
- Persistent database
- Policy/approval engine
- Evaluation dataset and offline AI evaluation
- Production monitoring and rate limits
