import os
import json
from datetime import datetime
import pandas as pd
import streamlit as st

try:
    from google import genai
except Exception:
    genai = None

st.set_page_config(page_title="RecoverAI", page_icon="💸", layout="wide")

DATA = [
    {"id":"RP1001","customer":"Aarav","amount":5000,"status":"failed","failure_reason":"insufficient_funds","attempts":1,"previous_successes":4,"hours_since_failure":3},
    {"id":"RP1002","customer":"Diya","amount":2000,"status":"failed","failure_reason":"network_error","attempts":1,"previous_successes":6,"hours_since_failure":1},
    {"id":"RP1003","customer":"Kabir","amount":8000,"status":"success","failure_reason":"","attempts":0,"previous_successes":8,"hours_since_failure":0},
    {"id":"RP1004","customer":"Ishaan","amount":3500,"status":"failed","failure_reason":"card_expired","attempts":2,"previous_successes":5,"hours_since_failure":18},
    {"id":"RP1005","customer":"Meera","amount":7000,"status":"failed","failure_reason":"timeout","attempts":1,"previous_successes":3,"hours_since_failure":2},
    {"id":"RP1006","customer":"Riya","amount":9000,"status":"failed","failure_reason":"insufficient_funds","attempts":1,"previous_successes":9,"hours_since_failure":5},
    {"id":"RP1007","customer":"Arjun","amount":1500,"status":"failed","failure_reason":"network_error","attempts":1,"previous_successes":2,"hours_since_failure":4},
    {"id":"RP1008","customer":"Nisha","amount":12000,"status":"failed","failure_reason":"card_expired","attempts":3,"previous_successes":1,"hours_since_failure":30},
    {"id":"RP1009","customer":"Vihaan","amount":4200,"status":"success","failure_reason":"","attempts":0,"previous_successes":7,"hours_since_failure":0},
    {"id":"RP1010","customer":"Anaya","amount":6500,"status":"failed","failure_reason":"timeout","attempts":1,"previous_successes":5,"hours_since_failure":6},
]

def risk_score(row):
    if row["status"] != "failed":
        return 0
    score = 45
    if row["previous_successes"] >= 5: score += 20
    elif row["previous_successes"] >= 2: score += 10
    if row["failure_reason"] in {"network_error", "timeout"}: score += 15
    if row["failure_reason"] == "insufficient_funds": score += 10
    if row["failure_reason"] == "card_expired": score -= 15
    if row["attempts"] >= 3: score -= 25
    if row["amount"] >= 5000: score += 5
    return max(5, min(score, 95))

def deterministic_recommendation(row):
    score = risk_score(row)
    if row["status"] != "failed":
        return "NO_ACTION", score
    if row["attempts"] >= 3:
        return "ESCALATE_TO_HUMAN", score
    if row["failure_reason"] == "card_expired":
        return "PAYMENT_METHOD_UPDATE", score
    if row["failure_reason"] in {"network_error", "timeout"} and score >= 60:
        return "RETRY", score
    if row["failure_reason"] == "insufficient_funds" and row["previous_successes"] >= 3:
        return "REMINDER_THEN_RETRY", score
    return "SEND_REMINDER", score

def local_explanation(row):
    action, score = deterministic_recommendation(row)
    reasons = []
    if row["previous_successes"] >= 5:
        reasons.append("customer has a strong successful payment history")
    if row["failure_reason"] in {"network_error", "timeout"}:
        reasons.append("the failure can be transient")
    if row["failure_reason"] == "insufficient_funds":
        reasons.append("the customer has previously completed successful payments")
    if row["failure_reason"] == "card_expired":
        reasons.append("the stored payment method likely needs updating")
    if row["attempts"] >= 3:
        reasons.append("multiple attempts have already failed")
    if not reasons:
        reasons.append("the case does not have enough positive recovery signals")
    return {
        "action": action,
        "confidence": score,
        "expected_recovery": round(row["amount"] * score / 100),
        "reasoning": reasons
    }

