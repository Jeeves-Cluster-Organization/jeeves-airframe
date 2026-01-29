"""
NLI (Natural Language Inference) service for claim verification.

Per Constitution P1 (Accuracy First): This service verifies that claims
are actually entailed by their cited evidence, preventing hallucination.

Uses a pretrained cross-encoder NLI model for zero-shot entailment checking.
No training data required - works out of the box.

Usage:
    from jeeves_infra.memory.services.nli_service import NLIService

    nli = NLIService()
    result = nli.verify_claim(
        claim="UserService handles authentication",
        evidence="class UserService:\n    def authenticate(self, user)..."
    )
    # result.label = "entailment", result.score = 0.92
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from jeeves_infra.logging import get_component_logger
from jeeves_infra.protocols import LoggerProtocol


@dataclass
class NLIResult:
    """Result of NLI verification."""
    label: str  # "entailment", "neutral", or "contradiction"
    score: float  # Confidence score 0-1
    entailment_score: float  # Direct entailment probability

    @property
    def is_entailed(self) -> bool:
        """Check if claim is entailed with reasonable confidence."""
        return self.label == "entailment" and self.score > 0.5

    @property
    def is_contradicted(self) -> bool:
        """Check if claim is contradicted."""
        return self.label == "contradiction" and self.score > 0.5


@dataclass
class ClaimVerificationResult:
    """Result of verifying a claim against evidence."""
    claim: str
    citation: str
    nli_result: NLIResult
    verified: bool
    confidence: float
    reason: str


class NLIService:
    """
    NLI-based claim verification service.

    Uses a pretrained cross-encoder model for natural language inference.
    Determines if evidence (premise) entails a claim (hypothesis).

    Per Constitution P1: Anti-hallucination gate - ensures claims are
    supported by actual code evidence.
    """

    # Default model - small, fast, good for NLI
    DEFAULT_MODEL = "cross-encoder/nli-MiniLM2-L6-H768"

    # Label mappings for different model outputs
    LABEL_MAPPINGS = {
        "ENTAILMENT": "entailment",
        "NEUTRAL": "neutral",
        "CONTRADICTION": "contradiction",
        "entailment": "entailment",
        "neutral": "neutral",
        "contradiction": "contradiction",
        # Some models use numeric labels
        "0": "contradiction",
        "1": "neutral",
        "2": "entailment",
    }

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: str = "cpu",
        enabled: bool = True,
        logger: Optional[LoggerProtocol] = None
    ):
        """
        Initialize NLI service.

        Args:
            model_name: HuggingFace model name for NLI. Defaults to cross-encoder/nli-MiniLM2-L6-H768
            device: Device to run on ("cpu" or "cuda")
            enabled: Whether NLI verification is enabled (for graceful degradation)
            logger: Optional logger instance (ADR-001 DI)
        """
        self._logger = get_component_logger("nli_service", logger).bind(model=model_name or self.DEFAULT_MODEL)
        self.model_name = model_name or self.DEFAULT_MODEL
        self.device = device
        self.enabled = enabled

        self._pipeline = None
        self._initialized = False

        if enabled:
            self._initialize_model()

    def _initialize_model(self) -> None:
        """Lazy initialization of the NLI model."""
        if self._initialized:
            return

        try:
            from transformers import pipeline

            self._pipeline = pipeline(
                "text-classification",
                model=self.model_name,
                device=-1 if self.device == "cpu" else 0
            )
            self._initialized = True
            self._logger.info(
                "nli_service_initialized",
                model=self.model_name,
                device=self.device
            )
        except ImportError as e:
            self._logger.warning(
                "nli_service_disabled_no_transformers",
                error=str(e)
            )
            self.enabled = False
        except Exception as e:
            self._logger.error(
                "nli_service_init_failed",
                error=str(e),
                model=self.model_name
            )
            self.enabled = False

    def check_entailment(self, premise: str, hypothesis: str) -> NLIResult:
        """
        Check if premise entails hypothesis.

        Args:
            premise: The evidence/context (e.g., code snippet)
            hypothesis: The claim to verify

        Returns:
            NLIResult with label and confidence scores
        """
        if not self.enabled or not self._pipeline:
            # Return neutral result when disabled
            return NLIResult(
                label="neutral",
                score=0.5,
                entailment_score=0.5
            )

        try:
            # Format input for cross-encoder NLI model
            # Most NLI models expect: premise [SEP] hypothesis
            input_text = f"{premise}</s></s>{hypothesis}"

            # Truncate if too long (model has max length)
            max_length = 512
            if len(input_text) > max_length * 4:  # Rough char estimate
                premise_truncated = premise[:max_length * 2]
                input_text = f"{premise_truncated}</s></s>{hypothesis}"

            result = self._pipeline(input_text)

            # Handle different output formats
            if isinstance(result, list):
                result = result[0]

            raw_label = result.get("label", "neutral")
            score = result.get("score", 0.5)

            # Normalize label
            label = self.LABEL_MAPPINGS.get(raw_label, "neutral")

            # Calculate entailment score
            if label == "entailment":
                entailment_score = score
            elif label == "contradiction":
                entailment_score = 1.0 - score
            else:
                entailment_score = 0.5

            self._logger.debug(
                "nli_check_complete",
                label=label,
                score=score,
                premise_len=len(premise),
                hypothesis_len=len(hypothesis)
            )

            return NLIResult(
                label=label,
                score=score,
                entailment_score=entailment_score
            )

        except Exception as e:
            self._logger.error(
                "nli_check_failed",
                error=str(e),
                premise_len=len(premise),
                hypothesis_len=len(hypothesis)
            )
            # Return neutral on error (fail open)
            return NLIResult(
                label="neutral",
                score=0.5,
                entailment_score=0.5
            )

    def verify_claim(
        self,
        claim: str,
        evidence: str,
        citation: str = "",
        threshold: float = 0.6
    ) -> ClaimVerificationResult:
        """
        Verify a single claim against evidence.

        Per Constitution P1: Every claim needs evidence support.

        Args:
            claim: The claim to verify
            evidence: The code/text evidence
            citation: The file:line reference for the evidence
            threshold: Minimum entailment score to consider verified

        Returns:
            ClaimVerificationResult with verification status
        """
        if not evidence or not evidence.strip():
            return ClaimVerificationResult(
                claim=claim,
                citation=citation,
                nli_result=NLIResult("neutral", 0.0, 0.0),
                verified=False,
                confidence=0.0,
                reason="No evidence provided"
            )

        # Build premise from evidence
        premise = f"Code evidence from {citation}:\n{evidence}" if citation else evidence
        hypothesis = claim

        nli_result = self.check_entailment(premise, hypothesis)

        # Determine verification status
        if nli_result.label == "entailment" and nli_result.score >= threshold:
            verified = True
            reason = "Claim is supported by evidence"
        elif nli_result.label == "contradiction" and nli_result.score >= threshold:
            verified = False
            reason = "Claim contradicts evidence"
        elif nli_result.label == "neutral":
            # Neutral with high confidence means evidence doesn't address claim
            verified = False
            reason = "Evidence does not directly support or contradict claim"
        else:
            verified = False
            reason = f"Low confidence ({nli_result.score:.2f})"

        self._logger.info(
            "claim_verification_complete",
            verified=verified,
            label=nli_result.label,
            score=nli_result.score,
            claim_preview=claim[:50]
        )

        return ClaimVerificationResult(
            claim=claim,
            citation=citation,
            nli_result=nli_result,
            verified=verified,
            confidence=nli_result.score,
            reason=reason
        )

    def verify_claims_batch(
        self,
        claims: List[Dict[str, str]],
        evidence_map: Dict[str, str],
        threshold: float = 0.6
    ) -> List[ClaimVerificationResult]:
        """
        Verify multiple claims against their evidence.

        Args:
            claims: List of dicts with "claim" and "citation" keys
            evidence_map: Map of citation -> evidence text
            threshold: Minimum entailment score

        Returns:
            List of ClaimVerificationResult
        """
        results = []

        for claim_data in claims:
            claim = claim_data.get("claim", "")
            citation = claim_data.get("citation", "")

            # Look up evidence by citation
            evidence = evidence_map.get(citation, "")

            result = self.verify_claim(
                claim=claim,
                evidence=evidence,
                citation=citation,
                threshold=threshold
            )
            results.append(result)

        verified_count = sum(1 for r in results if r.verified)
        self._logger.info(
            "batch_verification_complete",
            total=len(claims),
            verified=verified_count,
            rejected=len(claims) - verified_count
        )

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "enabled": self.enabled,
            "initialized": self._initialized,
            "model": self.model_name,
            "device": self.device
        }


# Singleton instance for reuse
_nli_service_instance: Optional[NLIService] = None


def get_nli_service(
    model_name: Optional[str] = None,
    enabled: bool = True
) -> NLIService:
    """
    Get or create NLI service singleton.

    Args:
        model_name: Optional model override
        enabled: Whether service is enabled

    Returns:
        NLIService instance
    """
    global _nli_service_instance

    if _nli_service_instance is None:
        _nli_service_instance = NLIService(
            model_name=model_name,
            enabled=enabled
        )

    return _nli_service_instance
