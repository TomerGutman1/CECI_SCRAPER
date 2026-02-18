"""
Tag Validation Checks Module

Implements comprehensive tag validation including:
- Tag accuracy against content
- Tag consistency checks
- Authorized tag list validation
- Cross-field tag correlation
"""

import re
import logging
from typing import Dict, List, Set, Any, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass

from ..qa_core import AbstractQACheck, QAIssue, CheckSeverity

logger = logging.getLogger(__name__)


# Authorized policy tags (from new_tags.md)
AUTHORIZED_POLICY_TAGS = {
    "אזרחים ותיקים", "אנרגיה מים ותשתיות", "ביטחון פנים", "בינוי ושיכון",
    "בריאות ורפואה", "דיור, נדלן ותכנון", "דת ומוסדות דת", "הגנת הסביבה ואקלים",
    "התייעלות המנגנון הממשלתי", "חוץ הסברה ותפוצות", "חינוך", "חקיקה, משפט ורגולציה",
    "חקלאות ופיתוח הכפר", "יוקר המחייה", "מדיני ביטחוני", "מדע, טכנולוגיה וחדשנות",
    "מורשת", "מינהל ציבורי ושירות המדינה", "מינויים", "מיעוטים", "מנהלת תקומה",
    "מנהלתי", "משבר הקורונה", "משטרת ישראל", "משפטים", "תרבות וספורט",
    "פיתוח הנגב והגליל", "פיתוח הפריפריה ואוכלוסיות", "פיתוח כלכלי ותחרות",
    "קליטת עלייה", "רגולציה", "רווחה ושירותים חברתיים", "תחבורה ובטיחות בדרכים",
    "תיירות", "תעסוקה ועבודה", "תעשייה מסחר ומשק", "תקציב, פיננסים, ביטוח ומיסוי",
    "תקשורת ומדיה", "שוויון חברתי וזכויות אדם", "שלטון מקומי", "החברה הערבית",
    "החברה החרדית", "נשים ומגדר", "שיקום הצפון", "שיקום הדרום"
}

# Policy tag keywords for relevance checking
POLICY_TAG_KEYWORDS = {
    "אזרחים ותיקים": [
        "קשיש", "אזרח ותיק", "אזרחים ותיקים", "גמלאי", "פנסיה", "זקנה",
        "סיעוד", "סיעודי", "גיל הפרישה", "גיל הזהב", "בית אבות", "דיור מוגן",
        "קצבת זקנה", "ביטוח לאומי", "תוחלת חיים"
    ],
    "אנרגיה מים ותשתיות": [
        "אנרגיה", "חשמל", "מים", "תשתיות", "גז טבעי", "נפט", "סולארי",
        "מקורות", "חברת חשמל", "מתקן אנרגיה", "התפלה", "ביוב", "תחנת כוח",
        "רשת החשמל", "אנרגיה מתחדשת", "מאגר גז", "צנרת", "לוויתן", "תמר",
        "קידוח", "דלק"
    ],
    "ביטחון פנים": [
        "ביטחון פנים", "כבאות", "שב\"כ", "טרור", "פשיעה", "אכיפה",
        "משמר הגבול", "מג\"ב", "סדר ציבורי", "עבריינות", "פיגוע",
        "חירום אזרחי", "הגנה אזרחית", "פיקוד העורף", "מקלט",
        "ביטחון המדינה", "איום ביטחוני", "שידורים", "מחבל",
        "שירות הביטחון", "גורמי ביטחון", "ביטחון הציבור"
    ],
    "בינוי ושיכון": [
        "בינוי", "שיכון", "בנייה", "דירות", "מגורים", "קבלן", "היתר בנייה",
        "תוכנית בניין עיר", "התחדשות עירונית", "פינוי בינוי", "תמ\"א 38",
        "יחידות דיור", "שכונה", "מבנה", "יישוב", "יישובים", "הקמת",
        "הקמה", "קהילתי", "מתחם"
    ],
    "בריאות ורפואה": [
        "בריאות", "רפואה", "חולה", "בית חולים", "רופא", "תרופ", "קופת חולים",
        "רפואי", "מטופל", "אשפוז", "מרפאה", "בריאות הנפש", "ביטוח בריאות",
        "סל בריאות", "מחלה", "טיפול רפואי", "חיסון", "שירותי בריאות",
        "רוקח", "אחות", "רפואה דחופה"
    ],
    "חינוך": [
        "חינוך", "תלמיד", "בית ספר", "מורה", "לימוד", "אוניברסיטה",
        "סטודנט", "הוראה", "מכללה", "גן ילדים", "גננת",
        "תוכנית לימודים", "משרד החינוך", "מל\"ג", "בגרות", "מכינה",
        "חינוך מיוחד", "השכלה גבוהה", "אקדמי", "ישיבה"
    ]
    # Additional keywords would be added for all other tags...
}


