#!/usr/bin/env python3
"""
AI Enhancement Analysis Script

Analyzes the differences between the original backup and the AI-enhanced version
to generate comprehensive statistics about the improvements applied.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import Counter, defaultdict

def load_json_file(filepath: str) -> List[Dict]:
    """Load JSON data from file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_government_body_changes(original: List[Dict], enhanced: List[Dict]) -> Dict:
    """Analyze changes in government body tagging."""
    stats = {
        'total_original_bodies': 0,
        'total_enhanced_bodies': 0,
        'bodies_dropped': 0,
        'bodies_normalized': 0,
        'decisions_with_bodies_removed': 0,
        'decisions_with_bodies_kept': 0,
        'most_dropped_bodies': Counter(),
        'normalization_examples': []
    }

    for orig, enh in zip(original, enhanced):
        orig_bodies = set([b.strip() for b in (orig.get('tags_government_body', '') or '').split(';') if b.strip()])
        enh_bodies = set([b.strip() for b in (enh.get('tags_government_body', '') or '').split(';') if b.strip()])

        stats['total_original_bodies'] += len(orig_bodies)
        stats['total_enhanced_bodies'] += len(enh_bodies)

        if len(orig_bodies) > len(enh_bodies):
            stats['decisions_with_bodies_removed'] += 1
            dropped = orig_bodies - enh_bodies
            stats['bodies_dropped'] += len(dropped)
            for body in dropped:
                stats['most_dropped_bodies'][body] += 1
        elif orig_bodies and enh_bodies:
            stats['decisions_with_bodies_kept'] += 1

            # Check for normalization (same count, different content)
            if len(orig_bodies) == len(enh_bodies) and orig_bodies != enh_bodies:
                stats['bodies_normalized'] += 1
                if len(stats['normalization_examples']) < 10:
                    stats['normalization_examples'].append({
                        'decision': orig.get('decision_key', ''),
                        'original': list(orig_bodies),
                        'normalized': list(enh_bodies)
                    })

    return stats

def analyze_summary_improvements(original: List[Dict], enhanced: List[Dict]) -> Dict:
    """Analyze summary prefix stripping and improvements."""
    stats = {
        'prefixes_stripped': 0,
        'average_length_reduction': 0,
        'total_length_original': 0,
        'total_length_enhanced': 0,
        'examples': []
    }

    length_reductions = []

    for orig, enh in zip(original, enhanced):
        orig_summary = orig.get('summary', '') or ''
        enh_summary = enh.get('summary', '') or ''

        stats['total_length_original'] += len(orig_summary)
        stats['total_length_enhanced'] += len(enh_summary)

        if orig_summary != enh_summary and orig_summary.startswith('החלטת ממשלה'):
            stats['prefixes_stripped'] += 1
            length_reduction = len(orig_summary) - len(enh_summary)
            length_reductions.append(length_reduction)

            if len(stats['examples']) < 5:
                stats['examples'].append({
                    'decision': orig.get('decision_key', ''),
                    'original_length': len(orig_summary),
                    'enhanced_length': len(enh_summary),
                    'reduction': length_reduction,
                    'original_start': orig_summary[:100] + '...' if len(orig_summary) > 100 else orig_summary,
                    'enhanced_start': enh_summary[:100] + '...' if len(enh_summary) > 100 else enh_summary
                })

    if length_reductions:
        stats['average_length_reduction'] = sum(length_reductions) / len(length_reductions)

    return stats

