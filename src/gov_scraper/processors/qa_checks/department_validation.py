"""
Department Validation Checks Module

Implements comprehensive department/government body validation including:
- Authorization against approved department lists
- Department name consistency
- Cross-field department correlation
- Historical department alignment
"""

import re
import logging
from typing import Dict, List, Set, Any, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass
from difflib import get_close_matches

from ..qa_core import AbstractQACheck, QAIssue, CheckSeverity

logger = logging.getLogger(__name__)


# Authorized government bodies (from new_departments.md)
AUTHORIZED_GOVERNMENT_BODIES = {
    "משרד הנגב, הגליל והחוסן הלאומי", "המשרד לביטחון לאומי", "המשרד לביטחון פנים",
    "המשרד להגנת הסביבה", "המשרד לפיתוח הנגב והגליל", "המשרד לשוויון חברתי",
    "המשרד לשירותי דת", "מל\"ג/ות\"ת", "מנהל התכנון", "מערך הדיגיטל",
    "משרד האוצר", "משרד האנרגיה והתשתיות", "משרד הביטחון", "משרד הבריאות",
    "משרד הדיגיטל", "משרד הדתות", "משרד החדשנות המדע והטכנולוגיה", "משרד החוץ",
    "משרד החינוך", "משרד החקלאות ופיתוח הכפר", "משרד הכלכלה והתעשייה",
    "משרד המשפטים", "משרד העבודה", "משרד העלייה והקליטה", "משרד הפנים",
    "משרד הרווחה", "משרד השיכון והבינוי", "משרד התחבורה והבטיחות בדרכים",
    "משרד התיירות", "משרד התקשורת", "משרד התרבות והספורט", "משרד ירושלים ומורשת",
    "משרד רה\"מ", "נציבות שירות המדינה", "רשות הרגולציה", "אגף תקציבים",
    "רשות החדשנות", "רשות החברות הממשלתיות", "רשות החירום הלאומית (רח\"ל)",
    "ועדת השרים", "ועדת הכספים", "היועץ המשפטי לממשלה", "משטרת ישראל", "כבאות והצלה"
}

# Department aliases and variations
DEPARTMENT_ALIASES = {
    "משרד רה\"מ": ["משרד ראש הממשלה", "מש\"ר", "PMO", "ראש הממשלה"],
    "משרד האוצר": ["משהאו", "אוצר", "מש האוצר", "Treasury", "MOF"],
    "משרד הביטחון": ["מש הביטחון", "מ\"ב", "MOD", "Defense"],
    "משרד החינוך": ["מש החינוך", "מ\"ח", "MOE", "Education"],
    "משרד הבריאות": ["מש הבריאות", "מב\"ר", "MOH", "Health"],
    "משרד הפנים": ["מש הפנים", "מ\"פ", "MOI", "Interior"],
    "משרד החוץ": ["מש החוץ", "MFA", "Foreign Affairs"],
    "משטרת ישראל": ["מש\"ט", "Police", "Israel Police"]
}

# Department categorization for cross-validation
DEPARTMENT_CATEGORIES = {
    "security": {
        "משרד הביטחון", "המשרד לביטחון לאומי", "המשרד לביטחון פנים",
        "משטרת ישראל", "רשות החירום הלאומית (רח\"ל)"
    },
    "economic": {
        "משרד האוצר", "משרד הכלכלה והתעשייה", "אגף תקציבים",
        "רשות החברות הממשלתיות", "רשות הרגולציה"
    },
    "social": {
        "משרד הרווחה", "משרד העבודה", "המשרד לשוויון חברתי",
        "משרד העלייה והקליטה"
    },
    "infrastructure": {
        "משרד האנרגיה והתשתיות", "משרד התחבורה והבטיחות בדרכים",
        "משרד השיכון והבינוי", "מערך הדיגיטל", "משרד הדיגיטל"
    }
}


@dataclass
class DepartmentValidation:
    """Result of department validation."""
    is_authorized: bool
    normalized_name: str
    close_matches: List[str]
    category: Optional[str] = None
    aliases_found: List[str] = None


