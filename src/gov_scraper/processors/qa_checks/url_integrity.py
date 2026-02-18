"""
URL Integrity Checks Module

Implements comprehensive URL validation including:
- URL format validation
- Accessibility checks
- Redirect validation
- Domain validation
- URL pattern consistency
"""

import re
import logging
import requests
from urllib.parse import urlparse, parse_qs, unquote
from typing import Dict, List, Set, Any, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass
import time

from ..qa_core import AbstractQACheck, QAIssue, CheckSeverity

logger = logging.getLogger(__name__)


@dataclass
class URLValidationResult:
    """Result of URL validation."""
    is_valid: bool
    status_code: Optional[int] = None
    response_time: Optional[float] = None
    final_url: Optional[str] = None
    redirect_count: int = 0
    error_message: Optional[str] = None
    content_type: Optional[str] = None


class URLIntegrityCheck(AbstractQACheck):
    """
    Comprehensive URL integrity validation.

    Checks for:
    - URL format validation
    - HTTP accessibility
    - Redirect chains
    - Domain consistency
    - URL parameter validation
    """

    def __init__(self,
                 check_accessibility: bool = True,
                 request_timeout: int = 10,
                 max_redirects: int = 5,
                 expected_domains: Set[str] = None,
                 **kwargs):
        super().__init__(
            check_name="url_integrity",
            description="Validates URL format, accessibility, and consistency",
            **kwargs
        )
        self.check_accessibility = check_accessibility
        self.request_timeout = request_timeout
        self.max_redirects = max_redirects
        self.expected_domains = expected_domains or {
            'www.gov.il',
            'gov.il',
            'mof.gov.il',
            'pmo.gov.il'
        }

        # URL patterns for Israeli government sites
        self.valid_url_patterns = [
            r'https?://(?:www\.)?gov\.il/',
            r'https?://\w+\.gov\.il/',
            r'https?://(?:www\.)?pmo\.gov\.il/',
            r'https?://(?:www\.)?mof\.gov\.il/'
        ]

        # Cache for URL validation results
        self._url_cache: Dict[str, URLValidationResult] = {}

    def _validate_record(self, record: Dict) -> List[QAIssue]:
        """Validate URLs in a single record."""
        issues = []
        decision_key = record.get('decision_key', 'unknown')

        # Check URL fields
        url_fields = ['decision_link', 'source_url', 'document_url']

        for field in url_fields:
            url = record.get(field, '')
            if not url:
                continue

            # Format validation
            format_issues = self._check_url_format(decision_key, field, url)
            issues.extend(format_issues)

            # Skip accessibility check if format is invalid
            if format_issues and any(issue.severity == CheckSeverity.HIGH for issue in format_issues):
                continue

            # Accessibility check
            if self.check_accessibility:
                access_issues = self._check_url_accessibility(decision_key, field, url)
                issues.extend(access_issues)

            # Pattern consistency
            pattern_issues = self._check_url_patterns(decision_key, field, url)
            issues.extend(pattern_issues)

            # Parameter validation (specific to gov.il URLs)
            param_issues = self._check_url_parameters(decision_key, field, url)
            issues.extend(param_issues)

        return issues

    def _check_url_format(self, decision_key: str, field: str, url: str) -> List[QAIssue]:
        """Check URL format validity."""
        issues = []

        # Basic format check
        try:
            parsed = urlparse(url)
        except Exception as e:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.HIGH,
                field=field,
                current_value=url,
                description=f"Invalid URL format: {str(e)}",
                expected_value="Valid URL format",
                parse_error=str(e)
            ))
            return issues

        # Check required components
        if not parsed.scheme:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.HIGH,
                field=field,
                current_value=url,
                description="Missing URL scheme (http/https)",
                expected_value="URL with scheme (https://...)",
                missing_component="scheme"
            ))

        if not parsed.netloc:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.HIGH,
                field=field,
                current_value=url,
                description="Missing domain name",
                expected_value="URL with valid domain",
                missing_component="netloc"
            ))

        # Check scheme
        if parsed.scheme and parsed.scheme.lower() not in ['http', 'https']:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.MEDIUM,
                field=field,
                current_value=url,
                description=f"Unexpected URL scheme: {parsed.scheme}",
                expected_value="http or https scheme",
                scheme_found=parsed.scheme
            ))

        # Prefer HTTPS
        if parsed.scheme and parsed.scheme.lower() == 'http' and 'gov.il' in parsed.netloc:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.LOW,
                field=field,
                current_value=url,
                description="Using HTTP instead of HTTPS for government site",
                expected_value="HTTPS URL for security",
                security_issue=True
            ))

        # Check for suspicious patterns
        suspicious_patterns = [
            r'javascript:', r'data:', r'file:', r'ftp:',
            r'\.\./', r'%2e%2e', r'%00', r'<script',
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, url.lower()):
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.HIGH,
                    field=field,
                    current_value=url,
                    description=f"Suspicious URL pattern detected: {pattern}",
                    expected_value="Safe URL without suspicious patterns",
                    suspicious_pattern=pattern
                ))

        # Check for encoding issues
        try:
            decoded_url = unquote(url)
            if len(decoded_url) != len(url) and any(ord(c) > 127 for c in decoded_url):
                # URL contains encoded non-ASCII characters
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.LOW,
                    field=field,
                    current_value=url,
                    description="URL contains encoded non-ASCII characters",
                    expected_value="ASCII URL or properly encoded international characters",
                    decoded_url=decoded_url
                ))
        except Exception:
            pass  # Skip encoding check if decoding fails

        return issues

    def _check_url_accessibility(self, decision_key: str, field: str, url: str) -> List[QAIssue]:
        """Check URL accessibility via HTTP request."""
        issues = []

        # Check cache first
        if url in self._url_cache:
            result = self._url_cache[url]
        else:
            result = self._validate_url_access(url)
            self._url_cache[url] = result

        if not result.is_valid:
            severity = CheckSeverity.HIGH
            if result.status_code:
                if result.status_code == 404:
                    description = f"URL not found (404 error)"
                elif result.status_code >= 500:
                    description = f"Server error ({result.status_code})"
                    severity = CheckSeverity.MEDIUM  # Might be temporary
                elif result.status_code in [401, 403]:
                    description = f"Access denied ({result.status_code})"
                    severity = CheckSeverity.MEDIUM  # Might require authentication
                else:
                    description = f"HTTP error ({result.status_code})"
            else:
                description = f"URL inaccessible: {result.error_message}"

            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=severity,
                field=field,
                current_value=url,
                description=description,
                expected_value="Accessible URL returning 2xx status",
                status_code=result.status_code,
                error_message=result.error_message,
                response_time=result.response_time
            ))

        # Check for excessive redirects
        if result.redirect_count > 3:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.MEDIUM,
                field=field,
                current_value=url,
                description=f"Excessive redirects: {result.redirect_count} hops",
                expected_value="Direct access or minimal redirects",
                redirect_count=result.redirect_count,
                final_url=result.final_url
            ))

        # Check for slow response
        if result.response_time and result.response_time > 5.0:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.LOW,
                field=field,
                current_value=url,
                description=f"Slow response: {result.response_time:.1f}s",
                expected_value="Response time < 5s",
                response_time=result.response_time,
                performance_issue=True
            ))

        return issues

    def _check_url_patterns(self, decision_key: str, field: str, url: str) -> List[QAIssue]:
        """Check URL patterns for consistency."""
        issues = []
        parsed = urlparse(url)

        # Check domain consistency
        if parsed.netloc and not any(domain in parsed.netloc for domain in self.expected_domains):
            # Check if it's a valid gov.il subdomain
            if not re.match(r'^[\w-]+\.gov\.il$', parsed.netloc):
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.MEDIUM,
                    field=field,
                    current_value=url,
                    description=f"Unexpected domain: {parsed.netloc}",
                    expected_value=f"One of: {', '.join(self.expected_domains)}",
                    domain_found=parsed.netloc,
                    expected_domains=list(self.expected_domains)
                ))

        # Check URL pattern consistency
        pattern_match = False
        for pattern in self.valid_url_patterns:
            if re.match(pattern, url):
                pattern_match = True
                break

        if not pattern_match and 'gov.il' in url:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.LOW,
                field=field,
                current_value=url,
                description="URL doesn't match expected government URL patterns",
                expected_value="URL matching standard gov.il patterns",
                patterns_checked=self.valid_url_patterns
            ))

        return issues

    def _check_url_parameters(self, decision_key: str, field: str, url: str) -> List[QAIssue]:
        """Check URL parameters for gov.il specific requirements."""
        issues = []
        parsed = urlparse(url)

        if not parsed.query:
            return issues  # No parameters to check

        try:
            params = parse_qs(parsed.query)
        except Exception as e:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.MEDIUM,
                field=field,
                current_value=url,
                description=f"Invalid URL parameters: {str(e)}",
                expected_value="Valid URL parameters",
                parameter_error=str(e)
            ))
            return issues

        # Check for common gov.il parameters
        expected_params = {
            'DecisionId', 'decision_id', 'id', 'ID',
            'meetingId', 'meeting_id',
            'docId', 'doc_id'
        }

        # Look for decision ID patterns
        has_decision_id = False
        for param_name, param_values in params.items():
            if param_name.lower() in [p.lower() for p in expected_params]:
                has_decision_id = True

                # Check parameter value format
                for value in param_values:
                    if not value or not value.strip():
                        issues.append(self.create_issue(
                            decision_key=decision_key,
                            severity=CheckSeverity.MEDIUM,
                            field=field,
                            current_value=url,
                            description=f"Empty parameter value: {param_name}",
                            expected_value="Non-empty parameter values",
                            empty_parameter=param_name
                        ))

        # For decision URLs, expect some form of ID
        if field == 'decision_link' and not has_decision_id:
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.LOW,
                field=field,
                current_value=url,
                description="Decision URL missing expected ID parameter",
                expected_value="URL with decision ID parameter",
                parameters_found=list(params.keys()),
                expected_parameters=list(expected_params)
            ))

        return issues

    def _validate_url_access(self, url: str) -> URLValidationResult:
        """Validate URL accessibility via HTTP request."""
        try:
            start_time = time.time()

            # Configure session with reasonable defaults
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (compatible; GOV2DB-URLChecker/1.0)'
            })

            response = session.get(
                url,
                timeout=self.request_timeout,
                allow_redirects=True,
                verify=True  # Verify SSL certificates
            )

            response_time = time.time() - start_time

            # Count redirects
            redirect_count = len(response.history)

            return URLValidationResult(
                is_valid=response.status_code < 400,
                status_code=response.status_code,
                response_time=response_time,
                final_url=response.url if response.url != url else None,
                redirect_count=redirect_count,
                content_type=response.headers.get('content-type')
            )

        except requests.exceptions.Timeout:
            return URLValidationResult(
                is_valid=False,
                error_message="Request timeout"
            )
        except requests.exceptions.ConnectionError as e:
            return URLValidationResult(
                is_valid=False,
                error_message=f"Connection error: {str(e)}"
            )
        except requests.exceptions.SSLError as e:
            return URLValidationResult(
                is_valid=False,
                error_message=f"SSL error: {str(e)}"
            )
        except requests.exceptions.RequestException as e:
            return URLValidationResult(
                is_valid=False,
                error_message=f"Request error: {str(e)}"
            )
        except Exception as e:
            return URLValidationResult(
                is_valid=False,
                error_message=f"Unexpected error: {str(e)}"
            )

    def _generate_summary(self, issues: List[QAIssue], total_scanned: int) -> Dict[str, Any]:
        """Generate summary statistics for URL integrity check."""
        summary = {
            "total_scanned": total_scanned,
            "total_issues": len(issues),
            "issue_rate": f"{(len(issues) / total_scanned * 100):.1f}%" if total_scanned > 0 else "0%"
        }

        # Group issues by type
        issue_types = defaultdict(int)
        severity_counts = defaultdict(int)
        field_counts = defaultdict(int)
        status_codes = defaultdict(int)

        for issue in issues:
            # Extract issue type from description
            desc = issue.description.lower()
            if "format" in desc or "scheme" in desc:
                issue_type = "format_errors"
            elif "404" in desc or "not found" in desc:
                issue_type = "not_found"
            elif "server error" in desc or "5xx" in desc:
                issue_type = "server_errors"
            elif "access denied" in desc or "401" in desc or "403" in desc:
                issue_type = "access_denied"
            elif "redirect" in desc:
                issue_type = "redirect_issues"
            elif "slow" in desc or "performance" in desc:
                issue_type = "performance_issues"
            elif "domain" in desc or "pattern" in desc:
                issue_type = "domain_issues"
            elif "parameter" in desc:
                issue_type = "parameter_issues"
            else:
                issue_type = "other"

            issue_types[issue_type] += 1
            severity_counts[issue.severity.value] += 1
            field_counts[issue.field] += 1

            # Track status codes
            if 'status_code' in issue.metadata:
                status_codes[issue.metadata['status_code']] += 1

        summary.update({
            "issues_by_type": dict(issue_types),
            "issues_by_severity": dict(severity_counts),
            "issues_by_field": dict(field_counts),
            "http_status_codes": dict(status_codes) if status_codes else {}
        })

        # URL health metrics
        total_urls = sum(field_counts.values())
        if total_urls > 0:
            accessibility_rate = (1 - (issue_types.get("not_found", 0) + issue_types.get("server_errors", 0)) / total_urls) * 100
            format_error_rate = issue_types.get("format_errors", 0) / total_urls * 100

            summary.update({
                "accessibility_rate": f"{accessibility_rate:.1f}%",
                "format_error_rate": f"{format_error_rate:.1f}%",
                "total_urls_checked": total_urls,
                "cache_hits": len([url for url, result in self._url_cache.items() if result is not None])
            })

        return summary


