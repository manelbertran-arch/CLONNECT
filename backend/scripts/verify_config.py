#!/usr/bin/env python3
"""
Clonnect Configuration Verification Script

Run this before demos to verify all configuration is correct.

Usage:
    python scripts/verify_config.py
    python scripts/verify_config.py --creator fitpack_global
    python scripts/verify_config.py --fix  # Auto-fix common issues
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def ok(msg):
    print(f"{GREEN}✅ {msg}{RESET}")

def error(msg):
    print(f"{RED}❌ {msg}{RESET}")

def warn(msg):
    print(f"{YELLOW}⚠️  {msg}{RESET}")

def info(msg):
    print(f"{BLUE}ℹ️  {msg}{RESET}")


def check_env_vars():
    """Check required environment variables"""
    print("\n" + "="*60)
    print("1. ENVIRONMENT VARIABLES")
    print("="*60)

    issues = []

    # Required vars
    required = {
        "DATABASE_URL": "PostgreSQL connection",
        "GROQ_API_KEY": "Groq LLM API (or OPENAI_API_KEY)",
    }

    # Optional but important
    optional = {
        "OPENAI_API_KEY": "OpenAI embeddings",
        "INSTAGRAM_VERIFY_TOKEN": "Meta webhook verification",
        "RESEND_API_KEY": "Email notifications",
    }

    for var, desc in required.items():
        val = os.getenv(var)
        if not val:
            if var == "GROQ_API_KEY" and os.getenv("OPENAI_API_KEY"):
                ok(f"OPENAI_API_KEY set (alternative to GROQ_API_KEY)")
            else:
                error(f"{var} not set ({desc})")
                issues.append(f"Set {var}")
        else:
            # Check if key looks valid (not placeholder)
            if "xxx" in val.lower() or "your_" in val.lower() or len(val) < 10:
                warn(f"{var} looks like a placeholder")
                issues.append(f"Check {var} is real")
            else:
                ok(f"{var} is set")

    for var, desc in optional.items():
        val = os.getenv(var)
        if not val:
            warn(f"{var} not set ({desc}) - optional")
        else:
            ok(f"{var} is set")

    # Check LLM_PROVIDER
    llm_provider = os.getenv("LLM_PROVIDER", "openai")
    info(f"LLM_PROVIDER = {llm_provider}")

    if llm_provider == "groq" and not os.getenv("GROQ_API_KEY"):
        error("LLM_PROVIDER=groq but GROQ_API_KEY not set!")
        issues.append("Set GROQ_API_KEY or change LLM_PROVIDER")
    elif llm_provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        error("LLM_PROVIDER=openai but OPENAI_API_KEY not set!")
        issues.append("Set OPENAI_API_KEY or change LLM_PROVIDER")

    return issues


def check_database(creator_id: str = None):
    """Check database connection and creator config"""
    print("\n" + "="*60)
    print("2. DATABASE & CREATOR CONFIG")
    print("="*60)

    issues = []

    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Product

        if SessionLocal is None:
            error("Database not configured")
            issues.append("Configure DATABASE_URL")
            return issues

        db = SessionLocal()

        # Count creators
        creators = db.query(Creator).all()
        ok(f"Database connected - {len(creators)} creators found")

        if creator_id:
            # Check specific creator
            creator = db.query(Creator).filter(
                (Creator.name == creator_id) |
                (Creator.username == creator_id)
            ).first()

            if not creator:
                error(f"Creator '{creator_id}' not found in database")
                issues.append(f"Create creator {creator_id}")
            else:
                info(f"Creator: {creator.name} (ID: {creator.id})")

                # Check bot_active
                if not creator.bot_active:
                    error("bot_active = False - bot won't respond!")
                    issues.append("Set bot_active = True")
                else:
                    ok("bot_active = True")

                # Check copilot_mode
                if creator.copilot_mode is True:
                    warn("copilot_mode = True (messages need manual approval)")
                elif creator.copilot_mode is False:
                    ok("copilot_mode = False (autopilot mode)")
                else:
                    warn("copilot_mode = NULL (defaults to True)")
                    issues.append("Set copilot_mode explicitly")

                # Check products
                products = db.query(Product).filter(
                    Product.creator_id == str(creator.id)
                ).all()

                if not products:
                    warn(f"No products found for {creator_id}")
                else:
                    ok(f"{len(products)} products found")
                    # Check for placeholder payment links
                    for p in products:
                        if p.payment_link and "PENDIENTE" in p.payment_link:
                            warn(f"Product '{p.name}' has placeholder payment_link")
                            issues.append(f"Update payment_link for '{p.name}'")

                # Check leads
                leads = db.query(Lead).filter(
                    Lead.creator_id == str(creator.id)
                ).count()
                info(f"{leads} leads in database")

        else:
            # List all creators
            for c in creators:
                status = "🟢" if c.bot_active else "🔴"
                mode = "copilot" if c.copilot_mode else "autopilot"
                info(f"  {status} {c.name}: {mode}")

        db.close()

    except Exception as e:
        error(f"Database error: {e}")
        issues.append("Fix database connection")

    return issues


def check_instagram_token(creator_id: str = None):
    """Check Instagram token validity"""
    print("\n" + "="*60)
    print("3. INSTAGRAM TOKEN")
    print("="*60)

    issues = []

    if not creator_id:
        info("Specify --creator to check Instagram token")
        return issues

    try:
        from api.database import SessionLocal
        from api.models import Creator
        import httpx

        db = SessionLocal()
        creator = db.query(Creator).filter(
            (Creator.name == creator_id) |
            (Creator.username == creator_id)
        ).first()

        if not creator:
            db.close()
            return issues

        token = creator.instagram_access_token
        if not token:
            warn("No Instagram access token configured")
            issues.append("Connect Instagram in dashboard")
            db.close()
            return issues

        # Test token with a simple API call
        try:
            import asyncio

            async def test_token():
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        f"https://graph.facebook.com/v21.0/me",
                        params={"access_token": token}
                    )
                    return resp.status_code, resp.json()

            status, data = asyncio.run(test_token())

            if status == 200:
                ok(f"Instagram token valid (ID: {data.get('id', 'unknown')})")
            elif status == 401 or status == 400:
                error("Instagram token EXPIRED or INVALID!")
                error(f"Error: {data.get('error', {}).get('message', 'Unknown')}")
                issues.append("Re-authenticate Instagram in dashboard")
            else:
                warn(f"Token check returned status {status}")

        except Exception as e:
            warn(f"Could not verify token: {e}")

        db.close()

    except Exception as e:
        error(f"Error checking token: {e}")

    return issues


def check_nurturing(creator_id: str = None):
    """Check nurturing sequences"""
    print("\n" + "="*60)
    print("4. NURTURING SEQUENCES")
    print("="*60)

    issues = []

    if not creator_id:
        info("Specify --creator to check nurturing config")
        return issues

    config_path = Path(f"data/nurturing/{creator_id}_sequences.json")

    if not config_path.exists():
        warn(f"No nurturing config for {creator_id}")
        info("Nurturing sequences are inactive by default")
        issues.append("Activate nurturing sequences in dashboard")
        return issues

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        sequences = config.get("sequences", {})
        active_count = sum(1 for s in sequences.values() if s.get("is_active"))

        if active_count == 0:
            warn("No nurturing sequences are active!")
            issues.append("Activate at least one nurturing sequence")
        else:
            ok(f"{active_count} nurturing sequences active")
            for name, seq in sequences.items():
                if seq.get("is_active"):
                    info(f"  ✓ {name}")

    except Exception as e:
        error(f"Error reading nurturing config: {e}")

    return issues


def check_content_index(creator_id: str = None):
    """Check content index (RAG)"""
    print("\n" + "="*60)
    print("5. CONTENT INDEX (RAG)")
    print("="*60)

    issues = []

    if not creator_id:
        info("Specify --creator to check content index")
        return issues

    try:
        from api.database import SessionLocal
        from api.models import ContentChunk

        db = SessionLocal()
        chunks = db.query(ContentChunk).filter(
            ContentChunk.creator_id == creator_id
        ).count()
        db.close()

        if chunks == 0:
            warn(f"No content chunks for {creator_id}")
            issues.append("Run content ingestion or scrape Instagram")
        else:
            ok(f"{chunks} content chunks indexed")

    except Exception as e:
        # Fallback to JSON
        index_path = Path(f"data/content_index/{creator_id}/chunks.json")
        if index_path.exists():
            with open(index_path, 'r') as f:
                chunks = json.load(f)
            ok(f"{len(chunks)} content chunks in JSON index")
        else:
            warn(f"No content index for {creator_id}")
            issues.append("Run content ingestion")

    return issues


def main():
    parser = argparse.ArgumentParser(description="Verify Clonnect configuration")
    parser.add_argument("--creator", "-c", help="Creator ID to check")
    parser.add_argument("--fix", action="store_true", help="Auto-fix common issues")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("   CLONNECT CONFIGURATION VERIFICATION")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    if args.creator:
        info(f"Checking creator: {args.creator}")

    all_issues = []

    # Run checks
    all_issues.extend(check_env_vars())
    all_issues.extend(check_database(args.creator))
    all_issues.extend(check_instagram_token(args.creator))
    all_issues.extend(check_nurturing(args.creator))
    all_issues.extend(check_content_index(args.creator))

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    if all_issues:
        error(f"{len(all_issues)} issues found:")
        for i, issue in enumerate(all_issues, 1):
            print(f"  {i}. {issue}")

        if args.fix:
            print("\n" + "="*60)
            print("AUTO-FIX (--fix)")
            print("="*60)
            info("Auto-fix not implemented for security reasons")
            info("Please fix issues manually in the dashboard")

        return 1
    else:
        ok("All checks passed! Ready for demo.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
