# Security Questionnaire and Policy

The platform supports SSO using SAML 2.0 or OIDC when deployed behind an enterprise identity provider. API calls require an API key in local demo mode and can be extended to OAuth or gateway authentication in production.

Data in transit should be encrypted with TLS 1.2 or higher. Data at rest should be encrypted using AES-256 or the equivalent managed encryption controls of the hosting platform.

Audit events record document ingestion, RFP analysis, question answering, draft generation, evaluation runs, provider choices, and approval-relevant metadata. Every generated answer carries a trace ID for review.

Security reviewers should verify customer-specific data retention, data residency, incident response, and subprocessors before production rollout.
