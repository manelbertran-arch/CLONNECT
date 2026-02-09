#!/usr/bin/env python3
"""
Export training data from PostgreSQL for Together.ai fine-tuning.

Generates JSONL in the format required by Llama fine-tuning:
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}

Usage:
    DATABASE_URL="postgresql://..." python scripts/export_training_data.py

Or set DATABASE_URL in environment and run:
    python scripts/export_training_data.py
"""

import os
import sys
import json
from datetime import datetime
from collections import defaultdict
from typing import Optional

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# Database connection
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_91lRcgDvZAIy@ep-raspy-truth-agjtq3o5-pooler.c-2.eu-central-1.aws.neon.tech/neondb?sslmode=require"
)

# Output file
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "stefano_training_data.jsonl")

# System prompt for Stefano's clone
SYSTEM_PROMPT = """Eres el clon de Stefano, un experto en marketing digital, copywriting y negocios online. Tu estilo es:

- Cercano y directo, como hablando con un amigo
- Usas "tú" (no voseo)
- Respuestas cortas y al grano (2-3 frases máximo)
- Ocasionalmente usas emojis pero sin abusar
- Conoces profundamente los productos y servicios de Stefano
- Siempre buscas ayudar y aportar valor
- Si no sabes algo, lo dices honestamente
- Nunca inventas precios ni URLs

Productos principales:
- Mentoría 1:1 de copywriting y marketing
- Cursos online de email marketing y ventas
- Recursos gratuitos en el podcast y YouTube

Responde siempre en español."""


def get_creator_info(session) -> Optional[dict]:
    """Get Stefano's creator config from database."""
    result = session.execute(
        text("SELECT id, name, clone_tone, clone_vocabulary FROM creators WHERE name ILIKE '%stefan%' OR name ILIKE '%manel%' LIMIT 1")
    )
    row = result.fetchone()
    if row:
        return {
            "id": str(row[0]),
            "name": row[1],
            "tone": row[2],
            "vocabulary": row[3]
        }
    return None


def get_conversations(session, creator_id: str) -> list:
    """
    Get all conversations grouped by lead, with user messages and bot responses.
    Only includes conversations where the bot actually responded (role='assistant').
    """
    # Get all messages ordered by lead and time
    result = session.execute(
        text("""
            SELECT
                m.lead_id,
                m.role,
                m.content,
                m.created_at,
                l.username,
                l.name
            FROM messages m
            JOIN leads l ON m.lead_id = l.id
            WHERE l.creator_id = :creator_id
            ORDER BY m.lead_id, m.created_at
        """),
        {"creator_id": creator_id}
    )

    # Group by lead
    conversations_by_lead = defaultdict(list)
    for row in result:
        lead_id = str(row[0])
        conversations_by_lead[lead_id].append({
            "role": row[1],
            "content": row[2],
            "created_at": row[3],
            "username": row[4],
            "name": row[5]
        })

    return conversations_by_lead


def create_training_examples(conversations: dict) -> list:
    """
    Convert conversations to training examples.

    Each example is a user message followed by an assistant response.
    We create sliding windows of context for multi-turn conversations.
    """
    examples = []

    for lead_id, messages in conversations.items():
        if len(messages) < 2:
            continue

        # Build conversation turns
        current_context = []

        for i, msg in enumerate(messages):
            role = msg["role"]
            content = msg["content"]

            # Skip empty messages
            if not content or not content.strip():
                continue

            # Normalize role names
            if role in ["user", "lead", "follower"]:
                role = "user"
            elif role in ["assistant", "bot", "clone"]:
                role = "assistant"
            else:
                continue  # Skip unknown roles

            # Add to context
            current_context.append({
                "role": role,
                "content": content.strip()
            })

            # When we have a user message followed by assistant response, create example
            if role == "assistant" and len(current_context) >= 2:
                # Find the last user message before this assistant response
                user_idx = None
                for j in range(len(current_context) - 2, -1, -1):
                    if current_context[j]["role"] == "user":
                        user_idx = j
                        break

                if user_idx is not None:
                    # Create training example with context
                    example_messages = [{"role": "system", "content": SYSTEM_PROMPT}]

                    # Add conversation history (last N turns for context)
                    context_start = max(0, user_idx - 4)  # Include up to 2 previous exchanges
                    for ctx_msg in current_context[context_start:]:
                        example_messages.append({
                            "role": ctx_msg["role"],
                            "content": ctx_msg["content"]
                        })

                    examples.append({"messages": example_messages})

    return examples


