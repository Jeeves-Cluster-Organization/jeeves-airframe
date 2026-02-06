"""
Unit tests for NLI (Natural Language Inference) service.

Tests the claim verification functionality used by the Critic agent
for anti-hallucination validation per Constitution P1.

Constitutional Import Boundary Note:
- Mission system layer tests the avionics layer functionality
- Direct avionics imports are acceptable here for testing
- App layer tests must use mission_system.adapters instead
"""

import pytest
from unittest.mock import MagicMock, patch

# Mission system tests avionics functionality - direct import acceptable
from jeeves_infra.memory.services.nli_service import (
    NLIService,
    NLIResult,
    ClaimVerificationResult,
    get_nli_service,
)


class TestNLIResult:
    """Tests for NLIResult dataclass."""

    def test_is_entailed_true(self):
        """Test is_entailed returns True for entailment with high score."""
        result = NLIResult(label="entailment", score=0.85, entailment_score=0.85)
        assert result.is_entailed is True

    def test_is_entailed_false_low_score(self):
        """Test is_entailed returns False for low confidence."""
        result = NLIResult(label="entailment", score=0.4, entailment_score=0.4)
        assert result.is_entailed is False

    def test_is_entailed_false_wrong_label(self):
        """Test is_entailed returns False for non-entailment label."""
        result = NLIResult(label="neutral", score=0.9, entailment_score=0.5)
        assert result.is_entailed is False

    def test_is_contradicted_true(self):
        """Test is_contradicted returns True for contradiction."""
        result = NLIResult(label="contradiction", score=0.8, entailment_score=0.2)
        assert result.is_contradicted is True

    def test_is_contradicted_false(self):
        """Test is_contradicted returns False for non-contradiction."""
        result = NLIResult(label="neutral", score=0.7, entailment_score=0.5)
        assert result.is_contradicted is False


class TestNLIServiceDisabled:
    """Tests for NLI service when disabled."""

    def test_disabled_service_returns_neutral(self):
        """Test disabled service returns neutral results."""
        service = NLIService(enabled=False)

        result = service.check_entailment(
            premise="The sky is blue",
            hypothesis="The weather is nice"
        )

        assert result.label == "neutral"
        assert result.score == 0.5

    def test_disabled_verify_claim_returns_unverified(self):
        """Test disabled service verify_claim returns appropriate result."""
        service = NLIService(enabled=False)

        result = service.verify_claim(
            claim="UserService handles auth",
            evidence="class UserService: pass",
            citation="user.py:1"
        )

        # When disabled, verification should still work but with neutral NLI
        assert result.nli_result.label == "neutral"


class TestNLIServiceMocked:
    """Tests for NLI service with mocked pipeline."""

    @pytest.fixture
    def mock_pipeline(self):
        """Create a mock transformers pipeline."""
        mock = MagicMock()
        mock.return_value = [{"label": "ENTAILMENT", "score": 0.92}]
        return mock

    @pytest.fixture
    def nli_service_with_mock(self, mock_pipeline):
        """Create NLI service with mocked pipeline.

        Note: We create with enabled=False to skip _initialize_model,
        then manually set the pipeline mock. This avoids needing to
        patch the transformers import.
        """
        service = NLIService(enabled=False)
        service._pipeline = mock_pipeline
        service._initialized = True
        service.enabled = True  # Re-enable after setting up mock
        return service

    def test_check_entailment_entailment(self, nli_service_with_mock, mock_pipeline):
        """Test check_entailment detects entailment."""
        mock_pipeline.return_value = [{"label": "ENTAILMENT", "score": 0.92}]

        result = nli_service_with_mock.check_entailment(
            premise="class UserService:\n    def authenticate(self, user): pass",
            hypothesis="UserService has an authenticate method"
        )

        assert result.label == "entailment"
        assert result.score == 0.92
        assert result.entailment_score == 0.92

    def test_check_entailment_contradiction(self, nli_service_with_mock, mock_pipeline):
        """Test check_entailment detects contradiction."""
        mock_pipeline.return_value = [{"label": "CONTRADICTION", "score": 0.88}]

        result = nli_service_with_mock.check_entailment(
            premise="class UserService: pass",
            hypothesis="UserService has 100 methods"
        )

        assert result.label == "contradiction"
        assert result.score == 0.88
        assert abs(float(result.entailment_score) - 0.12) < 0.01

    def test_check_entailment_neutral(self, nli_service_with_mock, mock_pipeline):
        """Test check_entailment detects neutral."""
        mock_pipeline.return_value = [{"label": "NEUTRAL", "score": 0.75}]

        result = nli_service_with_mock.check_entailment(
            premise="def foo(): pass",
            hypothesis="The weather is nice"
        )

        assert result.label == "neutral"
        assert result.score == 0.75
        assert result.entailment_score == 0.5

    def test_verify_claim_verified(self, nli_service_with_mock, mock_pipeline):
        """Test verify_claim returns verified for entailed claim."""
        mock_pipeline.return_value = [{"label": "ENTAILMENT", "score": 0.85}]

        result = nli_service_with_mock.verify_claim(
            claim="UserService handles authentication",
            evidence="class UserService:\n    def authenticate(self, user, password): ...",
            citation="services/user.py:10",
            threshold=0.6
        )

        assert result.verified is True
        assert result.confidence == 0.85
        assert "supported" in result.reason.lower()

    def test_verify_claim_rejected_contradiction(self, nli_service_with_mock, mock_pipeline):
        """Test verify_claim rejects contradicted claim."""
        mock_pipeline.return_value = [{"label": "CONTRADICTION", "score": 0.9}]

        result = nli_service_with_mock.verify_claim(
            claim="UserService is a database",
            evidence="class UserService:\n    def authenticate(self): pass",
            citation="services/user.py:10",
            threshold=0.6
        )

        assert result.verified is False
        assert "contradict" in result.reason.lower()

    def test_verify_claim_rejected_low_confidence(self, nli_service_with_mock, mock_pipeline):
        """Test verify_claim rejects low confidence entailment."""
        mock_pipeline.return_value = [{"label": "ENTAILMENT", "score": 0.4}]

        result = nli_service_with_mock.verify_claim(
            claim="UserService handles auth",
            evidence="class UserService: pass",
            citation="user.py:1",
            threshold=0.6
        )

        assert result.verified is False
        assert "confidence" in result.reason.lower() or "0.4" in result.reason

    def test_verify_claim_empty_evidence(self, nli_service_with_mock):
        """Test verify_claim handles empty evidence."""
        result = nli_service_with_mock.verify_claim(
            claim="Some claim",
            evidence="",
            citation="file.py:1"
        )

        assert result.verified is False
        assert "no evidence" in result.reason.lower()

    def test_verify_claims_batch(self, nli_service_with_mock, mock_pipeline):
        """Test batch claim verification."""
        # Mock different responses for different calls
        mock_pipeline.side_effect = [
            [{"label": "ENTAILMENT", "score": 0.9}],
            [{"label": "CONTRADICTION", "score": 0.85}],
            [{"label": "NEUTRAL", "score": 0.7}],
        ]

        claims = [
            {"claim": "Claim 1", "citation": "file1.py:1"},
            {"claim": "Claim 2", "citation": "file2.py:2"},
            {"claim": "Claim 3", "citation": "file3.py:3"},
        ]
        evidence_map = {
            "file1.py:1": "evidence for claim 1",
            "file2.py:2": "evidence for claim 2",
            "file3.py:3": "evidence for claim 3",
        }

        results = nli_service_with_mock.verify_claims_batch(
            claims=claims,
            evidence_map=evidence_map,
            threshold=0.6
        )

        assert len(results) == 3
        assert results[0].verified is True  # Entailment
        assert results[1].verified is False  # Contradiction
        assert results[2].verified is False  # Neutral


