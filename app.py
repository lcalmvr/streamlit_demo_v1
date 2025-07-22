import streamlit as st
import requests, base64, time, json
from openai import OpenAI

# ─── Config ───
API_KEY   = st.secrets["DOCUPIPE_API_KEY"]
BASE_URL  = "https://app.docupipe.ai"
SCHEMA_ID = "59839e02"

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Session state
st.session_state.setdefault("schema_data", None)
st.session_state.setdefault("chat_messages", [])

st.title("📄 DocuPipe + GPT Inspector")

# ─── Helper functions ───
def upload(file):
    b64 = base64.b64encode(file.read()).decode()
    r = requests.post(
        f"{BASE_URL}/document",
        json={"document": {"file": {"contents": b64, "filename": file.name}}},
        headers={
            "X-API-Key": API_KEY,
            "accept": "application/json",
            "content-type": "application/json",
        },
    )
    r.raise_for_status()
    return r.json()["documentId"]

def poll(endpoint, done_check):
    placeholder = st.empty()
    for i in range(1, 11):
        with st.spinner(f"Polling {endpoint} ({i}/10)…"):
            time.sleep(1.5)
        data = requests.get(f"{BASE_URL}/{endpoint}",
                            headers={"X-API-Key": API_KEY}).json()
        placeholder.json(data)                # JSON viewer is safe
        if done_check(data):
            return data
    st.error("Timed out.")
    return None

def standardize(doc_id):
    r = requests.post(
        f"{BASE_URL}/standardize",
        json={"documentId": doc_id, "schemaId": SCHEMA_ID},
        headers={"X-API-Key": API_KEY, "accept": "application/json"},
    )
    r.raise_for_status()
    return r.json()["standardizationId"]

def render_chat():
    # Previous messages
    for m in st.session_state.chat_messages:
        with st.chat_message(m["role"]):
            st.write(m["content"])            # <- write() avoids markdown parsing

    # New question
    if user_q := st.chat_input("Ask about this schema…"):
        st.session_state.chat_messages.append({"role": "user", "content": user_q})

        with st.chat_message("assistant"):
            prompt = (
                "You are an AI analyst.  Use ONLY the JSON provided below.\n\n"
                f"Question: {user_q}\n\n"
                f"JSON:\n{json.dumps(st.session_state.schema_data)[:30_000]}"  # keep prompt size sane
            )
            resp = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
            )
            answer = resp.choices[0].message.content
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": answer}
            )
            st.write(answer)                  # <- again, write() not markdown

# ─── UI ───
uploaded = st.file_uploader("Choose a PDF / image")

if st.button("Run Full Flow") and uploaded:
    doc_id = upload(uploaded)
    st.success(f"Uploaded → id {doc_id}")

    parsed = poll(f"document/{doc_id}", lambda d: d.get("status") == "completed")
    if not parsed:
        st.stop()
    st.subheader("Parsed response")
    st.json(parsed.get("result"))

    std_id = standardize(doc_id)
    st.success(f"Standardizing… id {std_id}")

    standardized = poll(
        f"standardization/{std_id}", lambda d: d.get("data") is not None
    )
    if standardized:
        st.session_state.schema_data = standardized["data"]
        st.subheader("Standardized schema")
        st.code(json.dumps(st.session_state.schema_data, indent=2), language="json")
        st.session_state.chat_messages.clear()
        render_chat()

elif st.session_state.schema_data:
    render_chat()

