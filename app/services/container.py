from functools import lru_cache

from app.core.config import Settings, get_settings
from app.providers.factory import build_llm_provider
from app.repositories.memory import repository
from app.services.action_plan import StakeholderActionPlanService
from app.services.api_contracts import ApiContractService
from app.services.artifact_inventory import ArtifactInventoryService
from app.services.audit import AuditService
from app.services.bid_simulator import BidScenarioSimulatorService
from app.services.ci_doctor import CiDoctorService
from app.services.compliance import ComplianceControlMappingService
from app.services.contract_risk import ContractRiskService
from app.services.corpus_coverage import CorpusCoverageService
from app.services.customer_intelligence import CustomerIntelligenceService
from app.services.deal_readiness import DealReadinessService
from app.services.demo_script import DemoScriptService
from app.services.draft_generation import DraftGenerationService
from app.services.evaluation import EvaluationService
from app.services.evidence_gap import EvidenceGapService
from app.services.final_handoff import FinalHandoffService
from app.services.git_readiness import GitReadinessService
from app.services.ingestion import DocumentIngestionService
from app.services.launch_checklist import LaunchChecklistService
from app.services.leadership_brief import LeadershipBriefService
from app.services.metrics import MetricsService
from app.services.portfolio import PortfolioService
from app.services.procurement import ProcurementQuestionRiskService
from app.services.release import ReleaseService
from app.services.retrieval import RetrievalService
from app.services.review_board import RfpReviewBoardService
from app.services.reviewer import ReviewerQuickstartService
from app.services.rfp_analysis import RfpAnalysisService
from app.services.runtime_demo import RuntimeDemoService
from app.services.submission_decision import SubmissionDecisionService
from app.services.submission_regression import SubmissionRegressionService
from app.services.timeline_orchestration import TimelineOrchestrationService
from app.services.ui_verification import UIVerificationService
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
        self.bid_simulator = BidScenarioSimulatorService(settings)
        self.customer_intelligence = CustomerIntelligenceService(settings)
        self.compliance = ComplianceControlMappingService(self.repo, settings)
        self.contract_risk = ContractRiskService(self.repo, settings)
        self.corpus_coverage = CorpusCoverageService(self.repo, settings)
        self.action_plan = StakeholderActionPlanService(settings)
        self.deal_readiness = DealReadinessService(settings)
        self.evidence_gap = EvidenceGapService(settings)
        self.leadership_brief = LeadershipBriefService(settings)
        self.submission_decision = SubmissionDecisionService(settings)
        self.submission_regression = SubmissionRegressionService(settings)
        self.demo_script = DemoScriptService(settings)
        self.api_contracts = ApiContractService(settings)
        self.artifact_inventory = ArtifactInventoryService(settings)
        self.launch_checklist = LaunchChecklistService(settings)
        self.ci_doctor = CiDoctorService(settings)
        self.portfolio = PortfolioService(settings)
        self.release = ReleaseService(settings)
        self.reviewer = ReviewerQuickstartService(settings)
        self.ui_verification = UIVerificationService(settings)
        self.final_handoff = FinalHandoffService(settings)
        self.git_readiness = GitReadinessService(settings)
        self.runtime_demo = RuntimeDemoService(settings)
        self.timeline_orchestration = TimelineOrchestrationService(settings)
        self.win_strategy = WinStrategyService(self.repo, settings)
        self.ingestion = DocumentIngestionService(self.repo, self.vector_store, settings)
        self.retrieval = RetrievalService(self.repo, self.vector_store)
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
        self.procurement = ProcurementQuestionRiskService(
            self.repo,
            settings,
            self.retrieval,
            self.customer_intelligence,
            self.review_board,
            self.compliance,
        )


@lru_cache
def get_container() -> ServiceContainer:
    return ServiceContainer(get_settings())