class TestNLIServiceLabelMapping:
    """Tests for label normalization."""

    @pytest.fixture
    def service(self):
        """Create service for testing."""
        return NLIService(enabled=False)

    def test_label_mapping_uppercase(self, service):
        """Test uppercase label mapping."""
        assert service.LABEL_MAPPINGS["ENTAILMENT"] == "entailment"
        assert service.LABEL_MAPPINGS["NEUTRAL"] == "neutral"
        assert service.LABEL_MAPPINGS["CONTRADICTION"] == "contradiction"

    def test_label_mapping_lowercase(self, service):
        """Test lowercase label mapping."""
        assert service.LABEL_MAPPINGS["entailment"] == "entailment"
        assert service.LABEL_MAPPINGS["neutral"] == "neutral"
        assert service.LABEL_MAPPINGS["contradiction"] == "contradiction"

    def test_label_mapping_numeric(self, service):
        """Test numeric label mapping (some models use this)."""
        assert service.LABEL_MAPPINGS["0"] == "contradiction"
        assert service.LABEL_MAPPINGS["1"] == "neutral"
        assert service.LABEL_MAPPINGS["2"] == "entailment"


class TestGetNLIServiceSingleton:
    """Tests for singleton pattern."""

    def test_get_nli_service_returns_instance(self):
        """Test get_nli_service returns an NLIService instance."""
        # Reset singleton
        import jeeves_infra.memory.services.nli_service as nli_module
        nli_module._nli_service_instance = None

        service = get_nli_service(enabled=False)
        assert isinstance(service, NLIService)

    def test_get_nli_service_returns_same_instance(self):
        """Test get_nli_service returns same instance on subsequent calls."""
        # Reset singleton
        import jeeves_infra.memory.services.nli_service as nli_module
        nli_module._nli_service_instance = None

        service1 = get_nli_service(enabled=False)
        service2 = get_nli_service(enabled=False)

        assert service1 is service2


class TestNLIServiceErrorHandling:
    """Tests for error handling."""

    def test_check_entailment_handles_pipeline_error(self):
        """Test check_entailment handles pipeline errors gracefully."""
        service = NLIService(enabled=False)
        service._pipeline = MagicMock(side_effect=Exception("Pipeline error"))
        service._initialized = True
        service.enabled = True

        result = service.check_entailment("premise", "hypothesis")

        # Should return neutral on error (fail open)
        assert result.label == "neutral"
        assert result.score == 0.5

    def test_verify_claim_handles_nli_error(self):
        """Test verify_claim handles NLI errors gracefully."""
        service = NLIService(enabled=False)
        service._pipeline = MagicMock(side_effect=Exception("NLI error"))
        service._initialized = True
        service.enabled = True

        result = service.verify_claim(
            claim="test claim",
            evidence="test evidence",
            citation="test.py:1"
        )

        # Should handle error gracefully
        assert result.nli_result.label == "neutral"


class TestNLIServiceStats:
    """Tests for service statistics."""

    def test_get_stats(self):
        """Test get_stats returns expected fields."""
        service = NLIService(enabled=False)

        stats = service.get_stats()

        assert "enabled" in stats
        assert "initialized" in stats
        assert "model" in stats
        assert "device" in stats
        assert stats["enabled"] is False
        assert stats["model"] == NLIService.DEFAULT_MODEL