@dataclass
class TagRelevanceResult:
    """Result of tag relevance analysis."""
    tag: str
    relevance_score: float
    matching_keywords: List[str]
    total_keywords: int
    content_analyzed: str


class TagValidationCheck(AbstractQACheck):
    """
    Comprehensive tag validation.

    Checks for:
    - Tag authorization (against approved lists)
    - Tag-content relevance
    - Tag consistency across fields
    - Tag completeness
    """

    def __init__(self,
                 min_relevance_score: float = 0.1,
                 check_content_relevance: bool = True,
                 **kwargs):
        super().__init__(
            check_name="tag_validation",
            description="Validates tag accuracy, relevance, and consistency",
            **kwargs
        )
        self.min_relevance_score = min_relevance_score
        self.check_content_relevance = check_content_relevance
        self.authorized_tags = AUTHORIZED_POLICY_TAGS
        self.tag_keywords = POLICY_TAG_KEYWORDS

    def _validate_record(self, record: Dict) -> List[QAIssue]:
        """Validate tags for a single record."""
        issues = []
        decision_key = record.get('decision_key', 'unknown')

        # Check policy tags
        policy_tags = record.get('policy_areas', [])
        if isinstance(policy_tags, str):
            policy_tags = [tag.strip() for tag in policy_tags.split(',') if tag.strip()]

        for tag in policy_tags:
            tag_issues = self._validate_policy_tag(decision_key, tag, record)
            issues.extend(tag_issues)

        # Check tag completeness
        completeness_issues = self._check_tag_completeness(decision_key, record)
        issues.extend(completeness_issues)

        # Check tag consistency
        consistency_issues = self._check_tag_consistency(decision_key, record)
        issues.extend(consistency_issues)

        return issues

    def _validate_policy_tag(self, decision_key: str, tag: str, record: Dict) -> List[QAIssue]:
        """Validate a single policy tag."""
        issues = []

        # Check authorization
        if tag not in self.authorized_tags:
            # Check for close matches
            close_matches = self._find_close_tag_matches(tag)

            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.HIGH,
                field="policy_areas",
                current_value=tag,
                description=f"Unauthorized policy tag: '{tag}'",
                expected_value=f"One of authorized tags: {', '.join(sorted(self.authorized_tags))}",
                unauthorized_tag=tag,
                close_matches=close_matches[:3] if close_matches else []
            ))

        # Check content relevance
        if self.check_content_relevance and tag in self.tag_keywords:
            relevance_result = self._check_tag_relevance(tag, record)

            if relevance_result.relevance_score < self.min_relevance_score:
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.MEDIUM,
                    field="policy_areas",
                    current_value=tag,
                    description=f"Tag may not be relevant to content (score: {relevance_result.relevance_score:.2f})",
                    expected_value=f"Relevance score >= {self.min_relevance_score}",
                    relevance_score=relevance_result.relevance_score,
                    matching_keywords=relevance_result.matching_keywords,
                    total_keywords=relevance_result.total_keywords
                ))

        return issues

    def _check_tag_completeness(self, decision_key: str, record: Dict) -> List[QAIssue]:
        """Check if record has appropriate tags."""
        issues = []

        policy_tags = record.get('policy_areas', [])
        if isinstance(policy_tags, str):
            policy_tags = [tag.strip() for tag in policy_tags.split(',') if tag.strip()]

        # Check for missing tags
        if not policy_tags:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.MEDIUM,
                field="policy_areas",
                current_value="",
                description="No policy tags assigned",
                expected_value="At least one relevant policy tag",
                tag_count=0
            ))

        # Check for excessive tags (may indicate over-tagging)
        elif len(policy_tags) > 5:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.LOW,
                field="policy_areas",
                current_value=f"{len(policy_tags)} tags",
                description=f"Many tags assigned ({len(policy_tags)}), may be over-tagged",
                expected_value="1-5 relevant tags",
                tag_count=len(policy_tags),
                tags=policy_tags
            ))

        # Check for generic/default tags that might indicate fallback behavior
        generic_patterns = ["מנהלתי", "מדיני ביטחוני"]
        for tag in policy_tags:
            if tag in generic_patterns:
                # Only flag if it's the only tag or dominant
                if len(policy_tags) == 1 or policy_tags.count(tag) > len(policy_tags) / 2:
                    issues.append(self.create_issue(
                        decision_key=decision_key,
                        severity=CheckSeverity.LOW,
                        field="policy_areas",
                        current_value=tag,
                        description=f"Generic/default tag may indicate insufficient analysis: '{tag}'",
                        expected_value="Specific, relevant policy tags",
                        generic_tag=tag,
                        total_tags=len(policy_tags)
                    ))

        return issues

    def _check_tag_consistency(self, decision_key: str, record: Dict) -> List[QAIssue]:
        """Check consistency between tags and other fields."""
        issues = []

        policy_tags = record.get('policy_areas', [])
        if isinstance(policy_tags, str):
            policy_tags = [tag.strip() for tag in policy_tags.split(',') if tag.strip()]

        government_body = record.get('government_body', '')
        operativity = record.get('operativity', '')

        # Check tag-body consistency
        if government_body and policy_tags:
            body_tag_issues = self._check_body_tag_consistency(
                decision_key, government_body, policy_tags
            )
            issues.extend(body_tag_issues)

        # Check operativity consistency
        if operativity and policy_tags:
            operativity_issues = self._check_operativity_tag_consistency(
                decision_key, operativity, policy_tags
            )
            issues.extend(operativity_issues)

        return issues

    def _check_tag_relevance(self, tag: str, record: Dict) -> TagRelevanceResult:
        """Check if tag is relevant to record content."""
        keywords = self.tag_keywords.get(tag, [])
        if not keywords:
            return TagRelevanceResult(tag, 1.0, [], 0, "")

        # Combine content fields for analysis
        content_fields = ['decision_content', 'decision_summary', 'title']
        combined_content = ""

        for field in content_fields:
            field_content = record.get(field, '')
            if field_content:
                combined_content += " " + field_content.lower()

        if not combined_content.strip():
            return TagRelevanceResult(tag, 0.0, [], len(keywords), "")

        # Count keyword matches
        matching_keywords = []
        for keyword in keywords:
            if keyword.lower() in combined_content:
                matching_keywords.append(keyword)

        relevance_score = len(matching_keywords) / len(keywords) if keywords else 0.0

        return TagRelevanceResult(
            tag=tag,
            relevance_score=relevance_score,
            matching_keywords=matching_keywords,
            total_keywords=len(keywords),
            content_analyzed=combined_content[:200]
        )

    def _check_body_tag_consistency(self, decision_key: str, government_body: str, policy_tags: List[str]) -> List[QAIssue]:
        """Check consistency between government body and policy tags."""
        issues = []

        # Define expected tag-body relationships
        body_tag_mapping = {
            "משרד החינוך": ["חינוך"],
            "משרד הבריאות": ["בריאות ורפואה"],
            "משרד הביטחון": ["מדיני ביטחוני"],
            "משרד השיכון והבינוי": ["בינוי ושיכון", "דיור, נדלן ותכנון"],
            "משרד החקלאות": ["חקלאות ופיתוח הכפר"],
            "משרד האנרגיה": ["אנרגיה מים ותשתיות"],
            "משרד הרווחה": ["רווחה ושירותים חברתיים"],
            "משרד התחבורה": ["תחבורה ובטיחות בדרכים"],
            "משרד המשפטים": ["חקיקה, משפט ורגולציה", "משפטים"],
            "משרד החוץ": ["חוץ הסברה ותפוצות"],
            "משרד האוצר": ["תקציב, פיננסים, ביטוח ומיסוי"]
        }

        # Check for specific mismatches
        for body_pattern, expected_tags in body_tag_mapping.items():
            if body_pattern in government_body:
                tag_match = any(tag in policy_tags for tag in expected_tags)
                if not tag_match:
                    issues.append(self.create_issue(
                        decision_key=decision_key,
                        severity=CheckSeverity.MEDIUM,
                        field="policy_areas",
                        current_value=f"Body: {government_body}, Tags: {', '.join(policy_tags)}",
                        description=f"Government body '{body_pattern}' doesn't match policy tags",
                        expected_value=f"Tags including one of: {', '.join(expected_tags)}",
                        government_body=government_body,
                        policy_tags=policy_tags,
                        expected_tags=expected_tags
                    ))

        return issues

    def _check_operativity_tag_consistency(self, decision_key: str, operativity: str, policy_tags: List[str]) -> List[QAIssue]:
        """Check consistency between operativity and policy tags."""
        issues = []

        # Some tags are typically more operational or declarative
        operational_tags = {
            "מינויים", "תקציב, פיננסים, ביטוח ומיסוי", "חקיקה, משפט ורגולציה",
            "מנהלת תקומה", "הגנת הסביבה ואקלים"
        }

        declarative_tags = {
            "מדיני ביטחוני", "חוץ הסברה ותפוצות", "מורשת"
        }

        if operativity == "אופרטיבית":
            declarative_found = [tag for tag in policy_tags if tag in declarative_tags]
            if declarative_found:
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.LOW,
                    field="operativity",
                    current_value=f"אופרטיבית with {', '.join(declarative_found)}",
                    description="Operational decision with typically declarative policy tags",
                    expected_value="Consistency between operativity and policy areas",
                    operativity=operativity,
                    conflicting_tags=declarative_found
                ))

        elif operativity == "דקלרטיבית":
            operational_found = [tag for tag in policy_tags if tag in operational_tags]
            if operational_found:
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.LOW,
                    field="operativity",
                    current_value=f"דקלרטיבית with {', '.join(operational_found)}",
                    description="Declarative decision with typically operational policy tags",
                    expected_value="Consistency between operativity and policy areas",
                    operativity=operativity,
                    conflicting_tags=operational_found
                ))

        return issues

    def _find_close_tag_matches(self, tag: str) -> List[str]:
        """Find close matches for unauthorized tags."""
        from difflib import get_close_matches

        return get_close_matches(
            tag,
            self.authorized_tags,
            n=3,
            cutoff=0.6
        )

    def _generate_summary(self, issues: List[QAIssue], total_scanned: int) -> Dict[str, Any]:
        """Generate summary statistics for tag validation check."""
        summary = {
            "total_scanned": total_scanned,
            "total_issues": len(issues),
            "issue_rate": f"{(len(issues) / total_scanned * 100):.1f}%" if total_scanned > 0 else "0%"
        }

        # Group issues by type
        issue_types = defaultdict(int)
        severity_counts = defaultdict(int)
        field_counts = defaultdict(int)
        unauthorized_tags = set()
        low_relevance_tags = set()

        for issue in issues:
            # Extract issue type from description
            desc = issue.description.lower()
            if "unauthorized" in desc:
                issue_type = "unauthorized_tags"
                unauthorized_tags.add(issue.metadata.get('unauthorized_tag', ''))
            elif "relevant" in desc or "relevance" in desc:
                issue_type = "relevance_issues"
                low_relevance_tags.add(issue.current_value)
            elif "no policy tags" in desc:
                issue_type = "missing_tags"
            elif "many tags" in desc or "over-tagged" in desc:
                issue_type = "excessive_tags"
            elif "generic" in desc or "default" in desc:
                issue_type = "generic_tags"
            elif "consistency" in desc:
                issue_type = "consistency_issues"
            else:
                issue_type = "other"

            issue_types[issue_type] += 1
            severity_counts[issue.severity.value] += 1
            field_counts[issue.field] += 1

        summary.update({
            "issues_by_type": dict(issue_types),
            "issues_by_severity": dict(severity_counts),
            "issues_by_field": dict(field_counts)
        })

        # Tag quality metrics
        if issues:
            authorization_rate = (1 - issue_types.get("unauthorized_tags", 0) / len(issues)) * 100
            relevance_rate = (1 - issue_types.get("relevance_issues", 0) / len(issues)) * 100

            summary.update({
                "authorization_rate": f"{authorization_rate:.1f}%",
                "relevance_rate": f"{relevance_rate:.1f}%",
                "unauthorized_tags_found": list(unauthorized_tags),
                "low_relevance_tags": list(low_relevance_tags),
                "total_authorized_tags": len(self.authorized_tags)
            })

        return summary


