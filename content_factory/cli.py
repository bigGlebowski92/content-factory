#!/usr/bin/env python3
"""Command-line interface for Content Factory."""

import argparse
import asyncio
import sys
from pathlib import Path

from content_factory.config import load_config
from content_factory.models import Topic
from content_factory.orchestrator import Orchestrator
from content_factory.storage import Storage


def print_task_summary(task):
    """Print a summary of a task."""
    print(f"\n{'='*60}")
    print(f"Task ID: {task.id}")
    print(f"Direction: {task.direction}")
    print(f"Status: {task.status.value}")
    print(f"Topic: {task.topic.text}")
    print(f"Rubric: {task.topic.rubric}")
    print(f"Revision Count: {task.revision_count}")
    
    if task.dossier:
        print(f"\nFact Dossier: {len(task.dossier.facts)} facts gathered")
        for i, fact in enumerate(task.dossier.facts[:3], 1):
            print(f"  {i}. {fact.statement[:80]}...")
    
    if task.generated_texts:
        text = task.generated_texts[-1]
        print(f"\nGenerated Text:")
        print(f"  Title: {text.title}")
        print(f"  Format: {text.format.value}")
        print(f"  Word Count: {text.word_count}")
        print(f"  Sources Cited: {len(text.sources_cited)}")
    
    if task.audit_result:
        print(f"\nAudit Result:")
        print(f"  Verdict: {task.audit_result.verdict.value}")
        print(f"  Score: {task.audit_result.score:.2f}")
        print(f"  Remarks: {len(task.audit_result.remarks)}")
        if task.audit_result.remarks:
            for remark in task.audit_result.remarks[:2]:
                print(f"    - {remark.rule}: {remark.comment}")
    
    if task.error_message:
        print(f"\nError: {task.error_message}")
    
    print(f"{'='*60}\n")


async def run_cycle(args):
    """Run a full generation cycle."""
    settings = load_config()
    storage = Storage(data_dir=settings.database_path.replace(".db", ""))
    orchestrator = Orchestrator(settings, storage)
    
    print(f"Running cycle for direction: {args.direction}")
    
    if args.use_mock:
        print("Using MOCK provider (no API calls)")
        settings.use_mock_provider = True
    
    topic = None
    if args.topic:
        topic = Topic(
            text=args.topic,
            rubric=args.rubric or "general",
            rationale=args.rationale or "User-provided topic",
            direction=args.direction,
        )
        print(f"Using provided topic: {args.topic}")
    else:
        print("Generating topic automatically...")
    
    try:
        task = await orchestrator.run_full_cycle(
            direction=args.direction,
            topic=topic,
        )
        
        print_task_summary(task)
        
        print("\n✓ Cycle completed successfully!")
        print(f"Task is now in {task.status.value} status and awaits human approval.")
        print("No content will be published without explicit approval.\n")
        
        return 0
    
    except Exception as e:
        print(f"\n✗ Error: {e}\n", file=sys.stderr)
        return 1


async def show_spending(args):
    """Show current spending statistics."""
    settings = load_config()
    storage = Storage(data_dir=settings.database_path.replace(".db", ""))
    orchestrator = Orchestrator(settings, storage)
    
    limits = orchestrator.check_spend_limits()
    
    print("\n" + "="*60)
    print("SPENDING STATISTICS")
    print("="*60)
    
    print("\nDaily:")
    print(f"  Spent: ${limits['daily']['spent_usd']:.4f}")
    print(f"  Limit: ${limits['daily']['limit_usd']:.2f}")
    print(f"  Usage: {limits['daily']['percentage']:.1f}%")
    if limits['daily']['exceeded']:
        print("  ⚠️  LIMIT EXCEEDED")
    
    print("\nMonthly:")
    print(f"  Spent: ${limits['monthly']['spent_usd']:.4f}")
    print(f"  Limit: ${limits['monthly']['limit_usd']:.2f}")
    print(f"  Usage: {limits['monthly']['percentage']:.1f}%")
    if limits['monthly']['exceeded']:
        print("  ⚠️  LIMIT EXCEEDED")
    
    print("\n" + "="*60 + "\n")


def list_tasks(args):
    """List tasks."""
    settings = load_config()
    storage = Storage(data_dir=settings.database_path.replace(".db", ""))
    
    tasks = storage.list_tasks(direction=args.direction)
    
    if not tasks:
        print("\nNo tasks found.\n")
        return
    
    print(f"\n{'='*80}")
    print(f"TASKS ({len(tasks)} total)")
    print(f"{'='*80}")
    
    for task in tasks:
        status_emoji = {
            "draft": "📝",
            "research": "🔍",
            "generation": "✍️",
            "audit": "🔎",
            "approval": "⏳",
            "approved": "✅",
            "rejected": "❌",
            "scheduled": "📅",
            "published": "📣",
            "disputed": "⚖️",
            "error": "⚠️",
        }.get(task.status.value, "•")
        
        print(f"\n{status_emoji} {task.id}")
        print(f"   Direction: {task.direction}")
        print(f"   Topic: {task.topic.text[:60]}...")
        print(f"   Status: {task.status.value}")
        print(f"   Created: {task.created_at.strftime('%Y-%m-%d %H:%M')}")


