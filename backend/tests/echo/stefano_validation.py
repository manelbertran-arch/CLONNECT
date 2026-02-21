"""
Stefano Subjective Validation — HTML Exam Generator.

Generates an interactive HTML page where Stefano can rate clone responses
on a 1-5 scale. Results are saved as JSON for analysis.

Usage:
    python -m tests.echo.stefano_validation --creator stefano --count 20
    python -m tests.echo.stefano_validation --creator stefano --output /tmp/exam.html

Targets:
    - Mean rating > 3.5/5
    - >70% of ratings are 4 or 5
"""
import json
import logging
import argparse
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from tests.echo.generate_test_set import load_test_set, generate_synthetic_test_set

logger = logging.getLogger(__name__)

EXAM_SIZE = 20
TARGET_MEAN = 3.5
TARGET_HIGH_RATE = 0.70  # 70% of 4s and 5s


# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ECHO Validation — {creator_name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f0f;
            color: #e0e0e0;
            padding: 20px;
            max-width: 800px;
            margin: 0 auto;
        }}
        h1 {{
            color: #fff;
            margin-bottom: 8px;
            font-size: 24px;
        }}
        .subtitle {{
            color: #888;
            margin-bottom: 30px;
            font-size: 14px;
        }}
        .progress-bar {{
            width: 100%;
            height: 6px;
            background: #2a2a2a;
            border-radius: 3px;
            margin-bottom: 30px;
            position: sticky;
            top: 0;
            z-index: 10;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #6366f1, #8b5cf6);
            border-radius: 3px;
            transition: width 0.3s ease;
        }}
        .card {{
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            transition: border-color 0.2s;
        }}
        .card.rated {{
            border-color: #6366f1;
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}
        .card-number {{
            color: #6366f1;
            font-weight: 600;
            font-size: 14px;
        }}
        .card-category {{
            background: #2a2a2a;
            color: #aaa;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
        }}
        .context {{
            color: #999;
            font-size: 13px;
            margin-bottom: 12px;
            font-style: italic;
        }}
        .message-group {{
            margin-bottom: 16px;
        }}
        .message {{
            padding: 10px 14px;
            border-radius: 12px;
            margin-bottom: 6px;
            max-width: 85%;
            font-size: 14px;
            line-height: 1.5;
        }}
        .message.user {{
            background: #2a2a2a;
            color: #ccc;
            margin-left: auto;
            border-bottom-right-radius: 4px;
        }}
        .message.bot {{
            background: linear-gradient(135deg, #1e1b4b, #312e81);
            color: #e0e0ff;
            border-bottom-left-radius: 4px;
            border: 1px solid #4338ca;
        }}
        .message-label {{
            font-size: 11px;
            color: #666;
            margin-bottom: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .rating-group {{
            display: flex;
            gap: 8px;
            margin-top: 16px;
            justify-content: center;
        }}
        .rating-btn {{
            width: 56px;
            height: 56px;
            border-radius: 12px;
            border: 2px solid #333;
            background: #1a1a1a;
            color: #aaa;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}
        .rating-btn:hover {{
            border-color: #6366f1;
            color: #fff;
            transform: scale(1.05);
        }}
        .rating-btn.selected {{
            background: #6366f1;
            border-color: #6366f1;
            color: #fff;
            transform: scale(1.1);
        }}
        .rating-btn .label {{
            font-size: 8px;
            margin-top: 2px;
            opacity: 0.7;
        }}
        .notes-input {{
            width: 100%;
            background: #111;
            border: 1px solid #333;
            color: #ccc;
            border-radius: 8px;
            padding: 8px 12px;
            margin-top: 10px;
            font-size: 13px;
            resize: vertical;
            min-height: 40px;
            display: none;
        }}
        .notes-input.visible {{
            display: block;
        }}
        .submit-section {{
            text-align: center;
            padding: 40px 0;
        }}
        .submit-btn {{
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            color: #fff;
            border: none;
            padding: 14px 40px;
            border-radius: 10px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.2s;
        }}
        .submit-btn:hover {{
            opacity: 0.9;
        }}
        .submit-btn:disabled {{
            opacity: 0.4;
            cursor: not-allowed;
        }}
        .results {{
            display: none;
            background: #1a1a1a;
            border: 2px solid #6366f1;
            border-radius: 12px;
            padding: 30px;
            text-align: center;
        }}
        .results h2 {{
            color: #fff;
            margin-bottom: 16px;
        }}
        .results .score {{
            font-size: 48px;
            font-weight: 700;
            color: #6366f1;
        }}
        .results .detail {{
            color: #888;
            margin-top: 8px;
        }}
        .copy-btn {{
            margin-top: 20px;
            background: #2a2a2a;
            border: 1px solid #444;
            color: #ccc;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 13px;
        }}
        .copy-btn:hover {{ background: #333; }}
    </style>
</head>
<body>

<h1>ECHO Clone Validation</h1>
<p class="subtitle">
    Creator: {creator_name} | {exam_count} conversations |
    Generated: {generated_at}
</p>

<div class="progress-bar">
    <div class="progress-fill" id="progressFill" style="width: 0%"></div>
</div>

<div id="cardsContainer">
{cards_html}
</div>

<div class="submit-section" id="submitSection">
    <p style="color: #888; margin-bottom: 16px;">
        Rate all <span id="remainingCount">{exam_count}</span> conversations to submit.
    </p>
    <button class="submit-btn" id="submitBtn" disabled onclick="submitResults()">
        Submit Results
    </button>
</div>

<div class="results" id="resultsSection">
    <h2>Results</h2>
    <div class="score" id="meanScore">-</div>
    <p class="detail" id="resultDetail"></p>
    <button class="copy-btn" onclick="copyResults()">Copy JSON Results</button>
    <pre id="jsonOutput" style="display:none"></pre>
</div>

<script>
const ratings = {{}};
const notes = {{}};
const totalCards = {exam_count};
const testCaseIds = {test_case_ids_json};

function rate(cardId, score) {{
    ratings[cardId] = score;

    // Update button states
    document.querySelectorAll(`#card-${{cardId}} .rating-btn`).forEach(btn => {{
        btn.classList.toggle('selected', parseInt(btn.dataset.score) === score);
    }});

    // Show notes input
    document.querySelector(`#card-${{cardId}} .notes-input`).classList.add('visible');

    // Mark card as rated
    document.getElementById(`card-${{cardId}}`).classList.add('rated');

    updateProgress();
}}

function updateNotes(cardId, text) {{
    notes[cardId] = text;
}}

function updateProgress() {{
    const rated = Object.keys(ratings).length;
    const pct = (rated / totalCards) * 100;
    document.getElementById('progressFill').style.width = pct + '%';
    document.getElementById('remainingCount').textContent = totalCards - rated;
    document.getElementById('submitBtn').disabled = rated < totalCards;
}}

function submitResults() {{
    const scores = Object.values(ratings);
    const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
    const high = scores.filter(s => s >= 4).length;
    const highRate = (high / scores.length) * 100;

    document.getElementById('meanScore').textContent = mean.toFixed(2) + '/5';

    const passMsg = mean >= {target_mean} && highRate >= {target_high_pct}
        ? 'PASS' : 'NEEDS IMPROVEMENT';

    document.getElementById('resultDetail').innerHTML =
        `Mean: ${{mean.toFixed(2)}}/5 | 4-5 rate: ${{highRate.toFixed(0)}}% (${{high}}/${{scores.length}})<br>` +
        `Target: mean > {target_mean}, 4-5 rate > {target_high_pct}%<br>` +
        `<strong style="color: ${{passMsg === 'PASS' ? '#22c55e' : '#ef4444'}}">${{passMsg}}</strong>`;

    // Build result JSON
    const result = {{
        creator: '{creator_name}',
        submitted_at: new Date().toISOString(),
        total: totalCards,
        mean: parseFloat(mean.toFixed(2)),
        median: scores.sort((a,b) => a-b)[Math.floor(scores.length/2)],
        high_count: high,
        high_rate: parseFloat((highRate/100).toFixed(3)),
        distribution: {{
            1: scores.filter(s=>s===1).length,
            2: scores.filter(s=>s===2).length,
            3: scores.filter(s=>s===3).length,
            4: scores.filter(s=>s===4).length,
            5: scores.filter(s=>s===5).length,
        }},
        ratings: testCaseIds.map(id => ({{
            test_case_id: id,
            rating: ratings[id] || null,
            notes: notes[id] || null,
        }})),
        pass: mean >= {target_mean} && highRate >= {target_high_pct},
    }};

    document.getElementById('jsonOutput').textContent = JSON.stringify(result, null, 2);
    document.getElementById('resultsSection').style.display = 'block';
    document.getElementById('submitSection').style.display = 'none';

    // Scroll to results
    document.getElementById('resultsSection').scrollIntoView({{ behavior: 'smooth' }});
}}

function copyResults() {{
    const text = document.getElementById('jsonOutput').textContent;
    navigator.clipboard.writeText(text).then(() => {{
        const btn = document.querySelector('.copy-btn');
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = 'Copy JSON Results', 2000);
    }});
}}
</script>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Card HTML generator
# ---------------------------------------------------------------------------

CARD_TEMPLATE = """
<div class="card" id="card-{card_id}">
    <div class="card-header">
        <span class="card-number">#{index} of {total}</span>
        <span class="card-category">{category} | {topic}</span>
    </div>
    <div class="context">{context}</div>

    <div class="message-group">
        {history_html}
        <div class="message-label">Follower:</div>
        <div class="message user">{follower_message}</div>
        <div class="message-label" style="margin-top: 10px">Clone response:</div>
        <div class="message bot">{clone_response}</div>
    </div>

    <div class="rating-group">
        <button class="rating-btn" data-score="1" onclick="rate('{card_id}', 1)">
            1<span class="label">Nada</span>
        </button>
        <button class="rating-btn" data-score="2" onclick="rate('{card_id}', 2)">
            2<span class="label">Poco</span>
        </button>
        <button class="rating-btn" data-score="3" onclick="rate('{card_id}', 3)">
            3<span class="label">Regular</span>
        </button>
        <button class="rating-btn" data-score="4" onclick="rate('{card_id}', 4)">
            4<span class="label">Bien</span>
        </button>
        <button class="rating-btn" data-score="5" onclick="rate('{card_id}', 5)">
            5<span class="label">Exacto</span>
        </button>
    </div>
    <textarea class="notes-input" placeholder="Notas opcionales..."
        onchange="updateNotes('{card_id}', this.value)"></textarea>
</div>"""


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def generate_card_html(
    test_case: dict,
    clone_response: str,
    index: int,
    total: int,
) -> str:
    """Generate HTML for a single evaluation card."""
    card_id = test_case.get("id", f"card_{index}")
    category = test_case.get("lead_category", "unknown")
    topic = test_case.get("metadata", {}).get("topic", "general")
    context = test_case.get("context", "")
    follower_message = test_case.get("follower_message", "")

    # Build history HTML
    history = test_case.get("conversation_history", [])
    history_html = ""
    for msg in history[-4:]:  # Last 4 messages of context
        role_class = "user" if msg["role"] == "user" else "bot"
        label = "Follower" if msg["role"] == "user" else "Clone"
        history_html += f'<div class="message-label">{label}:</div>\n'
        history_html += f'<div class="message {role_class}">{_escape_html(msg["content"])}</div>\n'

    return CARD_TEMPLATE.format(
        card_id=card_id,
        index=index,
        total=total,
        category=category,
        topic=topic,
        context=_escape_html(context),
        history_html=history_html,
        follower_message=_escape_html(follower_message),
        clone_response=_escape_html(clone_response),
    )


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

async def generate_validation_html(
    creator_name: str,
    test_cases: list[dict],
    pipeline=None,
    count: int = EXAM_SIZE,
    output_path: str | Path | None = None,
) -> Path:
    """
    Generate the Stefano validation HTML file.

    If pipeline is provided, generates clone responses.
    Otherwise, uses 'real_response' as the clone response (for testing the framework).
    """
    import random

    # Sample test cases
    if len(test_cases) > count:
        random.seed(42)
        selected = random.sample(test_cases, count)
    else:
        selected = test_cases[:count]

    # Generate clone responses
    clone_responses = []
    for tc in selected:
        if pipeline:
            try:
                response = await pipeline.process_dm(
                    message=tc.get("follower_message", ""),
                    sender_id=tc.get("lead_id", "test"),
                )
                clone_responses.append(response.content)
            except Exception as e:
                logger.error(f"Pipeline error for {tc.get('id')}: {e}")
                clone_responses.append(tc.get("real_response", "Error generating response"))
        else:
            # Use real response for framework testing
            clone_responses.append(tc.get("real_response", ""))

    # Generate cards HTML
    cards_html = ""
    test_case_ids = []
    for i, (tc, clone_resp) in enumerate(zip(selected, clone_responses), 1):
        cards_html += generate_card_html(tc, clone_resp, i, len(selected))
        test_case_ids.append(tc.get("id", f"card_{i}"))

    # Build full HTML
    html = HTML_TEMPLATE.format(
        creator_name=creator_name,
        exam_count=len(selected),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        cards_html=cards_html,
        test_case_ids_json=json.dumps(test_case_ids),
        target_mean=TARGET_MEAN,
        target_high_pct=int(TARGET_HIGH_RATE * 100),
    )

    # Write file
    if output_path is None:
        output_path = Path(__file__).parent / f"validation_{creator_name}.html"
    output_path = Path(output_path)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"Validation HTML saved to {output_path}")
    return output_path


def analyze_validation_results(results_json: str | dict) -> dict:
    """
    Analyze results submitted by the creator.

    Input: JSON string or dict from the HTML form submission.
    """
    if isinstance(results_json, str):
        results = json.loads(results_json)
    else:
        results = results_json

    scores = [r["rating"] for r in results.get("ratings", []) if r.get("rating")]

    if not scores:
        return {"error": "No ratings found", "pass": False}

    mean = sum(scores) / len(scores)
    sorted_scores = sorted(scores)
    median = sorted_scores[len(sorted_scores) // 2]
    high_count = sum(1 for s in scores if s >= 4)
    high_rate = high_count / len(scores)

    distribution = {i: scores.count(i) for i in range(1, 6)}
    pass_test = mean >= TARGET_MEAN and high_rate >= TARGET_HIGH_RATE

    # Find problematic responses (rated 1-2)
    low_rated = [
        r for r in results.get("ratings", [])
        if r.get("rating") and r["rating"] <= 2
    ]

    return {
        "total_rated": len(scores),
        "mean": round(mean, 2),
        "median": median,
        "high_count": high_count,
        "high_rate": round(high_rate, 3),
        "distribution": distribution,
        "low_rated": low_rated,
        "pass": pass_test,
        "target_mean": TARGET_MEAN,
        "target_high_rate": TARGET_HIGH_RATE,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate ECHO validation HTML for creator")
    parser.add_argument("--creator", default="stefano", help="Creator name")
    parser.add_argument("--count", type=int, default=EXAM_SIZE, help="Number of conversations")
    parser.add_argument("--test-set", default=None, help="Test set JSON path")
    parser.add_argument("--output", default=None, help="Output HTML path")
    parser.add_argument("--synthetic", action="store_true", help="Use synthetic data")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.test_set:
        test_cases, _ = load_test_set(args.test_set)
    elif args.synthetic:
        test_cases = generate_synthetic_test_set(count=args.count + 10)
    else:
        # Try default path
        default_path = Path(__file__).parent / "test_sets" / f"{args.creator}_v1.json"
        if default_path.exists():
            test_cases, _ = load_test_set(default_path)
        else:
            logger.info("No test set found, generating synthetic")
            test_cases = generate_synthetic_test_set(count=args.count + 10)

    output_path = asyncio.run(
        generate_validation_html(
            creator_name=args.creator.title(),
            test_cases=test_cases,
            count=args.count,
            output_path=args.output,
        )
    )

    print(f"\nValidation HTML generated: {output_path}")
    print(f"Open in browser: file://{output_path.resolve()}")


if __name__ == "__main__":
    main()
