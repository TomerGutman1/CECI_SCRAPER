"""
Tag Migration Module - Migrate old tags to new standardized tags using AI.

This module handles the one-time migration of:
- tags_policy_area -> new policy tags from new_tags.md
- tags_government_body -> new department names from new_departments.md

Algorithm (6 steps):
1. Exact Match
2. Substring Match (High Confidence)
3. Word Overlap Match (Jaccard similarity >= 50%)
4. AI Semantic Match (by tag name)
5. AI Summary Analysis (per record, no cache)
6. Fallback -> "שונות"
"""

import os
import re
import logging
import json
import csv
from datetime import datetime
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from ..db.connector import get_supabase_client
from ..config import GEMINI_API_KEY, GEMINI_MODEL, MAX_RETRIES, RETRY_DELAY
from .ai import make_openai_request_with_retry

# Set up logging
logger = logging.getLogger(__name__)

# Project root directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


@dataclass
class MappingStats:
    """Track mapping statistics for observability."""
    exact: int = 0
    substring: int = 0
    word_overlap: int = 0
    ai_tag: int = 0
    ai_summary: int = 0
    fallback: int = 0

    examples: Dict[str, List[Dict]] = field(default_factory=lambda: defaultdict(list))
    fallback_records: List[Dict] = field(default_factory=list)

    def add_example(self, method: str, old_tag: str, new_tag: str, decision_key: str = None):
        """Add an example mapping."""
        if len(self.examples[method]) < 5:  # Keep max 5 examples per method
            self.examples[method].append({
                "old": old_tag,
                "new": new_tag,
                "decision_key": decision_key
            })

    def add_fallback(self, old_tag: str, decision_key: str):
        """Record a fallback case."""
        self.fallback_records.append({
            "old_tag": old_tag,
            "decision_key": decision_key
        })

    def to_dict(self) -> Dict:
        """Convert stats to dictionary for JSON export."""
        return {
            "exact": {"count": self.exact, "examples": self.examples.get("exact", [])},
            "substring": {"count": self.substring, "examples": self.examples.get("substring", [])},
            "word_overlap": {"count": self.word_overlap, "examples": self.examples.get("word_overlap", [])},
            "ai_tag": {"count": self.ai_tag, "examples": self.examples.get("ai_tag", [])},
            "ai_summary": {"count": self.ai_summary, "examples": self.examples.get("ai_summary", [])},
            "fallback": {"count": self.fallback, "records": self.fallback_records}
        }

    def total(self) -> int:
        """Get total count."""
        return self.exact + self.substring + self.word_overlap + self.ai_tag + self.ai_summary + self.fallback


# =============================================================================
# Tag Loading
# =============================================================================

