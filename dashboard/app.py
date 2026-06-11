import json
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
        "Requirement Matrix / Export",
        "Customer Fit / Response Memory",
        "Action Plan / Handoff Board",
        "Review Board / Red Team",
        "Evaluation and Metrics",
        "Audit Events",
        "Deal Readiness / Executive Report",
        "Win Strategy / Pricing Memo",
        "Contract Risk / Negotiation Brief",
        "Evidence Gaps / Source Requests",
        "Timeline / Submission Calendar",
        "Submission Decision",
        "Leadership Brief",
        "Regression / Demo Script",
        "Launch Checklist",
        "Portfolio Pack",
        "Release Pack",
        "CI Doctor / Audit Pack",
        "Reviewer Quickstart",
        "API Contract",
        "Artifact Inventory",
        "UI Verification",
        "Final Handoff",
        "Git Readiness",
        "Runtime Demo",
        "RAG Corpus",
        "Compliance Evidence",
        "Procurement Q&A",
        "Bid/No-Bid ROI",
        "Objection Handling Pack",
        "Win/Loss Learning",
        "Reviewer Collaboration",
        "Evidence Freshness",
        "Evidence Conflicts",
        "Privacy Retention",
        "Submission Exceptions",
        "Citation Lineage",
        "Cost Governance",
        "Source Trust Gate",
        "Model Risk Register",
        "Procurement Risk Desk",
        "Answer Reuse Library",
        "Buyer Intelligence Pack",
        "Agent Council",
        "Decision Provenance",
        "Governed Retrieval",
        "Retrieval Experiments",
        "Proposal Observability",
        "Submission Certification",
        "Verification Evidence",
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
        st.session_state.analysis = result
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
        st.session_state.answer = answer
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
        st.session_state.draft = draft
        for section in draft["sections"]:
            st.markdown(f"### {section['title']}")
            st.write(section["body"])
        st.write("Assumptions", draft["assumptions"])
        st.write("Risks", draft["risks"])
        st.dataframe(draft["citations"], use_container_width=True)

