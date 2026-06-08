import os
from pathlib import Path

import httpx
import streamlit as st

API_URL = os.getenv("RFP_API_URL", "http://127.0.0.1:8000").rstrip("/")
DEFAULT_KEY = os.getenv("RFP_API_KEY", "local-demo-key")
SAMPLE_DIR = Path("sample_data")


def api_client() -> httpx.Client:
    return httpx.Client(base_url=API_URL, headers={"X-API-Key": st.session_state.api_key}, timeout=20.0)


def post_json(path: str, payload: dict) -> dict:
    with api_client() as client:
        response = client.post(path, json=payload)
        response.raise_for_status()
        return response.json()


def post_upload(path: str, file_name: str, content: bytes, document_type: str) -> dict:
    with api_client() as client:
        response = client.post(
            path,
            data={"document_type": document_type, "source": "dashboard-upload", "tags": "upload"},
            files={"file": (file_name, content)},
        )
        response.raise_for_status()
        return response.json()


def get_json(path: str) -> dict | list:
    with api_client() as client:
        response = client.get(path)
        response.raise_for_status()
        return response.json()


st.set_page_config(page_title="RFP Response Intelligence Copilot", layout="wide")
st.title("RFP Response Intelligence Copilot")

if "api_key" not in st.session_state:
    st.session_state.api_key = DEFAULT_KEY

with st.sidebar:
    st.text_input("API URL", value=API_URL, disabled=True)
    st.text_input("API key", key="api_key", type="password")
    if st.button("Load demo token"):
        with httpx.Client(base_url=API_URL, timeout=10.0) as client:
            st.session_state.api_key = client.post("/auth/demo-token").json()["api_key"]
        st.success("Demo token loaded.")
    try:
        health = get_json("/health")
        st.caption(f"{health['status']} | provider={health['provider_mode']} | vector={health['vector_store_mode']}")
    except Exception as exc:
        st.warning(f"API unavailable: {exc}")

tabs = st.tabs(
    [
        "Ingest Documents",
        "Analyze RFP",
        "Ask Questions",
        "Draft Response",
        "Evaluation and Metrics",
        "Audit Events",
    ]
)

with tabs[0]:
    st.subheader("Ingest Source Documents")
    sample_files = sorted(path.name for path in SAMPLE_DIR.glob("*") if path.suffix.lower() in {".md", ".txt", ".pdf"})
    selected = st.multiselect("Sample files", sample_files, default=sample_files[:4])
    if st.button("Ingest selected samples"):
        rows = []
        for filename in selected:
            payload = {
                "fixture_path": f"sample_data/{filename}",
                "document_type": "rfp" if "rfp" in filename else "knowledge_base",
                "source": "sample_data",
                "tags": ["sample"],
            }
            rows.append(post_json("/documents/ingest", payload))
        st.success(f"Ingested {len(rows)} documents.")
        st.json(rows)
    if st.button("Refresh documents"):
        docs = get_json("/documents")
        st.dataframe(docs, use_container_width=True)
    upload = st.file_uploader("Upload PDF, Markdown, or TXT", type=["pdf", "md", "txt"])
    upload_type = st.selectbox("Upload document type", ["rfp", "knowledge_base", "security", "compliance", "pricing"])
    if upload and st.button("Ingest upload"):
        result = post_upload("/documents/ingest-upload", upload.name, upload.getvalue(), upload_type)
        st.success(f"Ingested {result['document']['filename']}")
        st.json(result)

with tabs[1]:
    st.subheader("Analyze RFP")
    rfp_text = st.text_area(
        "RFP text",
        value=(SAMPLE_DIR / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
        if (SAMPLE_DIR / "acme_enterprise_rfp.md").exists()
        else "",
        height=260,
    )
    if st.button("Analyze"):
        result = post_json("/rfp/analyze", {"text": rfp_text})
        st.metric("Requirements", len(result["requirements"]))
        st.write("Deadlines", result["deadlines"])
        st.write("Missing information", result["missing_information"])
        st.dataframe(result["requirements"], use_container_width=True)

with tabs[2]:
    st.subheader("Ask Cited RFP Questions")
    question = st.text_input("Question", "What SSO and encryption controls are supported?")
    top_k = st.slider("Top K", 1, 8, 4)
    if st.button("Query"):
        answer = post_json("/rfp/query", {"question": question, "top_k": top_k})
        st.metric("Confidence", answer["confidence"])
        st.write(answer["answer_text"])
        if answer["missing_evidence"]:
            st.warning("\n".join(answer["missing_evidence"]))
        st.dataframe(answer["citations"], use_container_width=True)

with tabs[3]:
    st.subheader("Draft Response")
    sections = st.multiselect(
        "Sections",
        [
            "Executive Summary",
            "Technical Response",
            "Security Response",
            "Compliance Response",
            "Assumptions",
            "Risks",
        ],
        default=[
            "Executive Summary",
            "Technical Response",
            "Security Response",
            "Compliance Response",
        ],
    )
    if st.button("Generate draft"):
        draft = post_json("/rfp/draft-response", {"section_names": sections, "top_k": 5})
        for section in draft["sections"]:
            st.markdown(f"### {section['title']}")
            st.write(section["body"])
        st.write("Assumptions", draft["assumptions"])
        st.write("Risks", draft["risks"])
        st.dataframe(draft["citations"], use_container_width=True)

with tabs[4]:
    st.subheader("Evaluate Retrieval and Grounding")
    dataset = st.text_input("Dataset path", "sample_data/eval_dataset.json")
    if st.button("Run eval"):
        result = post_json("/rfp/evaluate", {"dataset_path": dataset, "top_k": 4})
        cols = st.columns(5)
        cols[0].metric("Precision@K", result["retrieval_precision_at_k"])
        cols[1].metric("Citation Coverage", result["citation_coverage"])
        cols[2].metric("Latency ms", result["average_latency_ms"])
        cols[3].metric("Input Tokens", result["input_tokens"])
        cols[4].metric("Cost", result["estimated_cost"])
        st.dataframe(result["details"], use_container_width=True)
    if st.button("Usage metrics"):
        usage = get_json("/metrics/usage")
        st.json(usage["totals"])
        st.dataframe(usage["metrics"], use_container_width=True)

with tabs[5]:
    st.subheader("Audit Events")
    if st.button("Load audit events"):
        events = get_json("/audit/events")["events"]
        st.dataframe(events, use_container_width=True)