def load_tags_from_md(filepath: str) -> List[str]:
    """
    Load tags from a markdown file.

    Expected format:
    1→tag name
    2→another tag

    Args:
        filepath: Path to the MD file

    Returns:
        List of tag strings
    """
    tags = []
    full_path = os.path.join(PROJECT_ROOT, filepath) if not os.path.isabs(filepath) else filepath

    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Tag file not found: {full_path}")

    with open(full_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # Remove line numbers and arrows (e.g., "1→tag name" or just "tag name")
            # Handle format: "     1→tag name" or "tag name"
            if '→' in line:
                line = line.split('→', 1)[1].strip()

            # Skip header lines
            if line.startswith('#') or line.startswith('משרדים') or line.startswith('תיוגי'):
                continue

            if line:
                tags.append(line)

    logger.info(f"Loaded {len(tags)} tags from {filepath}")
    return tags


def get_new_policy_areas() -> List[str]:
    """Load new policy area tags from new_tags.md."""
    return load_tags_from_md('new_tags.md')


def get_new_departments() -> List[str]:
    """Load new department names from new_departments.md."""
    return load_tags_from_md('new_departments.md')


# =============================================================================
# Database Operations
# =============================================================================

def fetch_all_records(
    start_date: str = None,
    end_date: str = None,
    max_records: int = None,
    decision_key_prefix: str = None
) -> List[Dict]:
    """
    Fetch records from the database with optional filtering.

    Args:
        start_date: Filter by decision_date >= start_date (YYYY-MM-DD format)
        end_date: Filter by decision_date <= end_date (YYYY-MM-DD format)
        max_records: Maximum number of records to fetch
        decision_key_prefix: Filter by decision_key prefix (e.g., "37_" for government 37)

    Returns:
        List of record dictionaries
    """
    client = get_supabase_client()

    # Fetch in chunks to avoid timeout
    all_records = []
    offset = 0
    chunk_size = 1000

    while True:
        # Build query
        query = client.table("israeli_government_decisions").select(
            "id, decision_key, decision_date, tags_policy_area, tags_government_body, summary"
        )

        # Apply filters
        if start_date:
            query = query.gte("decision_date", start_date)

        if end_date:
            query = query.lte("decision_date", end_date)

        if decision_key_prefix:
            query = query.like("decision_key", f"{decision_key_prefix}%")

        # Order by date (newest first)
        query = query.order("decision_date", desc=True)

        # Apply pagination
        if max_records and (offset + chunk_size) > max_records:
            # Adjust chunk size for last batch
            remaining = max_records - offset
            if remaining <= 0:
                break
            query = query.range(offset, offset + remaining - 1)
        else:
            query = query.range(offset, offset + chunk_size - 1)

        response = query.execute()

        if not response.data:
            break

        all_records.extend(response.data)
        offset += chunk_size

        # Check if we've reached max_records
        if max_records and len(all_records) >= max_records:
            all_records = all_records[:max_records]
            break

        if len(response.data) < chunk_size:
            break

    # Log filter info
    filter_info = []
    if start_date:
        filter_info.append(f"from {start_date}")
    if end_date:
        filter_info.append(f"to {end_date}")
    if max_records:
        filter_info.append(f"max {max_records}")
    if decision_key_prefix:
        filter_info.append(f"prefix '{decision_key_prefix}'")

    filter_str = f" (filters: {', '.join(filter_info)})" if filter_info else ""
    logger.info(f"Fetched {len(all_records)} records from database{filter_str}")

    return all_records


def update_record(decision_key: str, updates: Dict) -> bool:
    """
    Update a single record in the database.

    Args:
        decision_key: The unique decision key
        updates: Dictionary of fields to update

    Returns:
        True if successful, False otherwise
    """
    client = get_supabase_client()

    try:
        response = (
            client.table("israeli_government_decisions")
            .update(updates)
            .eq("decision_key", decision_key)
            .execute()
        )
        return True
    except Exception as e:
        logger.error(f"Failed to update record {decision_key}: {e}")
        return False


def batch_update_records(updates: List[Tuple[str, Dict]], batch_size: int = 10) -> Tuple[int, List[str]]:
    """
    Update multiple records in batches.

    Args:
        updates: List of (decision_key, updates_dict) tuples
        batch_size: Number of records per batch

    Returns:
        Tuple of (success_count, error_messages)
    """
    success_count = 0
    errors = []

    for i in range(0, len(updates), batch_size):
        batch = updates[i:i + batch_size]

        for decision_key, update_dict in batch:
            if update_record(decision_key, update_dict):
                success_count += 1
            else:
                errors.append(f"Failed to update {decision_key}")

        logger.info(f"Processed batch {i//batch_size + 1}: {len(batch)} records")

    return success_count, errors


# =============================================================================
# Mapping Algorithm
# =============================================================================

# Hebrew stop words to exclude from word matching
STOP_WORDS = {"ו", "ה", "של", "את", "על", "עם", "או", "גם", "כל", "לא", "אם", "כי", "זה", "זו", "אל"}


def get_words(text: str) -> Set[str]:
    """
    Extract meaningful words from text (words with 2+ characters, excluding stop words).

    Args:
        text: Hebrew text to process

    Returns:
        Set of meaningful words
    """
    words = set()
    # Replace commas and semicolons with spaces for splitting
    text = text.replace(",", " ").replace(";", " ")

    for word in text.split():
        word = word.strip()
        if len(word) > 2 and word not in STOP_WORDS:
            words.add(word)

    return words


def exact_match(old_tag: str, new_tags: List[str]) -> Optional[str]:
    """Step 1: Check for exact match."""
    if old_tag in new_tags:
        return old_tag
    return None


def substring_match(old_tag: str, new_tags: List[str]) -> Optional[str]:
    """
    Step 2: Substring match with high confidence.

    Special handling for "משרד ה" prefix.
    General rule: old_tag must be 10+ chars and be a prefix of new_tag.
    """
    # Special case: ministry names starting with "משרד ה"
    if old_tag.startswith("משרד ה"):
        for new_tag in new_tags:
            # Check if new_tag starts with old_tag (e.g., "משרד החינוך" in "משרד החינוך")
            if new_tag.startswith(old_tag):
                return new_tag
            # Reverse check
            if old_tag.startswith(new_tag):
                return new_tag

    # General: substring only with high confidence
    # Require old_tag to be 10+ chars and be a prefix
    if len(old_tag) >= 10:
        for new_tag in new_tags:
            if new_tag.startswith(old_tag):
                return new_tag

    return None


def word_overlap_match(old_tag: str, new_tags: List[str]) -> Optional[str]:
    """
    Step 2.5: Word overlap match using Jaccard similarity.

    Finds tags with >= 50% word overlap.
    """
    old_words = get_words(old_tag)

    if len(old_words) < 2:  # Need at least 2 meaningful words
        return None

    best_match = None
    best_score = 0.5  # Minimum threshold: 50%

    for new_tag in new_tags:
        new_words = get_words(new_tag)

        if not new_words:
            continue

        # Jaccard similarity
        intersection = len(old_words & new_words)
        union = len(old_words | new_words)
        score = intersection / union if union > 0 else 0

        if score > best_score:
            best_score = score
            best_match = new_tag

    return best_match


def ai_tag_match(old_tag: str, new_tags: List[str]) -> List[str]:
    """
    Step 3: AI semantic match based on tag name.

    Can return multiple tags (up to 3) if AI determines multiple are clearly relevant.

    Returns:
        List of matched tags (1-3) or empty list if no match found
    """
    tags_str = " | ".join(new_tags)

    prompt = f"""נתון תג ישן: "{old_tag}"

רשימת התגים המורשים:
{tags_str}

בחר את התג/ים המתאימים מהרשימה:
- אם יש התאמה אחת ברורה: החזר תג אחד
- אם יש 2-3 תגים רלוונטיים בוודאות גבוהה: החזר אותם מופרדים ב-;
- אל תחזיר יותר מ-3 תגים
- אם אין התאמה סמנטית ברורה: החזר "NO_MATCH"

חשוב: החזר רק את התגים המדויקים מהרשימה, ללא הסברים נוספים."""

    try:
        result = make_openai_request_with_retry(prompt, max_tokens=150)
        result = result.strip().strip('"').strip("'")

        if result == "NO_MATCH":
            return []

        # Parse multiple tags separated by semicolon
        matched_tags = []
        for tag in result.split(';'):
            tag = tag.strip()
            if tag in new_tags:
                matched_tags.append(tag)

        # Limit to 3 tags
        return matched_tags[:3]
    except Exception as e:
        logger.warning(f"AI tag match failed for '{old_tag}': {e}")

    return []


def ai_summary_match(summary: str, new_tags: List[str], tag_type: str) -> List[str]:
    """
    Step 4: AI analysis based on decision summary.

    This step runs per-record (no caching).
    Can return multiple tags (up to 3) if the summary covers multiple topics.

    Args:
        summary: The decision summary text
        new_tags: List of valid new tags
        tag_type: "policy" or "department"

    Returns:
        List of matched tags (1-3) or empty list
    """
    if not summary:
        return []

    tags_str = " | ".join(new_tags)
    tag_type_hebrew = "תחום מדיניות" if tag_type == "policy" else "גוף ממשלתי/משרד"

    prompt = f"""נתון תקציר של החלטת ממשלה:
"{summary[:1000]}"

בחר את ה{tag_type_hebrew}/ים המתאימים מהרשימה הבאה:
{tags_str}

הנחיות:
- אם יש התאמה אחת ברורה: החזר תג אחד
- אם ההחלטה מכסה 2-3 תחומים בוודאות: החזר אותם מופרדים ב-;
- אל תחזיר יותר מ-3 תגים
- החזר רק תגים שבאמת רלוונטיים להחלטה

החזר רק את התגים המדויקים מהרשימה, ללא הסברים."""

    try:
        result = make_openai_request_with_retry(prompt, max_tokens=150)
        result = result.strip().strip('"').strip("'")

        # Parse multiple tags separated by semicolon
        matched_tags = []
        for tag in result.split(';'):
            tag = tag.strip()
            if tag in new_tags:
                matched_tags.append(tag)

        # Limit to 3 tags
        return matched_tags[:3]
    except Exception as e:
        logger.warning(f"AI summary match failed: {e}")

    return []


def map_single_tag(
    old_tag: str,
    new_tags: List[str],
    tag_type: str,
    summary: str = None,
    decision_key: str = None,
    stats: MappingStats = None
) -> Tuple[List[str], str]:
    """
    Map a single old tag to new tag(s) using the 6-step algorithm.

    For exact/substring/word_overlap matches, returns a single tag.
    For AI matches, may return multiple tags (up to 3) if AI determines
    multiple are clearly relevant.

    Args:
        old_tag: The old tag to map
        new_tags: List of valid new tags
        tag_type: "policy" or "department"
        summary: Optional summary for AI analysis
        decision_key: Optional key for tracking
        stats: Optional stats object for tracking

    Returns:
        Tuple of (list_of_new_tags, method_used)
    """
    old_tag = old_tag.strip()

    if not old_tag:
        return ["שונות"], "empty"

    # Step 1: Exact Match (always single tag)
    result = exact_match(old_tag, new_tags)
    if result:
        if stats:
            stats.exact += 1
            stats.add_example("exact", old_tag, result, decision_key)
        return [result], "exact"

    # Step 2: Substring Match (always single tag)
    result = substring_match(old_tag, new_tags)
    if result:
        if stats:
            stats.substring += 1
            stats.add_example("substring", old_tag, result, decision_key)
        return [result], "substring"

    # Step 2.5: Word Overlap Match (always single tag)
    result = word_overlap_match(old_tag, new_tags)
    if result:
        if stats:
            stats.word_overlap += 1
            stats.add_example("word_overlap", old_tag, result, decision_key)
        return [result], "word_overlap"

    # Step 3: AI Tag Match (may return multiple tags)
    results = ai_tag_match(old_tag, new_tags)
    if results:
        if stats:
            stats.ai_tag += 1
            # Show first tag in example, mention if multiple
            example_tag = results[0] if len(results) == 1 else f"{results[0]} (+{len(results)-1})"
            stats.add_example("ai_tag", old_tag, example_tag, decision_key)
        return results, "ai_tag"

    # Step 4: AI Summary Match (may return multiple tags)
    if summary:
        results = ai_summary_match(summary, new_tags, tag_type)
        if results:
            if stats:
                stats.ai_summary += 1
                example_tag = results[0] if len(results) == 1 else f"{results[0]} (+{len(results)-1})"
                stats.add_example("ai_summary", old_tag, example_tag, decision_key)
            return results, "ai_summary"

    # Step 5: Fallback
    if stats:
        stats.fallback += 1
        stats.add_fallback(old_tag, decision_key)
    return ["שונות"], "fallback"


# =============================================================================
# Cache Building
# =============================================================================

def build_mapping_cache(
    unique_tags: Set[str],
    new_tags: List[str],
    tag_type: str,
    stats: MappingStats = None
) -> Dict[str, Tuple[List[str], str]]:
    """
    Build a mapping cache for unique tags (Steps 1-3 only, no summary analysis).

    Args:
        unique_tags: Set of unique old tags to map
        new_tags: List of valid new tags
        tag_type: "policy" or "department"
        stats: Optional stats object for tracking

    Returns:
        Dictionary mapping old_tag -> (list_of_new_tags, method)
    """
    cache = {}
    total = len(unique_tags)

    for i, old_tag in enumerate(sorted(unique_tags)):
        if not old_tag:
            continue

        # Only use steps 1-3 for cache (no summary analysis)
        new_tags_list, method = map_single_tag(
            old_tag, new_tags, tag_type,
            summary=None,  # No summary for cache
            decision_key=None,
            stats=stats
        )

        # If cache mapping resulted in fallback, we'll need per-record analysis
        if method == "fallback":
            cache[old_tag] = (None, "needs_summary")  # Mark for later
        else:
            cache[old_tag] = (new_tags_list, method)

        if (i + 1) % 10 == 0:
            logger.info(f"Cache progress: {i + 1}/{total} tags processed")

    return cache


# =============================================================================
# Record Processing
# =============================================================================

def extract_unique_tags(records: List[Dict], field: str) -> Set[str]:
    """
    Extract all unique tag values from records.

    Args:
        records: List of record dictionaries
        field: Field name to extract from (tags_policy_area or tags_government_body)

    Returns:
        Set of unique tag strings
    """
    unique_tags = set()

    for record in records:
        value = record.get(field)
        if not value:
            continue

        # Split by semicolon (the separator)
        tags = [t.strip() for t in str(value).split(';')]
        unique_tags.update(tag for tag in tags if tag)

    logger.info(f"Found {len(unique_tags)} unique values in {field}")
    return unique_tags


def map_multi_tags(
    field_value: str,
    cache: Dict[str, Tuple[List[str], str]],
    new_tags: List[str],
    tag_type: str,
    summary: str = None,
    decision_key: str = None,
    stats: MappingStats = None
) -> Tuple[str, List[str]]:
    """
    Map a field with multiple semicolon-separated tags.

    Each old tag may map to 1-3 new tags, so the result may have more tags
    than the original input (but duplicates are removed).

    Args:
        field_value: The original field value (may contain multiple tags)
        cache: Pre-built mapping cache (maps to list of tags)
        new_tags: List of valid new tags
        tag_type: "policy" or "department"
        summary: Optional summary for fallback AI analysis
        decision_key: Optional key for tracking
        stats: Optional stats object

    Returns:
        Tuple of (mapped_value, methods_used)
    """
    if not field_value:
        # Empty field - try to fill from summary
        if summary:
            results = ai_summary_match(summary, new_tags, tag_type)
            if results:
                if stats:
                    stats.ai_summary += 1
                    stats.add_example("ai_summary", "(empty)", results[0], decision_key)
                return "; ".join(results), ["ai_summary"]

        if stats:
            stats.fallback += 1
            stats.add_fallback("(empty)", decision_key)
        return "שונות", ["fallback"]

    # Split by semicolon
    tags = [t.strip() for t in str(field_value).split(';')]
    mapped_tags = []
    methods = []

    for tag in tags:
        if not tag:
            continue

        # Check cache first
        if tag in cache:
            cached_value, cached_method = cache[tag]

            if cached_method == "needs_summary":
                # Need per-record AI analysis
                new_tags_list, method = map_single_tag(
                    tag, new_tags, tag_type,
                    summary=summary,
                    decision_key=decision_key,
                    stats=stats
                )
            else:
                # Use cached value (which is now a list) and track stats
                new_tags_list, method = cached_value, cached_method
                if stats:
                    # Increment the appropriate counter
                    if method == "exact":
                        stats.exact += 1
                    elif method == "substring":
                        stats.substring += 1
                    elif method == "word_overlap":
                        stats.word_overlap += 1
                    elif method == "ai_tag":
                        stats.ai_tag += 1
                    elif method == "ai_summary":
                        stats.ai_summary += 1
                    elif method == "fallback":
                        stats.fallback += 1
                        stats.add_fallback(tag, decision_key)
                    # Show first tag in example
                    example_tag = new_tags_list[0] if new_tags_list else tag
                    stats.add_example(method, tag, example_tag, decision_key)
        else:
            # Not in cache, do full mapping
            new_tags_list, method = map_single_tag(
                tag, new_tags, tag_type,
                summary=summary,
                decision_key=decision_key,
                stats=stats
            )

        # Extend with all mapped tags (flatten the list)
        mapped_tags.extend(new_tags_list)
        methods.append(method)

    # Remove duplicates while preserving order
    seen = set()
    unique_tags = []
    for tag in mapped_tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)

    return "; ".join(unique_tags), methods