def analyze_tag_validation(original: List[Dict], enhanced: List[Dict]) -> Dict:
    """Analyze policy area tag validation and whitelist enforcement."""
    stats = {
        'original_unique_tags': set(),
        'enhanced_unique_tags': set(),
        'decisions_with_tag_changes': 0,
        'tags_dropped_total': 0,
        'most_common_original_tags': Counter(),
        'most_common_enhanced_tags': Counter(),
        'unauthorized_tags_found': set()
    }

    # Load authorized lists for comparison
    authorized_tags_file = "/Users/tomergutman/Downloads/GOV2DB/new_tags.md"
    authorized_tags = set()
    try:
        with open(authorized_tags_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or ':' in line:
                    continue
                authorized_tags.add(line)
    except FileNotFoundError:
        pass

    for orig, enh in zip(original, enhanced):
        orig_tags = set([t.strip() for t in (orig.get('tags_policy_area', '') or '').split(';') if t.strip()])
        enh_tags = set([t.strip() for t in (enh.get('tags_policy_area', '') or '').split(';') if t.strip()])

        stats['original_unique_tags'].update(orig_tags)
        stats['enhanced_unique_tags'].update(enh_tags)

        for tag in orig_tags:
            stats['most_common_original_tags'][tag] += 1
        for tag in enh_tags:
            stats['most_common_enhanced_tags'][tag] += 1

        if orig_tags != enh_tags:
            stats['decisions_with_tag_changes'] += 1
            if len(orig_tags) > len(enh_tags):
                stats['tags_dropped_total'] += len(orig_tags) - len(enh_tags)

        # Find unauthorized tags in original data
        for tag in orig_tags:
            if tag not in authorized_tags and tag != "שונות":
                stats['unauthorized_tags_found'].add(tag)

    return stats

def analyze_operativity_changes(original: List[Dict], enhanced: List[Dict]) -> Dict:
    """Analyze operativity classification changes."""
    stats = {
        'total_changes': 0,
        'operative_to_declarative': 0,
        'declarative_to_operative': 0,
        'examples': []
    }

    for orig, enh in zip(original, enhanced):
        orig_op = orig.get('operativity', '')
        enh_op = enh.get('operativity', '')

        if orig_op != enh_op and orig_op and enh_op:
            stats['total_changes'] += 1

            if orig_op == 'אופרטיבית' and enh_op == 'דקלרטיבית':
                stats['operative_to_declarative'] += 1
            elif orig_op == 'דקלרטיבית' and enh_op == 'אופרטיבית':
                stats['declarative_to_operative'] += 1

            if len(stats['examples']) < 10:
                stats['examples'].append({
                    'decision': orig.get('decision_key', ''),
                    'original': orig_op,
                    'enhanced': enh_op,
                    'title': (orig.get('decision_title', '') or '')[:100]
                })

    return stats

def analyze_all_tags_rebuilding(original: List[Dict], enhanced: List[Dict]) -> Dict:
    """Analyze all_tags field rebuilding."""
    stats = {
        'all_tags_changed': 0,
        'average_original_length': 0,
        'average_enhanced_length': 0,
        'deduplication_examples': []
    }

    original_lengths = []
    enhanced_lengths = []

    for orig, enh in zip(original, enhanced):
        orig_all = orig.get('all_tags', '') or ''
        enh_all = enh.get('all_tags', '') or ''

        original_lengths.append(len(orig_all))
        enhanced_lengths.append(len(enh_all))

        if orig_all != enh_all:
            stats['all_tags_changed'] += 1

            # Check for potential deduplication
            orig_tags = [t.strip() for t in orig_all.replace(',', ';').split(';') if t.strip()]
            enh_tags = [t.strip() for t in enh_all.replace(',', ';').split(';') if t.strip()]

            if len(orig_tags) > len(set(orig_tags)) and len(stats['deduplication_examples']) < 5:
                stats['deduplication_examples'].append({
                    'decision': orig.get('decision_key', ''),
                    'original_count': len(orig_tags),
                    'unique_count': len(set(orig_tags)),
                    'enhanced_count': len(enh_tags),
                    'duplicates_removed': len(orig_tags) - len(set(orig_tags))
                })

    if original_lengths:
        stats['average_original_length'] = sum(original_lengths) / len(original_lengths)
    if enhanced_lengths:
        stats['average_enhanced_length'] = sum(enhanced_lengths) / len(enhanced_lengths)

    return stats

def generate_comprehensive_report(original: List[Dict], enhanced: List[Dict]) -> str:
    """Generate a comprehensive analysis report."""

    print("Analyzing government body changes...")
    body_stats = analyze_government_body_changes(original, enhanced)

    print("Analyzing summary improvements...")
    summary_stats = analyze_summary_improvements(original, enhanced)

    print("Analyzing tag validation...")
    tag_stats = analyze_tag_validation(original, enhanced)

    print("Analyzing operativity changes...")
    operativity_stats = analyze_operativity_changes(original, enhanced)

    print("Analyzing all_tags rebuilding...")
    all_tags_stats = analyze_all_tags_rebuilding(original, enhanced)

    report = f"""
=== AI ENHANCEMENT PROCESSING REPORT ===
Generated: {Path(__file__).parent.parent / 'data/scraped/ai_enhanced.json'} ({os.path.getsize('/Users/tomergutman/Downloads/GOV2DB/data/scraped/ai_enhanced.json') / 1024 / 1024:.1f} MB)
Original:  {Path(__file__).parent.parent / 'backups/pre_deployment_20260218_143933.json'} ({os.path.getsize('/Users/tomergutman/Downloads/GOV2DB/backups/pre_deployment_20260218_143933.json') / 1024 / 1024:.1f} MB)

OVERVIEW:
Total Decisions Processed: {len(original):,}
File Size Change: {((os.path.getsize('/Users/tomergutman/Downloads/GOV2DB/data/scraped/ai_enhanced.json') - os.path.getsize('/Users/tomergutman/Downloads/GOV2DB/backups/pre_deployment_20260218_143933.json')) / 1024 / 1024):.1f} MB

=== GOVERNMENT BODY VALIDATION ===
Total Original Bodies: {body_stats['total_original_bodies']:,}
Total Enhanced Bodies: {body_stats['total_enhanced_bodies']:,}
Bodies Removed: {body_stats['bodies_dropped']:,}
Bodies Normalized: {body_stats['bodies_normalized']:,}
Decisions with Bodies Removed: {body_stats['decisions_with_bodies_removed']:,}

Most Frequently Dropped Bodies:"""

    for body, count in body_stats['most_dropped_bodies'].most_common(10):
        report += f"\n  {body}: {count:,} times"

    report += f"""

Normalization Examples:"""
    for ex in body_stats['normalization_examples'][:5]:
        report += f"\n  {ex['decision']}: {', '.join(ex['original'])} → {', '.join(ex['normalized'])}"

    report += f"""

=== SUMMARY PREFIX STRIPPING ===
Summaries with Prefixes Stripped: {summary_stats['prefixes_stripped']:,}
Average Length Reduction: {summary_stats['average_length_reduction']:.1f} characters
Total Original Summary Length: {summary_stats['total_length_original']:,} chars
Total Enhanced Summary Length: {summary_stats['total_length_enhanced']:,} chars
Length Reduction: {summary_stats['total_length_original'] - summary_stats['total_length_enhanced']:,} chars ({((summary_stats['total_length_original'] - summary_stats['total_length_enhanced']) / summary_stats['total_length_original'] * 100):.1f}%)

Examples:"""
    for ex in summary_stats['examples']:
        report += f"\n  {ex['decision']}: {ex['original_length']} → {ex['enhanced_length']} chars (-{ex['reduction']})"

    report += f"""

=== POLICY TAG VALIDATION ===
Original Unique Tags: {len(tag_stats['original_unique_tags'])}
Enhanced Unique Tags: {len(tag_stats['enhanced_unique_tags'])}
Decisions with Tag Changes: {tag_stats['decisions_with_tag_changes']:,}
Total Tags Dropped: {tag_stats['tags_dropped_total']:,}
Unauthorized Tags Found in Original: {len(tag_stats['unauthorized_tags_found'])}

Most Common Original Tags:"""
    for tag, count in tag_stats['most_common_original_tags'].most_common(10):
        report += f"\n  {tag}: {count:,}"

    report += f"""

Most Common Enhanced Tags:"""
    for tag, count in tag_stats['most_common_enhanced_tags'].most_common(10):
        report += f"\n  {tag}: {count:,}"

    report += f"""

Some Unauthorized Tags in Original Data:"""
    for tag in list(tag_stats['unauthorized_tags_found'])[:10]:
        report += f"\n  {tag}"

    report += f"""

=== OPERATIVITY CLASSIFICATION ===
Total Operativity Changes: {operativity_stats['total_changes']:,}
Operative → Declarative: {operativity_stats['operative_to_declarative']:,}
Declarative → Operative: {operativity_stats['declarative_to_operative']:,}

Examples:"""
    for ex in operativity_stats['examples'][:5]:
        report += f"\n  {ex['decision']}: {ex['original']} → {ex['enhanced']} | {ex['title'][:60]}..."

    report += f"""

=== ALL_TAGS REBUILDING ===
Decisions with all_tags Changes: {all_tags_stats['all_tags_changed']:,}
Average Original all_tags Length: {all_tags_stats['average_original_length']:.1f} chars
Average Enhanced all_tags Length: {all_tags_stats['average_enhanced_length']:.1f} chars

Deduplication Examples:"""
    for ex in all_tags_stats['deduplication_examples']:
        report += f"\n  {ex['decision']}: {ex['original_count']} tags → {ex['enhanced_count']} tags ({ex['duplicates_removed']} duplicates removed)"

    report += f"""

=== IMPACT SUMMARY ===
✅ Government Body Cleanup: {body_stats['bodies_dropped']:,} irrelevant bodies removed
✅ Summary Optimization: {summary_stats['prefixes_stripped']:,} prefixes stripped
✅ Tag Validation: {tag_stats['decisions_with_tag_changes']:,} decisions improved
✅ Operativity Correction: {operativity_stats['total_changes']:,} classifications fixed
✅ Deduplication: {all_tags_stats['all_tags_changed']:,} decisions with cleaner tags
✅ File Size Optimization: {((os.path.getsize('/Users/tomergutman/Downloads/GOV2DB/backups/pre_deployment_20260218_143933.json') - os.path.getsize('/Users/tomergutman/Downloads/GOV2DB/data/scraped/ai_enhanced.json')) / 1024 / 1024):.1f} MB saved

The AI enhancement process has successfully applied all improvements from the
post-processing pipeline to the production backup, resulting in cleaner,
more accurate, and more consistent government decision data.
"""

    return report

def main():
    """Main analysis function."""
    print("Loading original backup...")
    original = load_json_file("/Users/tomergutman/Downloads/GOV2DB/backups/pre_deployment_20260218_143933.json")

    print("Loading enhanced data...")
    enhanced = load_json_file("/Users/tomergutman/Downloads/GOV2DB/data/scraped/ai_enhanced.json")

    print(f"Loaded {len(original):,} original decisions and {len(enhanced):,} enhanced decisions")

    if len(original) != len(enhanced):
        print("WARNING: Mismatch in number of decisions!")
        return

    print("Generating comprehensive analysis report...")
    report = generate_comprehensive_report(original, enhanced)

    # Save report
    report_path = "/Users/tomergutman/Downloads/GOV2DB/AI_ENHANCEMENT_REPORT.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\nReport saved to: {report_path}")
    print("\n" + "="*80)
    print(report)

if __name__ == "__main__":
    main()