#!/usr/bin/env python3
"""
URL Integrity Analysis Script

Investigates whether URLs stored in the database match the correct decisions.
This is critical for understanding potential data shifting issues.

Usage:
    python bin/analyze_url_integrity.py [--sample-size N] [--focus-government N] [--output-file path]
"""

import sys
import os
import re
import logging
import argparse
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import Counter, defaultdict

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from gov_scraper.db.connector import get_supabase_client
from gov_scraper.scrapers.decision import extract_decision_number_from_url

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_decision_key_components(decision_key: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract government number and decision number from decision_key (format: {gov}_{decision})."""
    if not decision_key or '_' not in decision_key:
        return None, None

    parts = decision_key.split('_', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, None


def extract_numbers_from_url(url: str) -> Dict[str, Optional[str]]:
    """
    Extract various number patterns from URL.

    Returns:
        Dict with extracted components:
        - decision_from_path: Decision number from /dec-XXXX-YYYY pattern
        - all_numbers: All number sequences found in URL
        - government_hints: Any government number hints
    """
    if not url:
        return {
            'decision_from_path': None,
            'all_numbers': [],
            'government_hints': [],
            'year_from_url': None
        }

    result = {
        'decision_from_path': None,
        'all_numbers': [],
        'government_hints': [],
        'year_from_url': None
    }

    # Extract decision number from gov.il patterns: /dec-XXXX-YYYY, /decXXXX-YYYY, or /decXXXX_YYYY
    decision_match = re.search(r'/dec-?(\d+)[-_](\d{4})', url)
    if decision_match:
        result['decision_from_path'] = decision_match.group(1)
        result['year_from_url'] = decision_match.group(2)

    # Find all number sequences (3+ digits)
    all_numbers = re.findall(r'\d{3,}', url)
    result['all_numbers'] = all_numbers

    # Look for government number hints (typically 35-37 range)
    gov_hints = [num for num in all_numbers if num in ['35', '36', '37', '38']]
    result['government_hints'] = gov_hints

    return result


def analyze_url_decision_match(record: Dict) -> Dict:
    """
    Analyze if URL matches the decision_key and identify issues.

    Args:
        record: Database record with decision_key, url, decision_title, summary

    Returns:
        Analysis results dictionary
    """
    decision_key = record.get('decision_key', '')
    url = record.get('decision_url', '')
    title = record.get('decision_title', '')
    summary = record.get('summary', '')

    gov_num, decision_num = extract_decision_key_components(decision_key)
    url_components = extract_numbers_from_url(url)

    analysis = {
        'decision_key': decision_key,
        'url': url,
        'gov_from_key': gov_num,
        'decision_from_key': decision_num,
        'decision_from_url': url_components['decision_from_path'],
        'year_from_url': url_components['year_from_url'],
        'all_url_numbers': url_components['all_numbers'],
        'government_hints': url_components['government_hints'],
        'title_preview': title[:100] + '...' if len(title) > 100 else title,
        'summary_preview': summary[:100] + '...' if len(summary) > 100 else summary,
        'issues': [],
        'severity': 'ok'
    }

    # Check for URL-decision_key mismatches
    if not url:
        analysis['issues'].append('missing_url')
        analysis['severity'] = 'warning'
    elif url_components['decision_from_path'] and decision_num:
        try:
            url_decision = str(int(url_components['decision_from_path']))  # Normalize
            key_decision = str(int(decision_num))  # Normalize

            if url_decision != key_decision:
                analysis['issues'].append('url_decision_mismatch')
                analysis['severity'] = 'critical'

                # Check if it's an adjacent number (off-by-one error)
                diff = abs(int(url_decision) - int(key_decision))
                if diff <= 2:
                    analysis['issues'].append('adjacent_decision_error')
                elif diff <= 10:
                    analysis['issues'].append('nearby_decision_error')
                else:
                    analysis['issues'].append('far_decision_error')

        except (ValueError, TypeError):
            analysis['issues'].append('number_parsing_error')
            analysis['severity'] = 'warning'

    # Check for government number consistency
    if gov_num and url_components['government_hints']:
        if gov_num not in url_components['government_hints']:
            analysis['issues'].append('government_number_inconsistency')
            if analysis['severity'] == 'ok':
                analysis['severity'] = 'warning'

    return analysis


def fetch_sample_records(client, sample_size: int = 500, focus_government: Optional[str] = None) -> List[Dict]:
    """
    Fetch a representative sample of records from the database.

    Args:
        client: Supabase client
        sample_size: Number of records to fetch
        focus_government: Specific government number to focus on

    Returns:
        List of database records
    """
    logger.info(f"Fetching sample of {sample_size} records...")

    query = client.table("israeli_government_decisions").select(
        "decision_key, decision_url, decision_title, summary, government_number, decision_date"
    )

    if focus_government:
        query = query.eq("government_number", focus_government)
        logger.info(f"Focusing on government {focus_government}")

    # Get a distributed sample across different dates
    response = query.order("decision_date", desc=True).limit(sample_size).execute()

    if not response.data:
        logger.error("No data returned from database")
        return []

    logger.info(f"Successfully fetched {len(response.data)} records")
    return response.data


def fetch_problematic_cases(client) -> List[Dict]:
    """Fetch known problematic cases for analysis."""
    logger.info("Fetching known problematic cases (36_1022, 36_1024)...")

    response = client.table("israeli_government_decisions").select(
        "decision_key, decision_url, decision_title, summary, government_number, decision_date"
    ).in_("decision_key", ["36_1022", "36_1024"]).execute()

    logger.info(f"Found {len(response.data)} problematic cases")
    return response.data


def analyze_patterns(analyses: List[Dict]) -> Dict:
    """Analyze patterns across all URL integrity analyses."""
    if not analyses:
        logger.warning("No analyses to process")
        return {
            'total_analyzed': 0,
            'severity_counts': Counter(),
            'issue_counts': Counter(),
            'government_distribution': Counter(),
            'mismatch_examples': [],
            'adjacent_errors': [],
            'missing_url_count': 0,
            'clean_records': 0,
            'decision_differences': []
        }

    logger.info(f"Analyzing patterns across {len(analyses)} records...")

    patterns = {
        'total_analyzed': len(analyses),
        'severity_counts': Counter(a['severity'] for a in analyses),
        'issue_counts': Counter(),
        'government_distribution': Counter(),
        'mismatch_examples': [],
        'adjacent_errors': [],
        'missing_url_count': 0,
        'clean_records': 0,
        'decision_differences': []
    }

    for analysis in analyses:
        # Count issues
        for issue in analysis['issues']:
            patterns['issue_counts'][issue] += 1

        # Government distribution
        if analysis['gov_from_key']:
            patterns['government_distribution'][analysis['gov_from_key']] += 1

        # Collect examples of different issue types
        if 'url_decision_mismatch' in analysis['issues']:
            patterns['mismatch_examples'].append({
                'decision_key': analysis['decision_key'],
                'url': analysis['url'],
                'decision_from_key': analysis['decision_from_key'],
                'decision_from_url': analysis['decision_from_url'],
                'title': analysis['title_preview']
            })

            # Calculate difference for pattern analysis
            try:
                diff = int(analysis['decision_from_url']) - int(analysis['decision_from_key'])
                patterns['decision_differences'].append(diff)
            except (ValueError, TypeError):
                pass

        if 'adjacent_decision_error' in analysis['issues']:
            patterns['adjacent_errors'].append(analysis)

        if 'missing_url' in analysis['issues']:
            patterns['missing_url_count'] += 1

        if analysis['severity'] == 'ok':
            patterns['clean_records'] += 1

    # Analyze difference patterns
    if patterns['decision_differences']:
        diff_counter = Counter(patterns['decision_differences'])
        patterns['common_differences'] = diff_counter.most_common(10)
        patterns['systematic_shift_detected'] = any(
            count > 5 for diff, count in diff_counter.items() if diff != 0
        )

    return patterns


def generate_report(patterns: Dict, analyses: List[Dict], output_file: Optional[str] = None) -> str:
    """Generate a comprehensive analysis report."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report = {
        'analysis_metadata': {
            'timestamp': timestamp,
            'total_records_analyzed': patterns['total_analyzed'],
            'analysis_version': '1.0',
            'focus': 'URL integrity and data shifting investigation'
        },
        'summary_statistics': {
            'critical_issues': patterns['severity_counts']['critical'],
            'warnings': patterns['severity_counts']['warning'],
            'clean_records': patterns['clean_records'],
            'missing_urls': patterns['missing_url_count'],
            'integrity_score': round((patterns['clean_records'] / patterns['total_analyzed']) * 100, 2)
        },
        'issue_breakdown': dict(patterns['issue_counts']),
        'government_distribution': dict(patterns['government_distribution']),
        'url_mismatch_analysis': {
            'total_mismatches': patterns['issue_counts']['url_decision_mismatch'],
            'adjacent_errors': patterns['issue_counts']['adjacent_decision_error'],
            'nearby_errors': patterns['issue_counts']['nearby_decision_error'],
            'far_errors': patterns['issue_counts']['far_decision_error'],
            'systematic_shift_detected': patterns.get('systematic_shift_detected', False),
            'common_difference_patterns': patterns.get('common_differences', [])
        },
        'critical_examples': patterns['mismatch_examples'][:10],  # Top 10 examples
        'recommendations': []
    }

    # Add recommendations based on findings
    if report['summary_statistics']['critical_issues'] > 0:
        report['recommendations'].append(
            f"CRITICAL: {report['summary_statistics']['critical_issues']} records have URL-decision mismatches requiring immediate investigation"
        )

    if patterns.get('systematic_shift_detected'):
        report['recommendations'].append(
            "SYSTEMATIC ISSUE: Pattern of consistent decision number differences detected - indicates scraping logic error"
        )

    if report['summary_statistics']['missing_urls'] > 10:
        report['recommendations'].append(
            f"URL Coverage: {report['summary_statistics']['missing_urls']} records missing URLs - check scraping completeness"
        )

    integrity_score = report['summary_statistics']['integrity_score']
    if integrity_score < 90:
        report['recommendations'].append(
            f"Data Quality Alert: Only {integrity_score}% of records have clean URL integrity - investigate scraping process"
        )

    # Save to file if requested
    if output_file:
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else '.', exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"Detailed report saved to: {output_file}")

    # Generate human-readable summary
    summary = f"""
=== URL INTEGRITY ANALYSIS REPORT ===
Generated: {timestamp}
Records Analyzed: {patterns['total_analyzed']}

INTEGRITY SCORE: {integrity_score}% ({patterns['clean_records']}/{patterns['total_analyzed']} clean records)

CRITICAL ISSUES:
- URL-Decision Mismatches: {patterns['issue_counts']['url_decision_mismatch']}
- Adjacent Errors (off-by-one): {patterns['issue_counts']['adjacent_decision_error']}
- Missing URLs: {patterns['missing_url_count']}

PATTERN ANALYSIS:
- Systematic shift detected: {patterns.get('systematic_shift_detected', False)}
- Most common differences: {patterns.get('common_differences', [])[:5]}

GOVERNMENT DISTRIBUTION:
{chr(10).join(f"- Government {gov}: {count} records" for gov, count in patterns['government_distribution'].most_common())}

EXAMPLE MISMATCHES:
"""

    for i, example in enumerate(patterns['mismatch_examples'][:3], 1):
        summary += f"{i}. {example['decision_key']} -> URL has decision {example['decision_from_url']}\n"
        summary += f"   Title: {example['title']}\n"

    summary += f"\nFull detailed report: {output_file}" if output_file else ""

    return summary


