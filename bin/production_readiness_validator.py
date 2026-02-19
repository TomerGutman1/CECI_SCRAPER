#!/usr/bin/env python3
"""
Production Readiness Validation Script
=====================================
Comprehensive quality assessment for algorithm improvements.
Tests all 4 major quality issues and provides GO/NO-GO recommendation.
"""
import json
import sys
import os
from pathlib import Path
from collections import Counter, defaultdict
import random
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gov_scraper.db.connector import get_supabase_client


def analyze_database_sample(sample_size=100, seed=42):
    """Get stratified sample from database for analysis."""
    print(f"🔍 Getting stratified sample of {sample_size} decisions...")

    try:
        client = get_supabase_client()

        # Get all decisions and filter by era in Python (simpler approach)
        all_result = client.table('israeli_government_decisions').select('*').limit(1000).execute()
        all_decisions = all_result.data

        # Filter by era (handle string government numbers)
        def get_gov_num(d):
            try:
                return int(d.get('government_number', 0))
            except (ValueError, TypeError):
                return 0

        recent_decisions = [d for d in all_decisions if get_gov_num(d) >= 35][:sample_size//3]
        mid_decisions = [d for d in all_decisions if 30 <= get_gov_num(d) < 35][:sample_size//3]
        old_decisions = [d for d in all_decisions if get_gov_num(d) < 30 and get_gov_num(d) > 0][:sample_size//3]

        all_decisions = recent_decisions + mid_decisions + old_decisions

        # Random sample with seed for reproducibility
        random.seed(seed)
        sample = random.sample(all_decisions, min(sample_size, len(all_decisions)))

        print(f"✅ Retrieved {len(sample)} decisions for analysis")
        print(f"   Recent (35+): {len([d for d in sample if get_gov_num(d) >= 35])}")
        print(f"   Mid (30-34): {len([d for d in sample if 30 <= get_gov_num(d) < 35])}")
        print(f"   Old (<30): {len([d for d in sample if get_gov_num(d) < 30 and get_gov_num(d) > 0])}")

        return sample

    except Exception as e:
        print(f"❌ Database error: {e}")
        return []


def analyze_policy_tag_relevance(decisions, detailed=False):
    """Analyze policy tag relevance accuracy."""
    print("\n📊 ANALYZING POLICY TAG RELEVANCE")
    print("=" * 50)

    total_decisions = len(decisions)
    decisions_with_tags = [d for d in decisions if d.get('tags_policy_area') and str(d['tags_policy_area']).strip()]

    # Manual spot checks for relevance (simplified scoring)
    relevant_count = 0
    irrelevant_count = 0

    for decision in decisions_with_tags[:20]:  # Spot check first 20
        title = (decision.get('decision_title') or '').strip()
        content = (decision.get('decision_content') or '').strip()
        tags_str = decision.get('tags_policy_area', '')
        tags = [tag.strip() for tag in tags_str.split(';') if tag.strip()] if tags_str else []

        # Simple heuristic checks for obvious mismatches
        is_appointment = any(keyword in (title + content).lower() for keyword in ['מינוי', 'הסמכת', 'מינו'])
        is_budget = any(keyword in (title + content).lower() for keyword in ['תקציב', 'כספים', 'מימון'])
        is_education = any(keyword in (title + content).lower() for keyword in ['חינוך', 'לימוד', 'מורה'])
        is_health = any(keyword in (title + content).lower() for keyword in ['בריאות', 'רפואה', 'רופא'])
        is_tourism = any(keyword in (title + content).lower() for keyword in ['תיירות', 'נופש'])

        has_admin_tag = 'מינהל ציבורי ושירות המדינה' in tags or 'מנהלתי' in tags
        has_budget_tag = any(tag for tag in tags if 'תקציב' in tag or 'כספים' in tag)
        has_education_tag = 'חינוך' in tags
        has_health_tag = 'בריאות ורפואה' in tags
        has_tourism_tag = 'תיירות' in tags

        # Score relevance
        relevant_indicators = 0
        total_indicators = 0

        if is_appointment:
            total_indicators += 1
            if has_admin_tag:
                relevant_indicators += 1

        if is_budget:
            total_indicators += 1
            if has_budget_tag:
                relevant_indicators += 1

        if is_education:
            total_indicators += 1
            if has_education_tag:
                relevant_indicators += 1

        if is_health:
            total_indicators += 1
            if has_health_tag:
                relevant_indicators += 1

        if is_tourism:
            total_indicators += 1
            if has_tourism_tag:
                relevant_indicators += 1

        if total_indicators > 0:
            relevance_score = relevant_indicators / total_indicators
            if relevance_score >= 0.7:
                relevant_count += 1
            else:
                irrelevant_count += 1

            if detailed:
                print(f"   {decision.get('decision_key')}: {relevance_score:.1%} - {tags[:2]}")

    tag_coverage = len(decisions_with_tags) / total_decisions * 100

    total_scored = relevant_count + irrelevant_count
    if total_scored > 0:
        relevance_rate = relevant_count / total_scored * 100
        print(f"Tag Coverage: {tag_coverage:.1f}% ({len(decisions_with_tags)}/{total_decisions})")
        print(f"Tag Relevance: {relevance_rate:.1f}% ({relevant_count}/{total_scored} spot-checked)")
    else:
        print("❌ Unable to score tag relevance")
        relevance_rate = 0

    return {
        'coverage': tag_coverage,
        'relevance': relevance_rate,
        'grade': 'A' if relevance_rate >= 90 else 'B+' if relevance_rate >= 85 else 'B' if relevance_rate >= 80 else 'C+' if relevance_rate >= 75 else 'C'
    }


def analyze_operativity_balance(decisions, detailed=False):
    """Analyze operativity classification balance."""
    print("\n⚖️ ANALYZING OPERATIVITY BALANCE")
    print("=" * 50)

    total_decisions = len(decisions)
    decisions_with_operativity = [d for d in decisions if d.get('operativity') is not None]

    operative_count = len([d for d in decisions_with_operativity if d['operativity'] == 'אופרטיבית'])
    declarative_count = len([d for d in decisions_with_operativity if d['operativity'] == 'דקלרטיבית'])

    if len(decisions_with_operativity) > 0:
        operative_percent = operative_count / len(decisions_with_operativity) * 100
        coverage = len(decisions_with_operativity) / total_decisions * 100

        print(f"Operativity Coverage: {coverage:.1f}% ({len(decisions_with_operativity)}/{total_decisions})")
        print(f"Operative: {operative_percent:.1f}% ({operative_count})")
        print(f"Declarative: {100-operative_percent:.1f}% ({declarative_count})")

        # Check for bias (target is 60-65% operative)
        target_min, target_max = 60, 65
        if operative_percent < 50:
            bias_status = "Under-operative (too many declarative)"
            grade = 'C'
        elif operative_percent > 80:
            bias_status = "Over-operative (systematic bias)"
            grade = 'C'
        elif target_min <= operative_percent <= target_max:
            bias_status = "Well-balanced (within target)"
            grade = 'A'
        elif 55 <= operative_percent <= 70:
            bias_status = "Acceptable balance"
            grade = 'B+'
        else:
            bias_status = "Slight imbalance"
            grade = 'B'

        print(f"Balance Assessment: {bias_status}")

        if detailed:
            print("\nPattern Analysis:")
            appointment_decisions = [d for d in decisions_with_operativity if 'מינוי' in (d.get('decision_title') or '')]
            if appointment_decisions:
                appointment_operative = len([d for d in appointment_decisions if d['operativity'] == 'אופרטיבית'])
                print(f"  Appointments: {appointment_operative}/{len(appointment_decisions)} operative (should be 0%)")

        return {
            'coverage': coverage,
            'operative_percent': operative_percent,
            'balance_grade': grade,
            'within_target': target_min <= operative_percent <= target_max
        }
    else:
        print("❌ No operativity data found")
        return {'coverage': 0, 'operative_percent': 0, 'balance_grade': 'F', 'within_target': False}


def analyze_government_body_accuracy(decisions, detailed=False):
    """Analyze government body detection accuracy."""
    print("\n🏛️ ANALYZING GOVERNMENT BODY DETECTION")
    print("=" * 50)

    total_decisions = len(decisions)
    decisions_with_bodies = [d for d in decisions if d.get('tags_government_body') and str(d['tags_government_body']).strip()]

    # Load authorized bodies for validation
    try:
        with open('new_departments.md', 'r', encoding='utf-8') as f:
            authorized_bodies = set(line.strip() for line in f if line.strip() and not line.startswith('#'))
        print(f"   Loaded {len(authorized_bodies)} authorized bodies")
    except Exception as e:
        print(f"   Failed to load authorized bodies: {e}")
        authorized_bodies = set()

    hallucinations = 0
    total_body_tags = 0
    relevant_bodies = 0

    for decision in decisions_with_bodies:
        bodies_str = decision.get('tags_government_body', '')
        # Parse the government bodies string - could be semicolon separated
        if bodies_str.strip():
            bodies = [body.strip() for body in bodies_str.split(';') if body.strip()]
        else:
            bodies = []

        title = decision.get('decision_title') or ''
        content_text = decision.get('decision_content') or ''
        content = title + ' ' + content_text

        for body in bodies:
            total_body_tags += 1

            # Check if body is authorized
            if body not in authorized_bodies:
                hallucinations += 1
                if detailed or total_body_tags <= 5:  # Show first few for debugging
                    print(f"   Hallucination: '{body}' in {decision.get('decision_key')}")
                    print(f"     Available matches: {[b for b in authorized_bodies if body[:5] in b][:3]}")

            # Simple relevance check - is body mentioned in content?
            body_keywords = body.replace('משרד ', '').replace('ועדת ', '').split()
            if any(keyword in content for keyword in body_keywords if len(keyword) > 2):
                relevant_bodies += 1

    coverage = len(decisions_with_bodies) / total_decisions * 100
    if total_body_tags > 0:
        hallucination_rate = hallucinations / total_body_tags * 100
        relevance_rate = relevant_bodies / total_body_tags * 100
        accuracy = 100 - hallucination_rate
    else:
        hallucination_rate = 0
        relevance_rate = 0
        accuracy = 0

    print(f"Body Tag Coverage: {coverage:.1f}% ({len(decisions_with_bodies)}/{total_decisions})")
    print(f"Total Body Tags: {total_body_tags}")
    print(f"Hallucinations: {hallucinations} ({hallucination_rate:.1f}%)")
    print(f"Accuracy: {accuracy:.1f}%")
    print(f"Content Relevance: {relevance_rate:.1f}%")

    grade = 'A' if accuracy >= 95 else 'B+' if accuracy >= 90 else 'B' if accuracy >= 85 else 'C+' if accuracy >= 80 else 'C'

    return {
        'coverage': coverage,
        'accuracy': accuracy,
        'hallucination_rate': hallucination_rate,
        'relevance_rate': relevance_rate,
        'grade': grade
    }


def analyze_summary_tag_alignment(decisions, detailed=False):
    """Analyze summary-tag alignment quality."""
    print("\n🔗 ANALYZING SUMMARY-TAG ALIGNMENT")
    print("=" * 50)

    alignment_issues = 0
    total_analyzed = 0

    for decision in decisions[:30]:  # Analyze first 30
        summary = (decision.get('summary') or '').strip()
        tags_str = decision.get('tags_policy_area', '')
        policy_tags = [tag.strip() for tag in tags_str.split(';') if tag.strip()] if tags_str else []

        if not summary or not policy_tags:
            continue

        total_analyzed += 1

        # Simple alignment checks
        summary_lower = summary.lower()

        # Check for obvious misalignments
        is_legal_summary = any(word in summary_lower for word in ['חוק', 'משפט', 'תקנה', 'קובע'])
        is_budget_summary = any(word in summary_lower for word in ['תקציב', 'כספים', 'מימון'])
        is_appointment_summary = any(word in summary_lower for word in ['מינוי', 'מינו', 'הסמכת'])
        is_tourism_summary = any(word in summary_lower for word in ['תיירות', 'נופש'])

        has_culture_tag = any('תרבות' in tag for tag in policy_tags)
        has_legal_tag = any('חקיקה' in tag or 'משפט' in tag for tag in policy_tags)
        has_budget_tag = any('תקציב' in tag or 'כספים' in tag for tag in policy_tags)
        has_admin_tag = any('מינהל' in tag or 'מנהלתי' in tag for tag in policy_tags)

        # Detect misalignments
        misaligned = False

        # Legal content without legal tags
        if is_legal_summary and not has_legal_tag:
            misaligned = True

        # Budget content without budget tags
        if is_budget_summary and not has_budget_tag:
            misaligned = True

        # Appointment content without admin tags
        if is_appointment_summary and not has_admin_tag:
            misaligned = True

        # Tourism summary with culture tags (classic misalignment)
        if is_tourism_summary and has_culture_tag:
            misaligned = True

        if misaligned:
            alignment_issues += 1
            if detailed:
                print(f"   Misalignment: {decision.get('decision_key')} - {policy_tags[:2]}")

    if total_analyzed > 0:
        alignment_rate = (total_analyzed - alignment_issues) / total_analyzed * 100
        mismatch_rate = alignment_issues / total_analyzed * 100
    else:
        alignment_rate = 0
        mismatch_rate = 0

    print(f"Decisions Analyzed: {total_analyzed}")
    print(f"Alignment Issues: {alignment_issues}")
    print(f"Alignment Rate: {alignment_rate:.1f}%")
    print(f"Mismatch Rate: {mismatch_rate:.1f}%")

    grade = 'A' if mismatch_rate <= 10 else 'B+' if mismatch_rate <= 20 else 'B' if mismatch_rate <= 30 else 'C+' if mismatch_rate <= 40 else 'C'

    return {
        'alignment_rate': alignment_rate,
        'mismatch_rate': mismatch_rate,
        'issues_found': alignment_issues,
        'grade': grade
    }


def test_cross_era_consistency(decisions):
    """Test processing consistency across different government eras."""
    print("\n🏛️ TESTING CROSS-ERA CONSISTENCY")
    print("=" * 50)

    # Group by government era
    def get_gov_num(d):
        try:
            return int(d.get('government_number', 0))
        except (ValueError, TypeError):
            return 0

    era_groups = defaultdict(list)
    for decision in decisions:
        gov_num = get_gov_num(decision)
        if gov_num >= 35:
            era = 'Recent (35+)'
        elif gov_num >= 30:
            era = 'Mid (30-34)'
        elif gov_num > 0:
            era = 'Old (<30)'
        else:
            continue  # Skip invalid government numbers
        era_groups[era].append(decision)

    era_stats = {}
    for era, era_decisions in era_groups.items():
        if not era_decisions:
            continue

        # Calculate quality metrics per era
        with_policy_tags = len([d for d in era_decisions if d.get('tags_policy_area') and str(d['tags_policy_area']).strip()])
        with_body_tags = len([d for d in era_decisions if d.get('tags_government_body') and str(d['tags_government_body']).strip()])
        with_summaries = len([d for d in era_decisions if (d.get('summary') or '').strip()])
        operative_decisions = len([d for d in era_decisions if d.get('operativity') == 'אופרטיבית'])

        total = len(era_decisions)
        era_stats[era] = {
            'total': total,
            'policy_coverage': with_policy_tags / total * 100,
            'body_coverage': with_body_tags / total * 100,
            'summary_coverage': with_summaries / total * 100,
            'operative_rate': operative_decisions / total * 100 if total > 0 else 0
        }

        print(f"{era}: {total} decisions")
        print(f"  Policy tags: {era_stats[era]['policy_coverage']:.1f}%")
        print(f"  Body tags: {era_stats[era]['body_coverage']:.1f}%")
        print(f"  Summaries: {era_stats[era]['summary_coverage']:.1f}%")
        print(f"  Operative rate: {era_stats[era]['operative_rate']:.1f}%")

    # Check consistency (should be similar across eras)
    if len(era_stats) >= 2:
        consistency_score = 100  # Start with perfect score

        for metric in ['policy_coverage', 'body_coverage', 'summary_coverage']:
            values = [stats[metric] for stats in era_stats.values()]
            if max(values) - min(values) > 20:  # More than 20% variance
                consistency_score -= 15
            elif max(values) - min(values) > 10:  # More than 10% variance
                consistency_score -= 5

        print(f"\nConsistency Score: {consistency_score}%")
        grade = 'A' if consistency_score >= 90 else 'B+' if consistency_score >= 80 else 'B' if consistency_score >= 70 else 'C'

        return {
            'era_stats': era_stats,
            'consistency_score': consistency_score,
            'grade': grade
        }
    else:
        return {'era_stats': era_stats, 'consistency_score': 0, 'grade': 'N/A'}


def calculate_overall_grade(metrics):
    """Calculate overall system grade based on all metrics."""
    grade_points = {'A': 4.0, 'B+': 3.5, 'B': 3.0, 'C+': 2.5, 'C': 2.0, 'D': 1.0, 'F': 0.0, 'N/A': 2.5}

    grades = [
        metrics['policy_tags']['grade'],
        metrics['operativity']['balance_grade'],
        metrics['body_detection']['grade'],
        metrics['alignment']['grade']
    ]

    if metrics.get('consistency', {}).get('grade', 'N/A') != 'N/A':
        grades.append(metrics['consistency']['grade'])

    avg_points = sum(grade_points[g] for g in grades) / len(grades)

    if avg_points >= 3.8:
        overall = 'A'
    elif avg_points >= 3.3:
        overall = 'B+'
    elif avg_points >= 2.8:
        overall = 'B'
    elif avg_points >= 2.3:
        overall = 'C+'
    elif avg_points >= 1.8:
        overall = 'C'
    else:
        overall = 'D'

    return overall, avg_points


def generate_recommendation(metrics):
    """Generate GO/NO-GO recommendation with supporting evidence."""
    overall_grade, avg_points = calculate_overall_grade(metrics)

    # GO criteria: B+ (85%) minimum overall
    go_criteria_met = avg_points >= 3.3

    # Individual requirements
    policy_good = metrics['policy_tags']['relevance'] >= 65
    operativity_good = metrics['operativity']['within_target']
    bodies_good = metrics['body_detection']['accuracy'] >= 90
    alignment_good = metrics['alignment']['mismatch_rate'] <= 30

    critical_issues = []
    if not policy_good:
        critical_issues.append(f"Policy tag relevance: {metrics['policy_tags']['relevance']:.1f}% (need ≥65%)")
    if not operativity_good:
        critical_issues.append(f"Operativity not in target range 60-65%: {metrics['operativity']['operative_percent']:.1f}%")
    if not bodies_good:
        critical_issues.append(f"Government body accuracy: {metrics['body_detection']['accuracy']:.1f}% (need ≥90%)")
    if not alignment_good:
        critical_issues.append(f"Summary-tag mismatches: {metrics['alignment']['mismatch_rate']:.1f}% (need ≤30%)")

    # Final recommendation
    if go_criteria_met and len(critical_issues) <= 1:
        recommendation = "🟢 GO FOR PRODUCTION"
        confidence = "HIGH" if len(critical_issues) == 0 else "MEDIUM"
        reasoning = f"Overall grade {overall_grade} ({avg_points:.1f}/4.0) meets B+ minimum standard."
        if critical_issues:
            reasoning += f" One minor issue: {critical_issues[0]}"
    else:
        recommendation = "🔴 NO-GO - FURTHER IMPROVEMENTS NEEDED"
        confidence = "HIGH"
        reasoning = f"Overall grade {overall_grade} ({avg_points:.1f}/4.0) below B+ requirement."
        if critical_issues:
            reasoning += f" Critical issues: {len(critical_issues)} remaining."

    return {
        'recommendation': recommendation,
        'confidence': confidence,
        'reasoning': reasoning,
        'critical_issues': critical_issues,
        'overall_grade': overall_grade,
        'grade_points': avg_points
    }


def main():
    print("🚀 PRODUCTION READINESS VALIDATION")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Testing all algorithm improvements for production deployment")

    # Get sample decisions from database
    decisions = analyze_database_sample(sample_size=100, seed=42)
    if not decisions:
        print("❌ Failed to get database sample")
        sys.exit(1)

    # Run all quality analyses
    metrics = {}

    # 1. Policy Tag Relevance (Target: >65%)
    metrics['policy_tags'] = analyze_policy_tag_relevance(decisions, detailed=False)

    # 2. Operativity Balance (Target: 60-65% operative)
    metrics['operativity'] = analyze_operativity_balance(decisions, detailed=False)

    # 3. Government Body Accuracy (Target: >90%)
    metrics['body_detection'] = analyze_government_body_accuracy(decisions, detailed=False)

    # 4. Summary-Tag Alignment (Target: <30% mismatches)
    metrics['alignment'] = analyze_summary_tag_alignment(decisions, detailed=False)

    # 5. Cross-Era Consistency
    metrics['consistency'] = test_cross_era_consistency(decisions)

    # Generate final recommendation
    recommendation = generate_recommendation(metrics)

    # Print final report
    print("\n" + "="*60)
    print("🎯 PRODUCTION READINESS ASSESSMENT")
    print("="*60)

    print(f"\n📊 QUALITY METRICS SUMMARY:")
    print(f"  Policy Tag Relevance: {metrics['policy_tags']['relevance']:.1f}% (Grade: {metrics['policy_tags']['grade']})")
    print(f"  Operativity Balance: {metrics['operativity']['operative_percent']:.1f}% operative (Grade: {metrics['operativity']['balance_grade']})")
    print(f"  Government Body Accuracy: {metrics['body_detection']['accuracy']:.1f}% (Grade: {metrics['body_detection']['grade']})")
    print(f"  Summary-Tag Alignment: {metrics['alignment']['mismatch_rate']:.1f}% mismatches (Grade: {metrics['alignment']['grade']})")
    print(f"  Cross-Era Consistency: {metrics['consistency']['consistency_score']:.1f}% (Grade: {metrics['consistency']['grade']})")

    print(f"\n🎖️ OVERALL GRADE: {recommendation['overall_grade']} ({recommendation['grade_points']:.1f}/4.0)")

    print(f"\n🔔 RECOMMENDATION: {recommendation['recommendation']}")
    print(f"   Confidence: {recommendation['confidence']}")
    print(f"   Reasoning: {recommendation['reasoning']}")

    if recommendation['critical_issues']:
        print(f"\n⚠️ CRITICAL ISSUES TO ADDRESS:")
        for issue in recommendation['critical_issues']:
            print(f"   • {issue}")

    # Save detailed report
    report_file = f"data/production_readiness_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'metrics': metrics,
            'recommendation': recommendation,
            'sample_size': len(decisions)
        }, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Detailed report saved to: {report_file}")

    # Exit code based on recommendation
    if "GO FOR PRODUCTION" in recommendation['recommendation']:
        print("\n✅ System ready for full 25K processing!")
        sys.exit(0)
    else:
        print("\n❌ System requires further improvements before full deployment")
        sys.exit(1)


if __name__ == "__main__":
    main()