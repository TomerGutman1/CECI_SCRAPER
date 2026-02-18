"""Unified AI processor for Israeli Government Decisions - Single consolidated AI call."""

import json
import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from google import genai
from google.genai import types

from ..config import GEMINI_API_KEY, GEMINI_MODEL, MAX_RETRIES, RETRY_DELAY
from .ai_prompts import (
    UNIFIED_PROCESSING_PROMPT,
    OPERATIVITY_EXAMPLES,
    POLICY_TAG_EXAMPLES,
    validate_confidence_scores
)
from .ai_validator import AIResponseValidator

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class AIProcessingResult:
    """Structured result from unified AI processing."""
    summary: str
    operativity: str
    policy_areas: List[str]
    government_bodies: List[str]
    locations: List[str]
    special_categories: List[str]

    # Confidence scores (0.0-1.0)
    summary_confidence: float
    operativity_confidence: float
    tags_confidence: float

    # Evidence tracking
    summary_evidence: str  # Quote from source
    operativity_evidence: str
    tags_evidence: List[str]  # List of supporting quotes

    # Processing metadata
    processing_time: float
    api_calls_used: int
    fallback_used: bool = False


class UnifiedAIProcessor:
    """
    Unified AI processor that extracts all decision fields in a single API call.

    Features:
    - Single consolidated prompt for all extractions
    - Structured JSON output with confidence scores
    - Evidence tracking with source quotes
    - Smart fallback to individual calls if needed
    - Performance optimizations (caching, batching)
    """

    def __init__(self, policy_areas: List[str], government_bodies: List[str]):
        """Initialize with authorized tag lists."""
        self.policy_areas = policy_areas
        self.government_bodies = government_bodies
        self.validator = AIResponseValidator(policy_areas, government_bodies)
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.response_cache = {}  # Simple cache for retries

    def _get_smart_content(self, content: str, max_length: int = 4000) -> str:
        """
        Extract content intelligently for long decisions.
        Takes 70% from beginning and 30% from end for better context.
        """
        if len(content) <= max_length:
            return content

        head_size = int(max_length * 0.7)
        tail_size = max_length - head_size

        return f"{content[:head_size]}\n\n[...תוכן מקוצץ...]\n\n{content[-tail_size:]}"

    def _make_unified_request(self, prompt: str, max_tokens: int = 1500) -> str:
        """Make unified API request with retry logic and caching."""
        cache_key = hash(prompt)
        if cache_key in self.response_cache:
            logger.info("Using cached response for unified request")
            return self.response_cache[cache_key]

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Making unified Gemini request (attempt {attempt + 1}/{MAX_RETRIES})")

                response = self.client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="אתה מנתח מקצועי של החלטות ממשלה ישראליות. החזר תמיד JSON מובנה ומדויק.",
                        max_output_tokens=max_tokens,
                        temperature=0.1,  # Low temperature for consistency
                    ),
                )

                if not response.text:
                    raise Exception("Gemini returned empty response")

                result = response.text.strip()
                self.response_cache[cache_key] = result
                logger.info(f"Unified request successful (attempt {attempt + 1})")
                return result

            except Exception as e:
                logger.warning(f"Unified request failed (attempt {attempt + 1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    raise Exception(f"Unified AI request failed after {MAX_RETRIES} attempts: {e}")

    def _parse_unified_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON response from unified prompt."""
        try:
            # Clean up common AI response patterns
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            response = response.strip()

            parsed = json.loads(response)

            # Validate required fields
            required_fields = [
                'summary', 'operativity', 'policy_areas', 'government_bodies',
                'locations', 'special_categories', 'confidence_scores', 'evidence'
            ]

            for field in required_fields:
                if field not in parsed:
                    raise ValueError(f"Missing required field: {field}")

            return parsed

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse unified JSON response: {e}")
            logger.error(f"Response was: {response[:500]}")
            raise ValueError(f"Invalid JSON response from AI: {e}")

    def _extract_confidence_scores(self, parsed: Dict[str, Any]) -> Tuple[float, float, float]:
        """Extract and validate confidence scores."""
        confidence = parsed.get('confidence_scores', {})

        summary_conf = confidence.get('summary', 0.5)
        operativity_conf = confidence.get('operativity', 0.5)
        tags_conf = confidence.get('tags', 0.5)

        # Validate confidence scores are in range [0, 1]
        summary_conf = max(0.0, min(1.0, summary_conf))
        operativity_conf = max(0.0, min(1.0, operativity_conf))
        tags_conf = max(0.0, min(1.0, tags_conf))

        return summary_conf, operativity_conf, tags_conf

    def _create_processing_result(self, parsed: Dict[str, Any], processing_time: float) -> AIProcessingResult:
        """Create structured result from parsed response."""

        # Extract confidence scores
        summary_conf, operativity_conf, tags_conf = self._extract_confidence_scores(parsed)

        # Extract evidence
        evidence = parsed.get('evidence', {})

        return AIProcessingResult(
            summary=parsed['summary'],
            operativity=parsed['operativity'],
            policy_areas=parsed['policy_areas'],
            government_bodies=parsed['government_bodies'],
            locations=parsed['locations'],
            special_categories=parsed['special_categories'],
            summary_confidence=summary_conf,
            operativity_confidence=operativity_conf,
            tags_confidence=tags_conf,
            summary_evidence=evidence.get('summary_quote', ''),
            operativity_evidence=evidence.get('operativity_quote', ''),
            tags_evidence=evidence.get('tags_quotes', []),
            processing_time=processing_time,
            api_calls_used=1,
            fallback_used=False
        )

    def process_decision_unified(
        self,
        decision_content: str,
        decision_title: str,
        decision_date: str = None
    ) -> AIProcessingResult:
        """
        Process decision with unified AI call.

        Args:
            decision_content: Full decision text
            decision_title: Decision title
            decision_date: Optional decision date for context

        Returns:
            AIProcessingResult with all extracted fields and metadata
        """
        start_time = time.time()

        logger.info("Starting unified AI processing")

        try:
            # Prepare content for processing
            smart_content = self._get_smart_content(decision_content, 4000)

            # Build unified prompt
            prompt = UNIFIED_PROCESSING_PROMPT.format(
                policy_areas=" | ".join(self.policy_areas),
                government_bodies=" | ".join(self.government_bodies),
                operativity_examples=OPERATIVITY_EXAMPLES,
                policy_examples=POLICY_TAG_EXAMPLES,
                decision_title=decision_title,
                decision_content=smart_content,
                decision_date=f"תאריך: {decision_date}" if decision_date else ""
            )

            # Make unified API call
            response = self._make_unified_request(prompt, max_tokens=1500)

            # Parse response
            parsed = self._parse_unified_response(response)

            # Create result
            processing_time = time.time() - start_time
            result = self._create_processing_result(parsed, processing_time)

            # Validate result with semantic checks
            validation_result = self.validator.validate_unified_result(
                result, decision_content, decision_title
            )

            if not validation_result.is_valid:
                logger.warning(f"Validation failed: {validation_result.errors}")
                # Could trigger fallback here if needed

            logger.info(f"Unified processing completed in {processing_time:.2f}s")
            return result

        except Exception as e:
            logger.error(f"Unified processing failed: {e}")
            # Fallback to individual calls
            return self._fallback_to_individual_calls(
                decision_content, decision_title, decision_date, start_time
            )

    def _fallback_to_individual_calls(
        self,
        decision_content: str,
        decision_title: str,
        decision_date: str,
        start_time: float
    ) -> AIProcessingResult:
        """Fallback to individual AI calls if unified call fails."""
        logger.info("Falling back to individual AI calls")

        try:
            # Import individual functions from existing ai.py
            from .ai import (
                generate_summary,
                generate_operativity,
                generate_policy_area_tags_strict,
                generate_government_body_tags_validated,
                generate_location_tags,
                generate_special_category_tags
            )

            # Make individual calls (5-6 API calls)
            summary = generate_summary(decision_content, decision_title)
            operativity = generate_operativity(decision_content)
            policy_areas = generate_policy_area_tags_strict(decision_content, decision_title, summary)
            government_bodies = generate_government_body_tags_validated(decision_content, decision_title, summary)
            locations = generate_location_tags(decision_content, decision_title)
            special_categories = generate_special_category_tags(decision_content, decision_title, summary, decision_date)

            processing_time = time.time() - start_time

            # Convert to structured format
            return AIProcessingResult(
                summary=summary,
                operativity=operativity,
                policy_areas=policy_areas.split(';') if policy_areas else [],
                government_bodies=government_bodies.split(';') if government_bodies else [],
                locations=locations.split(',') if locations else [],
                special_categories=special_categories,
                summary_confidence=0.7,  # Default confidence for fallback
                operativity_confidence=0.7,
                tags_confidence=0.7,
                summary_evidence="",  # No evidence tracking for fallback
                operativity_evidence="",
                tags_evidence=[],
                processing_time=processing_time,
                api_calls_used=6,  # Individual calls
                fallback_used=True
            )

        except Exception as e:
            logger.error(f"Fallback processing also failed: {e}")
            raise Exception(f"Both unified and fallback processing failed: {e}")

    def process_decision_batch(self, decisions: List[Dict[str, str]]) -> List[AIProcessingResult]:
        """
        Process multiple decisions efficiently.

        Note: Current implementation processes sequentially.
        Future versions could implement true batching.
        """
        results = []

        for i, decision in enumerate(decisions):
            logger.info(f"Processing decision {i+1}/{len(decisions)}")

            try:
                result = self.process_decision_unified(
                    decision['decision_content'],
                    decision['decision_title'],
                    decision.get('decision_date')
                )
                results.append(result)

            except Exception as e:
                logger.error(f"Failed to process decision {i+1}: {e}")
                # Could add empty result or skip
                continue

        return results

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get processing performance statistics."""
        return {
            "cache_size": len(self.response_cache),
            "cache_hit_rate": "N/A",  # Would need hit tracking
            "average_processing_time": "N/A",  # Would need history
        }


def create_unified_processor(policy_areas: List[str], government_bodies: List[str]) -> UnifiedAIProcessor:
    """Factory function to create unified processor."""
    return UnifiedAIProcessor(policy_areas, government_bodies)