#!/usr/bin/env python3
"""
Analytics Report Generator for Clonnect Creators.

Generates reports for a creator's analytics data.

Usage:
    python scripts/generate_report.py --creator manel --period week
    python scripts/generate_report.py --creator manel --period day --date 2024-01-15
    python scripts/generate_report.py --creator manel --period month
    python scripts/generate_report.py --creator manel --full --output report.json
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.analytics import get_analytics_manager


def print_header(title: str):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_section(title: str):
    """Print a section header"""
    print(f"\n--- {title} ---")


def format_number(n: int) -> str:
    """Format number with thousand separators"""
    return f"{n:,}"


def format_percentage(p: float) -> str:
    """Format percentage"""
    return f"{p:.1f}%"


def format_currency(amount: float) -> str:
    """Format currency"""
    return f"{amount:,.2f} EUR"


def generate_daily_report(creator_id: str, date: str = None):
    """Generate daily report"""
    analytics = get_analytics_manager()
    stats = analytics.get_daily_stats(creator_id, date)

    print_header(f"DAILY REPORT - {stats.date}")
    print(f"Creator: {creator_id}")

    print_section("Messages")
    print(f"  Received: {format_number(stats.messages_received)}")
    print(f"  Sent:     {format_number(stats.messages_sent)}")
    print(f"  Total:    {format_number(stats.messages_received + stats.messages_sent)}")

    print_section("Engagement")
    print(f"  Unique followers: {format_number(stats.unique_followers)}")
    print(f"  New leads:        {format_number(stats.new_leads)}")
    print(f"  Conversions:      {format_number(stats.conversions)}")
    print(f"  Revenue:          {format_currency(stats.revenue)}")

    if stats.intents:
        print_section("Intent Distribution")
        total = sum(stats.intents.values())
        for intent, count in sorted(stats.intents.items(), key=lambda x: x[1], reverse=True)[:10]:
            pct = count / total * 100 if total > 0 else 0
            bar = "#" * int(pct / 5)
            print(f"  {intent:25} {count:5} ({pct:5.1f}%) {bar}")

    if stats.platforms:
        print_section("Platform Distribution")
        total = sum(stats.platforms.values())
        for platform, count in sorted(stats.platforms.items(), key=lambda x: x[1], reverse=True):
            pct = count / total * 100 if total > 0 else 0
            print(f"  {platform:15} {count:5} ({pct:5.1f}%)")

    return stats.to_dict()


def generate_weekly_report(creator_id: str):
    """Generate weekly report"""
    analytics = get_analytics_manager()
    weekly = analytics.get_weekly_stats(creator_id)

    print_header(f"WEEKLY REPORT")
    print(f"Creator: {creator_id}")
    print(f"Period:  {weekly['start_date']} to {weekly['end_date']}")

    totals = weekly['totals']

    print_section("Weekly Totals")
    print(f"  Messages received: {format_number(totals['messages_received'])}")
    print(f"  Messages sent:     {format_number(totals['messages_sent'])}")
    print(f"  Total messages:    {format_number(totals['total_messages'])}")
    print(f"  New leads:         {format_number(totals['new_leads'])}")
    print(f"  Conversions:       {format_number(totals['conversions'])}")
    print(f"  Revenue:           {format_currency(totals['revenue'])}")

    print_section("Daily Breakdown")
    print(f"  {'Date':<12} {'Recv':>8} {'Sent':>8} {'Leads':>7} {'Conv':>6} {'Revenue':>12}")
    print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*7} {'-'*6} {'-'*12}")

    for day in weekly['daily']:
        print(f"  {day['date']:<12} {day['messages_received']:>8} {day['messages_sent']:>8} "
              f"{day['new_leads']:>7} {day['conversions']:>6} {day['revenue']:>12.2f}")

    # Calculate averages
    num_days = len(weekly['daily'])
    if num_days > 0:
        print_section("Daily Averages")
        print(f"  Messages/day:    {totals['total_messages'] / num_days:.1f}")
        print(f"  Leads/day:       {totals['new_leads'] / num_days:.1f}")
        print(f"  Conversions/day: {totals['conversions'] / num_days:.2f}")

    return weekly


def generate_funnel_report(creator_id: str, days: int = 30):
    """Generate funnel report"""
    analytics = get_analytics_manager()
    funnel = analytics.get_funnel_stats(creator_id, days)

    print_header(f"FUNNEL REPORT (Last {days} days)")
    print(f"Creator: {creator_id}")

    print_section("Funnel Stages")

    stages = [
        ("Total Contacts", funnel.total_contacts, 100),
        ("Engaged (>1 msg)", funnel.engaged, funnel.engagement_rate * 100),
        ("Interested", funnel.interested, (funnel.interested / funnel.total_contacts * 100) if funnel.total_contacts > 0 else 0),
        ("Leads", funnel.leads, funnel.lead_rate * 100),
        ("High Intent (>50%)", funnel.high_intent, (funnel.high_intent / funnel.total_contacts * 100) if funnel.total_contacts > 0 else 0),
        ("Conversions", funnel.conversions, (funnel.conversions / funnel.total_contacts * 100) if funnel.total_contacts > 0 else 0),
    ]

    max_val = max(s[1] for s in stages) if stages else 1
    for name, value, pct in stages:
        bar_width = int(value / max_val * 30) if max_val > 0 else 0
        bar = "#" * bar_width
        print(f"  {name:<20} {value:>6} ({pct:>5.1f}%) |{bar}")

    print_section("Conversion Rates")
    print(f"  Engagement rate:  {format_percentage(funnel.engagement_rate * 100)}")
    print(f"  Lead rate:        {format_percentage(funnel.lead_rate * 100)}")
    print(f"  Lead->Conversion: {format_percentage(funnel.conversion_rate * 100)}")

    return funnel.to_dict()


def generate_platform_report(creator_id: str, days: int = 30):
    """Generate platform breakdown report"""
    analytics = get_analytics_manager()
    platforms = analytics.get_platform_stats(creator_id, days)

    print_header(f"PLATFORM REPORT (Last {days} days)")
    print(f"Creator: {creator_id}")

    if not platforms:
        print("\n  No platform data available")
        return {}

    print_section("Platform Breakdown")
    print(f"  {'Platform':<12} {'Recv':>8} {'Sent':>8} {'Total':>8} {'Leads':>7} {'Conv':>6} {'Users':>7}")
    print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*7} {'-'*6} {'-'*7}")

    for platform, stats in sorted(platforms.items(), key=lambda x: x[1]['total_messages'], reverse=True):
        print(f"  {platform:<12} {stats['messages_received']:>8} {stats['messages_sent']:>8} "
              f"{stats['total_messages']:>8} {stats['leads']:>7} {stats['conversions']:>6} "
              f"{stats['unique_followers']:>7}")

    # Calculate totals
    total_msgs = sum(p['total_messages'] for p in platforms.values())
    if total_msgs > 0:
        print_section("Platform Share")
        for platform, stats in sorted(platforms.items(), key=lambda x: x[1]['total_messages'], reverse=True):
            share = stats['total_messages'] / total_msgs * 100
            bar = "#" * int(share / 2)
            print(f"  {platform:<12} {share:>5.1f}% {bar}")

    return platforms


def generate_intent_report(creator_id: str, days: int = 30):
    """Generate intent distribution report"""
    analytics = get_analytics_manager()
    intents = analytics.get_intent_distribution(creator_id, days)

    print_header(f"INTENT DISTRIBUTION (Last {days} days)")
    print(f"Creator: {creator_id}")
    print(f"Total messages analyzed: {format_number(intents['total_messages'])}")

    if not intents['distribution']:
        print("\n  No intent data available")
        return intents

    print_section("Intent Breakdown")

    for intent, data in intents['distribution'].items():
        bar = "#" * int(data['percentage'] / 2)
        print(f"  {intent:<25} {data['count']:>6} ({data['percentage']:>5.1f}%) {bar}")

    # Group by category
    print_section("Intent Categories")

    categories = {
        "Interest": ["greeting", "interest_soft", "interest_strong", "lead_magnet"],
        "Objections": [k for k in intents['distribution'].keys() if k.startswith("objection_")],
        "Questions": ["question_product", "question_general"],
        "Other": ["thanks", "goodbye", "support", "escalation", "other"]
    }

    for category, intent_list in categories.items():
        total = sum(intents['distribution'].get(i, {}).get('count', 0) for i in intent_list)
        if total > 0:
            pct = total / intents['total_messages'] * 100 if intents['total_messages'] > 0 else 0
            print(f"  {category:<15} {total:>6} ({pct:>5.1f}%)")

    return intents


def generate_full_report(creator_id: str, output_file: str = None):
    """Generate complete analytics report"""
    analytics = get_analytics_manager()
    summary = analytics.get_summary(creator_id)

    print_header(f"FULL ANALYTICS REPORT")
    print(f"Creator: {creator_id}")
    print(f"Generated: {summary['generated_at']}")

    # Daily
    print_section("Today's Summary")
    today = summary['today']
    print(f"  Messages: {today['messages_received']} received, {today['messages_sent']} sent")
    print(f"  Followers: {today['unique_followers']} unique")
    print(f"  Leads: {today['new_leads']} new")
    print(f"  Conversions: {today['conversions']} ({format_currency(today['revenue'])})")

    # Weekly
    print_section("Weekly Summary")
    weekly = summary['weekly']['totals']
    print(f"  Total messages: {format_number(weekly['total_messages'])}")
    print(f"  New leads: {format_number(weekly['new_leads'])}")
    print(f"  Conversions: {format_number(weekly['conversions'])}")
    print(f"  Revenue: {format_currency(weekly['revenue'])}")

    # Funnel
    print_section("Funnel (30 days)")
    funnel = summary['funnel']
    print(f"  Contacts: {funnel['total_contacts']} -> Leads: {funnel['leads']} -> Conversions: {funnel['conversions']}")

    # Save to file if requested
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\n[Saved full report to {output_file}]")

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Generate analytics reports for Clonnect Creators"
    )
    parser.add_argument(
        "--creator", "-c",
        required=True,
        help="Creator ID"
    )
    parser.add_argument(
        "--period", "-p",
        choices=["day", "week", "month", "funnel", "platform", "intent"],
        default="week",
        help="Report period/type (default: week)"
    )
    parser.add_argument(
        "--date", "-d",
        help="Specific date for daily report (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days for funnel/platform/intent reports (default: 30)"
    )
    parser.add_argument(
        "--full", "-f",
        action="store_true",
        help="Generate full comprehensive report"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file for JSON export"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of formatted text"
    )

    args = parser.parse_args()

    try:
        if args.full:
            result = generate_full_report(args.creator, args.output)
        elif args.period == "day":
            result = generate_daily_report(args.creator, args.date)
        elif args.period == "week":
            result = generate_weekly_report(args.creator)
        elif args.period == "funnel":
            result = generate_funnel_report(args.creator, args.days)
        elif args.period == "platform":
            result = generate_platform_report(args.creator, args.days)
        elif args.period == "intent":
            result = generate_intent_report(args.creator, args.days)
        elif args.period == "month":
            # Generate weekly report for ~30 days
            result = generate_weekly_report(args.creator)
            # Also show funnel
            generate_funnel_report(args.creator, 30)
        else:
            result = generate_weekly_report(args.creator)

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))

        print("\n" + "=" * 60)
        print("  Report generated successfully")
        print("=" * 60)

    except Exception as e:
        print(f"\nError generating report: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
