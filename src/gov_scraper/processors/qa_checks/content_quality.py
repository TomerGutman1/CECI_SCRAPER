"""
Content Quality Checks Module

Implements comprehensive content quality validation including:
- Duplicate detection
- Content completeness validation
- Content integrity checks
- Text quality assessment
"""

import re
import logging
from typing import Dict, List, Set, Any, Optional
from collections import defaultdict, Counter
from difflib import SequenceMatcher
from dataclasses import dataclass

from ..qa_core import AbstractQACheck, QAIssue, CheckSeverity

logger = logging.getLogger(__name__)


@dataclass
class ContentMetrics:
    """Metrics for content quality assessment."""
    word_count: int
    char_count: int
    sentence_count: int
    paragraph_count: int
    avg_sentence_length: float
    repetition_score: float
    readability_score: float


class ContentQualityCheck(AbstractQACheck):
    """
    Comprehensive content quality validation.

    Checks for:
    - Duplicate content detection
    - Content completeness
    - Content integrity
    - Text quality metrics
    """

    def __init__(self,
                 duplicate_threshold: float = 0.85,
                 min_content_length: int = 50,
                 max_repetition_ratio: float = 0.3,
                 **kwargs):
        super().__init__(
            check_name="content_quality",
            description="Validates content quality including duplicates, completeness, and integrity",
            **kwargs
        )
        self.duplicate_threshold = duplicate_threshold
        self.min_content_length = min_content_length
        self.max_repetition_ratio = max_repetition_ratio

        # Cache for duplicate detection
        self._content_cache: Dict[str, List[str]] = defaultdict(list)

    def _validate_record(self, record: Dict) -> List[QAIssue]:
        """Validate content quality for a single record."""
        issues = []
        decision_key = record.get('decision_key', 'unknown')

        # Check each content field
        content_fields = ['decision_content', 'decision_summary', 'title']

        for field in content_fields:
            field_value = record.get(field, '')
            if not field_value:
                continue

            # Completeness check
            completeness_issues = self._check_completeness(decision_key, field, field_value)
            issues.extend(completeness_issues)

            # Quality metrics check
            quality_issues = self._check_quality_metrics(decision_key, field, field_value)
            issues.extend(quality_issues)

            # Duplicate detection
            duplicate_issues = self._check_duplicates(decision_key, field, field_value)
            issues.extend(duplicate_issues)

            # Content integrity
            integrity_issues = self._check_content_integrity(decision_key, field, field_value)
            issues.extend(integrity_issues)

        return issues

    def _check_completeness(self, decision_key: str, field: str, content: str) -> List[QAIssue]:
        """Check content completeness."""
        issues = []

        # Check minimum length
        if len(content.strip()) < self.min_content_length:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.MEDIUM,
                field=field,
                current_value=content[:100],
                description=f"Content too short: {len(content)} characters (minimum: {self.min_content_length})",
                expected_value=f"At least {self.min_content_length} characters",
                length=len(content),
                min_required=self.min_content_length
            ))

        # Check for placeholder text
        placeholders = [
            "לא זמין", "אין מידע", "טרם נקבע", "בבדיקה", "יעודכן בהמשך",
            "N/A", "TBD", "TODO", "???", "...", "ללא תוכן"
        ]

        content_lower = content.lower()
        for placeholder in placeholders:
            if placeholder.lower() in content_lower:
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.HIGH,
                    field=field,
                    current_value=content[:100],
                    description=f"Contains placeholder text: '{placeholder}'",
                    expected_value="Complete content without placeholders",
                    placeholder_found=placeholder
                ))

        # Check for incomplete sentences
        if content.strip() and not content.strip()[-1] in '.!?':
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.LOW,
                field=field,
                current_value=content[:100],
                description="Content appears to end abruptly (no sentence-ending punctuation)",
                expected_value="Content ending with proper punctuation"
            ))

        return issues

    def _check_quality_metrics(self, decision_key: str, field: str, content: str) -> List[QAIssue]:
        """Check content quality metrics."""
        issues = []
        metrics = self._calculate_content_metrics(content)

        # Check for excessive repetition
        if metrics.repetition_score > self.max_repetition_ratio:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.MEDIUM,
                field=field,
                current_value=content[:100],
                description=f"High repetition detected: {metrics.repetition_score:.2f} (max: {self.max_repetition_ratio})",
                expected_value=f"Repetition score below {self.max_repetition_ratio}",
                repetition_score=metrics.repetition_score,
                max_allowed=self.max_repetition_ratio
            ))

        # Check for unreasonably short sentences (may indicate truncation)
        if metrics.avg_sentence_length < 3:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.MEDIUM,
                field=field,
                current_value=content[:100],
                description=f"Very short average sentence length: {metrics.avg_sentence_length:.1f} words",
                expected_value="Average sentence length > 3 words",
                avg_sentence_length=metrics.avg_sentence_length
            ))

        # Check for single very long paragraph (poor formatting)
        if metrics.paragraph_count == 1 and metrics.word_count > 200:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.LOW,
                field=field,
                current_value=content[:100],
                description=f"Long content in single paragraph: {metrics.word_count} words",
                expected_value="Content broken into multiple paragraphs",
                word_count=metrics.word_count,
                paragraph_count=metrics.paragraph_count
            ))

        return issues

    def _check_duplicates(self, decision_key: str, field: str, content: str) -> List[QAIssue]:
        """Check for duplicate content."""
        issues = []

        # Normalize content for comparison
        normalized_content = self._normalize_content(content)

        # Check against cached content
        field_cache = self._content_cache[field]

        for cached_key, cached_content in field_cache:
            similarity = self._calculate_similarity(normalized_content, cached_content)

            if similarity >= self.duplicate_threshold:
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.HIGH,
                    field=field,
                    current_value=content[:100],
                    description=f"Duplicate content detected (similarity: {similarity:.2f})",
                    expected_value="Unique content",
                    similar_to=cached_key,
                    similarity_score=similarity,
                    threshold=self.duplicate_threshold
                ))

        # Add to cache
        field_cache.append((decision_key, normalized_content))

        return issues

    def _check_content_integrity(self, decision_key: str, field: str, content: str) -> List[QAIssue]:
        """Check content integrity and consistency."""
        issues = []

        # Check for encoding issues
        try:
            content.encode('utf-8')
        except UnicodeEncodeError as e:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.HIGH,
                field=field,
                current_value=content[:100],
                description=f"Encoding error: {str(e)}",
                expected_value="Valid UTF-8 encoded content",
                encoding_error=str(e)
            ))

        # Check for HTML/XML remnants
        html_patterns = [
            r'<[^>]+>', r'&\w+;', r'</', r'/>',
            r'&lt;', r'&gt;', r'&amp;', r'&quot;'
        ]

        for pattern in html_patterns:
            if re.search(pattern, content):
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.MEDIUM,
                    field=field,
                    current_value=content[:100],
                    description="Contains HTML/XML markup or entities",
                    expected_value="Plain text content",
                    pattern_found=pattern
                ))
                break

        # Check for excessive whitespace
        whitespace_issues = []
        if '\t' in content:
            whitespace_issues.append('tabs')
        if re.search(r'  +', content):  # Multiple consecutive spaces
            whitespace_issues.append('multiple_spaces')
        if re.search(r'\n\n\n+', content):  # Multiple consecutive newlines
            whitespace_issues.append('multiple_newlines')

        if whitespace_issues:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.LOW,
                field=field,
                current_value=content[:100],
                description=f"Whitespace formatting issues: {', '.join(whitespace_issues)}",
                expected_value="Properly formatted whitespace",
                whitespace_issues=whitespace_issues
            ))

        # Check for mixed RTL/LTR issues (Hebrew content specific)
        if self._has_mixed_direction_issues(content):
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.LOW,
                field=field,
                current_value=content[:100],
                description="Mixed RTL/LTR text direction may cause display issues",
                expected_value="Consistent text direction",
                has_hebrew=self._contains_hebrew(content),
                has_english=self._contains_english(content)
            ))

        return issues

    def _calculate_content_metrics(self, content: str) -> ContentMetrics:
        """Calculate various content quality metrics."""
        # Basic counts
        word_count = len(content.split())
        char_count = len(content)

        # Sentence count
        sentence_endings = ['.', '!', '?']
        sentence_count = sum(content.count(ending) for ending in sentence_endings)
        sentence_count = max(1, sentence_count)  # Avoid division by zero

        # Paragraph count
        paragraph_count = len([p for p in content.split('\n\n') if p.strip()])
        paragraph_count = max(1, paragraph_count)

        # Average sentence length
        avg_sentence_length = word_count / sentence_count

        # Repetition score
        repetition_score = self._calculate_repetition_score(content)

        # Simple readability score (word/sentence ratio)
        readability_score = avg_sentence_length

        return ContentMetrics(
            word_count=word_count,
            char_count=char_count,
            sentence_count=sentence_count,
            paragraph_count=paragraph_count,
            avg_sentence_length=avg_sentence_length,
            repetition_score=repetition_score,
            readability_score=readability_score
        )

    def _calculate_repetition_score(self, content: str) -> float:
        """Calculate repetition score (0-1, higher = more repetitive)."""
        words = content.lower().split()
        if len(words) < 2:
            return 0.0

        # Count word frequencies
        word_freq = Counter(words)

        # Calculate repetition as ratio of repeated words to total words
        repeated_words = sum(count - 1 for count in word_freq.values() if count > 1)
        repetition_ratio = repeated_words / len(words)

        return repetition_ratio

    def _normalize_content(self, content: str) -> str:
        """Normalize content for comparison."""
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', content.strip())

        # Remove punctuation and convert to lowercase
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = normalized.lower()

        return normalized

    def _calculate_similarity(self, content1: str, content2: str) -> float:
        """Calculate similarity between two content strings."""
        return SequenceMatcher(None, content1, content2).ratio()

    def _has_mixed_direction_issues(self, content: str) -> bool:
        """Check for mixed RTL/LTR text direction issues."""
        has_hebrew = self._contains_hebrew(content)
        has_english = self._contains_english(content)

        # Only flag if both are present and content is substantial
        return has_hebrew and has_english and len(content) > 100

    def _contains_hebrew(self, text: str) -> bool:
        """Check if text contains Hebrew characters."""
        hebrew_range = range(0x0590, 0x05FF)  # Hebrew Unicode block
        return any(ord(char) in hebrew_range for char in text)

    def _contains_english(self, text: str) -> bool:
        """Check if text contains English characters."""
        return any(char.isalpha() and ord(char) < 128 for char in text)

    def _generate_summary(self, issues: List[QAIssue], total_scanned: int) -> Dict[str, Any]:
        """Generate summary statistics for content quality check."""
        summary = {
            "total_scanned": total_scanned,
            "total_issues": len(issues),
            "issue_rate": f"{(len(issues) / total_scanned * 100):.1f}%" if total_scanned > 0 else "0%"
        }

        # Group issues by type
        issue_types = defaultdict(int)
        severity_counts = defaultdict(int)
        field_counts = defaultdict(int)

        for issue in issues:
            # Extract issue type from description
            desc = issue.description.lower()
            if "duplicate" in desc:
                issue_type = "duplicates"
            elif "short" in desc or "length" in desc:
                issue_type = "completeness"
            elif "repetition" in desc:
                issue_type = "repetition"
            elif "placeholder" in desc:
                issue_type = "placeholders"
            elif "encoding" in desc:
                issue_type = "encoding"
            elif "html" in desc or "markup" in desc:
                issue_type = "markup"
            elif "whitespace" in desc:
                issue_type = "formatting"
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

        # Quality metrics
        if issues:
            duplicate_rate = issue_types.get("duplicates", 0) / len(issues) * 100
            completeness_rate = issue_types.get("completeness", 0) / len(issues) * 100

            summary.update({
                "duplicate_rate": f"{duplicate_rate:.1f}%",
                "completeness_rate": f"{completeness_rate:.1f}%"
            })

        return summary