with tabs[4]:
    st.subheader("Requirement Matrix and Export Pack")
    st.caption("Analyze the sample RFP here or reuse the latest Analyze RFP tab result.")
    if st.button("Analyze sample for matrix"):
        sample_text = (SAMPLE_DIR / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
        st.session_state.analysis = post_json("/rfp/analyze", {"text": sample_text})
        st.success("Sample RFP analyzed.")
    analysis = st.session_state.get("analysis")
    draft = st.session_state.get("draft")
    if analysis:
        if st.button("Create requirement matrix"):
            matrix = post_json("/rfp/requirement-matrix", {"analyzed_payload": analysis})["matrix"]
            st.session_state.matrix = matrix
        matrix = st.session_state.get("matrix")
        if matrix:
            rows = [
                {
                    "requirement_id": row["requirement_id"],
                    "category": row["category"],
                    "priority": row["priority"],
                    "owner_role": row["owner_role"],
                    "status": row["status"],
                    "risk_level": row["risk_level"],
                    "evidence_refs": ", ".join(row["evidence_refs"]),
                    "missing_evidence": "; ".join(row["missing_evidence"]),
                    "requirement_text": row["requirement_text"],
                }
                for row in matrix
            ]
            st.dataframe(rows, use_container_width=True)
        include_current_draft = st.checkbox(
            "Include latest draft response",
            value=bool(draft),
            disabled=not bool(draft),
        )
        profiles = get_json("/customers/profiles")["profiles"]
        profile_names = {profile["name"]: profile["id"] for profile in profiles}
        export_profile_name = st.selectbox(
            "Customer profile for export",
            ["None"] + list(profile_names),
            key="export_customer_profile",
        )
        include_memory = st.checkbox(
            "Include approved response memory",
            value=export_profile_name != "None",
            disabled=export_profile_name == "None",
        )
        if st.button("Export response package"):
            payload = {"analyzed_payload": analysis, "write_artifact": True}
            if include_current_draft and draft:
                payload["draft_response"] = draft
            if export_profile_name != "None":
                payload["customer_profile_id"] = profile_names[export_profile_name]
                payload["include_response_memory"] = include_memory
            export = post_json("/rfp/export-package", payload)
            st.session_state.export_package = export
            st.success(f"Exported package: {export['artifact_path']}")
            st.json(export["package"]["executive_summary"])
            if export["package"].get("customer_fit"):
                st.json(export["package"]["customer_fit"])
            if export["package"].get("response_memory_matches"):
                st.dataframe(export["package"]["response_memory_matches"], use_container_width=True)
            st.download_button("Download Markdown", export["markdown"], file_name="rfp_response_export.md")
    else:
        st.info("Run Analyze RFP first, or analyze the sample RFP from this tab.")

with tabs[5]:
    st.subheader("Customer Fit and Response Memory")
    profiles = get_json("/customers/profiles")["profiles"]
    profile_lookup = {f"{profile['name']} ({profile['industry']})": profile for profile in profiles}
    selected_profile_label = st.selectbox("Customer profile", list(profile_lookup))
    selected_profile = profile_lookup[selected_profile_label]
    st.json(selected_profile)

    latest_analysis = st.session_state.get("analysis")
    latest_matrix = st.session_state.get("matrix")
    if st.button("Analyze customer fit"):
        payload = {"customer_profile_id": selected_profile["id"]}
        if latest_analysis:
            payload["analyzed_payload"] = latest_analysis
        elif latest_matrix:
            payload["requirement_matrix"] = latest_matrix
        else:
            sample_text = (SAMPLE_DIR / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
            payload["analyzed_payload"] = post_json("/rfp/analyze", {"text": sample_text})
        fit = post_json("/rfp/customer-fit", payload)
        st.session_state.customer_fit = fit
        cols = st.columns(3)
        cols[0].metric("Fit score", fit["fit_score"])
        cols[1].metric("Emphasize", len(fit["requirements_to_emphasize"]))
        cols[2].metric("Needs review", len(fit["requirements_needing_review"]))
        st.write("Recommended positioning", fit["recommended_positioning"])
        st.write("Profile risks", fit["profile_risks"])
        st.dataframe(fit["requirements_to_emphasize"], use_container_width=True)
        st.dataframe(fit["requirements_needing_review"], use_container_width=True)

    memory_query = st.text_input(
        "Memory query",
        "SSO encryption SOC 2 implementation plan",
    )
    memory_category = st.selectbox("Memory category", ["Any", "security", "compliance", "implementation", "pricing"])
    if st.button("Search approved responses"):
        payload = {
            "query": memory_query,
            "customer_profile_id": selected_profile["id"],
            "top_k": 5,
        }
        if memory_category != "Any":
            payload["category"] = memory_category
        memory = post_json("/rfp/response-memory/search", payload)
        st.session_state.response_memory = memory
        st.dataframe(memory["matches"], use_container_width=True)

with tabs[6]:
    st.subheader("Stakeholder Action Plan and Handoff Board")
    latest_analysis = st.session_state.get("analysis")
    latest_matrix = st.session_state.get("matrix")
    latest_fit = st.session_state.get("customer_fit")
    latest_review = st.session_state.get("review_report")
    profiles = get_json("/customers/profiles")["profiles"]
    profile_names = {profile["name"]: profile["id"] for profile in profiles}
    handoff_profile_name = st.selectbox(
        "Customer profile",
        ["None"] + list(profile_names),
        key="handoff_customer_profile",
    )
    if st.button("Create stakeholder action plan"):
        payload = {}
        if latest_analysis:
            payload["analyzed_payload"] = latest_analysis
        if latest_matrix:
            payload["requirement_matrix"] = latest_matrix
        if latest_fit:
            payload["customer_fit"] = latest_fit
        if latest_review:
            payload["review_findings"] = latest_review["findings"]
        if handoff_profile_name != "None":
            payload["customer_profile_id"] = profile_names[handoff_profile_name]
        if not latest_analysis and not latest_matrix:
            sample_text = (SAMPLE_DIR / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
            payload["analyzed_payload"] = post_json("/rfp/analyze", {"text": sample_text})
        plan = post_json("/rfp/action-plan", payload)
        st.session_state.action_plan = plan
        st.json(plan["summary"])
        st.dataframe(plan["tasks"], use_container_width=True)
    plan = st.session_state.get("action_plan")
    if plan and st.button("Export handoff board"):
        payload = {
            "action_plan": plan["tasks"],
            "write_artifact": True,
        }
        if latest_analysis:
            payload["analyzed_payload"] = latest_analysis
        if latest_matrix:
            payload["requirement_matrix"] = latest_matrix
        if latest_fit:
            payload["customer_fit"] = latest_fit
        if latest_review:
            payload["review_findings"] = latest_review["findings"]
        if handoff_profile_name != "None":
            payload["customer_profile_id"] = profile_names[handoff_profile_name]
        handoff = post_json("/rfp/handoff-board", payload)
        st.session_state.handoff_board = handoff
        st.success(f"Exported handoff board: {handoff['artifact_path']}")
        st.json(handoff["board"]["summary"])
        st.write("Next meeting agenda", handoff["board"]["next_meeting_agenda"])
        st.download_button("Download Handoff Markdown", handoff["markdown"], file_name="rfp_handoff_board.md")
    if not latest_analysis and not latest_matrix and not plan:
        st.info("Analyze an RFP or create a requirement matrix first, or generate the sample plan from this tab.")

with tabs[7]:
    st.subheader("Review Board and Red-Team Questions")
    latest_answer = st.session_state.get("answer")
    latest_analysis = st.session_state.get("analysis")
    latest_draft = st.session_state.get("draft")
    if latest_answer and st.button("Review latest answer"):
        review = post_json(
            "/rfp/review-answer",
            {
                "question": latest_answer["question"],
                "answer_text": latest_answer["answer_text"],
                "citations": latest_answer["citations"],
                "missing_evidence": latest_answer["missing_evidence"],
                "token_usage": latest_answer["token_usage"],
            },
        )
        st.metric("Review passed", "Yes" if review["passed"] else "No")
        st.session_state.review_report = review
        st.json(review["summary"])
        st.dataframe(review["findings"], use_container_width=True)
    if latest_analysis and st.button("Review latest package"):
        payload = {"analyzed_payload": latest_analysis, "write_artifact": False}
        if latest_draft:
            payload["draft_response"] = latest_draft
        review = post_json("/rfp/review-package", payload)
        st.metric("Review passed", "Yes" if review["passed"] else "No")
        st.session_state.review_report = review
        st.json(review["summary"])
        st.dataframe(review["findings"], use_container_width=True)
    red_team_path = SAMPLE_DIR / "red_team_questions.json"
    if red_team_path.exists() and st.button("Run red-team questions"):
        red_team = red_team_path.read_text(encoding="utf-8")
        questions = json.loads(red_team)["questions"]
        rows = []
        for item in questions:
            answer = post_json("/rfp/query", {"question": item["question"], "top_k": 4})
            review = post_json(
                "/rfp/review-answer",
                {
                    "question": answer["question"],
                    "answer_text": answer["answer_text"],
                    "citations": answer["citations"],
                    "missing_evidence": answer["missing_evidence"],
                    "token_usage": answer["token_usage"],
                },
            )
            rows.append(
                {
                    "risk_type": item.get("risk_type", "unknown"),
                    "question": item["question"],
                    "citations": len(answer["citations"]),
                    "missing_evidence": bool(answer["missing_evidence"]),
                    "review_passed": review["passed"],
                    "categories": ", ".join(
                        sorted({finding["category"] for finding in review["findings"]})
                    ),
                }
            )
        st.dataframe(rows, use_container_width=True)
    if not latest_answer and not latest_analysis:
        st.info("Ask a question or analyze an RFP first, then run the review board.")

with tabs[8]:
    st.subheader("Evaluate Retrieval and Grounding")
    dataset = st.text_input("Dataset path", "sample_data/eval_dataset.json")
    if st.button("Run eval"):
        result = post_json("/rfp/evaluate", {"dataset_path": dataset, "top_k": 4})
        st.session_state.evaluation_metrics = result
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

with tabs[9]:
    st.subheader("Audit Events")
    if st.button("Load audit events"):
        events = get_json("/audit/events")["events"]
        st.dataframe(events, use_container_width=True)

with tabs[10]:
    st.subheader("Deal Readiness and Executive Risk Report")
    latest_analysis = st.session_state.get("analysis")
    latest_matrix = st.session_state.get("matrix")
    latest_draft = st.session_state.get("draft")
    latest_fit = st.session_state.get("customer_fit")
    latest_review = st.session_state.get("review_report")
    latest_plan = st.session_state.get("action_plan")
    latest_eval = st.session_state.get("evaluation_metrics")

    if st.button("Analyze sample readiness inputs"):
        sample_text = (SAMPLE_DIR / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
        latest_analysis = post_json("/rfp/analyze", {"text": sample_text})
        latest_matrix = post_json("/rfp/requirement-matrix", {"analyzed_payload": latest_analysis})["matrix"]
        st.session_state.analysis = latest_analysis
        st.session_state.matrix = latest_matrix
        st.success("Sample analysis and matrix loaded.")

    payload = {}
    if latest_analysis:
        payload["analysis"] = latest_analysis
    if latest_matrix:
        payload["matrix"] = latest_matrix
    if latest_draft:
        payload["draft_response"] = latest_draft
    if latest_fit:
        payload["customer_fit"] = latest_fit
    if latest_review:
        payload["review_findings"] = latest_review["findings"]
    if latest_plan:
        payload["action_plan"] = latest_plan["tasks"]
    if latest_eval:
        payload["eval_metrics"] = latest_eval

    cols = st.columns(3)
    if cols[0].button("Create readiness scorecard", disabled=not bool(payload)):
        scorecard = post_json("/rfp/readiness-scorecard", payload)
        st.session_state.readiness_scorecard = scorecard
        st.metric("Readiness score", scorecard["readiness_score"])
        st.metric("Readiness level", scorecard["readiness_level"])
        st.write("Blockers", scorecard["blockers"])
        st.write("Recommended next actions", scorecard["recommended_next_actions"])
        st.dataframe(scorecard["owner_bottlenecks"], use_container_width=True)
        st.write("Score trace")
        st.dataframe(scorecard["score_trace"], use_container_width=True)
        st.write("Approval workflow")
        st.dataframe(scorecard["approval_workflow"], use_container_width=True)
        st.write("Human review queue")
        st.dataframe(scorecard["human_review_queue"], use_container_width=True)

    if cols[1].button("Export executive risk report", disabled=not bool(payload)):
        report = post_json("/rfp/executive-risk-report", {**payload, "write_artifact": True})
        st.session_state.executive_risk_report = report
        st.success(f"Exported executive report: {report['artifact_path']}")
        st.json(report["report"]["readiness"])
        st.write(report["report"]["submission_recommendation"])
        st.download_button(
            "Download Executive Report Markdown",
            report["markdown"],
            file_name="executive_risk_report.md",
        )

    if cols[2].button("Export readiness score pack", disabled=not bool(payload)):
        score_pack = post_json("/rfp/proposal-readiness-score-pack", {**payload, "write_artifact": True})
        st.session_state.proposal_readiness_score_pack = score_pack
        st.success(f"Exported readiness score pack: {score_pack['artifact_path']}")
        st.metric("Pack status", score_pack["status"])
        st.json(score_pack["pack"]["section_completeness"])
        st.json(score_pack["pack"]["score_trace_analysis"])
        st.dataframe(score_pack["pack"]["reviewer_bottlenecks"], use_container_width=True)
        st.dataframe(score_pack["pack"]["durable_approval_workflow"], use_container_width=True)
        st.dataframe(score_pack["pack"]["human_review_queue"], use_container_width=True)
        st.download_button(
            "Download Readiness Score Pack Markdown",
            score_pack["markdown"],
            file_name="proposal_readiness_score_pack.md",
        )

    if not payload:
        st.info("Run analysis, review, customer fit, or action planning first, or load sample readiness inputs.")

with tabs[11]:
    st.subheader("Competitive Win Strategy and Pricing Memo")
    latest_analysis = st.session_state.get("analysis")
    latest_matrix = st.session_state.get("matrix")
    latest_fit = st.session_state.get("customer_fit")
    latest_review = st.session_state.get("review_report")
    latest_plan = st.session_state.get("action_plan")
    latest_readiness = st.session_state.get("readiness_scorecard")
    latest_memory = st.session_state.get("response_memory")
    profiles = get_json("/customers/profiles")["profiles"]
    profile_names = {profile["name"]: profile["id"] for profile in profiles}
    win_profile_name = st.selectbox(
        "Customer profile",
        list(profile_names),
        key="win_strategy_customer_profile",
    )
    competitor_context = st.text_area(
        "Competitor context",
        "Incumbent competitor may bundle workflow tooling and offer a discount during procurement.",
        height=90,
    )
    pricing_notes = st.text_area(
        "Pricing notes",
        "Use standard tiers; route volume discounts, custom packaging, and public-sector terms for approval.",
        height=90,
    )
    if st.button("Load sample win-strategy inputs"):
        sample_text = (SAMPLE_DIR / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
        latest_analysis = post_json("/rfp/analyze", {"text": sample_text})
        latest_matrix = post_json("/rfp/requirement-matrix", {"analyzed_payload": latest_analysis})["matrix"]
        st.session_state.analysis = latest_analysis
        st.session_state.matrix = latest_matrix
        st.success("Sample analysis and matrix loaded.")

    payload = {
        "competitor_context": [line.strip() for line in competitor_context.splitlines() if line.strip()],
        "pricing_notes": [line.strip() for line in pricing_notes.splitlines() if line.strip()],
    }
    if latest_analysis:
        payload["analysis"] = latest_analysis
    if latest_matrix:
        payload["matrix"] = latest_matrix
    if latest_fit:
        payload["customer_fit"] = latest_fit
    else:
        payload["customer_profile_id"] = profile_names.get(win_profile_name, "regulated_healthcare")
    if latest_review:
        payload["review_findings"] = latest_review["findings"]
    if latest_plan:
        payload["action_plan"] = latest_plan["tasks"]
    if latest_readiness:
        payload["readiness_scorecard"] = latest_readiness
    if latest_memory:
        payload["response_memory_matches"] = latest_memory["matches"]

    cols = st.columns(2)
    if cols[0].button("Simulate win strategy"):
        strategy = post_json("/rfp/win-strategy", payload)
        st.session_state.win_strategy = strategy
        metric_cols = st.columns(4)
        metric_cols[0].metric("Win score", strategy["win_score"])
        metric_cols[1].metric("Win level", strategy["win_level"])
        metric_cols[2].metric("Competitor risk", strategy["competitor_risk_profile"]["risk_level"])
        metric_cols[3].metric("Pricing risk", strategy["pricing_risk"]["risk_level"])
        st.write(strategy["recommended_response_posture"])
        st.write("Red flags", strategy["red_flags"])
        st.dataframe(strategy["proof_points"], use_container_width=True)
        st.dataframe(strategy["next_actions_by_owner"], use_container_width=True)

    current_strategy = st.session_state.get("win_strategy")
    if cols[1].button("Export pricing risk memo"):
        memo_payload = {**payload, "write_artifact": True}
        if current_strategy:
            memo_payload["win_strategy"] = current_strategy
        memo = post_json("/rfp/pricing-risk-memo", memo_payload)
        st.session_state.pricing_memo = memo
        st.success(f"Exported pricing memo: {memo['artifact_path']}")
        st.write(memo["memo"]["leadership_recommendation"])
        st.json(
            {
                "win_score": memo["memo"]["win_score"],
                "win_level": memo["memo"]["win_level"],
                "pricing_assumptions": memo["memo"]["pricing_assumptions"],
            }
        )
        st.download_button(
            "Download Pricing Memo Markdown",
            memo["markdown"],
            file_name="pricing_risk_memo.md",
        )

with tabs[12]:
    st.subheader("Contract Redline Risk and Negotiation Brief")
    contract_path = SAMPLE_DIR / "customer_contract_terms.md"
    contract_text = st.text_area(
        "Contract or procurement terms",
        value=contract_path.read_text(encoding="utf-8") if contract_path.exists() else "",
        height=280,
    )
    latest_win_strategy = st.session_state.get("win_strategy")
    latest_pricing_memo = st.session_state.get("pricing_memo")
    profile_id = st.selectbox(
        "Customer context",
        ["regulated_healthcare", "fintech", "public_sector", "None"],
        key="contract_risk_profile",
    )
    risk_payload = {"text": contract_text}
    if profile_id != "None":
        risk_payload["customer_profile_id"] = profile_id

    cols = st.columns(2)
    if cols[0].button("Analyze contract risk", disabled=not bool(contract_text.strip())):
        risk = post_json("/rfp/contract-risk", risk_payload)
        st.session_state.contract_risk = risk
        metric_cols = st.columns(4)
        metric_cols[0].metric("Risk score", risk["risk_score"])
        metric_cols[1].metric("Status", risk["status"])
        metric_cols[2].metric("Risky clauses", len(risk["risky_clauses"]))
        metric_cols[3].metric("Missing evidence", len(risk["missing_evidence_warnings"]))
        st.json(risk["category_counts"])
        st.dataframe(risk["risky_clauses"], use_container_width=True)
        st.dataframe(risk["owner_actions"], use_container_width=True)
        if risk["missing_evidence_warnings"]:
            st.warning("\n".join(risk["missing_evidence_warnings"]))

    current_risk = st.session_state.get("contract_risk")
    if cols[1].button("Export negotiation brief", disabled=not bool(contract_text.strip() or current_risk)):
        brief_payload = {"write_artifact": True}
        if current_risk:
            brief_payload["contract_risk"] = current_risk
        else:
            brief_payload.update(risk_payload)
        if latest_win_strategy:
            brief_payload["win_strategy"] = latest_win_strategy
        if latest_pricing_memo:
            brief_payload["pricing_memo"] = latest_pricing_memo
        brief = post_json("/rfp/negotiation-brief", brief_payload)
        st.session_state.negotiation_brief = brief
        st.success(f"Exported negotiation brief: {brief['artifact_path']}")
        st.json(brief["brief"]["contract_risk_summary"])
        st.write("Win strategy context", brief["brief"]["win_strategy_context"])
        st.write("Pricing context", brief["brief"]["pricing_context"])
        st.download_button(
            "Download Negotiation Brief Markdown",
            brief["markdown"],
            file_name="negotiation_brief.md",
        )


with tabs[13]:
    st.subheader("Evidence Gaps and Source Requests")
    latest_analysis = st.session_state.get("analysis")
    latest_matrix = st.session_state.get("matrix")
    latest_review = st.session_state.get("review_report")
    latest_plan = st.session_state.get("action_plan")
    latest_readiness = st.session_state.get("readiness_scorecard")
    latest_win_strategy = st.session_state.get("win_strategy")
    latest_contract_risk = st.session_state.get("contract_risk")

    if st.button("Load sample evidence-gap inputs"):
        sample_text = (SAMPLE_DIR / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
        latest_analysis = post_json("/rfp/analyze", {"text": sample_text})
        latest_matrix = post_json("/rfp/requirement-matrix", {"analyzed_payload": latest_analysis})["matrix"]
        st.session_state.analysis = latest_analysis
        st.session_state.matrix = latest_matrix
        st.success("Sample analysis and matrix loaded.")

    payload = {}
    if latest_analysis:
        payload["analysis"] = latest_analysis
    if latest_matrix:
        payload["matrix"] = latest_matrix
    if latest_review:
        payload["review_findings"] = latest_review["findings"]
    if latest_plan:
        payload["action_plan"] = latest_plan["tasks"]
    if latest_readiness:
        payload["readiness_scorecard"] = latest_readiness
    if latest_win_strategy:
        payload["win_strategy"] = latest_win_strategy
    if latest_contract_risk:
        payload["contract_risk"] = latest_contract_risk

    cols = st.columns(2)
    if cols[0].button("Create evidence gap plan"):
        gaps = post_json("/rfp/evidence-gaps", payload)
        st.session_state.evidence_gaps = gaps
        metric_cols = st.columns(3)
        metric_cols[0].metric("Gap count", gaps["summary"]["gap_count"])
        metric_cols[1].metric("High severity", gaps["summary"]["high_severity_count"])
        metric_cols[2].metric("Owners", len(gaps["summary"]["owner_counts"]))
        st.dataframe(gaps["gaps"], use_container_width=True)
        st.json(gaps["summary"])

    current_gaps = st.session_state.get("evidence_gaps")
    if cols[1].button("Export source request pack"):
        pack_payload = {**payload, "write_artifact": True}
        if current_gaps:
            pack_payload["evidence_gaps"] = current_gaps["gaps"]
        pack = post_json("/rfp/source-request-pack", pack_payload)
        st.session_state.source_request_pack = pack
        st.success(f"Exported source request pack: {pack['artifact_path']}")
        st.json(pack["pack"]["summary"])
        st.dataframe(pack["pack"]["owner_matrix"], use_container_width=True)
        st.download_button(
            "Download Source Request Pack Markdown",
            pack["markdown"],
            file_name="source_request_pack.md",
        )

    if not payload and not current_gaps:
        st.info("Use existing workflow outputs, load sample inputs, or run the planner with the local sample fallback.")


with tabs[14]:
    st.subheader("Timeline and Submission Calendar")
    latest_analysis = st.session_state.get("analysis")
    latest_matrix = st.session_state.get("matrix")
    latest_review = st.session_state.get("review_report")
    latest_plan = st.session_state.get("action_plan")
    latest_readiness = st.session_state.get("readiness_scorecard")
    latest_win_strategy = st.session_state.get("win_strategy")
    latest_contract_risk = st.session_state.get("contract_risk")
    latest_gaps = st.session_state.get("evidence_gaps")
    latest_source_pack = st.session_state.get("source_request_pack")
    latest_leadership = st.session_state.get("leadership_brief")

    if st.button("Load sample timeline inputs"):
        sample_text = (SAMPLE_DIR / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
        latest_analysis = post_json("/rfp/analyze", {"text": sample_text})
        latest_matrix = post_json("/rfp/requirement-matrix", {"analyzed_payload": latest_analysis})["matrix"]
        st.session_state.analysis = latest_analysis
        st.session_state.matrix = latest_matrix
        st.success("Sample analysis and matrix loaded.")

    payload = {}
    if latest_analysis:
        payload["analysis"] = latest_analysis
    if latest_matrix:
        payload["matrix"] = latest_matrix
    if latest_review:
        payload["review_findings"] = latest_review["findings"]
    if latest_plan:
        payload["action_plan"] = latest_plan["tasks"]
    if latest_readiness:
        payload["readiness_scorecard"] = latest_readiness
    if latest_win_strategy:
        payload["win_strategy"] = latest_win_strategy
    if latest_contract_risk:
        payload["contract_risk"] = latest_contract_risk
    if latest_gaps:
        payload["evidence_gaps"] = latest_gaps["gaps"]
    if latest_source_pack:
        payload["source_request_pack"] = latest_source_pack["pack"]
    if latest_leadership:
        payload["leadership_brief"] = latest_leadership["brief"]

    cols = st.columns(2)
    if cols[0].button("Create timeline plan"):
        timeline = post_json("/rfp/timeline-plan", payload)
        st.session_state.timeline_plan = timeline
        metric_cols = st.columns(4)
        metric_cols[0].metric("Milestones", timeline["summary"]["milestone_count"])
        metric_cols[1].metric("Blocked", timeline["summary"]["blocked_count"])
        metric_cols[2].metric("Calendar entries", timeline["summary"]["calendar_entry_count"])
        metric_cols[3].metric("Readiness", timeline["summary"]["readiness_score"])
        st.dataframe(timeline["milestones"], use_container_width=True)
        st.write("Readiness gates")
        st.dataframe(timeline["readiness_gates"], use_container_width=True)
        st.write("Escalation triggers")
        st.dataframe(timeline["escalation_triggers"], use_container_width=True)

    current_timeline = st.session_state.get("timeline_plan")
    if cols[1].button("Export submission calendar pack"):
        pack_payload = {**payload, "write_artifact": True}
        if current_timeline:
            pack_payload["timeline_plan"] = current_timeline
        calendar_pack = post_json("/rfp/submission-calendar-pack", pack_payload)
        st.session_state.submission_calendar_pack = calendar_pack
        st.success(f"Exported submission calendar: {calendar_pack['artifact_path']}")
        st.json(calendar_pack["pack"]["summary"])
        st.dataframe(calendar_pack["pack"]["owner_matrix"], use_container_width=True)
        st.download_button(
            "Download Submission Calendar Markdown",
            calendar_pack["markdown"],
            file_name="submission_calendar_pack.md",
        )

    if not payload and not current_timeline:
        st.info("Use workflow outputs, load sample inputs, or run the local sample fallback with empty inputs.")


with tabs[15]:
    st.subheader("Submission Decision")
    st.caption("Final go/no-go gate for executive submission approval.")
    latest_analysis = st.session_state.get("analysis")
    latest_matrix = st.session_state.get("matrix")
    latest_draft = st.session_state.get("draft")
    latest_answer = st.session_state.get("answer")
    latest_review = st.session_state.get("review_report")
    latest_plan = st.session_state.get("action_plan")
    latest_readiness = st.session_state.get("readiness_scorecard")
    latest_eval = st.session_state.get("evaluation_metrics")
    latest_win_strategy = st.session_state.get("win_strategy")
    latest_contract_risk = st.session_state.get("contract_risk")
    latest_gaps = st.session_state.get("evidence_gaps")
    latest_source_pack = st.session_state.get("source_request_pack")
    latest_timeline = st.session_state.get("timeline_plan")
    latest_calendar = st.session_state.get("submission_calendar_pack")
    latest_leadership = st.session_state.get("leadership_brief")

    if st.button("Load sample decision inputs"):
        sample_text = (SAMPLE_DIR / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
        latest_analysis = post_json("/rfp/analyze", {"text": sample_text})
        latest_matrix = post_json("/rfp/requirement-matrix", {"analyzed_payload": latest_analysis})["matrix"]
        st.session_state.analysis = latest_analysis
        st.session_state.matrix = latest_matrix
        st.success("Sample decision inputs loaded.")

    payload = {}
    if latest_analysis:
        payload["analysis"] = latest_analysis
    if latest_matrix:
        payload["matrix"] = latest_matrix
    if latest_draft:
        payload["draft_response"] = latest_draft
    if latest_answer:
        payload["answers"] = [latest_answer]
    if latest_review:
        payload["review_findings"] = latest_review["findings"]
        payload["review_passed"] = latest_review["passed"]
    if latest_plan:
        payload["action_plan"] = latest_plan["tasks"]
    if latest_readiness:
        payload["readiness_scorecard"] = latest_readiness
    if latest_eval:
        payload["eval_metrics"] = latest_eval
    if latest_win_strategy:
        payload["win_strategy"] = latest_win_strategy
    if latest_contract_risk:
        payload["contract_risk"] = latest_contract_risk
    if latest_gaps:
        payload["evidence_gaps"] = latest_gaps["gaps"]
    if latest_source_pack:
        payload["source_request_pack"] = latest_source_pack["pack"]
        payload["source_request_artifact_path"] = latest_source_pack["artifact_path"]
        payload["source_request_json_artifact_path"] = latest_source_pack["json_artifact_path"]
    if latest_timeline:
        payload["timeline_plan"] = latest_timeline
    if latest_calendar:
        payload["submission_calendar_artifact_path"] = latest_calendar["artifact_path"]
        payload["submission_calendar_json_artifact_path"] = latest_calendar["json_artifact_path"]
    if latest_leadership:
        payload["leadership_brief"] = latest_leadership["brief"]
        payload["leadership_brief_artifact_path"] = latest_leadership["artifact_path"]
        payload["leadership_brief_json_artifact_path"] = latest_leadership["json_artifact_path"]

    cols = st.columns(2)
    if cols[0].button("Run submission decision"):
        decision = post_json("/rfp/submission-decision", payload)
        st.session_state.submission_decision = decision
        metric_cols = st.columns(4)
        metric_cols[0].metric("Decision", decision["decision"])
        metric_cols[1].metric("Score", decision["score"])
        metric_cols[2].metric("Blockers", len(decision["blocking_issues"]))
        metric_cols[3].metric("Exceptions", len(decision["exception_list"]))
        st.write("Rationale")
        st.write(decision["rationale"])
        st.dataframe(decision["blocking_issues"], use_container_width=True)
        st.dataframe(decision["approvals_required"], use_container_width=True)

    current_decision = st.session_state.get("submission_decision")
    if cols[1].button("Export executive submission memo"):
        memo_payload = {**payload, "write_artifact": True}
        if current_decision:
            memo_payload["submission_decision"] = current_decision
        memo = post_json("/rfp/executive-submission-memo", memo_payload)
        st.session_state.executive_submission_memo = memo
        st.success(f"Exported executive submission memo: {memo['artifact_path']}")
        st.json(memo["memo"]["go_no_go_summary"])
        st.download_button(
            "Download Executive Submission Memo Markdown",
            memo["markdown"],
            file_name="executive_submission_memo.md",
        )

    if not payload and not current_decision:
        st.info("Use workflow outputs, load sample inputs, or run the local fallback with empty inputs.")


with tabs[16]:
    st.subheader("Portfolio Demo Leadership Brief")
    latest_analysis = st.session_state.get("analysis")
    latest_matrix = st.session_state.get("matrix")
    latest_draft = st.session_state.get("draft")
    latest_answer = st.session_state.get("answer")
    latest_export = st.session_state.get("export_package")
    latest_fit = st.session_state.get("customer_fit")
    latest_review = st.session_state.get("review_report")
    latest_plan = st.session_state.get("action_plan")
    latest_handoff = st.session_state.get("handoff_board")
    latest_readiness = st.session_state.get("readiness_scorecard")
    latest_report = st.session_state.get("executive_risk_report")
    latest_eval = st.session_state.get("evaluation_metrics")
    profiles = get_json("/customers/profiles")["profiles"]
    profile_names = {profile["name"]: profile["id"] for profile in profiles}
    brief_profile_name = st.selectbox(
        "Customer profile for brief",
        ["None"] + list(profile_names),
        key="brief_customer_profile",
    )
    if st.button("Generate Leadership Brief"):
        if latest_analysis is None and latest_matrix is None:
            sample_text = (SAMPLE_DIR / "acme_enterprise_rfp.md").read_text(encoding="utf-8")
            latest_analysis = post_json("/rfp/analyze", {"text": sample_text})
            st.session_state.analysis = latest_analysis
        payload = {"write_artifact": True}
        if latest_analysis:
            payload["analysis"] = latest_analysis
        if latest_matrix:
            payload["matrix"] = latest_matrix
        if latest_draft:
            payload["draft_response"] = latest_draft
        if latest_answer:
            payload["answers"] = [latest_answer]
        if latest_export:
            payload["export_payload"] = latest_export["package"]
            payload["export_artifact_path"] = latest_export["artifact_path"]
            payload["export_json_artifact_path"] = latest_export["json_artifact_path"]
        if latest_fit:
            payload["customer_fit"] = latest_fit
        elif brief_profile_name != "None":
            payload["customer_profile_id"] = profile_names[brief_profile_name]
        if latest_review:
            payload["review_findings"] = latest_review["findings"]
            payload["review_passed"] = latest_review["passed"]
        if latest_plan:
            payload["action_plan"] = latest_plan["tasks"]
        if latest_handoff:
            payload["handoff_board"] = latest_handoff["board"]
            payload["handoff_artifact_path"] = latest_handoff["artifact_path"]
            payload["handoff_json_artifact_path"] = latest_handoff["json_artifact_path"]
        if latest_readiness:
            payload["readiness_scorecard"] = latest_readiness
        if latest_report:
            payload["executive_report"] = latest_report
        if latest_eval:
            payload["eval_metrics"] = latest_eval
        brief = post_json("/rfp/leadership-brief", payload)
        st.session_state.leadership_brief = brief
        st.success(f"Exported leadership brief: {brief['artifact_path']}")
        metrics = brief["brief"]["metrics"]
        cols = st.columns(4)
        cols[0].metric("Docs", metrics["docs_ingested"])
        cols[1].metric("Requirements", metrics["requirements"])
        cols[2].metric("Readiness", metrics["readiness_score"])
        cols[3].metric("Tasks", metrics["task_counts"]["total"])
        st.write("Next meeting agenda", brief["brief"]["recommended_next_meeting_agenda"])
        st.json(brief["brief"]["artifact_links"])
        st.download_button(
            "Download Leadership Brief Markdown",
            brief["markdown"],
            file_name="portfolio_leadership_brief.md",
        )

with tabs[17]:
    st.subheader("Submission Regression and Demo Script")
    st.caption("Run the deterministic local readiness gate and produce an interview-ready script artifact.")
    regression_top_k = st.slider("Regression top K", 1, 8, 4, key="regression_top_k")
    regression_profile = st.selectbox(
        "Regression customer profile",
        ["regulated_healthcare", "fintech", "public_sector"],
        key="regression_profile",
    )
    cols = st.columns(2)
    if cols[0].button("Run submission regression"):
        regression = post_json(
            "/rfp/submission-regression",
            {
                "top_k": regression_top_k,
                "customer_profile_id": regression_profile,
                "write_artifacts": True,
            },
        )
        st.session_state.submission_regression = regression
        st.metric("Regression", "PASS" if regression["passed"] else "FAIL")
        st.write(regression["interview_ready_summary"])
        if regression["warnings"]:
            st.warning("\n".join(regression["warnings"]))
        if regression["failed_checks"]:
            st.error(", ".join(regression["failed_checks"]))
        st.dataframe(
            [
                {
                    "check": check["name"],
                    "passed": check["passed"],
                    "evidence_count": check["evidence_count"],
                    **{
                        key: value
                        for key, value in check["details"].items()
                        if isinstance(value, (str, int, float, bool))
                    },
                }
                for check in regression["checks"]
            ],
            use_container_width=True,
        )
        st.json(regression["evidence_counts"])
        st.json(regression["artifact_paths"])

    latest_regression = st.session_state.get("submission_regression")
    if cols[1].button("Generate demo script", disabled=not bool(latest_regression)):
        script = post_json(
            "/rfp/demo-script",
            {
                "regression": latest_regression,
                "run_regression": False,
                "write_artifact": True,
            },
        )
        st.session_state.demo_script = script
        st.success(f"Generated demo script: {script['artifact_path']}")
        st.download_button(
            "Download Demo Script Markdown",
            script["markdown"],
            file_name="interview_demo_script.md",
        )
        st.json(script["script"]["sample_outputs_metrics"])

    if st.button("Generate script from fresh regression"):
        script = post_json(
            "/rfp/demo-script",
            {
                "run_regression": True,
                "regression_request": {
                    "top_k": regression_top_k,
                    "customer_profile_id": regression_profile,
                    "write_artifacts": True,
                },
                "write_artifact": True,
            },
        )
        st.session_state.demo_script = script
        st.success(f"Generated demo script: {script['artifact_path']}")
        st.write(script["script"]["interview_ready_summary"])
        st.download_button(
            "Download Fresh Demo Script Markdown",
            script["markdown"],
            file_name="interview_demo_script.md",
        )

with tabs[18]:
    st.subheader("Local Launch Checklist")
    st.caption("Verify local/mock readiness, inspect the API smoke matrix, and write interview-ready artifacts.")
    cols = st.columns(2)
    if cols[0].button("Load Smoke Matrix"):
        st.session_state.smoke_matrix = get_json("/ops/smoke-matrix")
    if cols[1].button("Generate Launch Checklist"):
        checklist = post_json("/ops/launch-checklist", {"write_artifact": True})
        st.session_state.launch_checklist = checklist
        st.session_state.smoke_matrix = checklist["smoke_matrix"]
        st.success(f"Launch checklist artifact: {checklist['artifact_path']}")

    smoke = st.session_state.get("smoke_matrix")
    if smoke:
        summary = smoke["readiness_summary"]
        status_cols = st.columns(4)
        status_cols[0].metric("Readiness", summary["readiness_level"])
        status_cols[1].metric("Endpoints", summary["total_endpoints"])
        status_cols[2].metric("Artifacts", summary["artifact_writing_endpoints"])
        status_cols[3].metric("Local Mock", "yes" if summary["local_mock_ready"] else "no")
        st.write("Recommended sequence", summary["recommended_sequence"])
        st.dataframe(
            [
                {
                    "endpoint": row["path"],
                    "method": row["method"],
                    "category": row["category"],
                    "expected": f"{row['expected_status']} - {row['expected_result']}",
                    "artifacts": ", ".join(row["required_artifact_expectations"]) or "None",
                    "auth": row["auth_notes"],
                }
                for row in smoke["rows"]
            ],
            use_container_width=True,
        )
        st.code("\n".join(summary["required_local_commands"]), language="bash")

    checklist = st.session_state.get("launch_checklist")
    if checklist:
        st.write("Artifact path", checklist["artifact_path"])
        st.write("JSON artifact path", checklist["json_artifact_path"])
        st.code("\n".join(checklist["checklist"]["install_run_commands"]), language="bash")
        st.write("Generated artifact paths", checklist["checklist"]["generated_artifact_paths"])
        st.download_button(
            "Download Launch Checklist Markdown",
            checklist["markdown"],
            file_name="local_launch_checklist.md",
        )


with tabs[19]:
    st.subheader("Portfolio Evidence and Interview Pack")
    st.caption(
        "Generate recruiter/interviewer proof that maps JD skills to implemented code, "
        "endpoints, tests, and artifacts."
    )
    cols = st.columns(2)
    if cols[0].button("Load Portfolio Evidence"):
        st.session_state.portfolio_evidence = get_json("/portfolio/evidence-index")
    if cols[1].button("Generate Interview Pack"):
        pack = post_json(
            "/portfolio/interview-pack",
            {
                "run_regression": True,
                "regression_request": {"top_k": 4, "write_artifacts": True},
                "write_artifact": True,
            },
        )
        st.session_state.portfolio_pack = pack
        st.session_state.portfolio_evidence = pack["evidence_index"]
        st.success(f"Interview Pack generated under portfolio_packs: {pack['artifact_path']}")

    evidence = st.session_state.get("portfolio_evidence")
    if evidence:
        metric_cols = st.columns(4)
        metric_cols[0].metric("Evidence score", evidence["evidence_score"])
        metric_cols[1].metric("Covered skills", evidence["covered_skill_count"])
        metric_cols[2].metric("Total skills", evidence["total_skill_count"])
        metric_cols[3].metric("Portfolio artifacts", "portfolio_packs")
        st.dataframe(
            [
                {
                    "skill": skill["jd_skill"],
                    "status": skill["coverage_status"],
                    "endpoints": ", ".join(skill["endpoints"]),
                    "tests/evals": ", ".join(skill["tests_evals"]),
                    "proof paths": ", ".join(skill["local_proof_paths"]),
                }
                for skill in evidence["skills"]
            ],
            use_container_width=True,
        )
        st.code("\n".join(evidence["proof_commands"]), language="bash")
        st.json(evidence["artifact_roots"])

    pack = st.session_state.get("portfolio_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Technical talking points")
        st.write(pack["pack"]["technical_talking_points"])
        st.write("3-minute demo script")
        st.dataframe(pack["pack"]["three_minute_demo_script"], use_container_width=True)
        st.write("Metrics and eval summary")
        st.json(pack["pack"]["metrics_eval_summary"])
        st.write("Resume / GitHub README bullets")
        st.write(pack["pack"]["resume_github_readme_bullets"])
        st.download_button(
            "Download Interview Pack Markdown",
            pack["markdown"],
            file_name="portfolio_interview_pack.md",
        )


with tabs[20]:
    st.subheader("Release Candidate Publish Pack")
    st.caption("Run the local GitHub publish gate and generate ignored Markdown/JSON artifacts for reviewer handoff.")
    cols = st.columns(2)
    if cols[0].button("Run Release Gate"):
        st.session_state.release_gate = get_json("/release/quality-gate")
    if cols[1].button("Generate Publish Pack"):
        publish_pack = post_json("/release/publish-pack", {"write_artifact": True})
        st.session_state.release_publish_pack = publish_pack
        st.session_state.release_gate = publish_pack["quality_gate"]
        st.success(f"Publish Pack generated: {publish_pack['artifact_path']}")

    gate = st.session_state.get("release_gate")
    if gate:
        metric_cols = st.columns(4)
        metric_cols[0].metric("Gate status", gate["status"])
        metric_cols[1].metric("Score", gate["score"])
        metric_cols[2].metric("Blockers", len(gate["blockers"]))
        metric_cols[3].metric("Warnings", len(gate["warnings"]))
        if gate["blockers"]:
            st.error("\n".join(gate["blockers"]))
        if gate["warnings"]:
            st.warning("\n".join(gate["warnings"]))
        st.write("Publish readiness")
        st.json(gate["publish_readiness"])
        st.write("Verification checklist")
        st.dataframe(gate["verification_checklist"], use_container_width=True)
        st.code(
            "\n".join(item["command"] for item in gate["verification_checklist"] if item.get("command")),
            language="bash",
        )
        st.write("Artifact coverage")
        st.json(gate["artifact_coverage"])

    pack = st.session_state.get("release_publish_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Release summary")
        st.json(pack["pack"]["release_summary"])
        st.write("Expected outputs")
        st.json(pack["pack"]["expected_outputs"])
        st.download_button(
            "Download Publish Pack Markdown",
            pack["markdown"],
            file_name="github_publish_pack.md",
        )


with tabs[21]:
    st.subheader("CI Doctor and Audit Pack")
    st.caption("Run the local CI/docs/tests/env/Docker/dependency and secret scan audit without external services.")
    cols = st.columns(2)
    if cols[0].button("Run CI Doctor"):
        st.session_state.ci_doctor = get_json("/ops/ci-doctor")
    if cols[1].button("Generate Audit Pack"):
        audit_pack = post_json("/ops/audit-pack", {"write_artifact": True})
        st.session_state.audit_pack = audit_pack
        st.session_state.ci_doctor = audit_pack["ci_doctor"]
        st.success(f"Audit Pack generated: {audit_pack['artifact_path']}")

    doctor = st.session_state.get("ci_doctor")
    if doctor:
        metric_cols = st.columns(4)
        metric_cols[0].metric("Doctor status", doctor["status"])
        metric_cols[1].metric("Score", doctor["score"])
        metric_cols[2].metric("Checks", doctor["summary"]["total_checks"])
        metric_cols[3].metric("Secret findings", doctor["secret_scan"]["finding_count"])
        st.dataframe(
            [
                {
                    "check": check["name"],
                    "category": check["category"],
                    "status": check["status"],
                    "command": check["command"] or "",
                    "missing": ", ".join(check["missing_paths"]),
                    "remediation": "; ".join(check["remediation"]),
                }
                for check in doctor["checks"]
            ],
            use_container_width=True,
        )
        st.write("Dependency inventory")
        st.json(doctor["dependency_inventory"])
        st.write("Secret scan summary")
        st.json(doctor["secret_scan"])
        st.code("\n".join(doctor["local_verification_commands"]), language="bash")

    audit_pack = st.session_state.get("audit_pack")
    if audit_pack:
        st.write("Generated artifact path", audit_pack["artifact_path"])
        st.write("Generated JSON path", audit_pack["json_artifact_path"])
        st.write("Publish-safety checklist")
        st.dataframe(audit_pack["pack"]["publish_safety_checklist"], use_container_width=True)
        st.write("Recruiter/interviewer explanation")
        st.write(audit_pack["pack"]["recruiter_interviewer_explanation"])
        st.download_button(
            "Download Audit Pack Markdown",
            audit_pack["markdown"],
            file_name="local_ci_audit_pack.md",
        )


with tabs[22]:
    st.subheader("Reviewer Quickstart")
    st.caption("Load the API-backed reviewer runbook and generate the recruiter/engineer Walkthrough Pack.")
    cols = st.columns(2)
    if cols[0].button("Load Reviewer Quickstart"):
        st.session_state.reviewer_quickstart = get_json("/reviewer/quickstart")
    if cols[1].button("Generate Walkthrough Pack"):
        pack = post_json("/reviewer/walkthrough-pack", {"write_artifact": True})
        st.session_state.reviewer_walkthrough_pack = pack
        st.session_state.reviewer_quickstart = pack["quickstart"]
        st.success(f"Walkthrough Pack generated under reviewer_packs: {pack['artifact_path']}")

    quickstart = st.session_state.get("reviewer_quickstart")
    if quickstart:
        metric_cols = st.columns(4)
        metric_cols[0].metric("Status", quickstart["status"])
        metric_cols[1].metric("Endpoints", len(quickstart["endpoint_walkthrough_order"]))
        metric_cols[2].metric("Artifacts", len(quickstart["artifact_proof_map"]))
        metric_cols[3].metric("Local Mock", "yes" if quickstart["local_mock_default"] else "no")
        st.write("One-command demo")
        st.code(quickstart["one_command_demo"], language="bash")
        st.write("Verification commands")
        st.code("\n".join(quickstart["verification_commands"]), language="bash")
        st.write("Proof tour")
        st.write(quickstart["proof_tour"])
        st.dataframe(
            [
                {
                    "endpoint": f"{row['method']} {row['path']}",
                    "goal": row["reviewer_goal"],
                    "auth": "X-API-Key" if row["requires_api_key"] else "public",
                }
                for row in quickstart["endpoint_walkthrough_order"]
            ],
            use_container_width=True,
        )
        st.write("Artifact proof map")
        st.json(quickstart["artifact_proof_map"])
        st.write("Role-specific reviewer notes")
        st.json(quickstart["role_specific_reviewer_notes"])

    pack = st.session_state.get("reviewer_walkthrough_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Recruiter-friendly story")
        st.write(pack["pack"]["recruiter_friendly_story"])
        st.write("Engineer deep-dive path")
        st.write(pack["pack"]["engineer_deep_dive_path"])
        st.write("API/RAG proof tour")
        st.write(pack["pack"]["api_rag_proof_tour"])
        st.download_button(
            "Download Walkthrough Pack Markdown",
            pack["markdown"],
            file_name="reviewer_walkthrough_pack.md",
        )


with tabs[23]:
    st.subheader("API Contract")
    st.caption("Verify the OpenAPI-derived API surface and generate a runnable Reviewer Collection Pack.")
    cols = st.columns(2)
    if cols[0].button("Load API Contract Audit"):
        st.session_state.api_contract_audit = get_json("/api/contract-audit")
    if cols[1].button("Generate Reviewer Collection"):
        collection = post_json("/api/reviewer-collection", {"write_artifact": True})
        st.session_state.reviewer_collection_pack = collection
        st.session_state.api_contract_audit = collection["contract_audit"]
        st.success(f"Reviewer Collection generated under api_contracts: {collection['artifact_path']}")

    audit = st.session_state.get("api_contract_audit")
    if audit:
        metric_cols = st.columns(4)
        metric_cols[0].metric("Status", audit["status"])
        metric_cols[1].metric("Score", audit["score"])
        metric_cols[2].metric("OpenAPI routes", audit["openapi_route_count"])
        metric_cols[3].metric("Auth protected", audit["auth_protected_endpoint_count"])
        st.write("Coverage checks")
        st.dataframe(
            [
                {
                    "check": audit["docs_api_coverage"]["name"],
                    "status": audit["docs_api_coverage"]["status"],
                    "coverage": f"{audit['docs_api_coverage']['passed']}/{audit['docs_api_coverage']['total']}",
                    "missing": ", ".join(audit["docs_api_coverage"]["missing_paths"]),
                },
                {
                    "check": audit["dashboard_smoke_alignment"]["name"],
                    "status": audit["dashboard_smoke_alignment"]["status"],
                    "coverage": (
                        f"{audit['dashboard_smoke_alignment']['passed']}/"
                        f"{audit['dashboard_smoke_alignment']['total']}"
                    ),
                    "missing": ", ".join(audit["dashboard_smoke_alignment"]["missing_paths"]),
                },
                {
                    "check": audit["generated_artifact_endpoint_coverage"]["name"],
                    "status": audit["generated_artifact_endpoint_coverage"]["status"],
                    "coverage": (
                        f"{audit['generated_artifact_endpoint_coverage']['passed']}/"
                        f"{audit['generated_artifact_endpoint_coverage']['total']}"
                    ),
                    "missing": ", ".join(audit["generated_artifact_endpoint_coverage"]["missing_paths"]),
                },
                {
                    "check": audit["rag_eval_red_team_endpoint_coverage"]["name"],
                    "status": audit["rag_eval_red_team_endpoint_coverage"]["status"],
                    "coverage": (
                        f"{audit['rag_eval_red_team_endpoint_coverage']['passed']}/"
                        f"{audit['rag_eval_red_team_endpoint_coverage']['total']}"
                    ),
                    "missing": ", ".join(audit["rag_eval_red_team_endpoint_coverage"]["missing_paths"]),
                },
            ],
            use_container_width=True,
        )
        st.write("Endpoint inventory")
        st.dataframe(
            [
                {
                    "domain": domain,
                    "method": endpoint["method"],
                    "path": endpoint["path"],
                    "auth": "X-API-Key" if endpoint["auth_required"] else "public",
                    "docs/api": endpoint["docs_api_covered"],
                    "dashboard": endpoint["dashboard_referenced"],
                    "artifacts": ", ".join(endpoint["artifact_expectations"]),
                }
                for domain, endpoints in audit["endpoint_inventory"].items()
                for endpoint in endpoints
            ],
            use_container_width=True,
        )
        if audit["missing_docs_warnings"]:
            st.warning("\n".join(audit["missing_docs_warnings"]))
        st.write("Limitations")
        st.write(audit["local_only_limitations"])

    collection = st.session_state.get("reviewer_collection_pack")
    if collection:
        st.write("Generated artifact path", collection["artifact_path"])
        st.write("Generated JSON path", collection["json_artifact_path"])
        st.write("Demo token flow")
        st.code("\n".join(collection["collection"]["demo_token_flow"]), language="powershell")
        st.write("RAG/eval/red-team verification order")
        st.write(collection["collection"]["rag_eval_red_team_verification_order"])
        st.write("Recruiter / engineer explanation")
        st.json(collection["collection"]["reviewer_explanation"])
        st.download_button(
            "Download Reviewer Collection Markdown",
            collection["markdown"],
            file_name="api_reviewer_collection.md",
        )


with tabs[24]:
    st.subheader("Artifact Inventory")
    st.caption("Inspect ignored generated artifact directories and write the README Badge/Checklist Pack.")
    cols = st.columns(2)
    if cols[0].button("Load Artifact Inventory"):
        st.session_state.artifact_inventory = get_json("/artifacts/inventory")
    if cols[1].button("Generate README Checklist"):
        checklist = post_json("/artifacts/readme-checklist", {"write_artifact": True})
        st.session_state.readme_checklist = checklist
        st.session_state.artifact_inventory = checklist["inventory"]
        st.success(f"README Checklist generated: {checklist['artifact_path']}")

    inventory = st.session_state.get("artifact_inventory")
    if inventory:
        metric_cols = st.columns(4)
        metric_cols[0].metric("Directories", inventory["total_directories"])
        metric_cols[1].metric("Files", inventory["total_files"])
        metric_cols[2].metric("Latest files", inventory["latest_artifact_count"])
        metric_cols[3].metric("Ignored", inventory["ignored_status"].replace("_", " "))
        st.dataframe(
            [
                {
                    "key": item["key"],
                    "files": item["file_count"],
                    "producer": item["producer_endpoint"],
                    "purpose": item["reviewer_purpose"],
                    "freshness": " ".join(item["freshness_notes"]),
                    "latest": ", ".join(file["name"] for file in item["latest_files"]),
                }
                for item in inventory["directories"]
            ],
            use_container_width=True,
        )
        st.write("Local commands")
        st.code("\n".join(inventory["local_commands"]), language="bash")
        st.write("Reviewer proof checklist")
        st.write(inventory["reviewer_proof_checklist"])

    checklist = st.session_state.get("readme_checklist")
    if checklist:
        st.write("Generated artifact path", checklist["artifact_path"])
        st.write("Generated JSON path", checklist["json_artifact_path"])
        st.write("README badge suggestions")
        st.dataframe(checklist["checklist"]["readme_badge_suggestions"], use_container_width=True)
        st.write("Cleanup and regeneration notes")
        st.write(checklist["checklist"]["cleanup_regeneration_notes"])
        st.download_button(
            "Download README Checklist Markdown",
            checklist["markdown"],
            file_name="readme_checklist.md",
        )


with tabs[25]:
    st.subheader("Dashboard Smoke and UI Verification")
    st.caption("Verify dashboard source wiring, expected tab labels, endpoint references, and reviewer artifacts.")
    cols = st.columns(2)
    if cols[0].button("Run Dashboard Smoke"):
        st.session_state.dashboard_smoke = get_json("/ui/dashboard-smoke")
    if cols[1].button("Generate UI Verification Pack"):
        pack = post_json("/ui/verification-pack", {"write_artifact": True})
        st.session_state.ui_verification_pack = pack
        st.session_state.dashboard_smoke = pack["dashboard_smoke"]
        st.success(f"UI Verification Pack generated: {pack['artifact_path']}")

    smoke = st.session_state.get("dashboard_smoke")
    if smoke:
        summary = smoke["summary"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Status", smoke["status"])
        metric_cols[1].metric("Views", f"{summary['views_present']}/{summary['view_count']}")
        metric_cols[2].metric("Endpoints", f"{summary['endpoints_referenced']}/{summary['endpoint_count']}")
        metric_cols[3].metric("Routes", f"{summary['routes_defined']}/{summary['endpoint_count']}")
        if summary["failed_checks"]:
            st.error(", ".join(summary["failed_checks"]))
        st.write("Checked views")
        st.dataframe(
            [
                {
                    "view": view["label"],
                    "status": view["status"],
                    "endpoints": ", ".join(view["endpoint_paths"]),
                    "artifact_root": view["artifact_root"] or "",
                }
                for view in smoke["expected_views"]
            ],
            use_container_width=True,
        )
        st.write("Checked endpoints")
        st.dataframe(smoke["endpoint_references"], use_container_width=True)
        st.write("Generated artifact tabs")
        st.dataframe(smoke["generated_artifact_tabs"], use_container_width=True)
        st.write("Local run commands")
        st.code("\n".join(smoke["local_run_commands"]), language="bash")
        st.write("Limitations")
        st.write(smoke["limitations"])

    pack = st.session_state.get("ui_verification_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Reviewer checklist")
        st.write(pack["pack"]["reviewer_checklist"])
        st.write("Screenshot placeholders")
        st.dataframe(pack["pack"]["screenshot_placeholders"], use_container_width=True)
        st.write("Troubleshooting")
        st.dataframe(pack["pack"]["troubleshooting"], use_container_width=True)
        st.download_button(
            "Download UI Verification Markdown",
            pack["markdown"],
            file_name="ui_verification_pack.md",
        )


with tabs[26]:
    st.subheader("Final Handoff")
    st.caption("Run the README Consistency final audit and generate the ignored Final Handoff Pack.")
    cols = st.columns(2)
    if cols[0].button("Run Final Audit"):
        st.session_state.final_audit = get_json("/handoff/final-audit")
    if cols[1].button("Generate Final Handoff Pack"):
        pack = post_json("/handoff/final-pack", {"write_artifact": True})
        st.session_state.final_handoff_pack = pack
        st.session_state.final_audit = pack["final_audit"]
        st.success(f"Final Handoff Pack generated: {pack['artifact_path']}")

    final_audit = st.session_state.get("final_audit")
    if final_audit:
        metric_cols = st.columns(4)
        metric_cols[0].metric("Final audit", final_audit["status"])
        metric_cols[1].metric("Score", final_audit["score"])
        metric_cols[2].metric("Checks", len(final_audit["checks"]))
        metric_cols[3].metric("Failed", final_audit["summary"]["failed_checks"])
        st.dataframe(
            [
                {
                    "check": check["name"],
                    "category": check["category"],
                    "status": check["status"],
                    "missing terms": ", ".join(check["missing_terms"]),
                    "missing paths": ", ".join(check["missing_paths"]),
                }
                for check in final_audit["checks"]
            ],
            use_container_width=True,
        )
        st.write("Endpoint inventory")
        st.json(final_audit["endpoint_inventory"])
        st.code("\n".join(final_audit["local_verification_commands"]), language="bash")

    pack = st.session_state.get("final_handoff_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Recruiter README blurb")
        st.write(pack["pack"]["recruiter_final_readme_blurb"])
        st.write("RAG/eval proof summary")
        st.json(pack["pack"]["rag_eval_proof_summary"])
        st.download_button(
            "Download Final Handoff Markdown",
            pack["markdown"],
            file_name="final_handoff_pack.md",
        )


with tabs[27]:
    st.subheader("Git Readiness")
    st.caption(
        "Run local-only GitHub Push Readiness and Branch Hygiene checks without staging, committing, pushing, "
        "or calling GitHub."
    )
    cols = st.columns(2)
    if cols[0].button("Load Git Readiness"):
        st.session_state.git_readiness = get_json("/git/readiness")
    if cols[1].button("Generate Branch Hygiene Pack"):
        pack = post_json("/git/push-plan", {"write_artifact": True})
        st.session_state.git_push_plan = pack
        st.session_state.git_readiness = pack["readiness"]
        st.success(f"GitHub Push Readiness Pack generated under git_packs: {pack['artifact_path']}")

    readiness = st.session_state.get("git_readiness")
    if readiness:
        summary = readiness["working_tree_summary"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Status", readiness["status"])
        metric_cols[1].metric("Branch", readiness["current_branch"] or "unknown")
        metric_cols[2].metric("Changed", summary["changed"])
        metric_cols[3].metric("Ignored", summary["ignored"])
        st.write("Dirty worktree guidance")
        st.write(readiness["dirty_worktree_guidance"])
        st.write("Changed file groups")
        st.json(readiness["changed_file_groups"])
        st.write("Generated artifact directories")
        st.dataframe(readiness["generated_artifact_directories"], use_container_width=True)
        if readiness["suspicious_large_generated_files"]:
            st.warning("Suspicious large/generated files need review before commit.")
            st.dataframe(readiness["suspicious_large_generated_files"], use_container_width=True)
        st.write("GitHub Actions")
        st.json(readiness["github_actions"])
        st.write("Recommended commit groups")
        st.dataframe(readiness["recommended_commit_groups"], use_container_width=True)
        st.code("\n".join(readiness["local_review_commands"]), language="bash")

    pack = st.session_state.get("git_push_plan")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Pre-push verification checklist")
        st.write(pack["pack"]["pre_push_verification_checklist"])
        st.write("Recruiter / GitHub README publish blurb")
        st.write(pack["pack"]["recruiter_github_readme_publish_blurb"])
        st.download_button(
            "Download Git Push Readiness Markdown",
            pack["markdown"],
            file_name="github_push_readiness_pack.md",
        )


with tabs[28]:
    st.subheader("Runtime Demo")
    st.caption("Check local FastAPI + Streamlit startup readiness and generate the Runtime Demo Server Pack.")
    cols = st.columns(2)
    if cols[0].button("Load Runtime Readiness"):
        st.session_state.runtime_demo_readiness = get_json("/runtime/demo-readiness")
    if cols[1].button("Generate Runtime Demo Pack"):
        pack = post_json("/runtime/demo-pack", {"write_artifact": True})
        st.session_state.runtime_demo_pack = pack
        st.session_state.runtime_demo_readiness = pack["readiness"]
        st.success(f"Runtime Demo Server Pack generated under runtime_packs: {pack['artifact_path']}")

    readiness = st.session_state.get("runtime_demo_readiness")
    if readiness:
        listening = sum(1 for check in readiness["process_port_checks"] if check["listening"])
        installed = sum(1 for check in readiness["dependency_checks"] if check["installed"])
        metric_cols = st.columns(4)
        metric_cols[0].metric("Status", readiness["status"])
        metric_cols[1].metric("Ports listening", listening)
        metric_cols[2].metric("Dependencies", f"{installed}/{len(readiness['dependency_checks'])}")
        metric_cols[3].metric("Provider", readiness["provider_mode"])
        st.write("Start commands")
        st.code("\n".join(readiness["local_run_commands"]), language="powershell")
        st.write("Stop commands")
        st.write(readiness["stop_commands"])
        st.write("Expected ports")
        st.dataframe(readiness["expected_ports"], use_container_width=True)
        st.write("Read-only port checks")
        st.dataframe(readiness["process_port_checks"], use_container_width=True)
        st.write("Environment requirements")
        st.dataframe(readiness["env_requirements"], use_container_width=True)
        st.write("Dependency checks")
        st.dataframe(readiness["dependency_checks"], use_container_width=True)
        st.write("Health and smoke URLs")
        st.dataframe(readiness["expected_health_urls"], use_container_width=True)
        st.write("RAG/eval/red-team commands")
        st.code("\n".join(readiness["rag_eval_red_team_commands"]), language="powershell")
        st.write("Demo flow order")
        st.write(readiness["demo_flow_order"])
        st.write("Screenshot checklist")
        st.dataframe(readiness["screenshot_checklist"], use_container_width=True)
        st.write("Troubleshooting")
        st.dataframe(readiness["troubleshooting"], use_container_width=True)
        st.write("Recruiter / engineer explanation")
        st.json(readiness["recruiter_engineer_explanation"])
        st.write("Known limitations")
        st.write(readiness["known_limitations"])

    pack = st.session_state.get("runtime_demo_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Health checks")
        st.dataframe(pack["pack"]["health_checks"], use_container_width=True)
        st.write("Screenshot placeholders")
        st.dataframe(pack["pack"]["screenshot_checklist_placeholders"], use_container_width=True)
        st.download_button(
            "Download Runtime Demo Markdown",
            pack["markdown"],
            file_name="runtime_demo_pack.md",
        )


with tabs[29]:
    st.subheader("RAG Corpus")
    st.caption("Inspect corpus coverage, eval coverage, red-team coverage, and generated RAG coverage artifacts.")
    cols = st.columns(2)
    if cols[0].button("Load Corpus Coverage"):
        st.session_state.rag_corpus_coverage = get_json("/rag/corpus-coverage")
    if cols[1].button("Generate Eval Coverage Pack"):
        pack = post_json("/rag/eval-coverage-pack", {"write_artifact": True})
        st.session_state.rag_eval_coverage_pack = pack
        st.session_state.rag_corpus_coverage = pack["coverage"]
        st.success(f"RAG coverage pack generated under rag_coverage: {pack['artifact_path']}")

    coverage = st.session_state.get("rag_corpus_coverage")
    if coverage:
        metric_cols = st.columns(4)
        metric_cols[0].metric("Status", coverage["status"])
        metric_cols[1].metric("Score", coverage["score"])
        metric_cols[2].metric("Docs", coverage["corpus_metadata"]["sample_document_count"])
        metric_cols[3].metric("Pack docs", coverage["corpus_metadata"]["required_enterprise_pack_doc_count"])
        st.write("Coverage checks")
        st.dataframe(
            [
                {
                    "check": coverage["doc_category_coverage"]["name"],
                    "status": coverage["doc_category_coverage"]["status"],
                    "coverage": coverage["doc_category_coverage"]["coverage"],
                    "missing": ", ".join(coverage["doc_category_coverage"]["missing"]),
                },
                {
                    "check": coverage["eval_coverage"]["name"],
                    "status": coverage["eval_coverage"]["status"],
                    "coverage": coverage["eval_coverage"]["coverage"],
                    "missing": ", ".join(coverage["eval_coverage"]["missing"]),
                },
                {
                    "check": coverage["citation_source_coverage"]["name"],
                    "status": coverage["citation_source_coverage"]["status"],
                    "coverage": coverage["citation_source_coverage"]["coverage"],
                    "missing": ", ".join(coverage["citation_source_coverage"]["missing"]),
                },
                {
                    "check": coverage["red_team_coverage"]["name"],
                    "status": coverage["red_team_coverage"]["status"],
                    "coverage": coverage["red_team_coverage"]["coverage"],
                    "missing": ", ".join(coverage["red_team_coverage"]["missing"]),
                },
                {
                    "check": coverage["missing_evidence_coverage"]["name"],
                    "status": coverage["missing_evidence_coverage"]["status"],
                    "coverage": coverage["missing_evidence_coverage"]["coverage"],
                    "missing": ", ".join(coverage["missing_evidence_coverage"]["missing"]),
                },
            ],
            use_container_width=True,
        )
        st.write("Corpus documents")
        st.dataframe(coverage["corpus_metadata"]["documents"], use_container_width=True)
        if coverage["gaps"]:
            st.warning("\n".join(coverage["gaps"]))
        if coverage["warnings"]:
            st.info("\n".join(coverage["warnings"]))
        st.write("Local commands")
        st.code("\n".join(coverage["local_commands"]), language="powershell")

    pack = st.session_state.get("rag_eval_coverage_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Reviewer summary")
        st.write(pack["pack"]["reviewer_summary"])
        st.download_button(
            "Download RAG Eval Coverage Markdown",
            pack["markdown"],
            file_name="rag_eval_coverage_pack.md",
        )


with tabs[30]:
    st.subheader("Compliance Evidence and Control Mapping")
    st.caption(
        "Map security, privacy, SLA, AI governance, DR, and residency asks to evidence, owners, gaps, "
        "and unsupported-claim flags."
    )
    cols = st.columns(2)
    if cols[0].button("Load Evidence Matrix"):
        st.session_state.compliance_evidence_matrix = get_json("/compliance/evidence-matrix")
    if cols[1].button("Generate Control Pack"):
        pack = post_json("/compliance/control-pack", {"write_artifact": True})
        st.session_state.compliance_control_pack = pack
        st.session_state.compliance_evidence_matrix = pack["matrix"]
        st.success(f"Control Mapping Pack generated under compliance_packs: {pack['artifact_path']}")

    matrix = st.session_state.get("compliance_evidence_matrix")
    if matrix:
        summary = matrix["coverage_summary"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Coverage", summary["coverage_ratio"])
        metric_cols[1].metric("Families", summary["control_family_count"])
        metric_cols[2].metric("Flags", summary["unsupported_claim_count"])
        metric_cols[3].metric("Warnings", summary["missing_evidence_warning_count"])
        st.write("Control coverage")
        st.dataframe(
            [
                {
                    "control": mapping["control_id"],
                    "family": mapping["control_family"],
                    "status": mapping["status"],
                    "confidence": mapping["confidence"],
                    "owner": mapping["owner"],
                    "requirements": len(mapping["requirement_links"]),
                    "sources": ", ".join(mapping["policy_sources"]),
                    "flags": "; ".join(mapping["unsupported_claim_flags"]),
                }
                for mapping in matrix["control_mappings"]
            ],
            use_container_width=True,
        )
        st.write("Source snippets")
        st.dataframe(
            [
                {
                    "control": mapping["control_id"],
                    "source": source["filename"],
                    "type": source["document_type"],
                    "score": source["score"],
                    "matched_terms": ", ".join(source["matched_terms"]),
                    "snippet": source["snippet"],
                }
                for mapping in matrix["control_mappings"]
                for source in mapping["source_docs"]
            ],
            use_container_width=True,
        )
        if matrix["unsupported_claims"]:
            st.warning("Unsupported claims need owner review before use.")
            st.dataframe(matrix["unsupported_claims"], use_container_width=True)
        st.write("Owner follow-ups")
        st.dataframe(matrix["owner_followups"], use_container_width=True)
        st.write("Local proof commands")
        st.code("\n".join(matrix["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(matrix["limitations"])

    pack = st.session_state.get("compliance_control_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Reviewer notes")
        st.write(pack["pack"]["reviewer_notes"])
        st.download_button(
            "Download Control Mapping Markdown",
            pack["markdown"],
            file_name="control_mapping_pack.md",
        )


with tabs[31]:
    st.subheader("Procurement Q&A Risk Simulator")
    st.caption(
        "Simulate procurement, security, legal, commercial, and implementation buyer questions; "
        "triage evidence support; and generate the Approval Workflow Pack."
    )
    cols = st.columns(2)
    if cols[0].button("Load Question Risk"):
        st.session_state.procurement_question_risk = get_json("/procurement/question-risk")
    if cols[1].button("Generate Approval Workflow Pack"):
        pack = post_json("/procurement/approval-pack", {"write_artifact": True})
        st.session_state.procurement_approval_pack = pack
        st.session_state.procurement_question_risk = pack["question_risk"]
        st.success(f"Approval Workflow Pack generated under procurement_packs: {pack['artifact_path']}")

    question_risk = st.session_state.get("procurement_question_risk")
    if question_risk:
        coverage = question_risk["coverage_summary"]
        approval = question_risk["approval_summary"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Questions", coverage["question_count"])
        metric_cols[1].metric("Coverage", coverage["coverage_ratio"])
        metric_cols[2].metric("Approvals", approval["approvals_required_count"])
        metric_cols[3].metric("Blocked", approval["blocked_count"])
        st.write("Question risk catalog")
        st.dataframe(
            [
                {
                    "type": item["question_type"],
                    "category": item["category"],
                    "risk": item["risk_level"],
                    "reviewer": item["required_reviewer_role"],
                    "status": item["approval_status"],
                    "evidence": item["evidence_support"],
                    "unsupported": item["unsupported_claim_flag"],
                    "citations": ", ".join(citation["filename"] for citation in item["citations"]),
                    "gaps": "; ".join(item["evidence_gaps"]),
                }
                for item in question_risk["questions"]
            ],
            use_container_width=True,
        )
        st.write("Coverage summary")
        st.json(coverage)
        st.write("Approval summary")
        st.json(approval)
        st.write("Citations and snippets")
        st.dataframe(
            [
                {
                    "question_id": item["question_id"],
                    "source": snippet["filename"],
                    "score": snippet["score"],
                    "snippet": snippet["snippet"],
                }
                for item in question_risk["questions"]
                for snippet in item["snippets"]
            ],
            use_container_width=True,
        )
        st.write("Local proof commands")
        st.code("\n".join(question_risk["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(question_risk["limitations"])

    pack = st.session_state.get("procurement_approval_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Reviewer checklist")
        st.write(pack["pack"]["reviewer_checklist"])
        st.write("Escalation owners")
        st.dataframe(pack["pack"]["escalation_owners"], use_container_width=True)
        st.write("Evidence gaps")
        st.dataframe(pack["pack"]["evidence_gaps"], use_container_width=True)
        st.download_button(
            "Download Approval Workflow Markdown",
            pack["markdown"],
            file_name="procurement_approval_workflow_pack.md",
        )


with tabs[32]:
    st.subheader("Bid/No-Bid Scenario Simulator + ROI Impact")
    st.caption(
        "Compare deterministic pursuit scenarios by deal value, effort, win probability, evidence readiness, "
        "timeline pressure, blockers, reviewers, and risk-adjusted ROI."
    )
    cols = st.columns(2)
    if cols[0].button("Load Scenario Analysis"):
        st.session_state.bid_scenario_analysis = get_json("/bid/scenario-analysis")
    if cols[1].button("Generate ROI Impact Pack"):
        pack = post_json("/bid/roi-pack", {"write_artifact": True})
        st.session_state.bid_roi_pack = pack
        st.session_state.bid_scenario_analysis = pack["scenario_analysis"]
        st.success(f"ROI Impact Pack generated under bid_packs: {pack['artifact_path']}")

    scenario_analysis = st.session_state.get("bid_scenario_analysis")
    if scenario_analysis:
        coverage = scenario_analysis["coverage_summary"]
        decisions = coverage["decision_counts"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Scenarios", coverage["scenario_count"])
        metric_cols[1].metric("Pursue", decisions.get("pursue", 0))
        metric_cols[2].metric("Conditional", decisions.get("pursue_with_conditions", 0))
        metric_cols[3].metric("No-bid", decisions.get("no_bid", 0))
        st.write("Scenario comparison")
        st.dataframe(
            [
                {
                    "scenario": scenario["name"],
                    "recommendation": scenario["decision_recommendation"],
                    "deal_value": scenario["deal_value"],
                    "effort_hours": scenario["pursuit_effort_hours"],
                    "win_probability": scenario["win_probability"],
                    "risk-adjusted ROI": scenario["risk_adjusted_roi"],
                    "evidence": scenario["evidence_readiness"]["coverage_status"],
                    "timeline": scenario["timeline_pressure"]["status"],
                    "blockers": len(scenario["blockers"]),
                    "reviewers": ", ".join(scenario["required_reviewers"]),
                }
                for scenario in scenario_analysis["scenarios"]
            ],
            use_container_width=True,
        )
        st.write("Coverage summary")
        st.json(coverage)
        st.write("Blockers")
        st.dataframe(
            [
                {
                    "scenario": scenario["scenario_id"],
                    "severity": blocker["severity"],
                    "owner": blocker["owner"],
                    "source": blocker["source"],
                    "blocker": blocker["blocker"],
                    "impact": blocker["impact"],
                }
                for scenario in scenario_analysis["scenarios"]
                for blocker in scenario["blockers"]
            ],
            use_container_width=True,
        )
        st.write("Proof commands")
        st.code("\n".join(scenario_analysis["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(scenario_analysis["limitations"])

    pack = st.session_state.get("bid_roi_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Executive decision memo")
        st.json(pack["pack"]["executive_decision_memo"])
        st.write("Follow-up owners")
        st.dataframe(pack["pack"]["follow_up_owners"], use_container_width=True)
        st.download_button(
            "Download ROI Impact Markdown",
            pack["markdown"],
            file_name="bid_roi_impact_pack.md",
        )


with tabs[33]:
    st.subheader("Competitive Objection Handling Pack")
    st.caption(
        "Generate cited objection responses for competitor, pricing, security, compliance, "
        "and implementation concerns; show confidence, reviewer status, workflow checkpoints, and local artifact proof."
    )
    competitor_context = st.text_area(
        "Objection competitor context",
        "Incumbent competitor may bundle workflow tooling and offer a 25% discount during procurement.",
        height=90,
    )
    objection_notes = st.text_area(
        "Custom objection notes",
        "Customer asks why they should not choose a cheaper bundled competitor.",
        height=90,
    )
    payload = {
        "competitor_context": [line.strip() for line in competitor_context.splitlines() if line.strip()],
        "objection_notes": [line.strip() for line in objection_notes.splitlines() if line.strip()],
        "top_k": 4,
    }
    if st.session_state.get("analysis"):
        payload["analysis"] = st.session_state.analysis
    if st.session_state.get("matrix"):
        payload["matrix"] = st.session_state.matrix
    if st.session_state.get("win_strategy"):
        payload["win_strategy"] = st.session_state.win_strategy

    cols = st.columns(2)
    if cols[0].button("Generate objection handling"):
        st.session_state.objection_handling = post_json("/rfp/objection-handling", payload)
    if cols[1].button("Export Objection Handling Pack"):
        pack_payload = {**payload, "write_artifact": True}
        if st.session_state.get("objection_handling"):
            pack_payload["objection_handling"] = st.session_state.objection_handling
        pack = post_json("/rfp/objection-handling-pack", pack_payload)
        st.session_state.objection_handling_pack = pack
        st.session_state.objection_handling = pack["objection_handling"]
        st.success(f"Objection Handling Pack generated under objection_packs: {pack['artifact_path']}")

    handling = st.session_state.get("objection_handling")
    if handling:
        coverage = handling["coverage_summary"]
        confidence = handling["confidence_summary"]
        workflow = handling.get("workflow_summary", {})
        metric_cols = st.columns(5)
        metric_cols[0].metric("Objections", coverage["objection_count"])
        metric_cols[1].metric("Coverage", coverage["coverage_ratio"])
        metric_cols[2].metric("Avg confidence", confidence["average_confidence"])
        metric_cols[3].metric("Blocked", coverage["blocked_count"])
        metric_cols[4].metric("Transitions", workflow.get("transition_count", 0))
        st.dataframe(
            [
                {
                    "concern": item["concern_type"],
                    "risk": item["risk_level"],
                    "confidence": item["confidence"],
                    "approval": item["approval_status"],
                    "route": item.get("route_decision"),
                    "checkpoint": item.get("checkpoint_key"),
                    "reviewer": item["required_reviewer_role"],
                    "citations": ", ".join(citation["filename"] for citation in item["citations"]),
                    "missing": "; ".join(item["missing_evidence"]),
                }
                for item in handling["objections"]
            ],
            use_container_width=True,
        )
        st.write("Workflow replay")
        st.dataframe(
            [
                {
                    "objection": transition["objection_id"],
                    "seq": transition["sequence"],
                    "from": transition["from_state"] or "START",
                    "to": transition["to_state"],
                    "decision": transition["decision"],
                    "status": transition["status"],
                    "owner": transition["owner_role"],
                    "checkpoint": transition["checkpoint_key"],
                }
                for item in handling["objections"]
                for transition in item.get("workflow_trace", [])
            ],
            use_container_width=True,
        )
        st.write("Eval assertions")
        st.dataframe(handling.get("eval_assertions", []), use_container_width=True)
        st.write("Endpoint references")
        st.dataframe(handling["endpoint_references"], use_container_width=True)
        st.write("Proof commands")
        st.code("\n".join(handling["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(handling["limitations"])

    pack = st.session_state.get("objection_handling_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Reviewer workflow")
        st.dataframe(pack["pack"]["reviewer_workflow"], use_container_width=True)
        st.write("Pack workflow transitions")
        st.dataframe(pack["pack"]["workflow_transitions"], use_container_width=True)
        st.write("Pack eval assertions")
        st.dataframe(pack["pack"]["eval_assertions"], use_container_width=True)
        st.download_button(
            "Download Objection Handling Markdown",
            pack["markdown"],
            file_name="competitive_objection_handling_pack.md",
        )


with tabs[34]:
    st.subheader("Win/Loss Learning Loop")
    st.caption(
        "Ingest fake post-RFP outcomes, learn winning evidence patterns and loss guardrails, "
        "then generate retrieval, eval, and response guidance updates."
    )
    fixture_path = st.text_input("Outcome fixture", "sample_data/rfp_outcomes.json")
    activation_mode = st.selectbox(
        "Policy activation mode",
        ["shadow_eval", "review_only", "limited_rollout"],
        key="win_loss_activation_mode",
    )
    payload = {"outcomes_fixture_path": fixture_path, "top_k_patterns": 6}
    if st.session_state.get("analysis"):
        payload["analysis"] = st.session_state.analysis
    if st.session_state.get("matrix"):
        payload["matrix"] = st.session_state.matrix
    if st.session_state.get("win_strategy"):
        payload["win_strategy"] = st.session_state.win_strategy

    cols = st.columns(6)
    if cols[0].button("Analyze win/loss outcomes"):
        st.session_state.win_loss_learning = post_json("/learning/win-loss", payload)
    if cols[1].button("Generate Strategy Pack"):
        pack_payload = {**payload, "write_artifact": True}
        if st.session_state.get("win_loss_learning"):
            pack_payload["learning_response"] = st.session_state.win_loss_learning
        pack = post_json("/learning/win-loss-pack", pack_payload)
        st.session_state.win_loss_pack = pack
        st.session_state.win_loss_learning = pack["learning_response"]
        st.success(f"Win/Loss Strategy Pack generated under win_loss_packs: {pack['artifact_path']}")
    if cols[2].button("Plan Policy Activation"):
        policy_payload = {**payload, "activation_mode": activation_mode}
        if st.session_state.get("win_loss_learning"):
            policy_payload["learning_response"] = st.session_state.win_loss_learning
        if st.session_state.get("retrieval_experiments"):
            policy_payload["retrieval_experiment"] = st.session_state.retrieval_experiments
        st.session_state.win_loss_policy = post_json("/learning/win-loss-policy", policy_payload)
    if cols[3].button("Generate Policy Pack"):
        policy_pack_payload = {**payload, "activation_mode": activation_mode, "write_artifact": True}
        if st.session_state.get("win_loss_policy"):
            policy_pack_payload["activation_plan"] = st.session_state.win_loss_policy
        elif st.session_state.get("win_loss_learning"):
            policy_pack_payload["learning_response"] = st.session_state.win_loss_learning
        if st.session_state.get("retrieval_experiments"):
            policy_pack_payload["retrieval_experiment"] = st.session_state.retrieval_experiments
        policy_pack = post_json("/learning/win-loss-policy-pack", policy_pack_payload)
        st.session_state.win_loss_policy_pack = policy_pack
        st.session_state.win_loss_policy = policy_pack["activation_plan"]
        st.success(f"Win/Loss Policy Pack generated under win_loss_policy: {policy_pack['artifact_path']}")

    learning = st.session_state.get("win_loss_learning")
    if learning:
        summary = learning["pattern_summary"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Outcomes", learning["outcome_count"])
        metric_cols[1].metric("Win rate", learning["win_rate"])
        metric_cols[2].metric("Win patterns", len(learning["winning_evidence_patterns"]))
        metric_cols[3].metric("Loss patterns", len(learning["losing_risk_patterns"]))
        st.write("Pattern summary")
        st.json(summary)
        st.write("Winning evidence patterns")
        st.dataframe(learning["winning_evidence_patterns"], use_container_width=True)
        st.write("Losing risk patterns")
        st.dataframe(learning["losing_risk_patterns"], use_container_width=True)
        st.write("Retrieval recommendations")
        st.dataframe(learning["retrieval_recommendations"], use_container_width=True)
        st.write("Eval recommendations")
        st.dataframe(learning["eval_recommendations"], use_container_width=True)
        st.write("Response guidance updates")
        st.dataframe(learning["response_guidance_updates"], use_container_width=True)
        st.write("Local proof commands")
        st.code("\n".join(learning["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(learning["limitations"])

    pack = st.session_state.get("win_loss_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Executive summary")
        st.json(pack["pack"]["executive_summary"])
        st.write("Owner action plan")
        st.dataframe(pack["pack"]["owner_action_plan"], use_container_width=True)
        st.download_button(
            "Download Win/Loss Strategy Markdown",
            pack["markdown"],
            file_name="win_loss_strategy_pack.md",
        )

    policy = st.session_state.get("win_loss_policy")
    if policy:
        st.write("Policy activation plan")
        metric_cols = st.columns(4)
        metric_cols[0].metric("Status", policy["status"])
        metric_cols[1].metric("Policy", policy["recommended_policy_id"])
        metric_cols[2].metric("Rules", len(policy["policy_rules"]))
        metric_cols[3].metric("Checkpoints", len(policy["checkpoints"]))
        st.json(policy["governance_summary"])
        st.write("Policy rules")
        st.dataframe(policy["policy_rules"], use_container_width=True)
        st.write("State transitions")
        st.dataframe(policy["state_transitions"], use_container_width=True)
        st.write("Checkpoints")
        st.dataframe(policy["checkpoints"], use_container_width=True)
        st.write("Owner review queue")
        st.dataframe(policy["owner_review_queue"], use_container_width=True)
        st.write("Rollback plan")
        st.json(policy["rollback_plan"])
        st.code("\n".join(policy["local_proof_commands"]), language="powershell")

    policy_pack = st.session_state.get("win_loss_policy_pack")
    if policy_pack:
        st.write("Policy pack artifact path", policy_pack["artifact_path"])
        st.write("Policy pack JSON path", policy_pack["json_artifact_path"])
        st.download_button(
            "Download Win/Loss Policy Markdown",
            policy_pack["markdown"],
            file_name="win_loss_policy_activation_pack.md",
        )


with tabs[35]:
    st.subheader("Reviewer Collaboration")
    st.caption(
        "Build local reviewer assignments, decision comments, approval status, and redline summary "
        "from the current RFP package signals."
    )
    collaboration_payload = {}
    if st.session_state.get("analysis"):
        collaboration_payload["analysis"] = st.session_state.analysis
    if st.session_state.get("matrix"):
        collaboration_payload["matrix"] = st.session_state.matrix
    if st.session_state.get("draft"):
        collaboration_payload["draft_response"] = st.session_state.draft
    if st.session_state.get("review_report"):
        collaboration_payload["review_findings"] = st.session_state.review_report["findings"]
        collaboration_payload["review_passed"] = st.session_state.review_report["passed"]
    if st.session_state.get("action_plan"):
        collaboration_payload["action_plan"] = st.session_state.action_plan["tasks"]
    if st.session_state.get("contract_risk"):
        collaboration_payload["contract_risk"] = st.session_state.contract_risk
    if st.session_state.get("submission_decision"):
        collaboration_payload["submission_decision"] = st.session_state.submission_decision

    cols = st.columns(4)
    if cols[0].button("Build collaboration board"):
        board = post_json("/rfp/reviewer-collaboration", collaboration_payload)
        st.session_state.reviewer_collaboration = board
    if cols[1].button("Export Collaboration Pack"):
        pack_payload = {**collaboration_payload, "write_artifact": True}
        if st.session_state.get("reviewer_collaboration"):
            pack_payload["collaboration"] = st.session_state.reviewer_collaboration
        pack = post_json("/rfp/reviewer-collaboration-pack", pack_payload)
        st.session_state.reviewer_collaboration_pack = pack
        st.session_state.reviewer_collaboration = pack["collaboration"]
        st.success(f"Reviewer Collaboration Pack generated under review_boards: {pack['artifact_path']}")
    if cols[2].button("Replay reviewer workflow"):
        workflow_payload = {**collaboration_payload}
        if st.session_state.get("reviewer_collaboration"):
            workflow_payload["collaboration"] = st.session_state.reviewer_collaboration
        workflow = post_json("/rfp/reviewer-workflow", workflow_payload)
        st.session_state.reviewer_workflow = workflow
    if cols[3].button("Export Workflow Pack"):
        workflow_pack_payload = {**collaboration_payload, "write_artifact": True}
        if st.session_state.get("reviewer_collaboration"):
            workflow_pack_payload["collaboration"] = st.session_state.reviewer_collaboration
        if st.session_state.get("reviewer_workflow"):
            workflow_pack_payload["workflow"] = st.session_state.reviewer_workflow
        pack = post_json("/rfp/reviewer-workflow-pack", workflow_pack_payload)
        st.session_state.reviewer_workflow_pack = pack
        st.session_state.reviewer_workflow = pack["workflow"]
        st.session_state.reviewer_collaboration = pack["collaboration"]
        st.success(f"Reviewer Workflow Pack generated under review_boards: {pack['artifact_path']}")
    if cols[4].button("Load signoff ledger"):
        ledger_payload = {**collaboration_payload}
        if st.session_state.get("reviewer_collaboration"):
            ledger_payload["collaboration"] = st.session_state.reviewer_collaboration
        if st.session_state.get("reviewer_workflow"):
            ledger_payload["workflow"] = st.session_state.reviewer_workflow
        ledger = post_json("/rfp/reviewer-signoff-ledger", ledger_payload)
        st.session_state.reviewer_signoff_ledger = ledger
    if cols[5].button("Export Signoff Pack"):
        signoff_pack_payload = {**collaboration_payload, "write_artifact": True}
        if st.session_state.get("reviewer_collaboration"):
            signoff_pack_payload["collaboration"] = st.session_state.reviewer_collaboration
        if st.session_state.get("reviewer_workflow"):
            signoff_pack_payload["workflow"] = st.session_state.reviewer_workflow
        if st.session_state.get("reviewer_signoff_ledger"):
            signoff_pack_payload["ledger"] = st.session_state.reviewer_signoff_ledger
        pack = post_json("/rfp/reviewer-signoff-pack", signoff_pack_payload)
        st.session_state.reviewer_signoff_pack = pack
        st.session_state.reviewer_signoff_ledger = pack["ledger"]
        st.session_state.reviewer_workflow = pack["workflow"]
        st.session_state.reviewer_collaboration = pack["collaboration"]
        st.success(f"Reviewer Signoff Pack generated under reviewer_signoffs: {pack['artifact_path']}")

    board = st.session_state.get("reviewer_collaboration")
    if board:
        summary = board["approval_summary"]
        redlines = board["redline_summary"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Board", board["board_status"])
        metric_cols[1].metric("Assignments", summary["assignment_count"])
        metric_cols[2].metric("Blocked", summary["blocked_count"])
        metric_cols[3].metric("Redlines", redlines["redline_count"])
        st.write("Assignments")
        st.dataframe(
            [
                {
                    "reviewer": item["reviewer_name"],
                    "role": item["reviewer_role"],
                    "priority": item["priority"],
                    "status": item["status"],
                    "approval": item["approval_status"],
                    "requirements": ", ".join(item["requirement_ids"]),
                    "blocking_items": "; ".join(item["blocking_items"]),
                }
                for item in board["assignments"]
            ],
            use_container_width=True,
        )
        st.write("Decision comments")
        st.dataframe(board["decision_comments"], use_container_width=True)
        st.write("Redline summary")
        st.json(redlines)
        st.write("Reviewer queue")
        st.dataframe(board["reviewer_queue"], use_container_width=True)
        st.write("Local proof commands")
        st.code("\n".join(board["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(board["limitations"])

    pack = st.session_state.get("reviewer_collaboration_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Reviewer Collaboration Markdown",
            pack["markdown"],
            file_name="reviewer_collaboration_pack.md",
        )

    workflow = st.session_state.get("reviewer_workflow")
    if workflow:
        st.write("Reviewer workflow replay")
        workflow_cols = st.columns(4)
        workflow_cols[0].metric("Workflow", workflow["workflow_status"])
        workflow_cols[1].metric("State", workflow["current_state"])
        workflow_cols[2].metric("Checkpoints", workflow["state_summary"]["checkpoint_count"])
        workflow_cols[3].metric("Blocked", workflow["state_summary"]["blocked_checkpoint_count"])
        st.dataframe(workflow["checkpoints"], use_container_width=True)
        st.write("Traceable transitions")
        st.dataframe(workflow["transitions"], use_container_width=True)
        st.write("Approval path")
        st.dataframe(workflow["approval_path"], use_container_width=True)
        st.write("Replay notes")
        st.write(workflow["replay_notes"])

    workflow_pack = st.session_state.get("reviewer_workflow_pack")
    if workflow_pack:
        st.write("Generated workflow artifact path", workflow_pack["artifact_path"])
        st.write("Generated workflow JSON path", workflow_pack["json_artifact_path"])
        st.download_button(
            "Download Reviewer Workflow Markdown",
            workflow_pack["markdown"],
            file_name="reviewer_workflow_pack.md",
        )

    signoff = st.session_state.get("reviewer_signoff_ledger")
    if signoff:
        st.write("Reviewer signoff ledger")
        signoff_cols = st.columns(4)
        signoff_cols[0].metric("Ledger", signoff["ledger_status"])
        signoff_cols[1].metric("Records", signoff["summary"]["record_count"])
        signoff_cols[2].metric("Blocked", signoff["summary"]["blocked_count"])
        signoff_cols[3].metric("Queue", len(signoff["human_review_queue"]))
        st.write("Signoff records")
        st.dataframe(signoff["records"], use_container_width=True)
        st.write("Governance gates")
        st.dataframe(signoff["governance_gates"], use_container_width=True)
        st.write("Human review queue")
        st.dataframe(signoff["human_review_queue"], use_container_width=True)
        st.write("Transition log")
        st.dataframe(signoff["transition_log"], use_container_width=True)
        st.write("Local proof commands")
        st.code("\n".join(signoff["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(signoff["limitations"])

    signoff_pack = st.session_state.get("reviewer_signoff_pack")
    if signoff_pack:
        st.write("Generated signoff artifact path", signoff_pack["artifact_path"])
        st.write("Generated signoff JSON path", signoff_pack["json_artifact_path"])
        st.download_button(
            "Download Reviewer Signoff Markdown",
            signoff_pack["markdown"],
            file_name="reviewer_signoff_ledger_pack.md",
        )


with tabs[36]:
    st.subheader("Evidence Freshness and Expiry Risk")
    st.caption(
        "Score source documents by age, renewal date, owner coverage, unsupported-claim language, and endpoint use."
    )
    cols = st.columns(2)
    if cols[0].button("Load Freshness Report"):
        st.session_state.evidence_freshness = get_json("/evidence/freshness")
    if cols[1].button("Generate Freshness Pack"):
        pack = post_json("/evidence/freshness-pack", {"write_artifact": True})
        st.session_state.evidence_freshness_pack = pack
        st.session_state.evidence_freshness = pack["freshness"]
        st.success(f"Evidence Freshness Pack generated under freshness_packs: {pack['artifact_path']}")

    freshness = st.session_state.get("evidence_freshness")
    if freshness:
        summary = freshness["summary"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Avg score", summary["average_freshness_score"])
        metric_cols[1].metric("Sources", summary["source_count"])
        metric_cols[2].metric("Expired", summary["expired_count"])
        metric_cols[3].metric("Flags", summary["unsupported_claim_count"])
        st.write("Source freshness matrix")
        st.dataframe(
            [
                {
                    "source": item["filename"],
                    "type": item["document_type"],
                    "owner": item["policy_owner"],
                    "renewal": item["renewal_date"],
                    "status": item["expiry_status"],
                    "score": item["freshness_score"],
                    "risk": item["risk_level"],
                    "drivers": "; ".join(item["risk_drivers"]),
                    "endpoints": ", ".join(item["endpoint_references"]),
                }
                for item in freshness["sources"]
            ],
            use_container_width=True,
        )
        st.write("Renewal calendar")
        st.dataframe(freshness["renewal_calendar"], use_container_width=True)
        if freshness["unsupported_claims"]:
            st.warning("Unsupported or absolute claims require owner review before reuse.")
            st.dataframe(freshness["unsupported_claims"], use_container_width=True)
        st.write("Owner follow-ups")
        st.dataframe(freshness["owner_followups"], use_container_width=True)
        st.write("Endpoint references")
        st.dataframe(freshness["endpoint_references"], use_container_width=True)
        st.write("Local proof commands")
        st.code("\n".join(freshness["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(freshness["limitations"])

    pack = st.session_state.get("evidence_freshness_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Evidence Freshness Markdown",
            pack["markdown"],
            file_name="evidence_freshness_pack.md",
        )


with tabs[37]:
    st.subheader("Evidence Conflict Resolver")
    st.caption(
        "Find source-precedence, scope, and ambiguity conflicts before draft claims move to customer review."
    )
    cols = st.columns(2)
    if cols[0].button("Load Conflict Report"):
        st.session_state.evidence_conflicts = get_json("/evidence/conflicts")
    if cols[1].button("Generate Conflict Pack"):
        pack = post_json("/evidence/conflict-pack", {"write_artifact": True})
        st.session_state.evidence_conflict_pack = pack
        st.session_state.evidence_conflicts = pack["conflicts"]
        st.success(f"Evidence Conflict Pack generated under conflict_packs: {pack['artifact_path']}")

    conflicts = st.session_state.get("evidence_conflicts")
    if conflicts:
        summary = conflicts["summary"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Conflicts", summary["conflict_count"])
        metric_cols[1].metric("Blocked", summary["blocking_conflict_count"])
        metric_cols[2].metric("Needs review", summary["needs_review_count"])
        metric_cols[3].metric("Claims", summary["claim_count"])
        st.write("Conflict matrix")
        st.dataframe(
            [
                {
                    "conflict": item["conflict_id"],
                    "topic": item["topic"],
                    "severity": item["severity"],
                    "status": item["status"],
                    "owner": item["reviewer_owner"],
                    "resolution": item["resolution_guidance"],
                    "sources": ", ".join(citation["filename"] for citation in item["citations"]),
                }
                for item in conflicts["conflicts"]
            ],
            use_container_width=True,
        )
        st.write("Reviewer queue")
        st.dataframe(conflicts["reviewer_queue"], use_container_width=True)
        st.write("Endpoint references")
        st.dataframe(conflicts["endpoint_references"], use_container_width=True)
        if conflicts["conflicts"]:
            selected_conflict = st.selectbox(
                "Inspect conflict",
                [item["conflict_id"] for item in conflicts["conflicts"]],
            )
            selected = next(item for item in conflicts["conflicts"] if item["conflict_id"] == selected_conflict)
            st.write("Cited resolution")
            st.write(selected["cited_resolution"])
            st.write("Primary claim")
            st.json(selected["primary_claim"])
            st.write("Related claims")
            st.dataframe(selected["conflicting_claims"], use_container_width=True)
        st.write("Local proof commands")
        st.code("\n".join(conflicts["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(conflicts["limitations"])

    pack = st.session_state.get("evidence_conflict_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Evidence Conflict Markdown",
            pack["markdown"],
            file_name="evidence_conflict_pack.md",
        )


with tabs[38]:
    st.subheader("Privacy Retention Guardrails")
    st.caption(
        "Map prompt, log, vector metadata, artifact, upload, and eval-data surfaces to local privacy evidence, "
        "retention posture, redaction rules, and owner actions."
    )
    cols = st.columns(2)
    if cols[0].button("Load Privacy Guardrails"):
        st.session_state.privacy_retention_guardrails = get_json("/privacy/retention-guardrails")
    if cols[1].button("Generate Privacy Retention Pack"):
        pack = post_json("/privacy/retention-pack", {"write_artifact": True})
        st.session_state.privacy_retention_pack = pack
        st.session_state.privacy_retention_guardrails = pack["guardrails"]
        st.success(f"Privacy Retention Pack generated under privacy_packs: {pack['artifact_path']}")

    guardrails = st.session_state.get("privacy_retention_guardrails")
    if guardrails:
        summary = guardrails["summary"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Surfaces", summary["surface_count"])
        metric_cols[1].metric("High risk", summary["high_risk_surface_count"])
        metric_cols[2].metric("Missing controls", summary["missing_control_count"])
        metric_cols[3].metric("Actions", summary["retention_action_count"])
        st.write("Surface matrix")
        st.dataframe(
            [
                {
                    "surface": item["surface_name"],
                    "risk": item["risk_level"],
                    "score": item["risk_score"],
                    "owner": item["reviewer_owner"],
                    "retention": item["retention_posture"],
                    "missing": "; ".join(item["missing_controls"]),
                    "endpoints": ", ".join(item["endpoint_references"]),
                }
                for item in guardrails["surfaces"]
            ],
            use_container_width=True,
        )
        st.write("Mapped policy evidence")
        st.dataframe(
            [
                {
                    "surface": item["surface_name"],
                    "source": source["filename"],
                    "score": source["score"],
                    "terms": ", ".join(source["matched_terms"]),
                    "snippet": source["snippet"],
                }
                for item in guardrails["surfaces"]
                for source in item["policy_evidence"]
            ],
            use_container_width=True,
        )
        st.write("Retention actions")
        st.dataframe(guardrails["retention_actions"], use_container_width=True)
        st.write("Prompt and logging guidance")
        st.write(guardrails["prompt_logging_guidance"])
        st.write("Local proof commands")
        st.code("\n".join(guardrails["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(guardrails["limitations"])

    pack = st.session_state.get("privacy_retention_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Privacy Retention Markdown",
            pack["markdown"],
            file_name="privacy_retention_pack.md",
        )


with tabs[39]:
    st.subheader("Submission Exceptions")
    st.caption(
        "Convert unresolved blockers, conditional exceptions, reviewer comments, and redlines into a local "
        "approval register with expiry and evidence requirements."
    )
    exception_payload = {}
    if st.session_state.get("submission_decision"):
        exception_payload["submission_decision"] = st.session_state.submission_decision
    if st.session_state.get("reviewer_collaboration"):
        exception_payload["reviewer_collaboration"] = st.session_state.reviewer_collaboration
    if st.session_state.get("analysis"):
        exception_payload["analysis"] = st.session_state.analysis
    if st.session_state.get("matrix"):
        exception_payload["matrix"] = st.session_state.matrix
    if st.session_state.get("draft"):
        exception_payload["draft_response"] = st.session_state.draft
    if st.session_state.get("review_report"):
        exception_payload["review_findings"] = st.session_state.review_report["findings"]
        exception_payload["review_passed"] = st.session_state.review_report["passed"]
    if st.session_state.get("action_plan"):
        exception_payload["action_plan"] = st.session_state.action_plan["tasks"]
    if st.session_state.get("contract_risk"):
        exception_payload["contract_risk"] = st.session_state.contract_risk
    if st.session_state.get("evidence_gaps"):
        exception_payload["evidence_gaps"] = st.session_state.evidence_gaps

    cols = st.columns(2)
    if cols[0].button("Build exception register"):
        register = post_json("/rfp/exception-register", exception_payload)
        st.session_state.exception_register = register
    if cols[1].button("Export Exception Pack"):
        pack_payload = {**exception_payload, "write_artifact": True}
        if st.session_state.get("exception_register"):
            pack_payload["exception_register"] = st.session_state.exception_register
        pack = post_json("/rfp/exception-pack", pack_payload)
        st.session_state.exception_pack = pack
        st.session_state.exception_register = pack["exception_register"]
        st.success(f"Submission Exception Pack generated under exception_registers: {pack['artifact_path']}")

    register = st.session_state.get("exception_register")
    if register:
        summary = register["summary"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Status", register["register_status"])
        metric_cols[1].metric("Exceptions", summary["exception_count"])
        metric_cols[2].metric("Requires approval", summary["requires_approval_count"])
        metric_cols[3].metric("Expiring soon", summary["expiring_soon_count"])
        st.write("Exception register")
        st.dataframe(
            [
                {
                    "id": item["exception_id"],
                    "source": item["source"],
                    "type": item["waiver_type"],
                    "severity": item["severity"],
                    "owner": item["owner"],
                    "approver": item["approver_role"],
                    "status": item["status"],
                    "expires": item["expires_at"],
                    "title": item["title"],
                }
                for item in register["exceptions"]
            ],
            use_container_width=True,
        )
        st.write("Approval queue")
        st.dataframe(register["approval_queue"], use_container_width=True)
        st.write("Endpoint references")
        st.dataframe(register["endpoint_references"], use_container_width=True)
        st.write("Local proof commands")
        st.code("\n".join(register["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(register["limitations"])

    pack = st.session_state.get("exception_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Exception Register Markdown",
            pack["markdown"],
            file_name="submission_exception_register.md",
        )


with tabs[40]:
    st.subheader("Citation Lineage")
    st.caption(
        "Audit answer and draft citations back to repository documents and chunks, then flag stale references, "
        "missing sources, weak citations, and generated claims needing approval."
    )
    cols = st.columns(2)
    if cols[0].button("Load Lineage Audit"):
        st.session_state.citation_lineage = get_json("/evidence/citation-lineage")
    if cols[1].button("Generate Lineage Pack"):
        pack = post_json("/evidence/citation-lineage-pack", {"write_artifact": True})
        st.session_state.citation_lineage_pack = pack
        st.session_state.citation_lineage = pack["lineage"]
        st.success(f"Citation Lineage Pack generated under citation_lineage: {pack['artifact_path']}")

    lineage = st.session_state.get("citation_lineage")
    if lineage:
        summary = lineage["summary"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Score", summary["integrity_score"])
        metric_cols[1].metric("Citations", summary["citation_count"])
        metric_cols[2].metric("Verified", summary["verified_count"])
        metric_cols[3].metric("Issues", summary["blocking_issue_count"])
        st.write("Citation lineage matrix")
        st.dataframe(
            [
                {
                    "id": item["citation_id"],
                    "source": item["source_kind"],
                    "file": item["filename"],
                    "owner": item["policy_owner"],
                    "status": item["integrity_status"],
                    "risk": item["risk_level"],
                    "score": item["score"],
                    "flags": "; ".join(item["risk_flags"]),
                    "endpoints": ", ".join(item["endpoint_references"]),
                }
                for item in lineage["lineages"]
            ],
            use_container_width=True,
        )
        if lineage["generated_claim_flags"]:
            st.warning("Generated claim flags require reviewer approval.")
            st.dataframe(lineage["generated_claim_flags"], use_container_width=True)
        st.write("Missing citations")
        st.dataframe(lineage["missing_citations"], use_container_width=True)
        st.write("Stale citations")
        st.dataframe(lineage["stale_citations"], use_container_width=True)
        st.write("Owner follow-ups")
        st.dataframe(lineage["owner_followups"], use_container_width=True)
        st.write("Endpoint references")
        st.dataframe(lineage["endpoint_references"], use_container_width=True)
        st.write("Local proof commands")
        st.code("\n".join(lineage["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(lineage["limitations"])

    pack = st.session_state.get("citation_lineage_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Citation Lineage Markdown",
            pack["markdown"],
            file_name="citation_lineage_pack.md",
        )


with tabs[41]:
    st.subheader("Cost Governance")
    st.caption(
        "Forecast local RFP workflow token/cost exposure, verify provider readiness, and write reviewer proof "
        "for mock, OpenAI, or Azure OpenAI modes."
    )
    cols = st.columns(6)
    daily_rfps = cols[0].number_input("Daily RFPs", min_value=0, max_value=100, value=3)
    questions_per_rfp = cols[1].number_input("Questions/RFP", min_value=0, max_value=200, value=12)
    draft_sections = cols[2].number_input("Draft sections", min_value=0, max_value=50, value=5)
    eval_runs = cols[3].number_input("Eval runs", min_value=0, max_value=20, value=1)
    red_team_runs = cols[4].number_input("Red-team runs", min_value=0, max_value=20, value=1)
    daily_budget = cols[5].number_input("Daily budget", min_value=0.0, max_value=10000.0, value=25.0)
    governance_payload = {
        "daily_rfp_count": int(daily_rfps),
        "questions_per_rfp": int(questions_per_rfp),
        "draft_sections_per_rfp": int(draft_sections),
        "eval_runs_per_day": int(eval_runs),
        "red_team_runs_per_day": int(red_team_runs),
        "daily_budget_usd": float(daily_budget),
    }
    action_cols = st.columns(2)
    if action_cols[0].button("Analyze cost governance"):
        st.session_state.cost_governance = post_json("/ops/cost-governance", governance_payload)
    if action_cols[1].button("Generate Cost Governance Pack"):
        pack = post_json("/ops/cost-governance-pack", {**governance_payload, "write_artifact": True})
        st.session_state.cost_governance_pack = pack
        st.session_state.cost_governance = pack["governance"]
        st.success(f"Cost Governance Pack generated under cost_governance: {pack['artifact_path']}")

    governance = st.session_state.get("cost_governance")
    if governance:
        budget = governance["budget_summary"]
        provider = governance["provider_readiness"]
        metric_cols = st.columns(4)
        metric_cols[0].metric("Status", governance["governance_status"])
        metric_cols[1].metric("Provider", provider["provider_mode"])
        metric_cols[2].metric("Daily cost", budget["daily_estimated_cost"])
        metric_cols[3].metric("Budget use", budget["budget_utilization"])
        st.write("Provider readiness")
        st.json(provider)
        st.write("Workflow estimates")
        st.dataframe(governance["workflow_estimates"], use_container_width=True)
        st.write("Reviewer controls")
        st.dataframe(governance["reviewer_controls"], use_container_width=True)
        st.write("Local proof commands")
        st.code("\n".join(governance["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(governance["limitations"])

    pack = st.session_state.get("cost_governance_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Cost Governance Markdown",
            pack["markdown"],
            file_name="cost_governance_pack.md",
        )


with tabs[42]:
    st.subheader("Source Trust Gate")
    st.caption(
        "Consolidate freshness, conflict, and citation-lineage signals into source-level retrieval policies "
        "and reviewer approval queues."
    )
    action_cols = st.columns(2)
    if action_cols[0].button("Analyze source trust"):
        st.session_state.source_trust = get_json("/evidence/source-trust")
    if action_cols[1].button("Generate Source Trust Pack"):
        pack = post_json("/evidence/source-trust-pack", {"write_artifact": True})
        st.session_state.source_trust_pack = pack
        st.session_state.source_trust = pack["source_trust"]
        st.success(f"Source Trust Pack generated under source_trust: {pack['artifact_path']}")

    trust = st.session_state.get("source_trust")
    if trust:
        summary = trust["summary"]
        metric_cols = st.columns(5)
        metric_cols[0].metric("Status", trust["status"])
        metric_cols[1].metric("Avg trust", summary["average_trust_score"])
        metric_cols[2].metric("Approved", summary["approved_count"])
        metric_cols[3].metric("Needs approval", summary["approval_required_count"])
        metric_cols[4].metric("Blocked", summary["blocked_count"])
        st.write("Source trust matrix")
        st.dataframe(trust["sources"], use_container_width=True)
        st.write("Reviewer queue")
        st.dataframe(trust["reviewer_queue"], use_container_width=True)
        st.write("Retrieval policy updates")
        st.dataframe(trust["retrieval_policy_updates"], use_container_width=True)
        st.write("Endpoint references")
        st.dataframe(trust["endpoint_references"], use_container_width=True)
        st.write("Local proof commands")
        st.code("\n".join(trust["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(trust["limitations"])

    pack = st.session_state.get("source_trust_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Source Trust Markdown",
            pack["markdown"],
            file_name="source_trust_gate.md",
        )


with tabs[43]:
    st.subheader("Model Risk Register")
    st.caption("Review local model/provider risks, release gates, evidence, and governance owner queue.")
    action_cols = st.columns(2)
    if action_cols[0].button("Analyze model risk"):
        st.session_state.model_risk_register = get_json("/governance/model-risk-register")
    if action_cols[1].button("Generate Model Risk Pack"):
        pack = post_json("/governance/model-risk-pack", {"write_artifact": True})
        st.session_state.model_risk_pack = pack
        st.session_state.model_risk_register = pack["register"]
        st.success(f"Model Risk Pack generated under model_risk: {pack['artifact_path']}")

    register = st.session_state.get("model_risk_register")
    if register:
        summary = register["summary"]
        metric_cols = st.columns(5)
        metric_cols[0].metric("Status", register["register_status"])
        metric_cols[1].metric("Risks", summary["risk_count"])
        metric_cols[2].metric("High/Critical", summary["high_or_critical_count"])
        metric_cols[3].metric("Needs review", summary["needs_review_count"])
        metric_cols[4].metric("Provider", register["provider_mode"])
        st.write("Risk register")
        st.dataframe(register["risks"], use_container_width=True)
        st.write("Release gates")
        st.dataframe(register["release_gates"], use_container_width=True)
        st.write("Reviewer queue")
        st.dataframe(register["reviewer_queue"], use_container_width=True)
        st.write("Local proof commands")
        st.code("\n".join(register["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(register["limitations"])

    pack = st.session_state.get("model_risk_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Model Risk Markdown",
            pack["markdown"],
            file_name="model_risk_register.md",
        )


with tabs[44]:
    st.subheader("Procurement Risk Desk")
    st.caption(
        "Detect packet-level legal, pricing, data residency, insurance, and implementation risks; "
        "route owners; and generate the Risk Desk Pack."
    )
    action_cols = st.columns(2)
    if action_cols[0].button("Load Risk Desk"):
        st.session_state.procurement_risk_desk = get_json("/procurement/risk-desk")
    if action_cols[1].button("Generate Risk Desk Pack"):
        pack = post_json("/procurement/risk-desk-pack", {"write_artifact": True})
        st.session_state.procurement_risk_desk_pack = pack
        st.session_state.procurement_risk_desk = pack["risk_desk"]
        st.success(f"Risk Desk Pack generated under procurement_risk_desk: {pack['artifact_path']}")

    desk = st.session_state.get("procurement_risk_desk")
    if desk:
        summary = desk["summary"]
        metric_cols = st.columns(5)
        metric_cols[0].metric("Risks", summary["risk_count"])
        metric_cols[1].metric("Critical", summary["critical_count"])
        metric_cols[2].metric("High", summary["high_count"])
        metric_cols[3].metric("Blocked", summary["blocked_count"])
        metric_cols[4].metric("Avg score", summary["average_risk_score"])
        st.write("Risk desk")
        st.dataframe(
            [
                {
                    "category": item["category"],
                    "severity": item["severity"],
                    "score": item["risk_score"],
                    "status": item["status"],
                    "owner": item["owner_role"],
                    "reviewer": item["reviewer_role"],
                    "due": item["due_hint"],
                    "signals": len(item["source_signals"]),
                    "gaps": len(item["evidence_gaps"]),
                    "citations": ", ".join(citation["filename"] for citation in item["citations"]),
                }
                for item in desk["risks"]
            ],
            use_container_width=True,
        )
        st.write("Owner routing")
        st.dataframe(desk["owner_routing"], use_container_width=True)
        st.write("Governance summary")
        st.json(desk.get("governance_summary", {}))
        st.write("Durable workflow gates")
        st.dataframe(desk.get("workflow_stages", []), use_container_width=True)
        st.write("Human review queue")
        st.dataframe(desk.get("human_review_queue", []), use_container_width=True)
        st.write("Trace analysis")
        st.dataframe(desk.get("trace_spans", []), use_container_width=True)
        st.write("Evidence snippets")
        st.dataframe(
            [
                {
                    "risk_id": item["risk_id"],
                    "source": snippet["filename"],
                    "score": snippet["score"],
                    "snippet": snippet["snippet"],
                }
                for item in desk["risks"]
                for snippet in item["snippets"]
            ],
            use_container_width=True,
        )
        st.write("Proof commands")
        st.code("\n".join(desk["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(desk["limitations"])

    pack = st.session_state.get("procurement_risk_desk_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Executive notes")
        st.write(pack["pack"]["executive_notes"])
        st.download_button(
            "Download Risk Desk Markdown",
            pack["markdown"],
            file_name="procurement_risk_desk_pack.md",
        )


with tabs[45]:
    st.subheader("Answer Reuse Library")
    st.caption(
        "Review accepted response snippets as governed reusable language with owners, expiry, reuse decisions, "
        "and citation lineage."
    )
    profiles = get_json("/customers/profiles")["profiles"]
    profile_names = {profile["name"]: profile["id"] for profile in profiles}
    action_cols = st.columns(2)
    reuse_category = st.selectbox(
        "Category",
        ["Any", "security", "compliance", "implementation", "pricing"],
        key="answer_reuse_category",
    )
    reuse_profile_name = st.selectbox(
        "Customer profile",
        ["Any"] + list(profile_names),
        key="answer_reuse_profile",
    )
    include_expired = st.checkbox("Include expired snippets", value=True)
    payload = {"include_expired": include_expired}
    if reuse_category != "Any":
        payload["category"] = reuse_category
    if reuse_profile_name != "Any":
        payload["customer_profile_id"] = profile_names[reuse_profile_name]
    if action_cols[0].button("Load reuse library"):
        st.session_state.answer_reuse_library = post_json("/rfp/answer-reuse-library", payload)
    if action_cols[1].button("Generate Reuse Library Pack"):
        pack = post_json("/rfp/answer-reuse-library-pack", {**payload, "write_artifact": True})
        st.session_state.answer_reuse_library_pack = pack
        st.session_state.answer_reuse_library = pack["library"]
        st.success(f"Answer Reuse Library Pack generated under answer_reuse_library: {pack['artifact_path']}")

    st.subheader("Answer Reuse Drift")
    st.caption("Check reusable snippets against cited sources before broad customer-facing reuse.")
    drift_cols = st.columns(2)
    min_source_overlap = st.slider("Minimum source overlap", 1, 10, 4, key="answer_reuse_drift_overlap")
    drift_payload = {**payload, "min_source_overlap": min_source_overlap}
    if drift_cols[0].button("Load reuse drift"):
        st.session_state.answer_reuse_drift = post_json("/rfp/answer-reuse-drift", drift_payload)
    if drift_cols[1].button("Generate Reuse Drift Pack"):
        pack = post_json("/rfp/answer-reuse-drift-pack", {**drift_payload, "write_artifact": True})
        st.session_state.answer_reuse_drift_pack = pack
        st.session_state.answer_reuse_drift = pack["drift_report"]
        st.success(f"Answer Reuse Drift Pack generated under answer_reuse_drift: {pack['artifact_path']}")

    drift = st.session_state.get("answer_reuse_drift")
    if drift:
        summary = drift["summary"]
        drift_metric_cols = st.columns(5)
        drift_metric_cols[0].metric("Status", drift["status"])
        drift_metric_cols[1].metric("Checked", summary["snippet_count"])
        drift_metric_cols[2].metric("Average score", summary["average_drift_score"])
        drift_metric_cols[3].metric("Owner review", summary["owner_review_count"])
        drift_metric_cols[4].metric("Rewrite", summary["rewrite_count"])
        st.write("Drift findings")
        st.dataframe(
            [
                {
                    "id": item["snippet_id"],
                    "title": item["title"],
                    "owner": item["owner"],
                    "status": item["drift_status"],
                    "score": item["drift_score"],
                    "citation": item["citation_status"],
                    "missing_terms": ", ".join(item["missing_terms"]),
                    "stale_claim_terms": ", ".join(item["stale_claim_terms"]),
                }
                for item in drift["findings"]
            ],
            use_container_width=True,
        )
        st.write("Drift owner queue")
        st.dataframe(drift["owner_queue"], use_container_width=True)
        st.write("Workflow")
        st.json(drift["workflow"])

    library = st.session_state.get("answer_reuse_library")
    if library:
        summary = library["summary"]
        metric_cols = st.columns(5)
        metric_cols[0].metric("Status", library["status"])
        metric_cols[1].metric("Snippets", summary["snippet_count"])
        metric_cols[2].metric("Approved", summary["approved_count"])
        metric_cols[3].metric("Review", summary["review_required_count"])
        metric_cols[4].metric("Lineage issues", summary["lineage_issue_count"])
        st.write("Governed snippets")
        st.dataframe(
            [
                {
                    "id": item["snippet_id"],
                    "title": item["title"],
                    "category": item["category"],
                    "owner": item["owner"],
                    "expiry": item["expires_at"],
                    "status": item["expiry_status"],
                    "decision": item["reuse_decision"],
                    "confidence": item["confidence"],
                    "citations": ", ".join(item["citation_refs"]),
                }
                for item in library["snippets"]
            ],
            use_container_width=True,
        )
        st.write("Owner queue")
        st.dataframe(library["owner_queue"], use_container_width=True)
        st.write("Citation lineage")
        st.dataframe(
            [
                {
                    "snippet_id": item["snippet_id"],
                    "source": lineage["filename"],
                    "status": lineage["lineage_status"],
                    "risk": lineage["risk_level"],
                    "overlap": lineage["evidence_overlap"],
                    "citation": lineage["citation_ref"],
                }
                for item in library["snippets"]
                for lineage in item["citation_lineage"]
            ],
            use_container_width=True,
        )
        st.write("Proof commands")
        st.code("\n".join(library["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(library["limitations"])

    pack = st.session_state.get("answer_reuse_library_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Answer Reuse Library Markdown",
            pack["markdown"],
            file_name="answer_reuse_library_pack.md",
        )

    drift_pack = st.session_state.get("answer_reuse_drift_pack")
    if drift_pack:
        st.write("Generated drift artifact path", drift_pack["artifact_path"])
        st.write("Generated drift JSON path", drift_pack["json_artifact_path"])
        st.download_button(
            "Download Answer Reuse Drift Markdown",
            drift_pack["markdown"],
            file_name="answer_reuse_drift_pack.md",
        )


with tabs[46]:
    st.subheader("Buyer Intelligence Pack")
    st.caption(
        "Compose durable proposal workflow checkpoints, human approvals, governance gates, provider routes, "
        "shared state, local trace analysis, and replayable transition audits for buyer-grade RFP review."
    )
    action_cols = st.columns(6)
    if action_cols[0].button("Load buyer workflow"):
        st.session_state.buyer_intelligence = get_json("/proposal/buyer-intelligence")
    if action_cols[1].button("Generate Buyer Intelligence Pack"):
        pack = post_json("/proposal/buyer-intelligence-pack", {"write_artifact": True})
        st.session_state.buyer_intelligence_pack = pack
        st.session_state.buyer_intelligence = pack["workflow"]
        st.success(f"Buyer Intelligence Pack generated under buyer_intelligence: {pack['artifact_path']}")
    if action_cols[2].button("Load workflow replay"):
        st.session_state.buyer_workflow_replay = get_json("/proposal/buyer-intelligence-replay")
    if action_cols[3].button("Generate Replay Pack"):
        pack = post_json("/proposal/buyer-intelligence-replay-pack", {"write_artifact": True})
        st.session_state.buyer_workflow_replay_pack = pack
        st.session_state.buyer_workflow_replay = pack["replay"]
        st.success(f"Buyer Workflow Replay Pack generated under buyer_intelligence: {pack['artifact_path']}")
    if action_cols[4].button("Audit contracts"):
        st.session_state.buyer_structured_contracts = get_json("/proposal/buyer-contracts")
    if action_cols[5].button("Generate Contract Pack"):
        pack = post_json("/proposal/buyer-contracts-pack", {"write_artifact": True})
        st.session_state.buyer_structured_contracts_pack = pack
        st.session_state.buyer_structured_contracts = pack["contract_audit"]
        st.success(f"Buyer Structured Contract Pack generated under buyer_contracts: {pack['artifact_path']}")

    workflow = st.session_state.get("buyer_intelligence")
    if workflow:
        readout = workflow["buyer_readout"]
        metric_cols = st.columns(5)
        metric_cols[0].metric("Status", workflow["workflow_status"])
        metric_cols[1].metric("Stages", len(workflow["workflow_stages"]))
        metric_cols[2].metric("Approvals", len(workflow["human_approval_queue"]))
        metric_cols[3].metric("Gates", len(workflow["governance_gates"]))
        metric_cols[4].metric("Posture", readout["recommended_posture"])
        st.write("Durable workflow stages")
        st.dataframe(
            [
                {
                    "sequence": item["sequence"],
                    "stage": item["name"],
                    "owner": item["owner_role"],
                    "status": item["status"],
                    "durability_key": item["durability_key"],
                    "gates": ", ".join(item["governance_gates"]),
                }
                for item in workflow["workflow_stages"]
            ],
            use_container_width=True,
        )
        st.write("Human approval queue")
        st.dataframe(workflow["human_approval_queue"], use_container_width=True)
        st.write("Governance gates")
        st.dataframe(workflow["governance_gates"], use_container_width=True)
        st.write("Provider routes")
        st.dataframe(workflow["provider_routes"], use_container_width=True)
        st.write("Trace analysis")
        st.json(workflow["trace_analysis"])
        st.write("Local proof commands")
        st.code("\n".join(workflow["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(workflow["limitations"])

    replay = st.session_state.get("buyer_workflow_replay")
    if replay:
        replay_cols = st.columns(4)
        replay_cols[0].metric("Replay", replay["status"])
        replay_cols[1].metric("Transitions", replay["transition_count"])
        replay_cols[2].metric("Checkpoint", replay["checkpoint_validation"]["status"])
        replay_cols[3].metric("Eval scenarios", len(replay["eval_scenarios"]))
        st.write("Transition replay")
        st.dataframe(
            [
                {
                    "order": item["replay_order"],
                    "from": item["from_stage_id"] or "START",
                    "to": item["to_stage_id"],
                    "decision": item["decision"],
                    "status": item["status"],
                    "checkpoint": item["checkpoint_key"],
                }
                for item in replay["transitions"]
            ],
            use_container_width=True,
        )
        st.write("Route decisions")
        st.dataframe(replay["route_decisions"], use_container_width=True)
        st.write("Checkpoint validation")
        st.json(replay["checkpoint_validation"])
        st.write("Eval scenarios")
        st.dataframe(replay["eval_scenarios"], use_container_width=True)
        st.write("Replay proof commands")
        st.code("\n".join(replay["local_proof_commands"]), language="powershell")

    contracts = st.session_state.get("buyer_structured_contracts")
    if contracts:
        contract_cols = st.columns(5)
        contract_cols[0].metric("Contract status", contracts["status"])
        contract_cols[1].metric("Score", contracts["score"])
        contract_cols[2].metric("Checks", len(contracts["checks"]))
        contract_cols[3].metric("Role contracts", len(contracts["role_contracts"]))
        contract_cols[4].metric("Schemas", len(contracts["output_contracts"]))
        st.write("Output contracts")
        st.dataframe(contracts["output_contracts"], use_container_width=True)
        st.write("Role coverage")
        st.dataframe(contracts["role_contracts"], use_container_width=True)
        st.write("Contract checks")
        st.dataframe(contracts["checks"], use_container_width=True)
        st.write("Eval assertions")
        st.dataframe(contracts["eval_assertions"], use_container_width=True)
        st.write("Injected dependencies")
        st.json(contracts["injected_dependencies"])
        st.write("Contract proof commands")
        st.code("\n".join(contracts["local_proof_commands"]), language="powershell")

    pack = st.session_state.get("buyer_intelligence_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Durable state path", pack["state_artifact_path"])
        st.download_button(
            "Download Buyer Intelligence Markdown",
            pack["markdown"],
            file_name="buyer_intelligence_pack.md",
        )

    replay_pack = st.session_state.get("buyer_workflow_replay_pack")
    if replay_pack:
        st.write("Replay artifact path", replay_pack["artifact_path"])
        st.write("Replay JSON path", replay_pack["json_artifact_path"])
        st.download_button(
            "Download Buyer Workflow Replay Markdown",
            replay_pack["markdown"],
            file_name="buyer_workflow_replay_pack.md",
        )

    contract_pack = st.session_state.get("buyer_structured_contracts_pack")
    if contract_pack:
        st.write("Contract artifact path", contract_pack["artifact_path"])
        st.write("Contract JSON path", contract_pack["json_artifact_path"])
        st.download_button(
            "Download Buyer Structured Contract Markdown",
            contract_pack["markdown"],
            file_name="buyer_structured_contract_pack.md",
        )


with tabs[47]:
    st.subheader("Agent Council")
    st.caption(
        "Review a deterministic multi-agent proposal council with shared state, governed tool access, "
        "cross-functional handoffs, and local budget tracking."
    )
    action_cols = st.columns(2)
    if action_cols[0].button("Load agent council"):
        st.session_state.proposal_agent_council = get_json("/proposal/agent-council")
    if action_cols[1].button("Generate Agent Council Pack"):
        pack = post_json("/proposal/agent-council-pack", {"write_artifact": True})
        st.session_state.proposal_agent_council_pack = pack
        st.session_state.proposal_agent_council = pack["council"]
        st.success(f"Agent Council Pack generated under agent_council: {pack['artifact_path']}")

    council = st.session_state.get("proposal_agent_council")
    if council:
        summary = council["decision_summary"]
        metric_cols = st.columns(5)
        metric_cols[0].metric("Status", council["status"])
        metric_cols[1].metric("Agents", len(council["agents"]))
        metric_cols[2].metric("Turns", len(council["conversation"]))
        metric_cols[3].metric("Open handoffs", summary["open_handoffs"])
        metric_cols[4].metric("Tokens", council["budget_ledger"]["total_token_estimate"])
        st.write("Agents")
        st.dataframe(
            [
                {
                    "agent": item["agent_id"],
                    "role": item["role"],
                    "budget": item["budget_tokens"],
                    "allowed_tools": ", ".join(item["allowed_tools"]),
                    "blocked_tools": ", ".join(item["blocked_tools"]),
                }
                for item in council["agents"]
            ],
            use_container_width=True,
        )
        st.write("Conversation")
        st.dataframe(
            [
                {
                    "turn": item["turn"],
                    "role": item["role"],
                    "type": item["message_type"],
                    "handoff_to": item["handoff_to"],
                    "flags": ", ".join(item["governance_flags"]),
                    "tokens": item["token_estimate"],
                    "content": item["content"],
                }
                for item in council["conversation"]
            ],
            use_container_width=True,
        )
        st.write("Handoffs")
        st.dataframe(council["handoffs"], use_container_width=True)
        st.write("Tool governance")
        st.dataframe(council["tool_governance"], use_container_width=True)
        st.write("Budget ledger")
        st.json(council["budget_ledger"])
        st.write("Eval scenarios")
        st.dataframe(council["eval_scenarios"], use_container_width=True)
        st.write("Proof commands")
        st.code("\n".join(council["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(council["limitations"])

    pack = st.session_state.get("proposal_agent_council_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Transcript artifact path", pack["transcript_artifact_path"])
        st.download_button(
            "Download Agent Council Markdown",
            pack["markdown"],
            file_name="proposal_agent_council_pack.md",
        )


with tabs[48]:
    st.subheader("Decision Provenance")
    st.caption(
        "Inspect the typed decision graph that links buyer workflow checkpoints, agent turns, handoffs, "
        "governance gates, provider policy, source trust, model risk, procurement approvals, and eval assertions."
    )
    action_cols = st.columns(2)
    if action_cols[0].button("Load provenance graph"):
        st.session_state.decision_provenance = get_json("/proposal/decision-provenance")
    if action_cols[1].button("Generate Provenance Pack"):
        pack = post_json("/proposal/decision-provenance-pack", {"write_artifact": True})
        st.session_state.decision_provenance_pack = pack
        st.session_state.decision_provenance = pack["provenance"]
        st.success(f"Decision Provenance Pack generated under decision_provenance: {pack['artifact_path']}")

    provenance = st.session_state.get("decision_provenance")
    if provenance:
        summary = provenance["summary"]
        metric_cols = st.columns(5)
        metric_cols[0].metric("Status", provenance["status"])
        metric_cols[1].metric("Nodes", summary["node_count"])
        metric_cols[2].metric("Edges", summary["edge_count"])
        metric_cols[3].metric("Approvals", summary["approval_items"])
        metric_cols[4].metric("Provider", summary["provider_mode"])
        st.write("Provenance nodes")
        st.dataframe(
            [
                {
                    "node": item["node_id"],
                    "type": item["node_type"],
                    "owner": item["owner_role"],
                    "status": item["status"],
                    "refs": ", ".join(item["source_refs"][:3]),
                    "evidence": item["evidence"],
                }
                for item in provenance["nodes"]
            ],
            use_container_width=True,
        )
        st.write("Provenance edges")
        st.dataframe(provenance["edges"], use_container_width=True)
        st.write("Decision controls")
        st.dataframe(provenance["decision_controls"], use_container_width=True)
        st.write("Eval assertions")
        st.dataframe(provenance["eval_assertions"], use_container_width=True)
        st.write("Proof commands")
        st.code("\n".join(provenance["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(provenance["limitations"])

    pack = st.session_state.get("decision_provenance_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Decision Provenance Markdown",
            pack["markdown"],
            file_name="proposal_decision_provenance_pack.md",
        )


with tabs[49]:
    st.subheader("Governed Retrieval")
    st.caption(
        "Preview how Source Trust Gate policies affect retrieved citations before answer generation."
    )
    default_question = "What disaster recovery, uptime, SSO, encryption, and audit controls are supported?"
    question = st.text_input("Governed retrieval question", value=default_question)
    top_k = st.number_input("Top K", min_value=1, max_value=12, value=6, step=1)
    include_suppressed = st.checkbox("Include suppressed sources", value=False)
    action_cols = st.columns(2)
    payload = {
        "question": question,
        "top_k": int(top_k),
        "include_suppressed": include_suppressed,
    }
    if action_cols[0].button("Preview governed retrieval"):
        st.session_state.governed_retrieval = post_json("/evidence/governed-retrieval", payload)
    if action_cols[1].button("Generate Governed Retrieval Pack"):
        pack = post_json("/evidence/governed-retrieval-pack", {**payload, "write_artifact": True})
        st.session_state.governed_retrieval_pack = pack
        st.session_state.governed_retrieval = pack["governed_retrieval"]
        st.success(f"Governed Retrieval Pack generated under governed_retrieval: {pack['artifact_path']}")

    governed = st.session_state.get("governed_retrieval")
    if governed:
        summary = governed["summary"]
        metric_cols = st.columns(5)
        metric_cols[0].metric("Status", governed["status"])
        metric_cols[1].metric("Candidates", summary["candidate_count"])
        metric_cols[2].metric("Allowed", summary["allowed_count"])
        metric_cols[3].metric("Approvals", summary["approval_required_count"])
        metric_cols[4].metric("Blocked", summary["blocked_or_suppressed_count"])
        st.write("Governed retrieval results")
        st.dataframe(
            [
                {
                    "result": item["result_id"],
                    "source": item["filename"],
                    "policy": item["retrieval_policy"],
                    "action": item["governance_action"],
                    "visible": item["visible_to_generator"],
                    "approval": item["approval_required"],
                    "original": item["original_score"],
                    "adjusted": item["adjusted_score"],
                    "owners": ", ".join(item["reviewer_owners"]),
                    "reason": item["reason"],
                }
                for item in governed["results"]
            ],
            use_container_width=True,
        )
        st.write("Allowed citations")
        st.dataframe(governed["allowed_citations"], use_container_width=True)
        st.write("Blocked or suppressed results")
        st.dataframe(governed["blocked_results"], use_container_width=True)
        st.write("Human review queue")
        st.dataframe(governed["reviewer_queue"], use_container_width=True)
        st.write("Policy trace")
        st.json(governed["policy_trace"])
        st.write("Local proof commands")
        st.code("\n".join(governed["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(governed["limitations"])

    pack = st.session_state.get("governed_retrieval_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Governed Retrieval Markdown",
            pack["markdown"],
            file_name="governed_retrieval_pack.md",
        )


with tabs[50]:
    st.subheader("Retrieval Experiments")
    st.caption(
        "Compare local retrieval policies against the eval dataset with win/loss boosts, loss-gap guardrails, "
        "diagnostics, trace spans, and a governed shadow-eval recommendation."
    )
    dataset_path = st.text_input("Experiment dataset", "sample_data/eval_dataset.json")
    outcomes_path = st.text_input("Win/loss outcome fixture", "sample_data/rfp_outcomes.json")
    experiment_top_k = st.number_input("Experiment Top K", min_value=1, max_value=10, value=4, step=1)
    payload = {
        "dataset_path": dataset_path,
        "outcomes_fixture_path": outcomes_path,
        "top_k": int(experiment_top_k),
    }
    cols = st.columns(2)
    if cols[0].button("Run retrieval experiments"):
        st.session_state.retrieval_experiments = post_json("/rag/retrieval-experiments", payload)
    if cols[1].button("Generate experiment pack"):
        pack_payload = {**payload, "write_artifact": True}
        if st.session_state.get("retrieval_experiments"):
            pack_payload["comparison"] = st.session_state.retrieval_experiments
        pack = post_json("/rag/retrieval-experiment-pack", pack_payload)
        st.session_state.retrieval_experiment_pack = pack
        st.session_state.retrieval_experiments = pack["comparison"]
        st.success(f"Retrieval Experiment Pack generated under retrieval_experiments: {pack['artifact_path']}")

    comparison = st.session_state.get("retrieval_experiments")
    if comparison:
        metric_cols = st.columns(4)
        metric_cols[0].metric("Status", comparison["status"])
        metric_cols[1].metric("Recommended", comparison["recommended_policy_id"])
        metric_cols[2].metric("Policies", comparison["summary"]["policy_count"])
        metric_cols[3].metric("Questions", comparison["summary"]["question_count"])
        st.write("Policy results")
        st.dataframe(comparison["policy_results"], use_container_width=True)
        st.write("Governance decision")
        st.json(comparison["governance_decision"])
        st.write("Question diagnostics")
        st.dataframe(comparison["question_diagnostics"], use_container_width=True)
        st.write("Trace spans")
        st.dataframe(comparison["trace_spans"], use_container_width=True)
        st.write("Local commands")
        st.code("\n".join(comparison["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(comparison["limitations"])

    pack = st.session_state.get("retrieval_experiment_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Retrieval Experiment Markdown",
            pack["markdown"],
            file_name="retrieval_experiment_pack.md",
        )


with tabs[51]:
    st.subheader("Proposal Observability")
    st.caption(
        "Roll up buyer workflow traces, agent handoffs, decision provenance, retrieval diagnostics, "
        "experiment comparison, provider cost posture, audit, and metrics into one local control-plane view."
    )
    obs_dataset_path = st.text_input("Observability eval dataset", "sample_data/eval_dataset.json")
    obs_outcomes_path = st.text_input("Observability win/loss fixture", "sample_data/rfp_outcomes.json")
    obs_top_k = st.number_input("Observability Top K", min_value=1, max_value=10, value=4, step=1)
    payload = {
        "dataset_path": obs_dataset_path,
        "outcomes_fixture_path": obs_outcomes_path,
        "top_k": int(obs_top_k),
    }
    action_cols = st.columns(2)
    if action_cols[0].button("Load observability report"):
        st.session_state.proposal_observability = get_json("/ops/proposal-observability")
    if action_cols[1].button("Generate Observability Pack"):
        pack = post_json("/ops/proposal-observability-pack", {**payload, "write_artifact": True})
        st.session_state.proposal_observability_pack = pack
        st.session_state.proposal_observability = pack["observability"]
        st.success(f"Proposal Observability Pack generated under proposal_observability: {pack['artifact_path']}")

    observability = st.session_state.get("proposal_observability")
    if observability:
        summary = observability["summary"]
        provider = observability["provider_and_cost_signals"]
        experiment = observability["experiment_comparison"]
        metric_cols = st.columns(5)
        metric_cols[0].metric("Status", observability["status"])
        metric_cols[1].metric("Trace spans", summary["trace_span_count"])
        metric_cols[2].metric("Diagnostics", summary["retrieval_diagnostic_count"])
        metric_cols[3].metric("Human review", summary["human_review_signal_count"])
        metric_cols[4].metric("Provider", provider["provider_mode"])
        st.write("Experiment comparison")
        st.json(
            {
                "status": experiment["status"],
                "recommended_policy_id": experiment["recommended_policy_id"],
                "score_delta_vs_baseline": experiment["score_delta_vs_baseline"],
                "policy_count": experiment["policy_count"],
                "question_count": experiment["question_count"],
            }
        )
        st.write("Trace map")
        st.dataframe(observability["trace_map"], use_container_width=True)
        st.write("Retrieval diagnostics")
        st.dataframe(observability["retrieval_diagnostics"], use_container_width=True)
        st.write("Governance findings")
        st.dataframe(observability["governance_findings"], use_container_width=True)
        st.write("Human review signals")
        st.dataframe(observability["human_review_signals"], use_container_width=True)
        st.write("Provider and cost signals")
        st.json(provider)
        st.write("Local proof commands")
        st.code("\n".join(observability["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(observability["limitations"])

    pack = st.session_state.get("proposal_observability_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Proposal Observability Markdown",
            pack["markdown"],
            file_name="proposal_observability_pack.md",
        )


with tabs[52]:
    st.subheader("Submission Certification")
    st.caption(
        "Certify the buyer workflow, replay, role council, decision provenance, and structured contracts "
        "before a final proposal submission."
    )
    action_cols = st.columns(2)
    if action_cols[0].button("Load certification gate"):
        st.session_state.submission_certification = get_json("/proposal/submission-certification")
    if action_cols[1].button("Generate Certification Pack"):
        pack = post_json("/proposal/submission-certification-pack", {"write_artifact": True})
        st.session_state.submission_certification_pack = pack
        st.session_state.submission_certification = pack["certification"]
        st.success(f"Submission Certification Pack generated: {pack['artifact_path']}")

    certification = st.session_state.get("submission_certification")
    if certification:
        metric_cols = st.columns(5)
        metric_cols[0].metric("Status", certification["status"])
        metric_cols[1].metric("Score", certification["readiness_score"])
        metric_cols[2].metric("Gates", len(certification["gates"]))
        metric_cols[3].metric("Reviews", len(certification["reviewer_queue"]))
        metric_cols[4].metric("Transitions", len(certification["transitions"]))
        st.write("Recommendation")
        st.write(certification["recommendation"])
        st.write("Certification gates")
        st.dataframe(certification["gates"], use_container_width=True)
        st.write("State transitions")
        st.dataframe(certification["transitions"], use_container_width=True)
        st.write("Reviewer queue")
        st.dataframe(certification["reviewer_queue"], use_container_width=True)
        st.write("Eval assertions")
        st.dataframe(certification["eval_assertions"], use_container_width=True)
        st.write("Source artifacts")
        st.json(certification["source_artifacts"])
        st.write("Injected dependencies")
        st.json(certification["injected_dependencies"])
        st.write("Local proof commands")
        st.code("\n".join(certification["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(certification["limitations"])

    pack = st.session_state.get("submission_certification_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.download_button(
            "Download Submission Certification Markdown",
            pack["markdown"],
            file_name="proposal_submission_certification_pack.md",
        )


with tabs[53]:
    st.subheader("Verification Evidence")
    st.caption(
        "Capture the local acceptance ledger for pytest, ruff, eval, red-team, dashboard smoke, demo, "
        "release gate, final audit, artifact inventory, and reviewer signoff."
    )
    action_cols = st.columns(2)
    if action_cols[0].button("Load evidence ledger"):
        st.session_state.verification_evidence = get_json("/ops/verification-evidence")
    if action_cols[1].button("Generate Evidence Pack"):
        pack = post_json("/ops/verification-evidence-pack", {"write_artifact": True})
        st.session_state.verification_evidence_pack = pack
        st.session_state.verification_evidence = pack["evidence"]
        st.success(f"Verification Evidence Pack generated: {pack['artifact_path']}")

    evidence = st.session_state.get("verification_evidence")
    if evidence:
        summary = evidence["summary"]
        metric_cols = st.columns(5)
        metric_cols[0].metric("Status", evidence["status"])
        metric_cols[1].metric("Score", evidence["score"])
        metric_cols[2].metric("Recorded", f"{summary['recorded_command_count']}/{summary['required_command_count']}")
        metric_cols[3].metric("Failed", summary["failed_command_count"])
        metric_cols[4].metric("Artifacts", summary["artifact_files"])
        st.write("Command evidence")
        st.dataframe(evidence["command_evidence"], use_container_width=True)
        st.write("Release gate snapshot")
        st.json(evidence["release_gate_snapshot"])
        st.write("Final audit snapshot")
        st.json(evidence["final_audit_snapshot"])
        st.write("Dashboard smoke snapshot")
        st.json(evidence["dashboard_smoke_snapshot"])
        st.write("Artifact inventory snapshot")
        st.json(evidence["artifact_inventory_snapshot"])
        st.write("Reviewer signoff")
        st.dataframe(evidence["reviewer_signoff"], use_container_width=True)
        st.write("Local proof commands")
        st.code("\n".join(evidence["local_proof_commands"]), language="powershell")
        st.write("Limitations")
        st.write(evidence["limitations"])

    pack = st.session_state.get("verification_evidence_pack")
    if pack:
        st.write("Generated artifact path", pack["artifact_path"])
        st.write("Generated JSON path", pack["json_artifact_path"])
        st.write("Reviewer controls")
        st.write(pack["pack"]["reviewer_controls"])
        st.download_button(
            "Download Verification Evidence Markdown",
            pack["markdown"],
            file_name="verification_evidence_pack.md",
        )
