from functools import lru_cache

from app.core.config import Settings, get_settings
from app.providers.factory import build_llm_provider
from app.repositories.memory import repository
from app.services.access_policy import AccessPolicyService
from app.services.action_plan import StakeholderActionPlanService
from app.services.amendment_impact import RfpAmendmentImpactService
from app.services.answer_reuse_approval import AnswerReuseApprovalService
from app.services.answer_reuse_coverage import AnswerReuseCoverageService
from app.services.answer_reuse_drift import AnswerReuseDriftService
from app.services.answer_reuse_library import AnswerReuseLibraryService
from app.services.api_contracts import ApiContractService
from app.services.approval_simulation import ProposalApprovalSimulationService
from app.services.artifact_inventory import ArtifactInventoryService
from app.services.audit import AuditService
from app.services.bid_simulator import BidScenarioSimulatorService
from app.services.buyer_contracts import BuyerStructuredContractService
from app.services.buyer_intelligence import BuyerProposalIntelligenceService
from app.services.ci_doctor import CiDoctorService
from app.services.citation_lineage import CitationLineageService
from app.services.clarification_questions import ClarificationQuestionService
from app.services.compliance import ComplianceControlMappingService
from app.services.contract_risk import ContractRiskService
from app.services.corpus_coverage import CorpusCoverageService
from app.services.cost_governance import CostGovernanceService
from app.services.customer_intelligence import CustomerIntelligenceService
from app.services.deal_readiness import DealReadinessService
from app.services.decision_provenance import ProposalDecisionProvenanceService
from app.services.demo_script import DemoScriptService
from app.services.draft_generation import DraftGenerationService
from app.services.evaluation import EvaluationService
from app.services.evidence_conflicts import EvidenceConflictService
from app.services.evidence_freshness import EvidenceFreshnessService
from app.services.evidence_gap import EvidenceGapService
from app.services.evidence_sla import EvidenceFreshnessSlaService
from app.services.final_handoff import FinalHandoffService
from app.services.git_readiness import GitReadinessService
from app.services.governed_retrieval import GovernedRetrievalService
from app.services.ingestion import DocumentIngestionService
from app.services.launch_checklist import LaunchChecklistService
from app.services.leadership_brief import LeadershipBriefService
from app.services.metrics import MetricsService
from app.services.model_risk import ModelRiskRegisterService
from app.services.objection_handling import CompetitiveObjectionHandlingService
from app.services.portfolio import PortfolioService
from app.services.privacy_retention import PrivacyRetentionGuardrailService
from app.services.procurement import ProcurementQuestionRiskService
from app.services.procurement_risk_decisions import ProcurementRiskDecisionService
from app.services.procurement_risk_desk import ProcurementRiskDeskService
from app.services.proposal_agent_council import ProposalAgentCouncilService
from app.services.proposal_assurance import ProposalAssuranceBundleService
from app.services.proposal_benchmark import ProposalQualityBenchmarkService
from app.services.proposal_intake import ProposalIntakeTriageService
from app.services.proposal_observability import ProposalObservabilityService
from app.services.proposal_release_room import ProposalReleaseRoomService
from app.services.proposal_review_gate import ProposalReviewGateService
from app.services.provider_resilience import ProviderResilienceService
from app.services.release import ReleaseService
from app.services.retrieval import RetrievalService
from app.services.retrieval_experiments import RetrievalExperimentComparisonService
from app.services.review_board import RfpReviewBoardService
from app.services.reviewer import ReviewerQuickstartService
from app.services.reviewer_collaboration import ReviewerCollaborationService
from app.services.reviewer_escalation import ReviewerEscalationService
from app.services.reviewer_signoff import ReviewerSignoffLedgerService
from app.services.reviewer_workflow import ReviewerWorkflowService
from app.services.rfp_analysis import RfpAnalysisService
from app.services.runtime_demo import RuntimeDemoService
from app.services.source_trust import SourceTrustGateService
from app.services.submission_certification import ProposalSubmissionCertificationService
from app.services.submission_decision import SubmissionDecisionService
from app.services.submission_exceptions import SubmissionExceptionService
from app.services.submission_regression import SubmissionRegressionService
from app.services.timeline_orchestration import TimelineOrchestrationService
from app.services.trace_export import TraceExportService
from app.services.ui_verification import UIVerificationService
from app.services.verification_evidence import VerificationEvidenceService
from app.services.win_loss_learning import WinLossLearningService
from app.services.win_loss_policy import WinLossPolicyActivationService
from app.services.win_loss_replay import WinLossReplayService
from app.services.win_strategy import WinStrategyService
from app.services.workbench import RfpWorkbenchService
from app.vectorstores.factory import build_vector_store


class ServiceContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repo = repository
        self.vector_store = build_vector_store(settings)
        self.llm_provider = build_llm_provider(settings)
        self.audit = AuditService(self.repo, settings)
        self.metrics = MetricsService(self.repo, settings)
        self.cost_governance = CostGovernanceService(settings, self.metrics)
        self.model_risk = ModelRiskRegisterService(self.repo, settings)
        self.access_policy = AccessPolicyService(settings)
        self.buyer_intelligence = BuyerProposalIntelligenceService(settings)
        self.buyer_contracts = BuyerStructuredContractService(settings)
        self.proposal_agent_council = ProposalAgentCouncilService(settings)
        self.proposal_assurance = ProposalAssuranceBundleService(settings)
        self.proposal_benchmark = ProposalQualityBenchmarkService(settings)
        self.proposal_intake = ProposalIntakeTriageService(settings)
        self.decision_provenance = ProposalDecisionProvenanceService(settings)
        self.approval_simulation = ProposalApprovalSimulationService(settings)
        self.submission_certification = ProposalSubmissionCertificationService(settings)
        self.proposal_observability = ProposalObservabilityService(settings)
        self.proposal_release_room = ProposalReleaseRoomService(settings)
        self.proposal_review_gate = ProposalReviewGateService(settings)
        self.trace_export = TraceExportService(settings)
        self.provider_resilience = ProviderResilienceService(settings)
        self.bid_simulator = BidScenarioSimulatorService(settings)
        self.customer_intelligence = CustomerIntelligenceService(settings)
        self.answer_reuse_library = AnswerReuseLibraryService(self.repo, settings)
        self.answer_reuse_drift = AnswerReuseDriftService(settings, self.answer_reuse_library)
        self.answer_reuse_approval = AnswerReuseApprovalService(settings, self.answer_reuse_drift)
        self.answer_reuse_coverage = AnswerReuseCoverageService(settings, self.answer_reuse_library)
        self.compliance = ComplianceControlMappingService(self.repo, settings)
        self.contract_risk = ContractRiskService(self.repo, settings)
        self.corpus_coverage = CorpusCoverageService(self.repo, settings)
        self.action_plan = StakeholderActionPlanService(settings)
        self.amendment_impact = RfpAmendmentImpactService(settings)
        self.deal_readiness = DealReadinessService(settings)
        self.evidence_gap = EvidenceGapService(settings)
        self.leadership_brief = LeadershipBriefService(settings)
        self.submission_decision = SubmissionDecisionService(settings)
        self.submission_exceptions = SubmissionExceptionService(settings)
        self.submission_regression = SubmissionRegressionService(settings)
        self.source_trust = SourceTrustGateService(settings)
        self.demo_script = DemoScriptService(settings)
        self.api_contracts = ApiContractService(settings)
        self.artifact_inventory = ArtifactInventoryService(settings)
        self.launch_checklist = LaunchChecklistService(settings)
        self.ci_doctor = CiDoctorService(settings)
        self.portfolio = PortfolioService(settings)
        self.release = ReleaseService(settings)
        self.reviewer = ReviewerQuickstartService(settings)
        self.reviewer_collaboration = ReviewerCollaborationService(settings)
        self.reviewer_workflow = ReviewerWorkflowService(settings)
        self.reviewer_signoff = ReviewerSignoffLedgerService(settings)
        self.reviewer_escalation = ReviewerEscalationService(settings)
        self.ui_verification = UIVerificationService(settings)
        self.verification_evidence = VerificationEvidenceService(settings)
        self.final_handoff = FinalHandoffService(settings)
        self.git_readiness = GitReadinessService(settings)
        self.runtime_demo = RuntimeDemoService(settings)
        self.timeline_orchestration = TimelineOrchestrationService(settings)
        self.win_loss_learning = WinLossLearningService(settings)
        self.win_loss_policy = WinLossPolicyActivationService(settings)
        self.win_loss_replay = WinLossReplayService(settings)
        self.win_strategy = WinStrategyService(self.repo, settings)
        self.ingestion = DocumentIngestionService(self.repo, self.vector_store, settings)
        self.retrieval = RetrievalService(self.repo, self.vector_store)
        self.clarification_questions = ClarificationQuestionService(settings, self.retrieval)
        self.retrieval_experiments = RetrievalExperimentComparisonService(
            settings,
            self.retrieval,
            self.win_loss_learning,
        )
        self.governed_retrieval = GovernedRetrievalService(settings, self.retrieval)
        self.analysis = RfpAnalysisService(self.repo)
        self.generation = DraftGenerationService(
            self.repo,
            self.retrieval,
            self.llm_provider,
            self.metrics,
        )
        self.workbench = RfpWorkbenchService(self.repo, settings, self.metrics)
        self.review_board = RfpReviewBoardService()
        self.evaluation = EvaluationService(self.retrieval, self.generation)
        self.evidence_conflicts = EvidenceConflictService(self.repo, settings)
        self.evidence_freshness = EvidenceFreshnessService(self.repo, settings)
        self.evidence_sla = EvidenceFreshnessSlaService(settings)
        self.citation_lineage = CitationLineageService(self.repo, settings)
        self.objection_handling = CompetitiveObjectionHandlingService(
            self.repo,
            settings,
            self.retrieval,
            self.customer_intelligence,
            self.review_board,
        )
        self.procurement = ProcurementQuestionRiskService(
            self.repo,
            settings,
            self.retrieval,
            self.customer_intelligence,
            self.review_board,
            self.compliance,
        )
        self.procurement_risk_desk = ProcurementRiskDeskService(settings, self.retrieval)
        self.procurement_risk_decisions = ProcurementRiskDecisionService(settings)
        self.privacy_retention = PrivacyRetentionGuardrailService(self.repo, settings)


@lru_cache
def get_container() -> ServiceContainer:
    return ServiceContainer(get_settings())
