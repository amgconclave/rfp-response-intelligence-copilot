# AI Governance and Security Controls

## Grounded generation policy

The copilot must ground generated RFP answers in approved source documents. Answers with no sufficiently relevant citations must return missing evidence warnings and should not be submitted as supported claims. Review board checks flag unsupported claims, weak citations, high-risk requirements, and cost or latency warnings.

## Model governance

Default local mock mode is deterministic and does not send prompts to a paid model provider. Optional OpenAI or Azure OpenAI use requires configured credentials, provider approval, security review, and customer-specific data handling controls. Model outputs remain drafts until reviewed against citations.

## Security controls

Security controls include API-key protected endpoints, trace IDs, audit event logging, token and latency metrics, source document tagging, least-privilege reviewer workflows, and explicit missing-evidence handling for adversarial prompts.

## Human review

Human reviewers own final RFP language, pricing approvals, privacy claims, security exceptions, and customer-specific commitments. The AI governance policy requires reviewer signoff before submitting claims about FedRAMP, HIPAA, uptime, subprocessors, disaster recovery, or implementation timelines.