def process_record(
    record: Dict,
    policy_cache: Dict[str, Tuple[List[str], str]],
    dept_cache: Dict[str, Tuple[List[str], str]],
    new_policy_tags: List[str],
    new_dept_tags: List[str],
    policy_stats: MappingStats,
    dept_stats: MappingStats
) -> Dict:
    """
    Process a single record, mapping both tag fields.

    Returns:
        Dictionary with the new values
    """
    decision_key = record.get('decision_key', '')
    summary = record.get('summary', '')

    # Map policy area tags
    new_policy, _ = map_multi_tags(
        record.get('tags_policy_area'),
        policy_cache,
        new_policy_tags,
        "policy",
        summary=summary,
        decision_key=decision_key,
        stats=policy_stats
    )

    # Map department tags
    new_dept, _ = map_multi_tags(
        record.get('tags_government_body'),
        dept_cache,
        new_dept_tags,
        "department",
        summary=summary,
        decision_key=decision_key,
        stats=dept_stats
    )

    return {
        'decision_key': decision_key,
        'old_policy': record.get('tags_policy_area'),
        'new_policy': new_policy,
        'old_dept': record.get('tags_government_body'),
        'new_dept': new_dept
    }


# =============================================================================
# Reporting
# =============================================================================

def generate_report(
    policy_stats: MappingStats,
    dept_stats: MappingStats,
    total_records: int,
    changed_records: int
) -> str:
    """Generate a formatted migration report."""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def format_stats(stats: MappingStats, name: str) -> str:
        total = stats.total()
        lines = [
            f"{'='*67}",
            f"{name} - פירוט לפי שלב:",
            f"{'='*67}",
        ]

        for method, count, emoji in [
            ("exact", stats.exact, "✅"),
            ("substring", stats.substring, "✅"),
            ("word_overlap", stats.word_overlap, "✅"),
            ("ai_tag", stats.ai_tag, "✅"),
            ("ai_summary", stats.ai_summary, "✅"),
            ("fallback", stats.fallback, "⚠️"),
        ]:
            pct = (count / total * 100) if total > 0 else 0
            label = {
                "exact": "Exact Match",
                "substring": "Substring Match",
                "word_overlap": "Word Overlap",
                "ai_tag": "AI Tag Match",
                "ai_summary": "AI Summary Analysis",
                "fallback": 'Fallback (שונות)'
            }[method]
            lines.append(f"   {emoji} {label:25} {count:5} ({pct:5.1f}%)")

        # Add examples
        lines.append("")
        lines.append("   דוגמאות מיפוי:")
        for method in ["exact", "substring", "word_overlap", "ai_tag", "ai_summary"]:
            for example in stats.examples.get(method, [])[:2]:
                lines.append(f"   ├─ \"{example['old']}\" → \"{example['new']}\" [{method}]")

        # Add fallbacks
        if stats.fallback_records:
            lines.append("")
            lines.append(f"   ⚠️ Fallbacks (נפלו ל-\"שונות\"):")
            for fb in stats.fallback_records[:5]:
                lines.append(f"   ├─ \"{fb['old_tag']}\" (decision_key: {fb['decision_key']})")
            if len(stats.fallback_records) > 5:
                lines.append(f"   └─ ... ועוד {len(stats.fallback_records) - 5}")

        return "\n".join(lines)

    report = f"""
╔══════════════════════════════════════════════════════════════════╗
║  📊 Migration Report - {timestamp}                       ║
╚══════════════════════════════════════════════════════════════════╝

📈 סטטיסטיקות כלליות:
   סה"כ רשומות:           {total_records:,}
   רשומות שעודכנו:         {changed_records:,} ({changed_records/total_records*100:.1f}%)
   רשומות ללא שינוי:       {total_records - changed_records:,} ({(total_records - changed_records)/total_records*100:.1f}%)

{format_stats(policy_stats, "📋 tags_policy_area")}

{format_stats(dept_stats, "🏛️ tags_government_body")}
"""
    return report


