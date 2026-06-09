# Data Processing Addendum and Privacy Policy

## Data processing roles

The customer is the controller of RFP content, uploaded source documents, reviewer comments, and generated response drafts. The copilot acts as a processor for configured workspace data and only processes content to provide retrieval, drafting, evaluation, workflow, audit, and artifact generation services.

## Personal data and retention

Approved source documents may contain business contact names, work email addresses, procurement questions, vendor security questionnaires, and contract metadata. Default local demo retention is controlled by the local storage directory. Production deployments should set retention windows, deletion procedures, and export procedures in the customer order form.

## Subprocessors and residency

The local portfolio demo uses no external subprocessors by default. Optional OpenAI, Azure OpenAI, Azure AI Search, Qdrant Cloud, CRM, Slack, or calendar integrations require a customer-approved subprocessor list, data-region review, and separate credentials. The policy does not claim that every subprocessor is located only in the United States.

## Privacy controls

Privacy controls include API-key protection, source tagging, audit events, generated artifact directories ignored by git, configurable provider mode, and missing-evidence guardrails that prevent unsupported privacy claims from being treated as approved responses.