class DuplicateDetectionCheck(AbstractQACheck):
    """
    Specialized duplicate detection check.

    Focuses specifically on finding duplicate content across records.
    """

    def __init__(self,
                 similarity_threshold: float = 0.85,
                 fields_to_check: List[str] = None,
                 **kwargs):
        super().__init__(
            check_name="duplicate_detection",
            description="Specialized duplicate content detection",
            **kwargs
        )
        self.similarity_threshold = similarity_threshold
        self.fields_to_check = fields_to_check or ['decision_content', 'title', 'decision_summary']

        # Store all processed content for cross-comparison
        self.processed_content: Dict[str, Dict[str, str]] = {}

    def run(self, records: List[Dict]) -> 'QAScanResult':
        """Override run to perform cross-record duplicate detection."""
        from ..qa_core import QAScanResult
        import time

        start_time = time.time()
        self._init_progress(len(records))

        # First pass: collect all content
        all_content = {}
        for record in records:
            decision_key = record.get('decision_key', 'unknown')
            record_content = {}

            for field in self.fields_to_check:
                content = record.get(field, '')
                if content and len(content.strip()) > 10:  # Skip very short content
                    normalized = self._normalize_content(content)
                    record_content[field] = normalized

            if record_content:
                all_content[decision_key] = record_content

        # Second pass: find duplicates
        all_issues = []
        processed_pairs = set()

        for key1, content1 in all_content.items():
            for key2, content2 in all_content.items():
                if key1 >= key2:  # Avoid duplicate comparisons
                    continue

                pair = tuple(sorted([key1, key2]))
                if pair in processed_pairs:
                    continue
                processed_pairs.add(pair)

                # Check each field
                for field in self.fields_to_check:
                    if field not in content1 or field not in content2:
                        continue

                    similarity = self._calculate_similarity(content1[field], content2[field])

                    if similarity >= self.similarity_threshold:
                        # Create issues for both records
                        for decision_key in [key1, key2]:
                            issue = self.create_issue(
                                decision_key=decision_key,
                                severity=CheckSeverity.HIGH,
                                field=field,
                                current_value=content1[field][:100] if decision_key == key1 else content2[field][:100],
                                description=f"Duplicate content detected with {key2 if decision_key == key1 else key1}",
                                expected_value="Unique content",
                                duplicate_of=key2 if decision_key == key1 else key1,
                                similarity_score=similarity,
                                threshold=self.similarity_threshold
                            )
                            all_issues.append(issue)

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
        """Not used in duplicate detection - override run instead."""
        return []

    def _normalize_content(self, content: str) -> str:
        """Normalize content for comparison."""
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', content.strip())

        # Convert to lowercase but preserve Hebrew
        normalized = normalized.lower()

        return normalized

    def _calculate_similarity(self, content1: str, content2: str) -> float:
        """Calculate similarity between two content strings."""
        return SequenceMatcher(None, content1, content2).ratio()

    def _generate_summary(self, issues: List[QAIssue], total_scanned: int) -> Dict[str, Any]:
        """Generate summary for duplicate detection."""
        duplicate_pairs = set()
        field_counts = defaultdict(int)

        for issue in issues:
            duplicate_of = issue.metadata.get('duplicate_of')
            if duplicate_of:
                pair = tuple(sorted([issue.decision_key, duplicate_of]))
                duplicate_pairs.add(pair)
                field_counts[issue.field] += 1

        return {
            "total_scanned": total_scanned,
            "total_issues": len(issues),
            "unique_duplicate_pairs": len(duplicate_pairs),
            "duplicates_by_field": dict(field_counts),
            "similarity_threshold": self.similarity_threshold,
            "duplicate_rate": f"{(len(duplicate_pairs) * 2 / total_scanned * 100):.1f}%" if total_scanned > 0 else "0%"
        }