class TagConsistencyCheck(AbstractQACheck):
    """
    Specialized check for tag consistency across the dataset.

    Looks for patterns and inconsistencies in tag usage.
    """

    def __init__(self, **kwargs):
        super().__init__(
            check_name="tag_consistency",
            description="Validates tag consistency patterns across dataset",
            **kwargs
        )
        self.tag_usage_patterns = defaultdict(list)
        self.tag_cooccurrence = defaultdict(Counter)

    def run(self, records: List[Dict]) -> 'QAScanResult':
        """Override run to perform cross-record consistency analysis."""
        from ..qa_core import QAScanResult
        import time

        start_time = time.time()
        self._init_progress(len(records))

        # First pass: collect tag usage patterns
        all_issues = []

        for record in records:
            decision_key = record.get('decision_key', 'unknown')
            policy_tags = record.get('policy_areas', [])

            if isinstance(policy_tags, str):
                policy_tags = [tag.strip() for tag in policy_tags.split(',') if tag.strip()]

            government_body = record.get('government_body', '')

            # Store patterns
            for tag in policy_tags:
                self.tag_usage_patterns[tag].append({
                    'decision_key': decision_key,
                    'government_body': government_body,
                    'co_tags': [t for t in policy_tags if t != tag]
                })

            # Track co-occurrence
            for i, tag1 in enumerate(policy_tags):
                for tag2 in policy_tags[i+1:]:
                    self.tag_cooccurrence[tag1][tag2] += 1
                    self.tag_cooccurrence[tag2][tag1] += 1

        # Second pass: identify consistency issues
        consistency_issues = self._analyze_tag_patterns(records)
        all_issues.extend(consistency_issues)

        self._complete_progress()
        execution_time = time.time() - start_time

        return QAScanResult(
            check_name=self.check_name,
            total_scanned=len(records),
            issues_found=len(all_issues),
            issues=all_issues,
            summary=self._generate_summary(all_issues, len(records)),
            execution_time=execution_time,
            progress=self._progress
        )

    def _validate_record(self, record: Dict) -> List[QAIssue]:
        """Not used in consistency check - override run instead."""
        return []

    def _analyze_tag_patterns(self, records: List[Dict]) -> List[QAIssue]:
        """Analyze tag usage patterns for inconsistencies."""
        issues = []

        # Check for tags that should commonly appear together but don't
        for tag, cooccurrences in self.tag_cooccurrence.items():
            total_usage = len(self.tag_usage_patterns[tag])

            for co_tag, co_count in cooccurrences.most_common(5):
                co_percentage = co_count / total_usage

                # Find cases where these tags should appear together but don't
                if co_percentage > 0.7:  # Very commonly co-occur
                    # Find records with only one of these tags
                    single_tag_records = [
                        usage for usage in self.tag_usage_patterns[tag]
                        if co_tag not in usage['co_tags']
                    ]

                    for record_info in single_tag_records[:5]:  # Limit examples
                        issues.append(self.create_issue(
                            decision_key=record_info['decision_key'],
                            severity=CheckSeverity.LOW,
                            field="policy_areas",
                            current_value=tag,
                            description=f"Tag '{tag}' usually co-occurs with '{co_tag}' ({co_percentage:.1%} of time)",
                            expected_value=f"Both '{tag}' and '{co_tag}' tags",
                            missing_co_tag=co_tag,
                            co_occurrence_rate=co_percentage
                        ))

        return issues

    def _generate_summary(self, issues: List[QAIssue], total_scanned: int) -> Dict[str, Any]:
        """Generate summary for tag consistency check."""
        # Most commonly used tags
        tag_frequencies = {tag: len(usages) for tag, usages in self.tag_usage_patterns.items()}
        most_common_tags = sorted(tag_frequencies.items(), key=lambda x: x[1], reverse=True)[:10]

        # Most common co-occurrences
        top_cooccurrences = []
        for tag, cooccurrences in self.tag_cooccurrence.items():
            for co_tag, count in cooccurrences.most_common(3):
                if tag < co_tag:  # Avoid duplicates
                    top_cooccurrences.append((f"{tag} + {co_tag}", count))

        top_cooccurrences.sort(key=lambda x: x[1], reverse=True)

        return {
            "total_scanned": total_scanned,
            "total_issues": len(issues),
            "unique_tags_found": len(self.tag_usage_patterns),
            "most_common_tags": most_common_tags[:10],
            "top_tag_combinations": top_cooccurrences[:10],
            "consistency_patterns_analyzed": len(self.tag_cooccurrence)
        }