def export_backup_csv(records: List[Dict], filepath: str):
    """Export records to CSV as backup."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        if records:
            writer = csv.DictWriter(f, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)

    logger.info(f"Exported backup to {filepath}")


def export_report_json(
    policy_stats: MappingStats,
    dept_stats: MappingStats,
    mappings: List[Dict],
    filepath: str
):
    """Export full migration report as JSON."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    report = {
        "timestamp": datetime.now().isoformat(),
        "total_records": len(mappings),
        "stats": {
            "policy_area": policy_stats.to_dict(),
            "government_body": dept_stats.to_dict()
        },
        "mappings": mappings[:100]  # First 100 for reference
    }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"Exported report to {filepath}")


# =============================================================================
# Main Migration Functions
# =============================================================================

def run_preview(
    num_records: int = 10,
    start_date: str = None,
    end_date: str = None,
    decision_key_prefix: str = None
) -> Tuple[List[Dict], MappingStats, MappingStats]:
    """
    Run migration preview on a sample of records.

    Args:
        num_records: Number of records to preview
        start_date: Filter by decision_date >= start_date (YYYY-MM-DD)
        end_date: Filter by decision_date <= end_date (YYYY-MM-DD)
        decision_key_prefix: Filter by decision_key prefix (e.g., "37_")

    Returns:
        Tuple of (preview_results, policy_stats, dept_stats)
    """
    logger.info(f"Starting migration preview on {num_records} records...")

    # Load new tags
    new_policy_tags = get_new_policy_areas()
    new_dept_tags = get_new_departments()

    logger.info(f"Loaded {len(new_policy_tags)} policy tags, {len(new_dept_tags)} department tags")

    # Fetch sample records with filters
    records = fetch_all_records(
        start_date=start_date,
        end_date=end_date,
        max_records=num_records,
        decision_key_prefix=decision_key_prefix
    )

    # Initialize stats
    policy_stats = MappingStats()
    dept_stats = MappingStats()

    # Build caches from sample
    policy_unique = extract_unique_tags(records, 'tags_policy_area')
    dept_unique = extract_unique_tags(records, 'tags_government_body')

    policy_cache = build_mapping_cache(policy_unique, new_policy_tags, "policy")
    dept_cache = build_mapping_cache(dept_unique, new_dept_tags, "department")

    # Process records
    results = []
    for record in records:
        result = process_record(
            record,
            policy_cache, dept_cache,
            new_policy_tags, new_dept_tags,
            policy_stats, dept_stats
        )
        results.append(result)

    return results, policy_stats, dept_stats


