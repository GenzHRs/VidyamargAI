"""
VidyaMarg AI - Safe Database Cleanup & Schema Alignment Migration Script

This script:
1. Renames active candidate feature tables from legacy_* back to their canonical names.
2. Safely drops 16 approved admin-only and unused legacy tables in correct dependency order.
3. Provides a --dry-run flag to simulate without applying changes.
4. Reports all affected tables, row counts, and schema verification.
"""

import sqlite3
import argparse
import sys
from pathlib import Path

# Tables to restore to canonical names (from legacy_* to canonical)
TABLES_TO_RESTORE = [
    ("legacy_ai_mentor_sessions", "ai_mentor_sessions"),
    ("legacy_ai_mentor_messages", "ai_mentor_messages"),
    ("legacy_ai_mentor_study_plans", "ai_mentor_study_plans"),
    ("legacy_ai_mentor_insights", "ai_mentor_insights"),
    ("legacy_ai_mentor_artifacts", "ai_mentor_artifacts"),
    ("legacy_ai_mentor_usage", "ai_mentor_usage"),
    ("legacy_user_career_profiles", "user_career_profiles"),
    ("legacy_email_notifications", "email_notifications"),
    ("legacy_messages", "messages"),
    ("legacy_learning_events", "learning_events"),
    ("legacy_agent_memory", "agent_memory"),
    ("legacy_browser_sessions", "browser_sessions"),
    ("legacy_browser_cookies", "browser_cookies"),
]

# Approved tables for safe dropping in topological FK order
TABLES_TO_DROP = [
    "legacy_course_analytics",
    "legacy_telegram_sources",
    "legacy_video_analytics",
    "legacy_agent_health",
    "legacy_mcp_audit_logs",
    "legacy_circuit_breaker_states",
    "legacy_company_intelligence_cache",
    "legacy_mcp_chat_messages",  # dropped before sessions to satisfy FK
    "legacy_mcp_chat_sessions",
    "legacy_agent_activities",
    "legacy_vector_memory",
    "legacy_career_health_snapshots",
    "legacy_candidate_preferences",
    "legacy_application_history",
    "dead_letter_jobs",
    "tool_permissions",
]


def run_migration(db_path: Path, dry_run: bool = False):
    print(f"Connecting to database: {db_path.resolve()}")
    if not db_path.exists():
        print(f"ERROR: Database file {db_path} does not exist!")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    existing_tables = set(r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
    print(f"Total tables before migration: {len(existing_tables)}")

    restored_count = 0
    dropped_count = 0

    print("\n--- PHASE 1: RESTORING ACTIVE CANDIDATE TABLES ---")
    for old_name, new_name in TABLES_TO_RESTORE:
        if old_name in existing_tables:
            if new_name in existing_tables:
                print(f"[SKIP] Target table {new_name} already exists. Leaving as-is.")
            else:
                row_count = cursor.execute(f"SELECT COUNT(*) FROM {old_name}").fetchone()[0]
                print(f"[RESTORE] {old_name} -> {new_name} ({row_count} rows)")
                if not dry_run:
                    cursor.execute(f"ALTER TABLE {old_name} RENAME TO {new_name}")
                restored_count += 1
        else:
            if new_name in existing_tables:
                print(f"[OK] Table {new_name} is already canonical.")
            else:
                print(f"[NOTICE] Neither {old_name} nor {new_name} found in DB.")

    print("\n--- PHASE 2: DROPPING APPROVED ADMIN & UNUSED TABLES ---")
    for tbl in TABLES_TO_DROP:
        if tbl in existing_tables:
            row_count = cursor.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            print(f"[DROP] Table {tbl} (Row count: {row_count})")
            if not dry_run:
                cursor.execute(f"DROP TABLE IF EXISTS {tbl}")
            dropped_count += 1
        else:
            print(f"[SKIP] Table {tbl} does not exist in DB.")

    if not dry_run:
        conn.commit()

    post_tables = set(r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
    conn.close()

    print("\n--- MIGRATION SUMMARY ---")
    print(f"Mode: {'DRY RUN (No changes committed)' if dry_run else 'LIVE MIGRATION'}")
    print(f"Tables Restored to Canonical: {restored_count}")
    print(f"Obsolete Tables Dropped: {dropped_count}")
    print(f"Initial Table Count: {len(existing_tables)}")
    print(f"Final Table Count: {len(post_tables)}")
    print("Migration completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VidyaMarg AI Database Cleanup Migration")
    parser.add_argument("--db", type=str, default="vidyamarg.db", help="Path to sqlite db file")
    parser.add_argument("--dry-run", action="store_true", help="Simulate migration without modifying DB")
    args = parser.parse_args()

    run_migration(Path(args.db), dry_run=args.dry_run)
