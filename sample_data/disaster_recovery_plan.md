# Disaster Recovery Plan

## Recovery objectives

The disaster recovery plan defines recovery time objective and recovery point objective targets for production deployments. A standard production deployment should target a 24 hour RTO and 4 hour RPO for the application workspace when hosting, database, vector store, and backup services are configured by the customer.

## Backup scope

Backups should include approved source documents, document metadata, vector index rebuild inputs, audit event logs, generated response artifacts, and customer configuration. Local demo storage is not a managed backup system and should be regenerated from sample data.

## Recovery procedure

Recovery steps include restoring source document storage, rebuilding the vector index from approved documents, verifying API health, running standard eval, running red-team missing-evidence checks, regenerating launch and runtime packs, and confirming dashboard access.

## Limitations

The plan does not guarantee zero data loss, active-active failover, or a universal 99.99 percent uptime SLA. Customer-specific disaster recovery commitments must be approved in the order form and validated in a tabletop exercise.
