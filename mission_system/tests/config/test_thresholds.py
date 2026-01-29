"""Test Confidence and Threshold Configuration.

Per Engineering Improvement Plan v4.2 - Phase C1: Test Config Centralization.

This module centralizes all confidence thresholds and scoring values used in tests.
Instead of hardcoding values like 0.95, 0.8, 0.5 throughout test files, import from here.

Usage:
    from mission_system.tests.config.test_thresholds import TEST_HIGH_CONFIDENCE, TEST_LOW_CONFIDENCE

Constitutional Compliance:
- Amendment I: Repo Hygiene - Single source of truth for thresholds
- P6: Testable - Consistent threshold values across all tests
"""

# =============================================================================
# Confidence Levels (for test assertions)
# =============================================================================

# High confidence - used for successful operations, approvals
TEST_HIGH_CONFIDENCE = 0.95

# Medium-high confidence - used for typical successful responses
TEST_MEDIUM_HIGH_CONFIDENCE = 0.9

# Medium confidence - used for acceptable but not optimal results
TEST_MEDIUM_CONFIDENCE = 0.8

# Low confidence - used for edge cases, uncertain results
TEST_LOW_CONFIDENCE = 0.5

# Below threshold - used for testing rejection/retry scenarios
TEST_BELOW_THRESHOLD_CONFIDENCE = 0.3

# Very low confidence - used for failure scenarios
TEST_FAILURE_CONFIDENCE = 0.1


# =============================================================================
# Agent-Specific Thresholds (for test fixtures)
# =============================================================================

# Critic approval threshold (above this = accept without changes)
TEST_CRITIC_APPROVAL_THRESHOLD = 0.95

# Critic retry threshold (below this = retry)
TEST_CRITIC_RETRY_THRESHOLD = 0.6

# Planner clarification threshold
TEST_PLANNER_CLARIFICATION_THRESHOLD = 0.7

# Meta-validator pass threshold
TEST_META_VALIDATOR_PASS_THRESHOLD = 0.9


# =============================================================================
# Fuzzy Matching Thresholds (for search tests)
# =============================================================================

# Minimum fuzzy match score to consider a candidate
TEST_FUZZY_MATCH_MIN_SCORE = 0.5

# High fuzzy match score (strong match)
TEST_FUZZY_MATCH_HIGH_SCORE = 0.9

# Semantic search minimum similarity
TEST_SEMANTIC_SEARCH_MIN_SIMILARITY = 0.5


# =============================================================================
# Test Scenario Scores (for specific test cases)
# =============================================================================

# Score for exact string matches in tests
TEST_EXACT_MATCH_SCORE = 1.0

# Score for substring matches in tests
TEST_SUBSTRING_MATCH_SCORE = 0.9

# Score for partial matches in tests
TEST_PARTIAL_MATCH_SCORE = 0.7

# Score for weak matches in tests
TEST_WEAK_MATCH_SCORE = 0.4


# =============================================================================
# Embedding/Vector Thresholds
# =============================================================================

# Embedding dimension for all-MiniLM-L6-v2 (commonly used in tests)
TEST_EMBEDDING_DIMENSION = 384

# Minimum cosine similarity for related items
TEST_COSINE_SIMILARITY_MIN = 0.5

# High cosine similarity (very related)
TEST_COSINE_SIMILARITY_HIGH = 0.9

# Identity similarity (same text should have this)
TEST_COSINE_SIMILARITY_IDENTITY = 0.99