def run_dry_run(
    start_date: str = None,
    end_date: str = None,
    max_records: int = None,
    decision_key_prefix: str = None
) -> Tuple[List[Dict], MappingStats, MappingStats]:
    """
    Run full dry-run migration (no DB changes).

    Args:
        start_date: Filter by decision_date >= start_date (YYYY-MM-DD)
        end_date: Filter by decision_date <= end_date (YYYY-MM-DD)
        max_records: Maximum number of records to process
        decision_key_prefix: Filter by decision_key prefix (e.g., "37_")

    Returns:
        Tuple of (all_mappings, policy_stats, dept_stats)
    """
    logger.info("Starting full dry-run migration...")

    # Load new tags
    new_policy_tags = get_new_policy_areas()
    new_dept_tags = get_new_departments()

    logger.info(f"Loaded {len(new_policy_tags)} policy tags, {len(new_dept_tags)} department tags")

    # Fetch records with filters
    records = fetch_all_records(
        start_date=start_date,
        end_date=end_date,
        max_records=max_records,
        decision_key_prefix=decision_key_prefix
    )
    logger.info(f"Fetched {len(records)} records")

    # Initialize stats
    policy_stats = MappingStats()
    dept_stats = MappingStats()

    # Extract unique tags
    policy_unique = extract_unique_tags(records, 'tags_policy_area')
    dept_unique = extract_unique_tags(records, 'tags_government_body')

    logger.info(f"Found {len(policy_unique)} unique policy tags, {len(dept_unique)} unique dept tags")

    # Build caches
    logger.info("Building policy area cache...")
    policy_cache = build_mapping_cache(policy_unique, new_policy_tags, "policy")

    logger.info("Building department cache...")
    dept_cache = build_mapping_cache(dept_unique, new_dept_tags, "department")

    # Process all records
    logger.info("Processing records...")
    results = []
    for i, record in enumerate(records):
        result = process_record(
            record,
            policy_cache, dept_cache,
            new_policy_tags, new_dept_tags,
            policy_stats, dept_stats
        )
        results.append(result)

        if (i + 1) % 100 == 0:
            logger.info(f"Processed {i + 1}/{len(records)} records")

    return results, policy_stats, dept_stats


