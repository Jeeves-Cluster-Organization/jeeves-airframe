"""
Fuzzy matching utilities for text similarity scoring.

Provides multi-strategy fuzzy matching combining:
- Substring matching
- Word-level overlap
- Character-level similarity (SequenceMatcher)
"""

from difflib import SequenceMatcher
from typing import Dict, List, NamedTuple, Optional


class MatchScore(NamedTuple):
    """Detailed scoring breakdown for a fuzzy match."""
    total: float
    substring_score: float
    word_overlap_score: float
    char_similarity_score: float
    matched_field: str  # 'title', 'description', or 'combined'


class FuzzyMatcher:
    """
    Multi-strategy fuzzy text matcher with configurable thresholds.

    Combines three scoring strategies:
    1. Substring matching (exact substring presence)
    2. Word-level overlap (set intersection of words)
    3. Character-level similarity (SequenceMatcher ratio)

    Each strategy is weighted differently based on reliability.
    """

    def __init__(
        self,
        min_score_threshold: float = 0.5,
        substring_weight: float = 1.0,
        word_overlap_weight: float = 0.9,
        char_similarity_weight: float = 0.7
    ):
        """
        Initialize fuzzy matcher with configurable weights.

        Args:
            min_score_threshold: Minimum score to consider a match (0.0-1.0)
            substring_weight: Weight for exact substring matches
            word_overlap_weight: Weight for word-level overlap
            char_similarity_weight: Weight for character-level similarity
        """
        self.min_score_threshold = min_score_threshold
        self.substring_weight = substring_weight
        self.word_overlap_weight = word_overlap_weight
        self.char_similarity_weight = char_similarity_weight

    def score_match(
        self,
        search_query: str,
        target_text: str,
        secondary_text: Optional[str] = None,
        secondary_weight: float = 0.8
    ) -> MatchScore:
        """
        Compute fuzzy match score between query and target text(s).

        Args:
            search_query: Query string to match against
            target_text: Primary text to match (e.g., title)
            secondary_text: Optional secondary text (e.g., description)
            secondary_weight: Weight for secondary text matches (0.0-1.0)

        Returns:
            MatchScore with detailed scoring breakdown
        """
        search_lower = search_query.lower()
        search_words = set(search_lower.split())

        # Score primary text
        primary_score = self._score_single_field(search_lower, search_words, target_text.lower())

        # Score secondary text if provided
        if secondary_text:
            secondary_score = self._score_single_field(
                search_lower,
                search_words,
                secondary_text.lower()
            )
            # Combine scores (prioritize primary over secondary)
            if primary_score >= secondary_score * secondary_weight:
                total_score = primary_score
                matched_field = "title"
            else:
                total_score = secondary_score * secondary_weight
                matched_field = "description"
        else:
            total_score = primary_score
            matched_field = "title"

        return MatchScore(
            total=total_score,
            substring_score=0.0,  # Detailed breakdown not exposed in combined score
            word_overlap_score=0.0,
            char_similarity_score=0.0,
            matched_field=matched_field
        )

    def _score_single_field(self, search_lower: str, search_words: set, target_lower: str) -> float:
        """
        Score a single field using multi-strategy approach.

        Args:
            search_lower: Lowercased search query
            search_words: Set of words from search query
            target_lower: Lowercased target text

        Returns:
            Combined score (0.0-1.0)
        """
        if not target_lower:
            return 0.0

        # Strategy 1: Exact substring match (highest priority)
        substring_score = self.substring_weight if search_lower in target_lower else 0.0

        # Strategy 2: Word-level matching
        target_words = set(target_lower.split())
        word_overlap = len(search_words & target_words) / max(len(search_words), 1)
        word_score = word_overlap * self.word_overlap_weight

        # Strategy 3: Character-level similarity (fallback)
        char_score = SequenceMatcher(None, search_lower, target_lower).ratio()
        char_score *= self.char_similarity_weight

        # Return best score from all strategies
        return max(substring_score, word_score, char_score)

    def find_best_matches(
        self,
        search_query: str,
        candidates: List[Dict[str, str]],
        primary_field: str = "title",
        secondary_field: Optional[str] = None,
        limit: int = 5
    ) -> List[tuple[Dict[str, str], float]]:
        """
        Find best fuzzy matches from a list of candidates.

        Args:
            search_query: Query string to match
            candidates: List of dictionaries containing text fields
            primary_field: Key for primary text field (e.g., "title")
            secondary_field: Optional key for secondary field (e.g., "description")
            limit: Maximum number of matches to return

        Returns:
            List of (candidate, score) tuples, sorted by score descending
        """
        scored_candidates = []

        for candidate in candidates:
            primary_text = candidate.get(primary_field, "")
            secondary_text = candidate.get(secondary_field, "") if secondary_field else None

            match_score = self.score_match(
                search_query,
                primary_text,
                secondary_text
            )

            # Filter by threshold
            if match_score.total > self.min_score_threshold:
                scored_candidates.append((candidate, match_score.total))

        # Sort by score descending and apply limit
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        return scored_candidates[:limit]


# Convenience function for simple fuzzy matching
def fuzzy_match_score(query: str, target: str, threshold: float = 0.5) -> float:
    """
    Compute simple fuzzy match score between query and target.

    Args:
        query: Query string
        target: Target string to match against
        threshold: Minimum score threshold (not enforced, just for reference)

    Returns:
        Match score (0.0-1.0)
    """
    matcher = FuzzyMatcher(min_score_threshold=threshold)
    score = matcher.score_match(query, target)
    return score.total
