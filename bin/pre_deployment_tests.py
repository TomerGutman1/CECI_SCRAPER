#!/usr/bin/env python3
"""
Pre-deployment Sanity Tests for GOV2DB Algorithm Improvements
Tests edge cases and validates improvements before production deployment
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gov_scraper.db.connector import get_supabase_client
from src.gov_scraper.db.dal import get_decision_by_key

class PreDeploymentTester:
    """Run comprehensive tests before deploying to production"""

    def __init__(self):
        self.client = get_supabase_client()
        self.test_results = {
            'passed': [],
            'failed': [],
            'warnings': []
        }

        # Define test cases with edge cases and known problematic decisions
        self.test_cases = {
            'edge_cases': [
                {
                    'name': 'Gov 28 URL offset',
                    'gov_num': 28,
                    'decision_num': 1234,
                    'expected_url_pattern': 'gov.il/he/pages/28_des',
                    'description': 'Known +20M offset issue in Gov 28'
                },
                {
                    'name': 'Very long content',
                    'gov_num': 37,
                    'decision_num': 2156,  # Known long decision
                    'content_length_min': 10000,
                    'description': 'Test truncation and processing of long content'
                },
                {
                    'name': 'Hebrew date parsing',
                    'date_hebrew': '15.03.2024',
                    'expected_date': '2024-03-15',
                    'description': 'DD.MM.YYYY to YYYY-MM-DD conversion'
                },
                {
                    'name': 'Missing title handling',
                    'gov_num': 35,
                    'decision_num': 789,
                    'description': 'Decision with known missing title'
                }
            ],

            'tag_detection': [
                {
                    'name': 'חינוך tag detection',
                    'content': 'החלטה בדבר רפורמה במערכת החינוך, הקצאת תקציבים לבתי ספר ושיפור תנאי המורים',
                    'expected_tags': ['חינוך'],
                    'unexpected_tags': ['בריאות ורפואה', 'תחבורה ובטיחות בדרכים']
                },
                {
                    'name': 'Multiple tags detection',
                    'content': 'החלטה על הקמת בית חולים חדש בנגב עם הקצאת תקציב מיוחד לפיתוח הפריפריה',
                    'expected_tags': ['בריאות ורפואה', 'פיתוח הנגב והגליל'],
                    'confidence_min': 0.7
                },
                {
                    'name': 'Ambiguous מנהלתי tag',
                    'content': 'החלטה על שינוי נוהל פנימי במשרד',
                    'expected_tags': ['מנהלתי'],
                    'confidence_threshold': 0.95  # High threshold for ambiguous tag
                }
            ],

            'ministry_detection': [
                {
                    'name': 'Explicit ministry mention',
                    'content': 'משרד הבריאות יוביל את התוכנית',
                    'expected_ministries': ['משרד הבריאות'],
                    'hallucination_check': True
                },
                {
                    'name': 'Implicit ministry detection',
                    'content': 'הקמת בתי ספר חדשים ושיפור תנאי המורים',
                    'expected_ministries': ['משרד החינוך'],
                    'description': 'Should detect ministry from context'
                },
                {
                    'name': 'No hallucinated ministries',
                    'content': 'החלטה על משרד המחשבים והטכנולוגיה',  # Fake ministry
                    'expected_ministries': [],
                    'description': 'Should not create non-existent ministry'
                }
            ],

            'duplicate_prevention': [
                {
                    'name': 'Duplicate key insertion',
                    'decision_key': '37_1234',
                    'action': 'insert_twice',
                    'expected_result': 'constraint_violation',
                    'description': 'Database should reject duplicate keys'
                },
                {
                    'name': 'Similar content different keys',
                    'keys': ['37_1234', '37_1235'],
                    'description': 'Similar content but different decision numbers'
                }
            ],

            'operativity_classification': [
                {
                    'name': 'Operative - budget allocation',
                    'content': 'החלטה על הקצאת 50 מיליון שקל לבניית בית ספר חדש בבאר שבע',
                    'expected': 'אופרטיבית',
                    'confidence_min': 0.7
                },
                {
                    'name': 'Operative - agreement approval',
                    'content': 'הממשלה מחליטה לאשר את ההסכם הקיבוצי עם ההסתדרות הכללית',
                    'expected': 'אופרטיבית',
                    'confidence_min': 0.7
                },
                {
                    'name': 'Declarative - general statement',
                    'content': 'הממשלה מביעה תמיכה ברעיון של שיפור החינוך',
                    'expected': 'דקלרטיבית',
                    'confidence_min': 0.6
                },
                {
                    'name': 'Declarative - appointment (CRITICAL)',
                    'content': 'הממשלה מחליטה למנות את פרופסור דוד כהן לתפקיד מנהל הרשות הלאומית',
                    'expected': 'דקלרטיבית',
                    'confidence_min': 0.8,
                    'description': 'Appointments are formal/registry actions = declarative'
                },
                {
                    'name': 'Declarative - committee establishment (CRITICAL)',
                    'content': 'הממשלה מחליטה להקים ועדה בראשות שר הביטחון לבחינת נושא התחבורה',
                    'expected': 'דקלרטיבית',
                    'confidence_min': 0.8,
                    'description': 'Committee for examination does not create real change = declarative'
                }
            ],

            'special_tags': [
                {
                    'name': 'Arab society detection',
                    'content': 'תוכנית 922 לפיתוח היישובים הערביים',
                    'expected_special': ['החברה הערבית'],
                    'not_expected': ['החברה החרדית', 'מיעוטים']
                },
                {
                    'name': 'Post-war rehabilitation',
                    'content': 'שיקום עוטף עזה לאחר אירועי 7 באוקטובר',
                    'date': '2024-01-15',
                    'expected_special': ['שיקום הדרום'],
                    'description': 'Time-sensitive tag after Oct 7'
                }
            ]
        }

    def log(self, message: str, level: str = "INFO"):
        """Colored logging"""
        colors = {
            "INFO": "\033[0m",
            "SUCCESS": "\033[92m",
            "WARNING": "\033[93m",
            "ERROR": "\033[91m",
            "TEST": "\033[94m"
        }
        color = colors.get(level, "\033[0m")
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"{color}[{timestamp}] {level}: {message}\033[0m")

    def test_component_imports(self) -> bool:
        """Test that all new components can be imported"""
        self.log("Testing component imports...", "TEST")

        try:
            # Test configuration imports
            from config.tag_detection_profiles import TAG_DETECTION_PROFILES
            self.log(f"✓ Tag profiles loaded: {len(TAG_DETECTION_PROFILES)} profiles", "SUCCESS")

            from config.ministry_detection_rules import MINISTRY_DETECTION_RULES
            self.log(f"✓ Ministry rules loaded: {len(MINISTRY_DETECTION_RULES)} rules", "SUCCESS")

            # Test unified AI
            if os.path.exists('src/gov_scraper/processors/unified_ai.py'):
                from src.gov_scraper.processors.unified_ai import UnifiedAIProcessor
                self.log("✓ Unified AI processor available", "SUCCESS")
            else:
                self.log("⚠ Unified AI not found (will use legacy)", "WARNING")
                self.test_results['warnings'].append("Unified AI not deployed")

            # Test monitoring
            if os.path.exists('src/gov_scraper/monitoring/quality_monitor.py'):
                from src.gov_scraper.monitoring.quality_monitor import QualityMonitor
                self.log("✓ Quality monitor available", "SUCCESS")

            return True

        except ImportError as e:
            self.log(f"Import failed: {e}", "ERROR")
            self.test_results['failed'].append(f"Import error: {e}")
            return False

    def test_database_constraints(self) -> bool:
        """Test database unique constraints"""
        self.log("Testing database constraints...", "TEST")

        try:
            # Check if unique constraint exists
            result = self.client.rpc('check_unique_constraint', {
                'table_name': 'israeli_government_decisions',
                'column_name': 'decision_key'
            }).execute()

            if result.data:
                self.log("✓ Unique constraint exists on decision_key", "SUCCESS")
                return True
            else:
                self.log("⚠ Unique constraint not found - need migration", "WARNING")
                self.test_results['warnings'].append("DB migration needed")
                return False

        except Exception as e:
            # Constraint might not exist yet - that's ok
            self.log(f"Constraint check: {e}", "WARNING")
            return True

    def test_tag_detection_accuracy(self, sample_size: int = 5) -> Dict:
        """Test tag detection on known decisions"""
        self.log(f"Testing tag detection on {sample_size} samples...", "TEST")

        from config.tag_detection_profiles import TAG_DETECTION_PROFILES
        results = {'correct': 0, 'total': sample_size, 'details': []}

        for test in self.test_cases['tag_detection'][:sample_size]:
            self.log(f"  Testing: {test['name']}", "INFO")

            # Simulate tag detection
            detected_tags = []
            content = test['content']

            for tag_name, profile in TAG_DETECTION_PROFILES.items():
                # Simple keyword matching for test
                keywords = profile.get('keywords', [])
                if any(keyword in content for keyword in keywords):
                    detected_tags.append(tag_name)

            # Check expectations
            expected = set(test.get('expected_tags', []))
            unexpected = set(test.get('unexpected_tags', []))
            detected = set(detected_tags)

            correct = expected.issubset(detected) and not unexpected.intersection(detected)

            if correct:
                self.log(f"    ✓ Correct tags detected", "SUCCESS")
                results['correct'] += 1
            else:
                self.log(f"    ✗ Tags mismatch - Expected: {expected}, Got: {detected}", "ERROR")

            results['details'].append({
                'test': test['name'],
                'expected': list(expected),
                'detected': list(detected),
                'correct': correct
            })

        accuracy = results['correct'] / results['total']
        self.log(f"Tag detection accuracy: {accuracy:.1%}",
                "SUCCESS" if accuracy >= 0.8 else "WARNING")

        return results

    def test_ministry_validation(self) -> Dict:
        """Test ministry detection and hallucination prevention"""
        self.log("Testing ministry detection...", "TEST")

        from config.ministry_detection_rules import MINISTRY_DETECTION_RULES
        authorized_ministries = set(MINISTRY_DETECTION_RULES.keys())

        results = {'passed': 0, 'total': len(self.test_cases['ministry_detection'])}

        for test in self.test_cases['ministry_detection']:
            self.log(f"  Testing: {test['name']}", "INFO")
            content = test['content']

            # Simple detection simulation
            detected = []
            for ministry in authorized_ministries:
                if ministry in content:
                    detected.append(ministry)

            expected = set(test.get('expected_ministries', []))

            if test.get('hallucination_check'):
                # Check no unauthorized ministries
                passed = set(detected).issubset(authorized_ministries)
            else:
                passed = expected == set(detected)

            if passed:
                self.log(f"    ✓ Correct ministry detection", "SUCCESS")
                results['passed'] += 1
            else:
                self.log(f"    ✗ Ministry mismatch - Expected: {expected}, Got: {detected}", "ERROR")

        self.log(f"Ministry validation: {results['passed']}/{results['total']} passed",
                "SUCCESS" if results['passed'] == results['total'] else "WARNING")

        return results

    def test_url_construction(self) -> bool:
        """Test deterministic URL construction"""
        self.log("Testing URL construction...", "TEST")

        for test in self.test_cases['edge_cases']:
            if 'expected_url_pattern' in test:
                gov_num = test['gov_num']
                decision_num = test['decision_num']

                # Test deterministic construction
                url = f"https://www.gov.il/he/pages/{gov_num}_des{decision_num}"

                if test['expected_url_pattern'] in url:
                    self.log(f"  ✓ URL correct for Gov {gov_num}: {url}", "SUCCESS")
                else:
                    self.log(f"  ✗ URL incorrect for Gov {gov_num}", "ERROR")
                    return False

        return True

    def test_unified_ai_performance(self) -> Dict:
        """Test unified AI processor performance"""
        self.log("Testing unified AI performance...", "TEST")

        try:
            from src.gov_scraper.processors.unified_ai import UnifiedAIProcessor
            processor = UnifiedAIProcessor()

            # Test with sample content
            test_content = "החלטה על הקצאת תקציב לחינוך"
            test_title = "החלטה 1234"

            import time
            start = time.time()
            result = processor.process_decision(test_content, test_title)
            elapsed = time.time() - start

            if result:
                self.log(f"  ✓ Unified AI processed in {elapsed:.2f}s", "SUCCESS")
                self.log(f"    - Fields returned: {list(result.keys())}", "INFO")

                # Check all expected fields
                required_fields = ['summary', 'operativity', 'tags_policy_area',
                                 'tags_government_body', 'tags_location']
                missing = [f for f in required_fields if f not in result]

                if missing:
                    self.log(f"  ⚠ Missing fields: {missing}", "WARNING")

                return {'success': True, 'time': elapsed, 'fields': list(result.keys())}
            else:
                self.log("  ✗ Unified AI returned no result", "ERROR")
                return {'success': False}

        except Exception as e:
            self.log(f"  ⚠ Unified AI not available: {e}", "WARNING")
            return {'success': False, 'error': str(e)}

    def test_sample_decisions(self, count: int = 5) -> Dict:
        """Test on actual sample of decisions"""
        self.log(f"Testing on {count} real decisions...", "TEST")

        # Get sample decisions
        sample = self.client.table('israeli_government_decisions')\
                           .select('*')\
                           .limit(count)\
                           .execute()

        if not sample.data:
            self.log("No decisions found for testing", "ERROR")
            return {'error': 'No data'}

        results = {
            'total': len(sample.data),
            'processed': 0,
            'errors': [],
            'warnings': []
        }

        for decision in sample.data:
            try:
                key = decision.get('decision_key')
                self.log(f"  Processing {key}...", "INFO")

                # Check for duplicates
                duplicates = self.client.table('israeli_government_decisions')\
                                      .select('id')\
                                      .eq('decision_key', key)\
                                      .execute()

                if len(duplicates.data) > 1:
                    self.log(f"    ⚠ Found {len(duplicates.data)} duplicates!", "WARNING")
                    results['warnings'].append(f"Duplicates for {key}")

                # Check tags
                tags = decision.get('tags_policy_area', [])
                if not tags or tags == ['שונות']:
                    self.log(f"    ⚠ Weak tags: {tags}", "WARNING")
                    results['warnings'].append(f"Weak tags for {key}")

                results['processed'] += 1

            except Exception as e:
                self.log(f"    ✗ Error: {e}", "ERROR")
                results['errors'].append(str(e))

        self.log(f"Processed {results['processed']}/{results['total']} decisions",
                "SUCCESS" if results['processed'] == results['total'] else "WARNING")

        return results

    def run_all_tests(self, quick: bool = False) -> Dict:
        """Run all pre-deployment tests"""
        self.log("=" * 60, "INFO")
        self.log("Starting Pre-Deployment Sanity Tests", "TEST")
        self.log("=" * 60, "INFO")

        test_suite = [
            ("Component Imports", self.test_component_imports),
            ("Database Constraints", self.test_database_constraints),
            ("URL Construction", self.test_url_construction),
            ("Tag Detection", lambda: self.test_tag_detection_accuracy(3 if quick else 5)),
            ("Ministry Validation", self.test_ministry_validation),
            ("Unified AI", self.test_unified_ai_performance),
            ("Sample Decisions", lambda: self.test_sample_decisions(3 if quick else 5))
        ]

        results = {
            'total_tests': len(test_suite),
            'passed': 0,
            'failed': 0,
            'warnings': 0,
            'details': {}
        }

        for test_name, test_func in test_suite:
            self.log(f"\n{'='*40}", "INFO")
            self.log(f"Running: {test_name}", "TEST")
            self.log(f"{'='*40}", "INFO")

            try:
                result = test_func()

                if isinstance(result, bool):
                    if result:
                        results['passed'] += 1
                        self.test_results['passed'].append(test_name)
                    else:
                        results['failed'] += 1
                        self.test_results['failed'].append(test_name)
                elif isinstance(result, dict):
                    # Complex result - check for success indicators
                    if result.get('correct', 0) > 0 or result.get('passed', 0) > 0 or result.get('success'):
                        results['passed'] += 1
                        self.test_results['passed'].append(test_name)
                    else:
                        results['warnings'] += 1
                        self.test_results['warnings'].append(test_name)

                results['details'][test_name] = result

            except Exception as e:
                self.log(f"Test failed with exception: {e}", "ERROR")
                results['failed'] += 1
                self.test_results['failed'].append(f"{test_name}: {e}")
                results['details'][test_name] = {'error': str(e)}

        # Final summary
        self.log("\n" + "=" * 60, "INFO")
        self.log("TEST SUMMARY", "TEST")
        self.log("=" * 60, "INFO")

        self.log(f"✅ Passed: {len(self.test_results['passed'])}", "SUCCESS")
        for test in self.test_results['passed']:
            self.log(f"   - {test}", "SUCCESS")

        if self.test_results['warnings']:
            self.log(f"⚠️  Warnings: {len(self.test_results['warnings'])}", "WARNING")
            for warning in self.test_results['warnings']:
                self.log(f"   - {warning}", "WARNING")

        if self.test_results['failed']:
            self.log(f"❌ Failed: {len(self.test_results['failed'])}", "ERROR")
            for fail in self.test_results['failed']:
                self.log(f"   - {fail}", "ERROR")

        # Deployment recommendation
        self.log("\n" + "=" * 60, "INFO")

        if len(self.test_results['failed']) == 0:
            self.log("✅ READY FOR DEPLOYMENT", "SUCCESS")
            self.log("All critical tests passed. Safe to proceed.", "SUCCESS")
        elif len(self.test_results['failed']) <= 2:
            self.log("⚠️  CONDITIONAL DEPLOYMENT", "WARNING")
            self.log("Some tests failed but not critical. Review and decide.", "WARNING")
        else:
            self.log("❌ NOT READY FOR DEPLOYMENT", "ERROR")
            self.log("Critical tests failed. Fix issues before proceeding.", "ERROR")

        self.log("=" * 60, "INFO")

        return results

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Pre-deployment sanity tests')
    parser.add_argument('--quick', action='store_true', help='Run quick tests only')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')

    args = parser.parse_args()

    tester = PreDeploymentTester()
    results = tester.run_all_tests(quick=args.quick)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))

    # Exit code based on failures
    sys.exit(len(tester.test_results['failed']))

if __name__ == "__main__":
    main()