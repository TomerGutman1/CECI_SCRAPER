#!/usr/bin/env python3
"""
Phase 5: Content Anomalies Detection

Detect content-level problems like encoding issues, truncation, and scraping artifacts
in the Israeli government decisions database.

Usage:
    python bin/detect_content_anomalies.py [--sample-percent 5] [--seed 42]
"""

import os
import sys
import json
import re
import logging
import argparse
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gov_scraper.db.connector import get_supabase_client

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class ContentAnomalyDetector:
    """Detect various content-level anomalies in decision content."""

    def __init__(self):
        self.client = get_supabase_client()
        self.anomalies = {
            'encoding_issues': [],
            'cloudflare_remnants': [],
            'truncation_issues': [],
            'quality_issues': [],
            'suspicious_patterns': []
        }

        # Encoding issue patterns
        self.mojibake_patterns = [
            r'Ã',          # Common mojibake
            r'â€',         # UTF-8 decoded as Latin-1
            r'Ã¨|Ã©|Ã¡',  # Accented characters as mojibake
            r'\ufffd',     # Replacement character
            r'\\x[a-fA-F0-9]{2}',  # Hex escape sequences
        ]

        # Cloudflare detection patterns
        self.cloudflare_patterns = [
            r'Attention Required.*Cloudflare',
            r'Ray ID:?\s*[a-fA-F0-9]+',
            r'Cloudflare',
            r'Please enable JavaScript',
            r'DDoS protection by Cloudflare',
            r'Browser Integrity Check',
            r'Challenge Validation',
            r'Access denied'
        ]

        # Hebrew text patterns for validation
        self.hebrew_chars = r'[\u0590-\u05FF]'

        # Truncation indicators
        self.truncation_indicators = [
            r'\.{3,}$',           # Ending with ...
            r'המשך\.?\s*$',       # "continuation" in Hebrew
            r'המשך התוכן\.?\s*$', # "content continuation"
            r'להמשיך\.?\s*$',     # "to continue"
        ]

    def fetch_sample_records(self, sample_percent: float = 5.0, seed: int = None) -> List[Dict]:
        """Fetch a stratified sample of records with content field."""
        logger.info(f"Fetching stratified sample ({sample_percent}% per year) with content field...")

        # Import stratified sampling function
        from gov_scraper.processors.qa import fetch_records_stratified

        # Fetch sample with content field
        fields = [
            "decision_key", "decision_date", "decision_number",
            "decision_title", "decision_content", "decision_url"
        ]

        records = fetch_records_stratified(
            fields=fields,
            sample_percent_per_year=sample_percent,
            seed=seed
        )

        logger.info(f"Fetched {len(records)} records for content analysis")
        return records

    def detect_encoding_issues(self, content: str) -> List[str]:
        """Detect encoding issues in content."""
        issues = []

        if not content:
            return issues

        # Check for mojibake patterns
        for pattern in self.mojibake_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                issues.append(f"mojibake_pattern_{pattern[:5]}")

        # Check for mixed encodings (Latin chars mixed with Hebrew)
        latin_count = len(re.findall(r'[a-zA-Z]', content))
        hebrew_count = len(re.findall(self.hebrew_chars, content))
        total_letters = latin_count + hebrew_count

        if total_letters > 50:  # Only check substantial content
            latin_ratio = latin_count / total_letters
            if 0.1 < latin_ratio < 0.9:  # Mixed content (not just Hebrew or just Latin)
                # Check if Latin chars are in suspicious patterns (not URLs, names, etc.)
                suspicious_latin = re.findall(r'\b[a-zA-Z]{10,}\b', content)
                if len(suspicious_latin) > 5:
                    issues.append("suspicious_latin_mixing")

        # Check for null bytes or control characters
        if '\x00' in content:
            issues.append("null_bytes")

        control_chars = re.findall(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', content)
        if len(control_chars) > 2:  # Allow a few control chars
            issues.append("excessive_control_chars")

        return issues

    def detect_cloudflare_remnants(self, content: str) -> List[str]:
        """Detect Cloudflare blocking artifacts."""
        issues = []

        if not content:
            return issues

        content_lower = content.lower()

        for pattern in self.cloudflare_patterns:
            if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                issues.append(f"cloudflare_{pattern.split()[0].lower()}")

        # Check for JavaScript challenge patterns
        js_patterns = [
            r'setTimeout\(.*function',
            r'document\.getElementById',
            r'window\.location\.href',
            r'please.*javascript.*enable'
        ]

        for pattern in js_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                issues.append("javascript_challenge")
                break

        return issues

    def detect_truncation_issues(self, content: str) -> List[str]:
        """Detect content truncation issues."""
        issues = []

        if not content:
            return ["empty_content"]

        # Check for truncation indicators
        for pattern in self.truncation_indicators:
            if re.search(pattern, content.strip()):
                issues.append("explicit_truncation_marker")

        # Check for specific length limits (common database/processing limits)
        content_len = len(content)
        suspicious_lengths = [
            (32768, "32k_limit"),    # 32KB text limit
            (65536, "64k_limit"),    # 64KB limit
            (16384, "16k_limit"),    # 16KB limit
            (8192, "8k_limit"),      # 8KB limit
        ]

        for limit, issue_name in suspicious_lengths:
            if content_len == limit:
                issues.append(issue_name)

        # Check for abrupt endings (no proper punctuation)
        if content_len > 100:
            last_50 = content.strip()[-50:]
            if not re.search(r'[.!?]$', last_50.strip()):
                # Check if it ends mid-word or mid-sentence
                if re.search(r'[a-zA-Zא-ת]\s*$', last_50):
                    issues.append("abrupt_ending")

        return issues

    def detect_quality_issues(self, content: str, title: str = "") -> List[str]:
        """Detect general content quality issues."""
        issues = []

        if not content:
            return ["empty_content"]

        content_len = len(content.strip())

        # Very short content
        if content_len < 100:
            issues.append("very_short_content")
        elif content_len < 50:
            issues.append("extremely_short_content")

        # Repeated characters/patterns
        if re.search(r'(.)\1{20,}', content):  # 20+ repeated characters
            issues.append("excessive_repeated_chars")

        # HTML/XML artifacts
        html_tags = re.findall(r'<[^>]+>', content)
        if len(html_tags) > 5:
            issues.append("html_tags_present")

        # Check for XML artifacts
        if re.search(r'<\?xml|<!DOCTYPE', content):
            issues.append("xml_artifacts")

        # Excessive whitespace
        if content.count('\n') > content_len / 20:  # Too many line breaks
            issues.append("excessive_line_breaks")

        if content.count(' ') > content_len / 3:  # Suspicious spacing
            issues.append("excessive_spaces")

        # Content that's just punctuation or numbers
        alphanumeric = re.sub(r'[^\w\u0590-\u05FF]', '', content)
        if len(alphanumeric) < content_len / 10:
            issues.append("mostly_punctuation")

        # Check for content that doesn't match title
        if title and content_len > 200:
            # Extract key words from title
            title_words = re.findall(r'[\u0590-\u05FFa-zA-Z]+', title)
            if title_words:
                # Check if any title words appear in first 500 chars of content
                content_start = content[:500].lower()
                title_matches = sum(1 for word in title_words[:5]
                                  if word.lower() in content_start)
                if title_matches == 0:
                    issues.append("title_content_mismatch")

        return issues

    def analyze_record(self, record: Dict) -> Dict:
        """Analyze a single record for anomalies."""
        decision_key = record.get('decision_key', 'unknown')
        content = record.get('decision_content', '')
        title = record.get('decision_title', '')

        anomalies = {
            'decision_key': decision_key,
            'content_length': len(content) if content else 0,
            'issues': []
        }

        # Run all detection methods
        encoding_issues = self.detect_encoding_issues(content)
        cloudflare_issues = self.detect_cloudflare_remnants(content)
        truncation_issues = self.detect_truncation_issues(content)
        quality_issues = self.detect_quality_issues(content, title)

        # Collect all issues
        all_issues = (
            [(issue, 'encoding') for issue in encoding_issues] +
            [(issue, 'cloudflare') for issue in cloudflare_issues] +
            [(issue, 'truncation') for issue in truncation_issues] +
            [(issue, 'quality') for issue in quality_issues]
        )

        for issue, category in all_issues:
            anomalies['issues'].append({
                'type': issue,
                'category': category,
                'severity': self.assess_severity(issue, category)
            })

            # Store in main anomalies dict
            if category == 'encoding':
                self.anomalies['encoding_issues'].append((decision_key, issue, content[:200]))
            elif category == 'cloudflare':
                self.anomalies['cloudflare_remnants'].append((decision_key, issue, content[:200]))
            elif category == 'truncation':
                self.anomalies['truncation_issues'].append((decision_key, issue, content[:200]))
            elif category == 'quality':
                self.anomalies['quality_issues'].append((decision_key, issue, content[:200]))

        return anomalies

    def assess_severity(self, issue: str, category: str) -> str:
        """Assess severity of an issue."""
        high_severity = [
            'cloudflare', 'empty_content', '32k_limit', '64k_limit',
            'xml_artifacts', 'null_bytes', 'mostly_punctuation'
        ]

        medium_severity = [
            'explicit_truncation_marker', 'abrupt_ending', 'html_tags_present',
            'excessive_repeated_chars', 'title_content_mismatch', 'very_short_content'
        ]

        if any(h in issue for h in high_severity):
            return 'high'
        elif any(m in issue for m in medium_severity):
            return 'medium'
        else:
            return 'low'

    def run_analysis(self, sample_percent: float = 5.0, seed: int = None) -> Dict:
        """Run complete content anomaly analysis."""
        logger.info("Starting Phase 5: Content Anomalies Detection")

        # Fetch sample
        records = self.fetch_sample_records(sample_percent, seed)
        if not records:
            logger.error("No records fetched for analysis")
            return {}

        # Analyze each record
        results = []
        issue_counts = Counter()
        severity_counts = Counter()

        logger.info(f"Analyzing {len(records)} records for content anomalies...")

        for i, record in enumerate(records):
            if i % 100 == 0:
                logger.info(f"Processed {i}/{len(records)} records...")

            analysis = self.analyze_record(record)
            results.append(analysis)

            # Count issues
            for issue in analysis['issues']:
                issue_counts[f"{issue['category']}:{issue['type']}"] += 1
                severity_counts[issue['severity']] += 1

        # Compile final report
        report = {
            'timestamp': datetime.now().isoformat(),
            'sample_size': len(records),
            'sample_percent': sample_percent,
            'seed': seed,
            'summary': {
                'total_records_with_issues': sum(1 for r in results if r['issues']),
                'total_issues_found': sum(len(r['issues']) for r in results),
                'issue_counts': dict(issue_counts.most_common()),
                'severity_distribution': dict(severity_counts),
                'anomaly_categories': {
                    'encoding_issues': len(self.anomalies['encoding_issues']),
                    'cloudflare_remnants': len(self.anomalies['cloudflare_remnants']),
                    'truncation_issues': len(self.anomalies['truncation_issues']),
                    'quality_issues': len(self.anomalies['quality_issues'])
                }
            },
            'detailed_results': results[:50],  # First 50 for detailed view
            'sample_anomalies': {
                'encoding_issues': self.anomalies['encoding_issues'][:20],
                'cloudflare_remnants': self.anomalies['cloudflare_remnants'][:20],
                'truncation_issues': self.anomalies['truncation_issues'][:20],
                'quality_issues': self.anomalies['quality_issues'][:20]
            }
        }

        return report


def main():
    parser = argparse.ArgumentParser(description='Detect content anomalies in Israeli government decisions')
    parser.add_argument('--sample-percent', type=float, default=5.0,
                       help='Percentage of records to sample per year (default: 5.0)')
    parser.add_argument('--seed', type=int, default=42,
                       help='Random seed for reproducible sampling (default: 42)')

    args = parser.parse_args()

    detector = ContentAnomalyDetector()
    report = detector.run_analysis(args.sample_percent, args.seed)

    if not report:
        logger.error("Analysis failed")
        return 1

    # Save report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = os.path.join(PROJECT_ROOT, 'data', 'qa_reports')
    os.makedirs(report_dir, exist_ok=True)

    report_file = os.path.join(report_dir, f'phase5_anomalies_{timestamp}.json')

    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"Report saved to: {report_file}")

    # Print summary
    print(f"\n=== PHASE 5: CONTENT ANOMALIES DETECTION ===")
    print(f"Sample size: {report['sample_size']} records")
    print(f"Records with issues: {report['summary']['total_records_with_issues']}")
    print(f"Total issues found: {report['summary']['total_issues_found']}")

    print(f"\n--- SEVERITY DISTRIBUTION ---")
    for severity, count in report['summary']['severity_distribution'].items():
        print(f"{severity.upper()}: {count}")

    print(f"\n--- ANOMALY CATEGORIES ---")
    for category, count in report['summary']['anomaly_categories'].items():
        print(f"{category.replace('_', ' ').title()}: {count}")

    print(f"\n--- TOP ISSUES ---")
    for issue, count in list(report['summary']['issue_counts'].items())[:10]:
        print(f"{issue}: {count}")

    print(f"\nDetailed report saved to: {report_file}")

    return 0


if __name__ == '__main__':
    exit(main())