def main():
    """Main analysis function."""
    parser = argparse.ArgumentParser(description="Analyze URL integrity in Israeli government decisions database")
    parser.add_argument('--sample-size', type=int, default=500, help='Number of records to analyze (default: 500)')
    parser.add_argument('--focus-government', type=str, help='Focus on specific government number (e.g., 36)')
    parser.add_argument('--output-file', type=str,
                        default=f'data/qa_reports/url_integrity_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
                        help='Output file for detailed report')
    parser.add_argument('--include-problematic', action='store_true',
                        help='Include known problematic cases (36_1022, 36_1024) in analysis')
    parser.add_argument('--debug', action='store_true',
                        help='Show detailed analysis for each record')

    args = parser.parse_args()

    try:
        # Initialize database connection
        client = get_supabase_client()
        logger.info("Successfully connected to database")

        # Fetch records for analysis
        sample_records = fetch_sample_records(client, args.sample_size, args.focus_government)

        if args.include_problematic:
            problematic_records = fetch_problematic_cases(client)
            sample_records.extend(problematic_records)
            logger.info(f"Added {len(problematic_records)} known problematic cases")

        if not sample_records:
            logger.error("No records to analyze")
            return 1

        # Analyze each record
        logger.info("Starting URL integrity analysis...")
        analyses = []
        for i, record in enumerate(sample_records, 1):
            if i % 50 == 0:
                logger.info(f"Analyzed {i}/{len(sample_records)} records...")

            try:
                analysis = analyze_url_decision_match(record)
                analyses.append(analysis)

                if args.debug:
                    print(f"\n--- Record {i}: {analysis['decision_key']} ---")
                    print(f"URL: {analysis['url']}")
                    print(f"Key decision: {analysis['decision_from_key']}, URL decision: {analysis['decision_from_url']}")
                    print(f"Issues: {analysis['issues']}")
                    print(f"Title: {analysis['title_preview']}")
            except Exception as e:
                logger.error(f"Error analyzing record {i}: {record.get('decision_key', 'unknown')}: {e}")
                continue

        # Analyze patterns
        patterns = analyze_patterns(analyses)

        # Generate and display report
        report_summary = generate_report(patterns, analyses, args.output_file)
        print(report_summary)

        # Return appropriate exit code
        critical_issues = patterns['severity_counts']['critical']
        if critical_issues > 0:
            logger.warning(f"Analysis complete with {critical_issues} critical issues found")
            return 1
        else:
            logger.info("Analysis complete - no critical issues detected")
            return 0

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return 1


if __name__ == '__main__':
    exit(main())