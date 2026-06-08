# Acme Enterprise Analytics RFP

Acme Manufacturing is requesting proposals for an AI-assisted RFP response and knowledge automation platform. The response deadline is July 18, 2026.

## Business Objectives

- The vendor must provide document ingestion for PDF, TXT, and Markdown knowledge sources.
- The solution shall answer RFP and security questionnaire questions with cited evidence from approved documents.
- The platform must identify missing evidence and avoid unsupported claims.
- The vendor should provide dashboards for usage, evaluation, and audit review.

## Security and Compliance Requirements

- The solution must support SSO through SAML 2.0 or OIDC.
- The platform shall encrypt data at rest with AES-256 and encrypt data in transit with TLS 1.2 or higher.
- The vendor must provide SOC 2 Type II evidence and GDPR subprocessors on request.
- The system must log user actions, generated responses, provider choices, and approval-relevant events.

## Implementation Requirements

- The vendor must support a 30-day pilot using sample RFPs and prior proposal documents.
- The proposal should describe how retrieval quality, citation coverage, latency, token usage, and estimated cost are measured.
- The system should integrate with enterprise document repositories in a future phase.

## Pricing Requirements

- Pricing must describe implementation fees, platform subscription tiers, and usage-based AI cost assumptions.
- The vendor should flag any customer-specific commercial assumptions.

## Risks

- Acme cannot accept generated answers without traceable citations.
- Data residency preferences may apply for regulated divisions.