def ai_explanation(row):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        try:
            api_key = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            api_key = None

    if not api_key or genai is None:
        return local_explanation(row), False

    allowed = {
        "RETRY", "REMINDER_THEN_RETRY", "SEND_REMINDER",
        "PAYMENT_METHOD_UPDATE", "ESCALATE_TO_HUMAN", "NO_ACTION"
    }

    prompt = f"""
You are RecoverAI, a revenue recovery decision agent for a merchant.
Analyze this payment and return ONLY valid JSON with these keys:
action, confidence, expected_recovery, reasoning.

Allowed actions:
RETRY, REMINDER_THEN_RETRY, SEND_REMINDER, PAYMENT_METHOD_UPDATE,
ESCALATE_TO_HUMAN, NO_ACTION.

Rules:
- Never invent facts.
- Never claim a real payment was recovered.
- confidence must be 0-100.
- expected_recovery must not exceed the payment amount.
- reasoning must contain 2-4 concise, concrete reasons.
- Base the recommendation only on the supplied payment data.

Payment:
{json.dumps(row)}
"""

    last_error = None

    # Retry once to handle a transient first-request/API failure.
    for attempt in range(2):
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
            )

            raw = (response.text or "").strip()

            if "```" in raw:
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                raw = raw.strip()
                if raw.lower().startswith("json"):
                    raw = raw[4:].strip()

            start_json = raw.find("{")
            end_json = raw.rfind("}")
            if start_json == -1 or end_json == -1 or end_json <= start_json:
                raise ValueError("Gemini returned no valid JSON object")

            result = json.loads(raw[start_json:end_json + 1])

            action = str(result.get("action", "NO_ACTION")).strip().upper()
            if action not in allowed:
                action = "NO_ACTION"

            confidence = max(0, min(100, int(float(result.get("confidence", 0)))))
            expected = max(
                0,
                min(int(row["amount"]), int(float(result.get("expected_recovery", 0))))
            )

            reasoning = result.get("reasoning", [])
            if isinstance(reasoning, str):
                reasoning = [reasoning]
            reasoning = [str(x) for x in reasoning][:4]
            if not reasoning:
                reasoning = ["Gemini did not provide a detailed explanation."]

            return {
                "action": action,
                "confidence": confidence,
                "expected_recovery": expected,
                "reasoning": reasoning,
            }, True

        except Exception as exc:
            last_error = str(exc)

    st.session_state["ai_error"] = last_error or "Unknown Gemini error"
    return local_explanation(row), False


if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame(DATA)
if "audit" not in st.session_state:
    st.session_state.audit = []

df = st.session_state.df.copy()
df["risk_score"] = df.apply(risk_score, axis=1)
df["at_risk"] = df.apply(lambda r: r["amount"] if r["status"] == "failed" else 0, axis=1)

st.title("💸 RecoverAI")
st.caption("AI-powered revenue recovery decision agent — demo environment")

with st.sidebar:
    st.header("Control Center")
    st.write("Demo data is synthetic. No real payments are executed.")
    api_key_present = bool(os.getenv("GEMINI_API_KEY"))
    if not api_key_present:
        try:
            api_key_present = bool(st.secrets.get("GEMINI_API_KEY", ""))
        except Exception:
            api_key_present = False
    api_ready = api_key_present and genai is not None
    if api_ready:
        st.success("Gemini AI connected")
    else:
        st.info("Running with deterministic fallback")
    st.divider()
    if st.button("Reset demo"):
        st.session_state.df = pd.DataFrame(DATA)
        st.session_state.audit = []
        for key in ["latest_result", "latest_case", "latest_used_ai", "ai_error", "last_selected_case"]:
            st.session_state.pop(key, None)
        st.rerun()

failed = df[df["status"] == "failed"]
at_risk = int(failed["amount"].sum())
high_risk = int(failed[failed["risk_score"] >= 70]["amount"].sum())
recovered = int(df[df["status"] == "recovered"]["amount"].sum()) if "recovered" in df.columns else 0
recovery_rate = (recovered / at_risk * 100) if at_risk else 0