def filter_quality_examples(examples: list) -> list:
    """
    Filter out low-quality examples:
    - Too short responses
    - Error messages
    - Rate limit messages
    - Bot paused messages
    """
    filtered = []

    skip_patterns = [
        "bot pausado",
        "rate limit",
        "error",
        "lo siento, no puedo",
        "dame un momento",
        "procesando varios mensajes"
    ]

    for ex in examples:
        messages = ex["messages"]

        # Get the last assistant message
        assistant_msg = None
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                assistant_msg = msg["content"]
                break

        if not assistant_msg:
            continue

        # Skip too short responses (less than 10 chars)
        if len(assistant_msg) < 10:
            continue

        # Skip if contains skip patterns
        lower_msg = assistant_msg.lower()
        if any(pattern in lower_msg for pattern in skip_patterns):
            continue

        # Skip if user message is too short (spam/noise)
        user_msg = None
        for msg in messages:
            if msg["role"] == "user":
                user_msg = msg["content"]

        if user_msg and len(user_msg) < 3:
            continue

        filtered.append(ex)

    return filtered


def main():
    print("=" * 60)
    print("EXPORT TRAINING DATA FOR TOGETHER.AI FINE-TUNING")
    print("=" * 60)
    print(f"\nConnecting to database...")

    try:
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        print("Connected successfully!")
    except Exception as e:
        print(f"ERROR: Failed to connect to database: {e}")
        sys.exit(1)

    # Get creator info
    print("\nFetching creator info...")
    creator = get_creator_info(session)
    if not creator:
        print("ERROR: No creator found (Stefano/Manel)")
        sys.exit(1)

    print(f"  Creator: {creator['name']} (ID: {creator['id']})")
    print(f"  Tone: {creator['tone']}")

    # Get conversations
    print("\nFetching conversations...")
    conversations = get_conversations(session, creator["id"])
    print(f"  Found {len(conversations)} unique leads with conversations")

    total_messages = sum(len(msgs) for msgs in conversations.values())
    print(f"  Total messages: {total_messages}")

    # Create training examples
    print("\nCreating training examples...")
    examples = create_training_examples(conversations)
    print(f"  Raw examples: {len(examples)}")

    # Filter quality
    print("\nFiltering for quality...")
    filtered_examples = filter_quality_examples(examples)
    print(f"  Quality examples: {len(filtered_examples)}")

    if not filtered_examples:
        print("\nERROR: No quality examples found!")
        sys.exit(1)

    # Write to JSONL
    print(f"\nWriting to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for ex in filtered_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"  Written {len(filtered_examples)} examples")

    # Show sample
    print("\n" + "=" * 60)
    print("SAMPLE TRAINING EXAMPLE:")
    print("=" * 60)
    if filtered_examples:
        sample = filtered_examples[0]
        for msg in sample["messages"]:
            role = msg["role"].upper()
            content = msg["content"][:200] + "..." if len(msg["content"]) > 200 else msg["content"]
            print(f"\n[{role}]")
            print(content)

    print("\n" + "=" * 60)
    print("EXPORT COMPLETE!")
    print("=" * 60)
    print(f"\nOutput file: {OUTPUT_FILE}")
    print(f"Total examples: {len(filtered_examples)}")
    print(f"\nNext step: Upload to Together.ai")
    print(f"  together files upload {OUTPUT_FILE}")

    session.close()


if __name__ == "__main__":
    main()
