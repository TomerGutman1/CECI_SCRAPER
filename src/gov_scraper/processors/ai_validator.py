"""AI response validator for semantic validation and hallucination detection."""

import re
import logging
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of AI validation process."""
    is_valid: bool
    confidence_score: float
    errors: List[str]
    warnings: List[str]
    suggestions: List[str]


@dataclass
class SemanticAlignment:
    """Measures semantic alignment between different AI outputs."""
    tag_content_overlap: float  # Keyword overlap between tags and content
    summary_tag_alignment: float  # Semantic alignment between summary and tags
    operativity_content_match: float  # How well operativity matches content indicators
    overall_coherence: float  # Overall coherence score


class AIResponseValidator:
    """
    Validates AI responses for hallucinations and semantic consistency.

    Features:
    - Tag-content relevance checking (30% keyword overlap)
    - Summary-tag alignment verification
    - Confidence threshold enforcement
    - Hallucination detection through cross-validation
    - Hebrew-specific validation rules
    """

    def __init__(self, policy_areas: List[str], government_bodies: List[str]):
        """Initialize with authorized tag lists."""
        self.policy_areas = set(policy_areas)
        self.government_bodies = set(government_bodies)

        # Define confidence thresholds
        self.min_confidence_summary = 0.6
        self.min_confidence_operativity = 0.7
        self.min_confidence_tags = 0.5

        # Hebrew stop words for content analysis
        self.hebrew_stop_words = {
            "ו", "ה", "של", "את", "על", "עם", "או", "גם", "כל", "לא", "אם",
            "כי", "זה", "זו", "אל", "אלה", "אלו", "היא", "הוא", "הם", "הן",
            "אני", "אתה", "את", "אנחנו", "אתם", "אתן", "יש", "אין", "היה",
            "תהיה", "באמצעות", "לגבי", "אודות", "ביחס", "במסגרת"
        }

        # Operativity keywords for validation
        self.operative_keywords = {
            "להקצות", "למנות", "להקים", "לאשר", "לחייב", "לקבוע", "להורות",
            "לבצע", "להטיל", "לייעד", "לפעול", "לבטל", "לעדכן", "לשנות"
        }

        self.declarative_keywords = {
            "רושמת", "מביעה", "מכירה", "קוראת", "רואה", "מדגישה", "מחזקת",
            "תומכת", "מעודדת", "מציינת", "מבהירה", "מדגישה", "הערכה", "חשיבות"
        }

    def _extract_keywords(self, text: str, min_length: int = 3) -> Set[str]:
        """Extract meaningful keywords from Hebrew text."""
        # Clean text
        text = re.sub(r'[^\u0590-\u05FF\s]', ' ', text.lower())  # Hebrew only
        words = text.split()

        keywords = set()
        for word in words:
            word = word.strip()
            if len(word) >= min_length and word not in self.hebrew_stop_words:
                keywords.add(word)

        return keywords

    def _calculate_keyword_overlap(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts based on keywords."""
        keywords1 = self._extract_keywords(text1)
        keywords2 = self._extract_keywords(text2)

        if not keywords1 and not keywords2:
            return 1.0  # Both empty
        if not keywords1 or not keywords2:
            return 0.0  # One empty

        intersection = len(keywords1 & keywords2)
        union = len(keywords1 | keywords2)

        return intersection / union if union > 0 else 0.0

    def _validate_tag_content_relevance(self, tags: List[str], content: str, title: str) -> float:
        """Validate that tags are relevant to content (30% keyword overlap target)."""
        if not tags:
            return 0.0

        # Combine title and content for analysis
        full_text = f"{title} {content}"
        content_keywords = self._extract_keywords(full_text)

        if not content_keywords:
            return 0.0

        tag_relevance_scores = []

        for tag in tags:
            tag_keywords = self._extract_keywords(tag)
            if not tag_keywords:
                tag_relevance_scores.append(0.0)
                continue

            # Calculate overlap
            overlap = self._calculate_keyword_overlap(tag, full_text)
            tag_relevance_scores.append(overlap)

        # Return average relevance
        avg_relevance = sum(tag_relevance_scores) / len(tag_relevance_scores)
        return avg_relevance

    def _validate_summary_tag_alignment(self, summary: str, tags: List[str]) -> float:
        """Validate that summary aligns with selected tags."""
        if not summary or not tags:
            return 0.0

        # Calculate semantic overlap between summary and tags
        combined_tags = " ".join(tags)
        alignment_score = self._calculate_keyword_overlap(summary, combined_tags)

        # Summary should reflect the main topics indicated by tags
        return alignment_score

    def _validate_operativity_classification(self, operativity: str, content: str) -> float:
        """Validate operativity classification against content indicators."""
        content_lower = content.lower()

        operative_count = sum(1 for keyword in self.operative_keywords
                             if keyword in content_lower)
        declarative_count = sum(1 for keyword in self.declarative_keywords
                               if keyword in content_lower)

        total_indicators = operative_count + declarative_count

        if total_indicators == 0:
            return 0.5  # No clear indicators

        operative_ratio = operative_count / total_indicators

        if operativity == "אופרטיבית":
            # Operative classification should have more operative indicators
            return operative_ratio
        else:  # דקלרטיבית
            # Declarative classification should have more declarative indicators
            return 1.0 - operative_ratio

    def _detect_tag_hallucinations(self, tags: List[str], authorized_tags: Set[str]) -> List[str]:
        """Detect tags that don't exist in authorized lists."""
        hallucinations = []

        for tag in tags:
            if tag not in authorized_tags:
                # Check if it's a close match (possible typo)
                close_matches = [auth_tag for auth_tag in authorized_tags
                               if self._calculate_keyword_overlap(tag, auth_tag) > 0.7]

                if close_matches:
                    hallucinations.append(f"Possible typo: '{tag}' -> suggested: {close_matches[0]}")
                else:
                    hallucinations.append(f"Unknown tag: '{tag}'")

        return hallucinations

    def _validate_special_categories(self, special_categories: List[str], content: str, date: str = None) -> Tuple[bool, List[str]]:
        """Validate special category selections."""
        errors = []

        # Special categories should only be applied when explicitly relevant
        special_keywords = {
            "החברה הערבית": ["ערב", "ערבי", "בדואי", "922", "550"],
            "החברה החרדית": ["חרד", "חרדי", "ישיבה", "כולל", "גיוס חרדים"],
            "נשים ומגדר": ["נש", "מגדר", "שוויון", "הטרדה"],
            "שיקום הצפון": ["צפון", "גליל", "מטולה", "קריית שמונה"],
            "שיקום הדרום": ["דרום", "עוטף", "עזה", "תקומה", "חטוף"]
        }

        content_lower = content.lower()

        for category in special_categories:
            if category in special_keywords:
                required_keywords = special_keywords[category]
                found_keywords = [kw for kw in required_keywords if kw in content_lower]

                if not found_keywords:
                    errors.append(f"Special category '{category}' lacks supporting keywords in content")

            # Date-based validation for war-related categories
            if category in ["שיקום הצפון", "שיקום הדרום"] and date:
                try:
                    year = int(date.split('-')[0])
                    if year < 2023:
                        errors.append(f"Category '{category}' is anachronistic for date {date}")
                except:
                    pass  # Skip date validation if date format is unclear

        return len(errors) == 0, errors

    def validate_unified_result(self, result, content: str, title: str) -> ValidationResult:
        """
        Comprehensive validation of unified AI result.

        Args:
            result: AIProcessingResult from unified processing
            content: Original decision content
            title: Original decision title

        Returns:
            ValidationResult with validation outcome
        """
        errors = []
        warnings = []
        suggestions = []

        # 1. Confidence threshold validation
        if result.summary_confidence < self.min_confidence_summary:
            errors.append(f"Summary confidence {result.summary_confidence:.2f} below threshold {self.min_confidence_summary}")

        if result.operativity_confidence < self.min_confidence_operativity:
            warnings.append(f"Operativity confidence {result.operativity_confidence:.2f} below threshold {self.min_confidence_operativity}")

        if result.tags_confidence < self.min_confidence_tags:
            warnings.append(f"Tags confidence {result.tags_confidence:.2f} below threshold {self.min_confidence_tags}")

        # 2. Tag hallucination detection
        policy_hallucinations = self._detect_tag_hallucinations(result.policy_areas, self.policy_areas)
        if policy_hallucinations:
            errors.extend([f"Policy tag issue: {h}" for h in policy_hallucinations])

        body_hallucinations = self._detect_tag_hallucinations(result.government_bodies, self.government_bodies)
        if body_hallucinations:
            errors.extend([f"Government body issue: {h}" for h in body_hallucinations])

        # 3. Semantic validation
        # Tag-content relevance (30% overlap target)
        tag_relevance = self._validate_tag_content_relevance(
            result.policy_areas, content, title
        )

        if tag_relevance < 0.3:
            warnings.append(f"Low tag-content relevance {tag_relevance:.2f} (target: 0.30)")

        # Summary-tag alignment
        summary_alignment = self._validate_summary_tag_alignment(
            result.summary, result.policy_areas
        )

        if summary_alignment < 0.2:
            warnings.append(f"Low summary-tag alignment {summary_alignment:.2f}")

        # Operativity validation
        operativity_match = self._validate_operativity_classification(
            result.operativity, content
        )

        if operativity_match < 0.4:
            warnings.append(f"Operativity classification may be incorrect (match: {operativity_match:.2f})")

        # 4. Special categories validation
        special_valid, special_errors = self._validate_special_categories(
            result.special_categories, content
        )

        if not special_valid:
            errors.extend(special_errors)

        # 5. Content completeness
        if not result.summary or len(result.summary.strip()) < 10:
            errors.append("Summary is too short or empty")

        if not result.policy_areas:
            errors.append("No policy areas identified")

        # 6. Generate suggestions
        if tag_relevance < 0.2:
            suggestions.append("Consider reviewing tag selections - low relevance to content")

        if len(result.policy_areas) > 3:
            suggestions.append("Consider reducing number of policy tags for better focus")

        # Calculate overall confidence
        overall_confidence = (
            result.summary_confidence * 0.3 +
            result.operativity_confidence * 0.2 +
            result.tags_confidence * 0.3 +
            tag_relevance * 0.2
        )

        # Determine if valid
        is_valid = len(errors) == 0 and overall_confidence >= 0.5

        return ValidationResult(
            is_valid=is_valid,
            confidence_score=overall_confidence,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions
        )

    def validate_individual_field(self, field_name: str, value: Any, context: Dict[str, Any]) -> ValidationResult:
        """Validate individual field for fallback scenarios."""
        errors = []
        warnings = []

        if field_name == "summary":
            if not value or len(str(value).strip()) < 10:
                errors.append("Summary too short")

        elif field_name == "operativity":
            if value not in ["אופרטיבית", "דקלרטיבית"]:
                errors.append(f"Invalid operativity value: {value}")

        elif field_name == "policy_areas":
            if isinstance(value, str):
                tags = [t.strip() for t in value.split(';') if t.strip()]
            else:
                tags = value

            for tag in tags:
                if tag not in self.policy_areas:
                    errors.append(f"Unknown policy tag: {tag}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            confidence_score=0.7,  # Default for individual validation
            errors=errors,
            warnings=warnings,
            suggestions=[]
        )

    def get_validation_stats(self) -> Dict[str, Any]:
        """Get validation statistics for monitoring."""
        return {
            "confidence_thresholds": {
                "summary": self.min_confidence_summary,
                "operativity": self.min_confidence_operativity,
                "tags": self.min_confidence_tags
            },
            "authorized_tags_count": {
                "policy_areas": len(self.policy_areas),
                "government_bodies": len(self.government_bodies)
            }
        }


def create_validator(policy_areas: List[str], government_bodies: List[str]) -> AIResponseValidator:
    """Factory function to create validator."""
    return AIResponseValidator(policy_areas, government_bodies)