class DepartmentValidationCheck(AbstractQACheck):
    """
    Comprehensive department/government body validation.

    Checks for:
    - Authorization against approved lists
    - Name consistency and standardization
    - Cross-field correlation
    - Historical context validation
    """

    def __init__(self,
                 similarity_threshold: float = 0.8,
                 check_aliases: bool = True,
                 **kwargs):
        super().__init__(
            check_name="department_validation",
            description="Validates government body names, authorization, and consistency",
            **kwargs
        )
        self.similarity_threshold = similarity_threshold
        self.check_aliases = check_aliases
        self.authorized_bodies = AUTHORIZED_GOVERNMENT_BODIES
        self.department_aliases = DEPARTMENT_ALIASES
        self.department_categories = DEPARTMENT_CATEGORIES

        # Build reverse alias lookup
        self.alias_to_canonical = {}
        for canonical, aliases in self.department_aliases.items():
            for alias in aliases:
                self.alias_to_canonical[alias.lower()] = canonical

    def _validate_record(self, record: Dict) -> List[QAIssue]:
        """Validate department information for a single record."""
        issues = []
        decision_key = record.get('decision_key', 'unknown')

        # Primary validation
        government_body = record.get('government_body', '')
        if government_body:
            dept_issues = self._validate_department(decision_key, 'government_body', government_body)
            issues.extend(dept_issues)

        # Cross-field validation
        cross_field_issues = self._validate_cross_field_consistency(decision_key, record)
        issues.extend(cross_field_issues)

        # Context validation
        context_issues = self._validate_department_context(decision_key, record)
        issues.extend(context_issues)

        return issues

    def _validate_department(self, decision_key: str, field: str, department_name: str) -> List[QAIssue]:
        """Validate a single department name."""
        issues = []

        # Clean and normalize department name
        cleaned_name = self._clean_department_name(department_name)
        validation_result = self._check_department_authorization(cleaned_name)

        if not validation_result.is_authorized:
            severity = CheckSeverity.HIGH

            # Check for close matches to suggest corrections
            if validation_result.close_matches:
                description = f"Unauthorized department: '{department_name}'. Did you mean: {', '.join(validation_result.close_matches[:2])}?"
                severity = CheckSeverity.MEDIUM  # Lower severity if we have good suggestions
            else:
                description = f"Unauthorized department: '{department_name}'"

            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=severity,
                field=field,
                current_value=department_name,
                description=description,
                expected_value="Authorized government body name",
                unauthorized_department=department_name,
                cleaned_name=cleaned_name,
                close_matches=validation_result.close_matches,
                aliases_found=validation_result.aliases_found or []
            ))

        # Check for inconsistent naming (authorized but not canonical)
        if validation_result.is_authorized and validation_result.normalized_name != department_name:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.LOW,
                field=field,
                current_value=department_name,
                description=f"Non-canonical department name. Standard form: '{validation_result.normalized_name}'",
                expected_value=validation_result.normalized_name,
                current_form=department_name,
                canonical_form=validation_result.normalized_name,
                is_alias=True
            ))

        # Check for format issues
        format_issues = self._check_department_format(decision_key, field, department_name)
        issues.extend(format_issues)

        return issues

    def _validate_cross_field_consistency(self, decision_key: str, record: Dict) -> List[QAIssue]:
        """Validate consistency between department and other fields."""
        issues = []

        government_body = record.get('government_body', '')
        policy_areas = record.get('policy_areas', [])

        if isinstance(policy_areas, str):
            policy_areas = [tag.strip() for tag in policy_areas.split(',') if tag.strip()]

        if not government_body or not policy_areas:
            return issues

        # Check department-policy consistency
        expected_policies = self._get_expected_policies_for_department(government_body)
        if expected_policies:
            policy_match = any(policy in policy_areas for policy in expected_policies)

            if not policy_match:
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.LOW,
                    field="government_body",
                    current_value=f"Department: {government_body}, Policies: {', '.join(policy_areas)}",
                    description=f"Department '{government_body}' policies don't match typical areas",
                    expected_value=f"Policies including: {', '.join(expected_policies)}",
                    government_body=government_body,
                    current_policies=policy_areas,
                    expected_policies=expected_policies
                ))

        return issues

    def _validate_department_context(self, decision_key: str, record: Dict) -> List[QAIssue]:
        """Validate department in historical/contextual sense."""
        issues = []

        government_body = record.get('government_body', '')
        decision_date = record.get('decision_date', '')
        gov_num = record.get('gov_num', '')

        if not all([government_body, decision_date, gov_num]):
            return issues

        # Check for anachronistic department names
        anachronism_issues = self._check_department_anachronisms(
            decision_key, government_body, decision_date, gov_num
        )
        issues.extend(anachronism_issues)

        return issues

    def _clean_department_name(self, department_name: str) -> str:
        """Clean and normalize department name."""
        cleaned = department_name.strip()

        # Remove common prefixes/suffixes
        prefixes_to_remove = ['של ', 'ה', 'מ']
        suffixes_to_remove = ['*', '**', '***']

        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned)

        # Remove special characters at start/end
        cleaned = cleaned.strip('*-.,;')

        return cleaned

    def _check_department_authorization(self, department_name: str) -> DepartmentValidation:
        """Check if department is authorized and find alternatives."""
        cleaned_lower = department_name.lower()

        # Direct match check
        for authorized in self.authorized_bodies:
            if authorized.lower() == cleaned_lower:
                return DepartmentValidation(
                    is_authorized=True,
                    normalized_name=authorized,
                    close_matches=[]
                )

        # Alias check
        canonical = self.alias_to_canonical.get(cleaned_lower)
        if canonical:
            return DepartmentValidation(
                is_authorized=True,
                normalized_name=canonical,
                close_matches=[],
                aliases_found=[department_name]
            )

        # Fuzzy matching for suggestions
        close_matches = get_close_matches(
            department_name,
            self.authorized_bodies,
            n=3,
            cutoff=self.similarity_threshold
        )

        # Check aliases for fuzzy matches too
        alias_matches = []
        for canonical, aliases in self.department_aliases.items():
            for alias in aliases:
                if alias.lower() in cleaned_lower or cleaned_lower in alias.lower():
                    alias_matches.append(canonical)
                    break

        all_matches = list(set(close_matches + alias_matches))

        return DepartmentValidation(
            is_authorized=False,
            normalized_name=department_name,
            close_matches=all_matches[:3],
            aliases_found=alias_matches
        )

    def _check_department_format(self, decision_key: str, field: str, department_name: str) -> List[QAIssue]:
        """Check department name format for common issues."""
        issues = []

        # Check for obvious formatting issues
        format_issues = []

        # Multiple consecutive spaces
        if re.search(r'  +', department_name):
            format_issues.append('multiple_spaces')

        # Mixed Hebrew/English inappropriately
        has_hebrew = any('\u0590' <= char <= '\u05FF' for char in department_name)
        has_english = any(char.isalpha() and ord(char) < 128 for char in department_name)

        if has_hebrew and has_english:
            # Check if it's a legitimate mixed case (like abbreviations)
            if not re.search(r'["\(\)״]', department_name):  # No quotes or parentheses for abbreviations
                format_issues.append('mixed_language')

        # Unusual characters
        if re.search(r'[^\w\s\-\.\"\(\)״״\'\/]', department_name):
            format_issues.append('unusual_characters')

        # Too short (likely incomplete)
        if len(department_name.strip()) < 3:
            format_issues.append('too_short')

        # Too long (likely concatenated)
        if len(department_name) > 100:
            format_issues.append('too_long')

        if format_issues:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.LOW,
                field=field,
                current_value=department_name,
                description=f"Department name formatting issues: {', '.join(format_issues)}",
                expected_value="Properly formatted department name",
                format_issues=format_issues
            ))

        return issues

    def _get_expected_policies_for_department(self, department_name: str) -> List[str]:
        """Get expected policy areas for a department."""
        # Simplified mapping - in practice this would be more comprehensive
        department_policy_mapping = {
            "משרד החינוך": ["חינוך"],
            "משרד הבריאות": ["בריאות ורפואה"],
            "משרד הביטחון": ["מדיני ביטחוני"],
            "משרד השיכון והבינוי": ["בינוי ושיכון", "דיור, נדלן ותכנון"],
            "משרד החקלאות ופיתוח הכפר": ["חקלאות ופיתוח הכפר"],
            "משרד האנרגיה והתשתיות": ["אנרגיה מים ותשתיות"],
            "משרד הרווחה": ["רווחה ושירותים חברתיים"],
            "משרד התחבורה והבטיחות בדרכים": ["תחבורה ובטיחות בדרכים"],
            "משרד המשפטים": ["חקיקה, משפט ורגולציה", "משפטים"],
            "משרד החוץ": ["חוץ הסברה ותפוצות"],
            "משרד האוצר": ["תקציב, פיננסים, ביטוח ומיסוי"]
        }

        # Check exact match first
        if department_name in department_policy_mapping:
            return department_policy_mapping[department_name]

        # Check partial matches
        for dept, policies in department_policy_mapping.items():
            if dept in department_name or department_name in dept:
                return policies

        return []

    def _check_department_anachronisms(self, decision_key: str, department_name: str,
                                     decision_date: str, gov_num: str) -> List[QAIssue]:
        """Check for departments that didn't exist at decision time."""
        issues = []

        # This would require a comprehensive database of department changes over time
        # For now, implement basic checks for known major changes

        # Parse date for analysis
        from datetime import datetime
        try:
            date_obj = datetime.strptime(decision_date, "%Y-%m-%d").date()
        except ValueError:
            return issues  # Skip if date parsing fails

        # Example: Digital ministry was established later
        digital_ministries = ["מערך הדיגיטל", "משרד הדיגיטל"]
        if any(digital in department_name for digital in digital_ministries):
            # Digital ministry established around 2020
            from datetime import date as date_class
            if date_obj < date_class(2020, 1, 1):
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.MEDIUM,
                    field="government_body",
                    current_value=department_name,
                    description=f"Digital ministry mentioned before establishment date",
                    expected_value="Department that existed at decision time",
                    department=department_name,
                    decision_date=decision_date,
                    anachronism_type="early_reference"
                ))

        return issues

    def _generate_summary(self, issues: List[QAIssue], total_scanned: int) -> Dict[str, Any]:
        """Generate summary statistics for department validation check."""
        summary = {
            "total_scanned": total_scanned,
            "total_issues": len(issues),
            "issue_rate": f"{(len(issues) / total_scanned * 100):.1f}%" if total_scanned > 0 else "0%"
        }

        # Group issues by type
        issue_types = defaultdict(int)
        severity_counts = defaultdict(int)
        unauthorized_departments = set()
        format_issues = defaultdict(int)

        for issue in issues:
            # Extract issue type from description
            desc = issue.description.lower()
            if "unauthorized" in desc:
                issue_type = "unauthorized"
                unauthorized_departments.add(issue.metadata.get('unauthorized_department', ''))
            elif "canonical" in desc or "alias" in desc:
                issue_type = "naming_inconsistency"
            elif "formatting" in desc or "format" in desc:
                issue_type = "format_issues"
                format_issues_list = issue.metadata.get('format_issues', [])
                for fmt_issue in format_issues_list:
                    format_issues[fmt_issue] += 1
            elif "consistency" in desc or "policies" in desc:
                issue_type = "policy_mismatch"
            elif "anachronism" in desc:
                issue_type = "historical_issues"
            else:
                issue_type = "other"

            issue_types[issue_type] += 1
            severity_counts[issue.severity.value] += 1

        summary.update({
            "issues_by_type": dict(issue_types),
            "issues_by_severity": dict(severity_counts),
            "format_issues_breakdown": dict(format_issues)
        })

        # Department quality metrics
        if issues:
            authorization_rate = (1 - issue_types.get("unauthorized", 0) / len(issues)) * 100
            naming_consistency_rate = (1 - issue_types.get("naming_inconsistency", 0) / len(issues)) * 100

            summary.update({
                "authorization_rate": f"{authorization_rate:.1f}%",
                "naming_consistency_rate": f"{naming_consistency_rate:.1f}%",
                "unauthorized_departments_found": list(unauthorized_departments),
                "total_authorized_bodies": len(self.authorized_bodies),
                "aliases_supported": len(self.department_aliases)
            })

        return summary


