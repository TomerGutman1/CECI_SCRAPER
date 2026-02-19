"""Summary-Tag Alignment Validator for Israeli Government Decisions.

This module provides cross-validation to ensure summaries and tags address
the same aspects of decisions, fixing the 86% alignment mismatch issue.
"""

import logging
import re
from typing import List, Dict, Tuple, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AlignmentValidationResult:
    """Result of summary-tag alignment validation."""
    is_aligned: bool
    alignment_score: float  # 0.0-1.0
    issues: List[str]  # Specific alignment problems found
    suggestions: List[str]  # Suggested improvements
    corrected_tags: List[str]  # Alternative tags if misaligned


class SummaryTagAlignmentValidator:
    """Validates and improves alignment between summaries and tags."""

    def __init__(self, policy_areas: List[str]):
        """Initialize with authorized policy tags."""
        self.policy_areas = policy_areas
        self.hebrew_stopwords = {
            'של', 'את', 'על', 'עם', 'או', 'גם', 'כל', 'לא', 'אם', 'כי',
            'זה', 'זו', 'אל', 'מן', 'לפי', 'אחר', 'עד', 'בין', 'תוך'
        }

    def validate_alignment(
        self,
        summary: str,
        tags: List[str],
        decision_title: str = "",
        decision_content: str = ""
    ) -> AlignmentValidationResult:
        """
        Validate summary-tag alignment and suggest corrections.

        Args:
            summary: Generated summary text
            tags: List of policy tags assigned
            decision_title: Optional decision title for context
            decision_content: Optional full content for validation

        Returns:
            AlignmentValidationResult with validation results
        """
        issues = []
        suggestions = []
        corrected_tags = []

        # Extract keywords from summary
        summary_keywords = self._extract_keywords(summary)

        # Extract domain concepts from tags
        tag_concepts = self._extract_tag_concepts(tags)

        # Check semantic overlap
        semantic_score = self._calculate_semantic_overlap(summary_keywords, tag_concepts)

        # Check specific misalignment patterns
        pattern_issues = self._check_misalignment_patterns(summary, tags, decision_title)
        issues.extend(pattern_issues)

        # Check for over-tagging
        over_tagging_issues = self._check_overtagging(summary, tags)
        issues.extend(over_tagging_issues)

        # Calculate overall alignment score
        alignment_score = self._calculate_alignment_score(semantic_score, len(issues))

        # Generate suggestions if poorly aligned
        if alignment_score < 0.7:
            suggestions = self._generate_alignment_suggestions(
                summary, tags, summary_keywords, decision_title
            )
            corrected_tags = self._suggest_corrected_tags(
                summary, summary_keywords, decision_title
            )

        return AlignmentValidationResult(
            is_aligned=alignment_score >= 0.7,
            alignment_score=alignment_score,
            issues=issues,
            suggestions=suggestions,
            corrected_tags=corrected_tags
        )

    def _extract_keywords(self, text: str) -> Set[str]:
        """Extract meaningful keywords from text."""
        if not text:
            return set()

        # Clean and tokenize
        text = re.sub(r'[^\u0590-\u05FF\s]', ' ', text.lower())  # Hebrew only
        words = text.split()

        # Filter out stopwords and short words
        keywords = {
            word for word in words
            if len(word) > 2 and word not in self.hebrew_stopwords
        }

        return keywords

    def _extract_tag_concepts(self, tags: List[str]) -> Set[str]:
        """Extract conceptual keywords from policy tags."""
        concepts = set()

        # Map tags to their conceptual domains with expanded vocabulary
        tag_concepts_map = {
            'חינוך': {'חינוך', 'בתי', 'ספר', 'תלמידים', 'מורים', 'לימודים', 'חינוכי', 'חינוכיות', 'בית', 'הספר', 'תלמיד', 'מורה', 'הוראה'},
            'בריאות ורפואה': {'בריאות', 'רפואה', 'בתי', 'חולים', 'רופאים', 'טיפול', 'רפואי', 'בריאותי', 'חולה', 'רופא', 'בית', 'חולים'},
            'מדיני ביטחוני': {'ביטחון', 'מדיניות', 'צבא', 'הגנה', 'שלום', 'ביטחוני', 'מדיני', 'ביטחונית', 'מדינית'},
            'תחבורה ובטיחות בדרכים': {'תחבורה', 'כבישים', 'בטיחות', 'נהיגה', 'רכבים', 'תחבורתי', 'כביש', 'רכב', 'תנועה'},
            'אנרגיה מים ותשתיות': {'אנרגיה', 'מים', 'תשתיות', 'חשמל', 'דלק', 'תשתית', 'אנרגטי', 'מי', 'חשמלי'},
            'חקיקה, משפט ורגולציה': {'חוק', 'חקיקה', 'משפט', 'רגולציה', 'חוקי', 'טיוטת', 'הצעת', 'איסור', 'משפטי', 'חוקית', 'זנות'},
            'מינויים': {'מינוי', 'מנכל', 'מנהל', 'שר', 'יושב', 'ראש', 'למנות', 'ימונה', 'מינויו', 'מינויה', 'מנכ"ל', 'מנכ"לית'},
            'מנהלתי': {'נסיעה', 'ועדה', 'דיון', 'הסכמה', 'נוהל', 'ועדת', 'הקמת', 'הקמה', 'בחינת', 'בחינה', 'ישיבה'},
            'תיירות': {'תיירות', 'אתרים', 'מלונות', 'נופש', 'תיירותי', 'אתר', 'מלון', 'תייר'},
            'נשים ומגדר': {'נשים', 'מגדר', 'שוויון', 'הטרדה', 'אישה', 'מגדרי', 'נשית', 'אלימות'},
            'תרבות וספורט': {'תרבות', 'ספורט', 'תרבותי', 'ספורטיבי', 'אמנות', 'תיאטרון', 'מוזיקה'},
            'דיור, נדלן ותכנון': {'דיור', 'נדלן', 'תכנון', 'בינוי', 'שיכון', 'דירות', 'בניה', 'יישוב'},
            'תעשייה מסחר ומשק': {'תעשייה', 'מסחר', 'משק', 'כלכלה', 'תעשייתי', 'מסחרי', 'כלכלי'},
            'שונות': set()  # catch-all, no specific concepts
        }

        for tag in tags:
            if tag in tag_concepts_map:
                concepts.update(tag_concepts_map[tag])
            else:
                # Add tag words themselves as concepts
                concepts.update(self._extract_keywords(tag))

        return concepts

    def _calculate_semantic_overlap(self, summary_keywords: Set[str], tag_concepts: Set[str]) -> float:
        """Calculate semantic overlap between summary and tags."""
        if not summary_keywords or not tag_concepts:
            return 0.0

        intersection = summary_keywords.intersection(tag_concepts)
        union = summary_keywords.union(tag_concepts)

        return len(intersection) / len(union) if union else 0.0

    def _check_misalignment_patterns(self, summary: str, tags: List[str], title: str) -> List[str]:
        """Check for known misalignment patterns."""
        issues = []

        # Pattern 1: Legal/legislation content tagged as culture
        if any(word in summary.lower() for word in ['חוק', 'חקיקה', 'איסור', 'הצעת חוק']):
            if 'תרבות וספורט' in tags:
                issues.append("תוכן חקיקתי תויג כ'תרבות וספורט' - צריך להיות 'חקיקה, משפט ורגולציה'")

        # Pattern 2: Administrative actions tagged with domain-specific tags
        administrative_indicators = ['נסיעה', 'ועדה', 'דיון', 'הסכמה']
        if any(indicator in summary.lower() for indicator in administrative_indicators):
            domain_tags = [t for t in tags if t not in ['מנהלתי', 'מינויים']]
            if domain_tags:
                issues.append(f"פעולה מנהלתי תויגה עם תגיות תחומיות: {domain_tags}")

        # Pattern 3: Appointment content with domain tags
        if any(word in summary.lower() for word in ['מינוי', 'למנות']):
            domain_tags = [t for t in tags if t not in ['מינויים', 'מנהלתי']]
            if domain_tags:
                issues.append(f"מינוי תויג עם תגיות תחום: {domain_tags} - צריך להיות 'מינויים'")

        return issues

    def _check_overtagging(self, summary: str, tags: List[str]) -> List[str]:
        """Check for over-tagging issues."""
        issues = []

        if len(tags) > 2:
            # Check if summary actually covers all tagged domains
            summary_lower = summary.lower()
            unmentioned_tags = []

            for tag in tags:
                tag_concepts = self._extract_tag_concepts([tag])
                if not any(concept in summary_lower for concept in tag_concepts):
                    unmentioned_tags.append(tag)

            if unmentioned_tags:
                issues.append(f"תגיות שלא מוזכרות בסיכום: {unmentioned_tags}")

        return issues

    def _calculate_alignment_score(self, semantic_score: float, num_issues: int) -> float:
        """Calculate overall alignment score with improved logic."""
        # Base score from semantic overlap
        base_score = semantic_score

        # If no major issues detected, give minimum score of 0.7 for good semantic match
        if num_issues == 0 and base_score > 0.1:
            base_score = max(base_score, 0.7)

        # Penalize for issues found - more severe penalties for major misalignments
        penalty = min(0.5, num_issues * 0.15)  # Max 50% penalty, 15% per issue
        score = max(0.0, base_score - penalty)

        # Special case: if semantic overlap is very low (< 0.05) it's likely misaligned
        if semantic_score < 0.05:
            score = min(score, 0.4)

        return score

    def _generate_alignment_suggestions(
        self,
        summary: str,
        tags: List[str],
        summary_keywords: Set[str],
        title: str
    ) -> List[str]:
        """Generate suggestions to improve alignment."""
        suggestions = []

        # Suggest focusing summary on tagged domains
        if len(tags) > 1:
            suggestions.append("שקול לפרט בסיכום את כל התחומים המתוייגים או להקטין את מספר התגיות")

        # Suggest administrative classification for procedural content
        procedural_words = {'ועדה', 'דיון', 'נסיעה', 'הסכמה'}
        if procedural_words.intersection(summary_keywords):
            suggestions.append("שקול תיוג כ'מנהלתי' עבור תוכן פרוצדורלי")

        # Suggest appointment classification
        appointment_words = {'מינוי', 'למנות', 'ימונה'}
        if appointment_words.intersection(summary_keywords):
            suggestions.append("שקול תיוג כ'מינויים' עבור תוכן מינויים")

        return suggestions

    def _suggest_corrected_tags(
        self,
        summary: str,
        summary_keywords: Set[str],
        title: str
    ) -> List[str]:
        """Suggest corrected tags based on summary content."""
        suggested_tags = []

        # Legal/legislation content
        if any(word in summary_keywords for word in ['חוק', 'חקיקה', 'איסור']):
            suggested_tags.append('חקיקה, משפט ורגולציה')

        # Administrative content
        elif any(word in summary_keywords for word in ['ועדה', 'דיון', 'נסיעה']):
            suggested_tags.append('מנהלתי')

        # Appointment content
        elif any(word in summary_keywords for word in ['מינוי', 'למנות']):
            suggested_tags.append('מינויים')

        # Health content
        elif any(word in summary_keywords for word in ['בריאות', 'רופא', 'חולה']):
            suggested_tags.append('בריאות ורפואה')

        # Education content
        elif any(word in summary_keywords for word in ['חינוך', 'בית', 'ספר']):
            suggested_tags.append('חינוך')

        # Default fallback
        if not suggested_tags:
            suggested_tags.append('שונות')

        return suggested_tags

    def fix_alignment(
        self,
        summary: str,
        tags: List[str],
        decision_title: str = "",
        decision_content: str = ""
    ) -> Tuple[str, List[str]]:
        """
        Automatically fix alignment issues between summary and tags.

        Returns:
            Tuple of (potentially_modified_summary, corrected_tags)
        """
        validation = self.validate_alignment(summary, tags, decision_title, decision_content)

        if validation.is_aligned:
            return summary, tags

        # Use corrected tags if available
        if validation.corrected_tags:
            logger.info(f"Auto-correcting tags from {tags} to {validation.corrected_tags}")
            return summary, validation.corrected_tags

        # Keep original if no better alternative found
        return summary, tags


def create_alignment_validator(policy_areas: List[str]) -> SummaryTagAlignmentValidator:
    """Factory function to create alignment validator."""
    return SummaryTagAlignmentValidator(policy_areas)