class DomainConsistencyCheck(AbstractQACheck):
    """
    Specialized check for domain consistency across URL fields.

    Ensures all URLs in a record come from expected domains and are consistent.
    """

    def __init__(self,
                 expected_domains: Set[str] = None,
                 require_same_domain: bool = False,
                 **kwargs):
        super().__init__(
            check_name="domain_consistency",
            description="Validates domain consistency across URL fields",
            **kwargs
        )
        self.expected_domains = expected_domains or {'gov.il'}
        self.require_same_domain = require_same_domain

    def _validate_record(self, record: Dict) -> List[QAIssue]:
        """Validate domain consistency within a record."""
        issues = []
        decision_key = record.get('decision_key', 'unknown')

        # Extract all URLs and their domains
        url_fields = ['decision_link', 'source_url', 'document_url']
        record_domains = set()
        record_urls = {}

        for field in url_fields:
            url = record.get(field, '')
            if url:
                try:
                    parsed = urlparse(url)
                    domain = parsed.netloc.lower()
                    record_domains.add(domain)
                    record_urls[field] = (url, domain)
                except Exception:
                    continue

        if not record_urls:
            return issues  # No URLs to check

        # Check against expected domains
        for field, (url, domain) in record_urls.items():
            domain_valid = any(expected in domain for expected in self.expected_domains)

            if not domain_valid:
                issues.append(self.create_issue(
                    decision_key=decision_key,
                    severity=CheckSeverity.MEDIUM,
                    field=field,
                    current_value=url,
                    description=f"Domain not in expected list: {domain}",
                    expected_value=f"Domain containing one of: {', '.join(self.expected_domains)}",
                    domain_found=domain,
                    expected_domains=list(self.expected_domains)
                ))

        # Check for domain consistency within record
        if self.require_same_domain and len(record_domains) > 1:
            domain_list = sorted(record_domains)
            issues.append(self.create_issue(
                decision_key=decision_key,
                severity=CheckSeverity.LOW,
                field='multiple_urls',
                current_value=f"Domains: {', '.join(domain_list)}",
                description=f"Multiple domains in single record: {', '.join(domain_list)}",
                expected_value="Single domain across all URLs",
                domains_found=domain_list,
                url_count=len(record_urls)
            ))

        return issues

    def _generate_summary(self, issues: List[QAIssue], total_scanned: int) -> Dict[str, Any]:
        """Generate summary for domain consistency check."""
        domain_counts = defaultdict(int)
        field_counts = defaultdict(int)

        for issue in issues:
            domain = issue.metadata.get('domain_found')
            if domain:
                domain_counts[domain] += 1
            field_counts[issue.field] += 1

        return {
            "total_scanned": total_scanned,
            "total_issues": len(issues),
            "domains_found": dict(domain_counts),
            "issues_by_field": dict(field_counts),
            "expected_domains": list(self.expected_domains),
            "require_same_domain": self.require_same_domain
        }