class DepartmentConsistencyCheck(AbstractQACheck):
    """
    Specialized check for department consistency across the dataset.

    Analyzes department usage patterns and identifies inconsistencies.
    """

    def __init__(self, **kwargs):
        super().__init__(
            check_name="department_consistency",
            description="Validates department usage patterns and consistency",
            **kwargs
        )
        self.department_usage = defaultdict(int)
        self.department_variations = defaultdict(set)

    def run(self, records: List[Dict]) -> 'QAScanResult':
        """Override run to perform cross-record department analysis."""
        from ..qa_core import QAScanResult
        import time

        start_time = time.time()
        self._init_progress(len(records))

        # Collect department usage patterns
        for record in records:
            government_body = record.get('government_body', '')
            if government_body:
                self.department_usage[government_body] += 1

                # Track variations (similar department names)
                cleaned = self._clean_department_name(government_body)
                self.department_variations[cleaned].add(government_body)

        # Identify consistency issues
        all_issues = []
        consistency_issues = self._analyze_department_consistency(records)
        all_issues.extend(consistency_issues)

        self._complete_progress()
        execution_time = time.time() - start_time

        return QAScanResult(
            check_name=self.check_name,
            total_scanned=len(records),
            issues_found=len(all_issues),
            issues=all_issues,
            summary=self._generate_consistency_summary(all_issues, len(records)),
            execution_time=execution_time,
            progress=self._progress
        )

    def _validate_record(self, record: Dict) -> List[QAIssue]:
        """Not used in consistency check - override run instead."""
        return []

    def _clean_department_name(self, name: str) -> str:
        """Clean department name for comparison."""
        cleaned = name.lower().strip()
        # Remove common variations
        cleaned = re.sub(r'[״"\'\-\.]', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned

    def _analyze_department_consistency(self, records: List[Dict]) -> List[QAIssue]:
        """Analyze department usage for consistency issues."""
        issues = []

        # Find department names with multiple variations
        for cleaned_name, variations in self.department_variations.items():
            if len(variations) > 1:
                # Sort by frequency to identify canonical form
                variation_counts = [(var, self.department_usage[var]) for var in variations]
                variation_counts.sort(key=lambda x: x[1], reverse=True)

                canonical_form = variation_counts[0][0]
                minor_variations = [var for var, count in variation_counts[1:] if count < variation_counts[0][1] * 0.1]

                # Create issues for minor variations
                for minor_var in minor_variations:
                    # Find a representative record with this variation
                    representative_record = next(
                        (r for r in records if r.get('government_body') == minor_var),
                        None
                    )

                    if representative_record:
                        issues.append(self.create_issue(
                            decision_key=representative_record.get('decision_key', 'unknown'),
                            severity=CheckSeverity.LOW,
                            field="government_body",
                            current_value=minor_var,
                            description=f"Inconsistent department name variation. Most common form: '{canonical_form}'",
                            expected_value=canonical_form,
                            current_variation=minor_var,
                            canonical_form=canonical_form,
                            usage_count=self.department_usage[minor_var],
                            canonical_count=self.department_usage[canonical_form],
                            all_variations=list(variations)
                        ))

        return issues

    def _generate_consistency_summary(self, issues: List[QAIssue], total_scanned: int) -> Dict[str, Any]:
        """Generate summary for department consistency check."""
        # Most common departments
        most_common = sorted(self.department_usage.items(), key=lambda x: x[1], reverse=True)[:10]

        # Departments with variations
        departments_with_variations = {
            cleaned: list(variations)
            for cleaned, variations in self.department_variations.items()
            if len(variations) > 1
        }

        return {
            "total_scanned": total_scanned,
            "total_issues": len(issues),
            "unique_department_names": len(self.department_usage),
            "departments_with_variations": len(departments_with_variations),
            "most_common_departments": most_common,
            "variation_examples": dict(list(departments_with_variations.items())[:5])
        }