def run_execute(
    batch_size: int = 10,
    start_date: str = None,
    end_date: str = None,
    max_records: int = None,
    decision_key_prefix: str = None
) -> Tuple[int, int, List[str]]:
    """
    Execute the migration (applies changes to DB).

    Args:
        batch_size: Number of records to update per batch
        start_date: Filter by decision_date >= start_date (YYYY-MM-DD)
        end_date: Filter by decision_date <= end_date (YYYY-MM-DD)
        max_records: Maximum number of records to process
        decision_key_prefix: Filter by decision_key prefix (e.g., "37_")

    Returns:
        Tuple of (success_count, total_count, errors)
    """
    logger.info("Starting migration execution...")

    # First run dry-run to get mappings
    mappings, policy_stats, dept_stats = run_dry_run(
        start_date=start_date,
        end_date=end_date,
        max_records=max_records,
        decision_key_prefix=decision_key_prefix
    )

    # Generate timestamp for files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Export backup
    backup_path = os.path.join(PROJECT_ROOT, 'data', f'backup_{timestamp}.csv')
    export_backup_csv(mappings, backup_path)

    # Prepare updates (only for records that changed)
    updates = []
    for mapping in mappings:
        old_policy = mapping.get('old_policy') or ''
        new_policy = mapping.get('new_policy') or ''
        old_dept = mapping.get('old_dept') or ''
        new_dept = mapping.get('new_dept') or ''

        if old_policy != new_policy or old_dept != new_dept:
            updates.append((
                mapping['decision_key'],
                {
                    'tags_policy_area': new_policy,
                    'tags_government_body': new_dept
                }
            ))

    logger.info(f"Preparing to update {len(updates)} records...")

    # Execute updates
    success_count, errors = batch_update_records(updates, batch_size)

    # Export report
    report_path = os.path.join(PROJECT_ROOT, 'data', f'migration_report_{timestamp}.json')
    export_report_json(policy_stats, dept_stats, mappings, report_path)

    # Generate and print report
    report = generate_report(policy_stats, dept_stats, len(mappings), len(updates))
    print(report)

    logger.info(f"Migration complete: {success_count}/{len(updates)} records updated")

    return success_count, len(updates), errors
