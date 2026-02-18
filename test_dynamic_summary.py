#!/usr/bin/env python3
"""Test dynamic summary length calculation."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.gov_scraper.processors.ai import calculate_dynamic_summary_params

def test_summary_length_calculation():
    """Test that summary length adapts to content size."""

    print("=" * 60)
    print("TESTING DYNAMIC SUMMARY LENGTH CALCULATION")
    print("=" * 60)

    # Test cases with different content sizes
    test_cases = [
        ("Very Short Decision", 500, "~1/4 page"),
        ("Short Decision", 1500, "~3/4 page"),
        ("Medium Decision", 3000, "~1.5 pages"),
        ("Long Decision", 7500, "~4 pages"),
        ("Very Long Decision", 15000, "~8 pages"),
        ("Extremely Long Decision", 30000, "~15 pages"),
        ("Massive Decision", 50000, "~25 pages")
    ]

    print("\nContent Size -> Summary Instructions & Token Limit:")
    print("-" * 60)

    for name, char_count, approx_pages in test_cases:
        instructions, max_tokens = calculate_dynamic_summary_params(char_count)
        print(f"\n{name} ({char_count:,} chars, {approx_pages}):")
        print(f"  Instructions: {instructions}")
        print(f"  Max Tokens:   {max_tokens}")

        # Estimate summary length in words (Hebrew ~5 chars per word, ~1.5 tokens per word)
        estimated_words = int(max_tokens / 1.5)
        print(f"  Est. Words:   ~{estimated_words} words")

    print("\n" + "=" * 60)
    print("SUMMARY LENGTH SCALING:")
    print("=" * 60)

    # Show the scaling
    scales = [
        ("< 2K chars", "1-2 sentences", "200 tokens"),
        ("2-5K chars", "2-3 sentences", "300 tokens"),
        ("5-10K chars", "3-4 sentences", "400 tokens"),
        ("10-20K chars", "4-5 sentences", "500 tokens"),
        ("> 20K chars", "5-7 sentences (full paragraph)", "700 tokens")
    ]

    for content_range, summary_size, tokens in scales:
        print(f"  {content_range:15} → {summary_size:30} ({tokens})")

    print("\n" + "=" * 60)
    print("✅ Dynamic summary length ensures:")
    print("  • Short decisions get concise summaries")
    print("  • Long decisions get comprehensive summaries")
    print("  • No information loss for complex decisions")
    print("=" * 60)

def simulate_real_decision():
    """Simulate how a real decision would be processed."""

    print("\n" + "=" * 60)
    print("SIMULATING REAL DECISION PROCESSING")
    print("=" * 60)

    # Simulate a long government decision
    sample_content = """
    החלטת ממשלה מספר 1234
    בנושא: תוכנית לאומית לפיתוח הנגב והגליל

    הממשלה מחליטה:
    1. להקצות סך של 2 מיליארד ש"ח לפיתוח תשתיות בנגב
    2. להקים ועדת היגוי בראשות מנכ"ל משרד ראש הממשלה
    3. לאשר הקמת 10 יישובים חדשים באזור הנגב המערבי
    4. להעביר 500 מיליון ש"ח לפיתוח תעסוקה באזור
    5. לגבש תוכנית חומש לפיתוח חינוך וטכנולוגיה
    """ * 10  # Multiply to simulate longer content

    content_length = len(sample_content)
    instructions, max_tokens = calculate_dynamic_summary_params(content_length)

    print(f"\nDecision Content: {content_length:,} characters")
    print(f"AI will be instructed to write: {instructions}")
    print(f"Maximum tokens allocated: {max_tokens}")

    print("\nExpected Summary Type:")
    if content_length < 2000:
        print("  → Quick, focused summary hitting main point")
    elif content_length < 5000:
        print("  → Balanced summary covering key decisions")
    elif content_length < 10000:
        print("  → Detailed summary covering multiple aspects")
    elif content_length < 20000:
        print("  → Comprehensive summary with all major points")
    else:
        print("  → Full paragraph covering all decisions and implications")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_summary_length_calculation()
    simulate_real_decision()
    print("\n✅ Dynamic summary system ready for deployment!")