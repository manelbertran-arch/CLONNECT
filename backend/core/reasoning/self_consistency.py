"""
Self-Consistency Reasoning Module for Clonnect

Validates LLM responses by generating multiple samples and measuring consistency.
If responses are consistent -> high confidence -> use response
If responses vary -> low confidence -> fallback to safe response

Based on: "Self-Consistency Improves Chain of Thought Reasoning in Language Models"
(Wang et al., 2022)
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_NUM_SAMPLES = 3  # Number of response samples to generate
DEFAULT_CONFIDENCE_THRESHOLD = 0.6  # Minimum confidence to use response
DEFAULT_SIMILARITY_THRESHOLD = 0.7  # Minimum similarity between responses


@dataclass
class ConsistencyResult:
    """Result of self-consistency check"""
    response: str  # The selected response
    confidence: float  # Confidence score (0.0 - 1.0)
    is_consistent: bool  # Whether responses were consistent enough
    num_samples: int  # Number of samples generated
    similarity_scores: List[float]  # Pairwise similarity scores
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class SelfConsistencyValidator:
    """
    Validates responses using self-consistency checking.

    How it works:
    1. Generate N response samples for the same query
    2. Compare responses for semantic similarity
    3. If similar -> high confidence -> use best response
    4. If divergent -> low confidence -> use fallback
    """

    def __init__(
        self,
        llm_client,
        num_samples: int = DEFAULT_NUM_SAMPLES,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    ):
        self.llm = llm_client
        self.num_samples = num_samples
        self.confidence_threshold = confidence_threshold
        self.similarity_threshold = similarity_threshold

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two texts.
        Uses SequenceMatcher for character-level similarity.
        """
        if not text1 or not text2:
            return 0.0

        # Normalize texts
        t1 = text1.lower().strip()
        t2 = text2.lower().strip()

        # Use SequenceMatcher for similarity
        return SequenceMatcher(None, t1, t2).ratio()

    def _extract_key_elements(self, text: str) -> set:
        """
        Extract key semantic elements from text.
        Used for semantic similarity comparison.
        """
        if not text:
            return set()

        # Simple tokenization (could be enhanced with NLP)
        words = text.lower().split()

        # Filter stopwords (basic list)
        stopwords = {
            'el', 'la', 'los', 'las', 'un', 'una', 'de', 'que', 'y', 'a',
            'en', 'es', 'por', 'con', 'para', 'se', 'su', 'al', 'lo',
            'the', 'a', 'an', 'of', 'to', 'and', 'in', 'is', 'for', 'it'
        }

        return {w for w in words if len(w) > 2 and w not in stopwords}

    def _semantic_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate semantic similarity using key element overlap.
        """
        elements1 = self._extract_key_elements(text1)
        elements2 = self._extract_key_elements(text2)

        if not elements1 or not elements2:
            return 0.0

        # Jaccard similarity
        intersection = len(elements1 & elements2)
        union = len(elements1 | elements2)

        return intersection / union if union > 0 else 0.0

    def _combined_similarity(self, text1: str, text2: str) -> float:
        """
        Combined character and semantic similarity.
        """
        char_sim = self._calculate_similarity(text1, text2)
        semantic_sim = self._semantic_similarity(text1, text2)

        # Weighted average (character similarity more reliable)
        return 0.6 * char_sim + 0.4 * semantic_sim

    async def _generate_samples(
        self,
        messages: List[Dict[str, str]],
        num_samples: int,
        **kwargs
    ) -> List[str]:
        """
        Generate multiple response samples in parallel.
        """
        # Use higher temperature for diversity
        sample_kwargs = {**kwargs, 'temperature': 0.8}

        async def generate_one():
            try:
                return await self.llm.chat(messages, **sample_kwargs)
            except Exception as e:
                logger.warning(f"Sample generation failed: {e}")
                return None

        # Generate samples in parallel
        tasks = [generate_one() for _ in range(num_samples)]
        results = await asyncio.gather(*tasks)

        # Filter out failed samples
        return [r.strip() for r in results if r]

    def _calculate_consistency(self, samples: List[str]) -> Tuple[float, List[float]]:
        """
        Calculate overall consistency score from samples.

        Returns:
            (confidence, similarity_scores)
        """
        if len(samples) < 2:
            return 1.0, []  # Single sample = full confidence

        # Calculate pairwise similarities
        similarity_scores = []
        for i in range(len(samples)):
            for j in range(i + 1, len(samples)):
                sim = self._combined_similarity(samples[i], samples[j])
                similarity_scores.append(sim)

        if not similarity_scores:
            return 1.0, []

        # Average similarity as confidence
        avg_similarity = sum(similarity_scores) / len(similarity_scores)

        # Adjust confidence based on consistency
        # High variance = low confidence
        if len(similarity_scores) > 1:
            variance = sum((s - avg_similarity) ** 2 for s in similarity_scores) / len(similarity_scores)
            consistency_penalty = min(0.2, variance)
            confidence = avg_similarity - consistency_penalty
        else:
            confidence = avg_similarity

        return max(0.0, min(1.0, confidence)), similarity_scores

    def _select_best_response(self, samples: List[str]) -> str:
        """
        Select the best response from samples.
        Prefers the most "central" response (most similar to others).
        """
        if not samples:
            return ""

        if len(samples) == 1:
            return samples[0]

        # Calculate average similarity for each sample
        avg_similarities = []
        for i, sample in enumerate(samples):
            sims = []
            for j, other in enumerate(samples):
                if i != j:
                    sims.append(self._combined_similarity(sample, other))
            avg_sim = sum(sims) / len(sims) if sims else 0
            avg_similarities.append((avg_sim, sample))

        # Return the sample with highest average similarity (most central)
        return max(avg_similarities, key=lambda x: x[0])[1]

    async def validate(
        self,
        messages: List[Dict[str, str]],
        initial_response: Optional[str] = None,
        **kwargs
    ) -> ConsistencyResult:
        """
        Validate a response using self-consistency checking.

        Args:
            messages: The conversation messages (system + user)
            initial_response: Optional pre-generated response to include
            **kwargs: Additional LLM parameters

        Returns:
            ConsistencyResult with confidence and selected response
        """
        samples = []

        # Include initial response if provided
        if initial_response:
            samples.append(initial_response.strip())

        # Generate additional samples
        num_to_generate = self.num_samples - len(samples)
        if num_to_generate > 0:
            generated = await self._generate_samples(messages, num_to_generate, **kwargs)
            samples.extend(generated)

        if not samples:
            logger.error("No samples generated for self-consistency check")
            return ConsistencyResult(
                response="",
                confidence=0.0,
                is_consistent=False,
                num_samples=0,
                similarity_scores=[]
            )

        # Calculate consistency
        confidence, similarity_scores = self._calculate_consistency(samples)

        # Select best response
        best_response = self._select_best_response(samples)

        # Determine if consistent enough
        is_consistent = confidence >= self.confidence_threshold

        logger.info(
            f"Self-consistency: confidence={confidence:.2f}, "
            f"samples={len(samples)}, consistent={is_consistent}"
        )

        return ConsistencyResult(
            response=best_response,
            confidence=confidence,
            is_consistent=is_consistent,
            num_samples=len(samples),
            similarity_scores=similarity_scores,
            metadata={
                "threshold": self.confidence_threshold,
                "all_samples": samples if len(samples) <= 5 else samples[:5]
            }
        )

    async def validate_response(
        self,
        query: str,
        response: str,
        system_prompt: str = "",
        **kwargs
    ) -> ConsistencyResult:
        """
        Convenience method to validate a single query-response pair.

        Args:
            query: User's message
            response: Generated response to validate
            system_prompt: System prompt used
            **kwargs: Additional LLM parameters

        Returns:
            ConsistencyResult
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": query})

        return await self.validate(
            messages=messages,
            initial_response=response,
            **kwargs
        )


# Singleton instance
_validator: Optional[SelfConsistencyValidator] = None


def get_self_consistency_validator(
    llm_client=None,
    **kwargs
) -> SelfConsistencyValidator:
    """
    Get singleton instance of SelfConsistencyValidator.

    Args:
        llm_client: LLM client to use (required on first call)
        **kwargs: Configuration options

    Returns:
        SelfConsistencyValidator instance
    """
    global _validator

    if _validator is None:
        if llm_client is None:
            from core.llm import get_llm_client
            llm_client = get_llm_client()
        _validator = SelfConsistencyValidator(llm_client, **kwargs)

    return _validator


def reset_validator():
    """Reset singleton (for testing)"""
    global _validator
    _validator = None