async def schedule_task(args):
    """Schedule an approved task for Telegram."""
    from datetime import datetime
    from uuid import UUID

    settings = load_config()
    storage = Storage(data_dir=settings.database_path.replace(".db", ""))
    orchestrator = Orchestrator(settings, storage)

    when = datetime.fromisoformat(args.at)
    task = orchestrator.schedule_telegram(UUID(args.task_id), when)
    print(f"Scheduled {task.id} for {task.scheduled_at} (status={task.status.value})")
    return 0


async def publish_due(args):
    """Publish due scheduled Telegram posts."""
    settings = load_config()
    storage = Storage(data_dir=settings.database_path.replace(".db", ""))
    orchestrator = Orchestrator(settings, storage)
    tasks = await orchestrator.publish_due_telegram()
    print(f"Published {len(tasks)} task(s)")
    for task in tasks:
        print(f"  - {task.id} → {task.publication.message_id if task.publication else '?'}")
    return 0


def weekly_report(args):
    """Print weekly spend report."""
    settings = load_config()
    storage = Storage(data_dir=settings.database_path.replace(".db", ""))
    orchestrator = Orchestrator(settings, storage)
    report = orchestrator.weekly_spend_report(direction=args.direction)
    print("\n" + report["summary_text"] + "\n")
    return 0


async def publish_platform(args):
    """Publish approved task to website/platform."""
    from uuid import UUID

    settings = load_config()
    storage = Storage(data_dir=settings.database_path.replace(".db", ""))
    orchestrator = Orchestrator(settings, storage)
    task = await orchestrator.publish_to_platform(UUID(args.task_id))
    pub = task.platform_publication
    print(f"Platform published {task.id} (status remains {task.status.value})")
    if pub:
        print(f"  short_url: {pub.short_url}")
        print(f"  platform_url: {pub.platform_url}")
    return 0


def click_link(args):
    """Record a short-link click."""
    settings = load_config()
    storage = Storage(data_dir=settings.database_path.replace(".db", ""))
    orchestrator = Orchestrator(settings, storage)
    link = orchestrator.record_short_link_click(args.code)
    print(f"Click recorded: {link.code} → {link.clicks} clicks (channel={link.channel})")
    return 0


def click_analytics(args):
    """Print text → channel → clicks funnel."""
    from uuid import UUID

    settings = load_config()
    storage = Storage(data_dir=settings.database_path.replace(".db", ""))
    orchestrator = Orchestrator(settings, storage)
    task_id = UUID(args.task_id) if args.task_id else None
    report = orchestrator.click_funnel(task_id=task_id, channel=args.channel)
    print(f"\nTotal clicks: {report['total_clicks']}")
    for row in report["rows"]:
        print(
            f"  [{row['channel']}] {row['text_title'][:40]} "
            f"→ {row['clicks']} clicks ({row['short_code']})"
        )
    print()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Content Factory - Stages 1–3"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    run_parser = subparsers.add_parser("run", help="Run a generation cycle")
    run_parser.add_argument("direction", help="Direction name (e.g., mental_health)")
    run_parser.add_argument("--topic", help="Topic text (if not provided, will be generated)")
    run_parser.add_argument("--rubric", help="Topic rubric")
    run_parser.add_argument("--rationale", help="Topic rationale")
    run_parser.add_argument("--use-mock", action="store_true", help="Force use of mock provider")
    
    spending_parser = subparsers.add_parser("spending", help="Show spending statistics")
    
    list_parser = subparsers.add_parser("list", help="List tasks")
    list_parser.add_argument("--direction", help="Filter by direction")

    schedule_parser = subparsers.add_parser(
        "schedule", help="Schedule an approved task for Telegram"
    )
    schedule_parser.add_argument("task_id", help="Task UUID")
    schedule_parser.add_argument(
        "--at",
        required=True,
        help="ISO datetime to publish (e.g. 2026-10-02T12:00:00)",
    )

    subparsers.add_parser("publish-due", help="Publish due scheduled Telegram posts")

    weekly_parser = subparsers.add_parser("weekly-report", help="Weekly spend report")
    weekly_parser.add_argument("--direction", help="Filter by direction")

    platform_parser = subparsers.add_parser(
        "publish-platform", help="Publish approved task to website/platform"
    )
    platform_parser.add_argument("task_id", help="Task UUID")

    click_parser = subparsers.add_parser("click", help="Record a short-link click")
    click_parser.add_argument("code", help="Short link code")

    analytics_parser = subparsers.add_parser(
        "click-analytics", help="Text → channel → clicks report"
    )
    analytics_parser.add_argument("--task-id", help="Filter by task UUID")
    analytics_parser.add_argument("--channel", help="Filter by channel")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    if args.command == "run":
        return asyncio.run(run_cycle(args))
    elif args.command == "spending":
        asyncio.run(show_spending(args))
        return 0
    elif args.command == "list":
        list_tasks(args)
        return 0
    elif args.command == "schedule":
        return asyncio.run(schedule_task(args))
    elif args.command == "publish-due":
        return asyncio.run(publish_due(args))
    elif args.command == "weekly-report":
        return weekly_report(args)
    elif args.command == "publish-platform":
        return asyncio.run(publish_platform(args))
    elif args.command == "click":
        return click_link(args)
    elif args.command == "click-analytics":
        return click_analytics(args)
    
    return 1


if __name__ == "__main__":
    sys.exit(main())