c1,c2,c3,c4 = st.columns(4)
c1.metric("Revenue at Risk", f"₹{at_risk:,.0f}")
c2.metric("High-Risk Revenue", f"₹{high_risk:,.0f}")
c3.metric("Recovered", f"₹{recovered:,.0f}")
c4.metric("Recovery Rate", f"{recovery_rate:.1f}%")

st.divider()

tab1, tab2, tab3 = st.tabs(["📊 Overview", "🤖 AI Recovery Agent", "🧾 Audit Trail"])

with tab1:
    st.subheader("Revenue Recovery Overview")
    chart = failed[["id","amount"]].set_index("id")
    st.bar_chart(chart)
    display_cols = ["id","customer","amount","failure_reason","attempts","risk_score"]
    view = failed[display_cols].copy()
    view.columns = ["Payment","Customer","Amount (₹)","Failure reason","Attempts","Risk score"]
    st.dataframe(view, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Analyze a Recovery Case")
    case_id = st.selectbox("Select payment", df["id"].tolist())

    # Never show a previous payment's analysis for a newly selected payment.
    if st.session_state.get("last_selected_case") != case_id:
        for key in ["latest_result", "latest_case", "latest_used_ai", "ai_error"]:
            st.session_state.pop(key, None)
        st.session_state["last_selected_case"] = case_id

    row = df[df["id"] == case_id].iloc[0].to_dict()

    left,right = st.columns([1,1])
    with left:
        st.write("### Payment")
        st.write(f"**Customer:** {row['customer']}")
        st.write(f"**Amount:** ₹{row['amount']:,.0f}")
        st.write(f"**Status:** {row['status']}")
        st.write(f"**Failure:** {row['failure_reason'] or '—'}")
        st.write(f"**Previous successful payments:** {row['previous_successes']}")
        st.write(f"**Previous attempts:** {row['attempts']}")

    with right:
        if st.button("Analyze with RecoverAI", type="primary"):
            for key in ["latest_result", "latest_case", "latest_used_ai", "ai_error"]:
                st.session_state.pop(key, None)

            with st.spinner("RecoverAI is analyzing this payment with Gemini..."):
                result, used_ai = ai_explanation(row)

            st.session_state["latest_result"] = result
            st.session_state["latest_case"] = row
            st.session_state["latest_used_ai"] = used_ai
            st.session_state.audit.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "payment": row["id"],
                "event": "AI_ANALYSIS",
                "details": f"{result.get('action')} | confidence {result.get('confidence')}%"
            })

        if "latest_result" in st.session_state and st.session_state.get("latest_case", {}).get("id") == case_id:
            result = st.session_state["latest_result"]
            used_ai = st.session_state.get("latest_used_ai", False)
            if used_ai:
                st.success("🤖 Live Gemini analysis")
            else:
                st.warning("Using local fallback — Gemini analysis failed")
                if st.session_state.get("ai_error"):
                    st.caption(f"Debug: {st.session_state['ai_error']}")
            st.metric("Recovery confidence", f"{result.get('confidence', 0)}%")
            st.write(f"### Recommended action: `{result.get('action','UNKNOWN')}`")
            st.write(f"**Expected recoverable amount:** ₹{int(result.get('expected_recovery',0)):,.0f}")
            st.write("**Why:**")
            for reason in result.get("reasoning", []):
                st.write("•", reason)

            action = result.get("action")
            if action not in {"NO_ACTION", "ESCALATE_TO_HUMAN"}:
                if st.button("Approve recovery action"):
                    idx = df.index[df["id"] == case_id][0]
                    st.session_state.df.loc[idx, "status"] = "recovered"
                    st.session_state.audit.append({
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "payment": case_id,
                        "event": "RECOVERY_APPROVED",
                        "details": f"{action}; simulated recovery ₹{row['amount']:,.0f}"
                    })
                    st.success("Simulated recovery completed. No real payment was executed.")
                    st.rerun()

with tab3:
    st.subheader("Audit Trail")
    if st.session_state.audit:
        st.dataframe(pd.DataFrame(st.session_state.audit), use_container_width=True, hide_index=True)
    else:
        st.info("No decisions recorded yet.")

st.divider()
st.caption("RecoverAI is a prototype using synthetic data. Recovery actions are simulated and do not move real money.")
