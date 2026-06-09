# Implementation Guide

## Enterprise rollout model

The RFP Response Intelligence Copilot implementation guide uses a four phase enterprise rollout: discovery, secure workspace setup, corpus onboarding, and production readiness review. Discovery confirms RFP owners, security reviewers, legal reviewers, pricing approvers, response SLAs, required integrations, and approval workflow routing.

## Timeline and responsibilities

Standard implementation is planned for 30 business days when the customer provides approved source documents, SSO metadata, reviewer groups, and a pilot RFP by kickoff. The solutions owner manages weekly checkpoints, the security owner validates SSO and audit logging, the legal owner confirms DPA and subprocessor needs, and the customer success manager coordinates onboarding.

## Technical setup

The implementation supports local mock mode for pilot demos, Qdrant or FAISS vector-store adapters for retrieval, API-key protected FastAPI endpoints, and Streamlit dashboard access. Production setup should configure SAML or OIDC SSO, least-privilege reviewer roles, audit event retention, and source document tagging before the first live RFP.

## Acceptance criteria

Go-live acceptance requires at least one sample RFP, six or more approved knowledge-base documents, successful cited answer generation, standard eval pass, red-team missing-evidence pass, launch checklist pass, and a named owner for every blocked evidence gap.
