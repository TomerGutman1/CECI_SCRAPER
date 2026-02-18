"""
Mock data generators for QA testing.

This module provides utilities for generating realistic test data
for various QA scenarios.
"""

import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import json


@dataclass
class DataGeneratorConfig:
    """Configuration for data generation."""
    seed: Optional[int] = None
    hebrew_content: bool = True
    realistic_dates: bool = True
    include_problematic_data: bool = True
    problematic_rate: float = 0.2  # 20% of generated data has issues


class MockDataGenerator:
    """Generator for mock government decision data."""

    def __init__(self, config: Optional[DataGeneratorConfig] = None):
        self.config = config or DataGeneratorConfig()
        if self.config.seed:
            random.seed(self.config.seed)

        # Hebrew content templates
        self.hebrew_titles = [
            "החלטה על תקציב {domain}",
            "אישור תוכנית {domain}",
            "החלטה בנושא {topic}",
            "הנחיות לגבי {topic}",
            "תקנות חדשות ב{domain}",
            "שיפור שירותי {domain}",
            "החלטה על הקמת {institution}",
            "אישור הקצאת משאבים ל{domain}"
        ]

        self.hebrew_content_templates = [
            "הממשלה החליטה לאשר {action} בתחום {domain}. ההחלטה תיכנס לתוקף {date}.",
            "לאחר דיון מעמיק, הוחלט {action} במטרה לשפר את {target}.",
            "הממשלה מציינת כי {observation} ולכן יש צורך ב{action}.",
            "בהתאם להחלטת הממשלה, יש {action} בתחום {domain}.",
            "רה\"מ מבהיר כי {policy_statement} ולפיכך {action}.",
            "הוחלט לבטל את {old_policy} ולהחליף ב{new_policy}.",
            "הממשלה אישרה הקצאת {amount} מיליון שקל לצורך {purpose}.",
            "יש לעצור את {problematic_activity} ולהתחיל {corrective_action}."
        ]

        self.domains = [
            "החינוך", "הבריאות", "התחבורה", "הביטחון", "הכלכלה",
            "המשפטים", "הפנים", "החוץ", "הסביבה", "התרבות"
        ]

        self.policy_areas = [
            "כלכלה ואוצר", "חינוך", "בריאות", "בטחון", "תחבורה",
            "משפטים", "פנים", "חוץ", "סביבה", "תרבות ספורט", "שונות"
        ]

        self.government_bodies = [
            "משרד האוצר", "משרד החינוך", "משרד הבריאות", "משרד הביטחון",
            "משרד התחבורה", "משרד המשפטים", "משרד הפנים", "משרד החוץ",
            "משרד להגנת הסביבה", "משרד התרבות והספורט", "משרד העבודה והרווחה"
        ]

        self.locations = [
            "ארצי", "ירושלים", "תל אביב", "חיפה", "באר שבע", "צפון", "דרום",
            "מרכז", "יהודה ושומרון", "מקומי"
        ]

        # Problematic data patterns
        self.cloudflare_patterns = [
            "Just a moment... Cloudflare",
            "Ray ID: {ray_id}",
            "Verify you are human",
            "DDoS protection by Cloudflare",
            "Please enable JavaScript"
        ]

        self.fictional_ministries = [
            "משרד הקסמים והכישופים",
            "משרד הדרקונים",
            "Ministry of Magic",
            "Department of Silly Walks",
            "משרד החד-קרנים"
        ]

        self.operative_keywords = [
            "החליטה", "הוחלט", "לאשר", "לבטל", "לעצור", "להתחיל",
            "להקים", "לסגור", "להגדיל", "להקטין", "לשנות"
        ]

        self.declarative_keywords = [
            "מציינת", "מבהירה", "לדעת", "סבורה", "מעוניינת",
            "רואה", "חושבת", "מאמינה"
        ]

    def generate_decision_record(
        self,
        decision_key: Optional[str] = None,
        introduce_issues: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Generate a single decision record."""
        if introduce_issues is None:
            introduce_issues = (
                self.config.include_problematic_data and
                random.random() < self.config.problematic_rate
            )

        # Generate basic fields
        if not decision_key:
            gov_num = random.randint(1, 100)
            decision_num = random.randint(1, 1000)
            decision_key = f"GOV{gov_num}_{decision_num}"
        else:
            parts = decision_key.split('_')
            gov_num = int(parts[0].replace('GOV', ''))
            decision_num = int(parts[1])

        # Generate domain and topic
        domain = random.choice(self.domains)
        policy_area = self._match_policy_area(domain, introduce_issues)
        government_body = self._match_government_body(policy_area, introduce_issues)

        # Generate title
        title_template = random.choice(self.hebrew_titles)
        title = title_template.format(
            domain=domain,
            topic=domain,
            institution=f"מוסד {domain}"
        )

        # Generate content
        content = self._generate_content(domain, policy_area, introduce_issues)

        # Generate operativity
        operativity = self._generate_operativity(content, introduce_issues)

        # Generate summary
        summary = self._generate_summary(title, content, introduce_issues)

        # Generate date
        decision_date = self._generate_date(introduce_issues)

        # Generate location
        location = self._generate_location(government_body, introduce_issues)

        record = {
            "decision_key": decision_key,
            "gov_num": gov_num,
            "decision_num": decision_num,
            "decision_title": title,
            "decision_content": content,
            "decision_date": decision_date,
            "operativity": operativity,
            "summary": summary,
            "tags_policy_area": policy_area,
            "tags_government_body": government_body,
            "tags_locations": location,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        return record

    def generate_batch(self, count: int, **kwargs) -> List[Dict[str, Any]]:
        """Generate a batch of decision records."""
        return [self.generate_decision_record(**kwargs) for _ in range(count)]

    def generate_problematic_batch(self, count: int) -> List[Dict[str, Any]]:
        """Generate a batch of records with known issues."""
        return [
            self.generate_decision_record(introduce_issues=True)
            for _ in range(count)
        ]

    def generate_clean_batch(self, count: int) -> List[Dict[str, Any]]:
        """Generate a batch of clean records without issues."""
        return [
            self.generate_decision_record(introduce_issues=False)
            for _ in range(count)
        ]

    def generate_specific_issue_records(self, issue_type: str, count: int) -> List[Dict[str, Any]]:
        """Generate records with specific types of issues."""
        records = []
        for i in range(count):
            record = self.generate_decision_record(introduce_issues=False)
            record = self._introduce_specific_issue(record, issue_type, i)
            records.append(record)
        return records

    def _generate_content(self, domain: str, policy_area: str, introduce_issues: bool) -> str:
        """Generate decision content."""
        if introduce_issues and random.random() < 0.3:
            # Cloudflare contamination
            if random.random() < 0.5:
                pattern = random.choice(self.cloudflare_patterns)
                ray_id = ''.join(random.choices('0123456789abcdef', k=16))
                contamination = pattern.format(ray_id=ray_id)
                return contamination

            # Very short content
            if random.random() < 0.3:
                return "החלטה קצרה"

            # Empty content
            if random.random() < 0.2:
                return ""

        # Normal content generation
        template = random.choice(self.hebrew_content_templates)
        action = random.choice([
            "לאשר תוכנית חדשה", "להגדיל את התקציב", "לשפר את השירותים",
            "להקים ועדה", "לבטל את הפעילות", "לעצור את התוכנית"
        ])

        content = template.format(
            domain=domain,
            action=action,
            target=f"שירותי {domain}",
            observation=f"יש בעיות ב{domain}",
            policy_statement=f"המדיניות ב{domain} חשובה",
            old_policy="המדיניות הקודמת",
            new_policy="מדיניות מעודכנת",
            amount=random.randint(10, 500),
            purpose=f"שיפור {domain}",
            problematic_activity="הפעילות הבעייתית",
            corrective_action="פעילות מתקנת",
            date="בחודש הבא"
        )

        return content

    def _generate_operativity(self, content: str, introduce_issues: bool) -> str:
        """Generate operativity classification."""
        if introduce_issues and random.random() < 0.4:
            # Introduce mismatch
            operative_in_content = any(kw in content for kw in self.operative_keywords)
            declarative_in_content = any(kw in content for kw in self.declarative_keywords)

            if operative_in_content and not declarative_in_content:
                return "דקלרטיבית"  # Wrong classification
            elif declarative_in_content and not operative_in_content:
                return "אופרטיבית"  # Wrong classification

        # Correct classification
        operative_count = sum(1 for kw in self.operative_keywords if kw in content)
        declarative_count = sum(1 for kw in self.declarative_keywords if kw in content)

        if operative_count > declarative_count:
            return "אופרטיבית"
        elif declarative_count > 0:
            return "דקלרטיבית"
        else:
            return random.choice(["אופרטיבית", "דקלרטיבית"])

    def _generate_summary(self, title: str, content: str, introduce_issues: bool) -> str:
        """Generate summary."""
        if introduce_issues and random.random() < 0.4:
            issue_type = random.choice(["duplicate", "empty", "too_short", "too_long"])

            if issue_type == "duplicate":
                return title  # Same as title

            elif issue_type == "empty":
                return ""

            elif issue_type == "too_short":
                return "סיכום"

            elif issue_type == "too_long":
                return "סיכום ארוך מאוד " * 20

        # Generate proper summary
        if "החליטה" in content:
            return f"אישור {random.choice(['תוכנית', 'הצעה', 'פרויקט'])} חדש"
        elif "מציינת" in content:
            return f"הבהרת עמדה בנושא {random.choice(self.domains)}"
        else:
            return f"החלטה על {random.choice(['שיפור', 'פיתוח', 'הקמת'])} {random.choice(self.domains)}"

    def _generate_date(self, introduce_issues: bool) -> str:
        """Generate decision date."""
        if introduce_issues and random.random() < 0.2:
            # Invalid dates
            invalid_patterns = [
                "2024-13-01",  # Invalid month
                "2024-02-30",  # Invalid day
                "invalid-date",
                "",
                "2030-01-01"  # Future date
            ]
            return random.choice(invalid_patterns)

        # Valid date in reasonable range
        if self.config.realistic_dates:
            start_date = date(2020, 1, 1)
            end_date = date.today()
            days_diff = (end_date - start_date).days
            random_days = random.randint(0, days_diff)
            random_date = start_date + timedelta(days=random_days)
            return random_date.isoformat()
        else:
            return "2024-01-15"

    def _match_policy_area(self, domain: str, introduce_issues: bool) -> str:
        """Match policy area to domain."""
        if introduce_issues and random.random() < 0.3:
            # Return wrong policy area
            wrong_areas = [area for area in self.policy_areas if area != self._correct_policy_area(domain)]
            return random.choice(wrong_areas)

        return self._correct_policy_area(domain)

    def _correct_policy_area(self, domain: str) -> str:
        """Get correct policy area for domain."""
        domain_mapping = {
            "החינוך": "חינוך",
            "הבריאות": "בריאות",
            "התחבורה": "תחבורה",
            "הביטחון": "בטחון",
            "הכלכלה": "כלכלה ואוצר",
            "המשפטים": "משפטים",
            "הפנים": "פנים",
            "החוץ": "חוץ",
            "הסביבה": "סביבה",
            "התרבות": "תרבות ספורט"
        }
        return domain_mapping.get(domain, "שונות")

    def _match_government_body(self, policy_area: str, introduce_issues: bool) -> str:
        """Match government body to policy area."""
        if introduce_issues and random.random() < 0.3:
            if random.random() < 0.5:
                # Return fictional ministry
                return random.choice(self.fictional_ministries)
            else:
                # Return wrong ministry
                wrong_bodies = [body for body in self.government_bodies
                              if body != self._correct_government_body(policy_area)]
                return random.choice(wrong_bodies)

        return self._correct_government_body(policy_area)

    def _correct_government_body(self, policy_area: str) -> str:
        """Get correct government body for policy area."""
        area_mapping = {
            "חינוך": "משרד החינוך",
            "בריאות": "משרד הבריאות",
            "תחבורה": "משרד התחבורה",
            "בטחון": "משרד הביטחון",
            "כלכלה ואוצר": "משרד האוצר",
            "משפטים": "משרד המשפטים",
            "פנים": "משרד הפנים",
            "חוץ": "משרד החוץ",
            "סביבה": "משרד להגנת הסביבה",
            "תרבות ספורט": "משרד התרבות והספורט"
        }
        return area_mapping.get(policy_area, "משרד האוצר")

    def _generate_location(self, government_body: str, introduce_issues: bool) -> str:
        """Generate location tags."""
        if introduce_issues and random.random() < 0.2:
            # Return inconsistent location
            if "משרד" in government_body:
                return random.choice(["תל אביב", "חיפה"])  # Local for national ministry
            else:
                return "ארצי"

        # Consistent location
        if any(ministry in government_body for ministry in ["משרד האוצר", "משרד החינוך", "משרד הבריאות"]):
            return "ארצי"
        else:
            return random.choice(self.locations)

    def _introduce_specific_issue(self, record: Dict[str, Any], issue_type: str, index: int) -> Dict[str, Any]:
        """Introduce specific type of issue to a record."""
        if issue_type == "cloudflare":
            pattern = random.choice(self.cloudflare_patterns)
            ray_id = f"abc{index:03d}def{index:03d}"
            record["decision_content"] = pattern.format(ray_id=ray_id)

        elif issue_type == "operativity_mismatch":
            if index % 2 == 0:
                record["decision_content"] = f"הממשלה החליטה לבטל פעילות {index}"
                record["operativity"] = "דקלרטיבית"  # Wrong
            else:
                record["decision_content"] = f"הממשלה מציינת נושא {index}"
                record["operativity"] = "אופרטיבית"  # Wrong

        elif issue_type == "policy_mismatch":
            if "ביטחון" in record["decision_content"]:
                record["tags_policy_area"] = "חינוך"  # Wrong
            else:
                record["decision_content"] = "החלטה בנושא ביטחון המדינה"
                record["tags_policy_area"] = "חינוך"  # Wrong

        elif issue_type == "government_body_hallucination":
            record["tags_government_body"] = random.choice(self.fictional_ministries)

        elif issue_type == "summary_duplicate":
            record["summary"] = record["decision_title"]

        elif issue_type == "summary_empty":
            record["summary"] = ""

        elif issue_type == "date_invalid":
            invalid_dates = ["2024-13-01", "2024-02-30", "invalid-date", ""]
            record["decision_date"] = invalid_dates[index % len(invalid_dates)]

        elif issue_type == "content_empty":
            record["decision_content"] = ""

        return record


class QATestDataset:
    """Pre-built datasets for common testing scenarios."""

    def __init__(self, generator: Optional[MockDataGenerator] = None):
        self.generator = generator or MockDataGenerator()

    def get_cloudflare_contamination_dataset(self) -> List[Dict[str, Any]]:
        """Dataset with Cloudflare contamination issues."""
        return self.generator.generate_specific_issue_records("cloudflare", 10)

    def get_operativity_mismatch_dataset(self) -> List[Dict[str, Any]]:
        """Dataset with operativity classification mismatches."""
        return self.generator.generate_specific_issue_records("operativity_mismatch", 10)

    def get_policy_mismatch_dataset(self) -> List[Dict[str, Any]]:
        """Dataset with policy tag mismatches."""
        return self.generator.generate_specific_issue_records("policy_mismatch", 10)

    def get_government_body_hallucination_dataset(self) -> List[Dict[str, Any]]:
        """Dataset with hallucinated government bodies."""
        return self.generator.generate_specific_issue_records("government_body_hallucination", 10)

    def get_summary_quality_issues_dataset(self) -> List[Dict[str, Any]]:
        """Dataset with summary quality issues."""
        duplicate_records = self.generator.generate_specific_issue_records("summary_duplicate", 5)
        empty_records = self.generator.generate_specific_issue_records("summary_empty", 5)
        return duplicate_records + empty_records

    def get_mixed_issues_dataset(self) -> List[Dict[str, Any]]:
        """Dataset with various types of issues mixed together."""
        datasets = [
            self.get_cloudflare_contamination_dataset()[:3],
            self.get_operativity_mismatch_dataset()[:3],
            self.get_policy_mismatch_dataset()[:3],
            self.get_summary_quality_issues_dataset()[:3]
        ]
        mixed = []
        for dataset in datasets:
            mixed.extend(dataset)
        return mixed

    def get_performance_dataset(self, size: int) -> List[Dict[str, Any]]:
        """Large dataset for performance testing."""
        return self.generator.generate_batch(size)

    def get_regression_test_dataset(self) -> List[Dict[str, Any]]:
        """Dataset for regression testing with known issue patterns."""
        return [
            # Known Cloudflare pattern
            {
                "decision_key": "REG_CF_001",
                "decision_content": "Just a moment... Cloudflare Ray ID: test123",
                "operativity": "אופרטיבית",
                "decision_title": "החלטה מזוהמת",
                "summary": "סיכום תקין",
                "tags_policy_area": "שונות",
                "tags_government_body": "משרד האוצר",
                "decision_date": "2024-01-15"
            },
            # Known operativity mismatch
            {
                "decision_key": "REG_OP_001",
                "decision_content": "הממשלה החליטה לבטל את הפעילות",
                "operativity": "דקלרטיבית",  # Should be אופרטיבית
                "decision_title": "החלטת ביטול",
                "summary": "החלטה על ביטול פעילות",
                "tags_policy_area": "שונות",
                "tags_government_body": "משרד האוצר",
                "decision_date": "2024-01-15"
            },
            # Known summary duplicate
            {
                "decision_key": "REG_SUM_001",
                "decision_content": "תוכן החלטה מפורט",
                "operativity": "אופרטיבית",
                "decision_title": "החלטה על תקציב",
                "summary": "החלטה על תקציב",  # Same as title
                "tags_policy_area": "כלכלה ואוצר",
                "tags_government_body": "משרד האוצר",
                "decision_date": "2024-01-15"
            }
        ]


def create_test_database_dump(records: List[Dict[str, Any]], filepath: str) -> None:
    """Create a JSON dump of test records for loading into test database."""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def load_test_database_dump(filepath: str) -> List[Dict[str, Any]]:
    """Load test records from JSON dump."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)