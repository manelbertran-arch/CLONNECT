# 📊 CLONNECT ACADEMIC METRICS ROADMAP
## Metodología Specs-Driven - Modo Bypass Total

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║  INSTRUCCIÓN PARA CLAUDE CODE:                                                 ║
║                                                                                ║
║  1. Lee este archivo completo PRIMERO                                          ║
║  2. Ejecuta CADA spec en orden sin preguntar                                   ║
║  3. Si algo falla → log error → continuar siguiente                            ║
║  4. NO pidas confirmación NUNCA                                                ║
║  5. Al final genera METRICS_REPORT.md                                          ║
║                                                                                ║
║  MODO: BYPASS - Decisiones automáticas basadas en specs                        ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

---

# 📋 ÍNDICE DE SPECS

| ID | Nombre | Prioridad | Tiempo | Categoría |
|:---|:-------|:----------|:-------|:----------|
| SPEC-M00 | Setup Métricas | P0 | 10m | Setup |
| SPEC-M01 | Task Completion Rate | P1 | 2h | UX |
| SPEC-M02 | CSAT Post-Conversación | P1 | 3h | UX |
| SPEC-M03 | Abandonment Rate | P1 | 2h | UX |
| SPEC-M04 | Response Latency Tracker | P1 | 1h | UX |
| SPEC-M05 | Knowledge Retention Score | P1 | 2h | Cognitiva |
| SPEC-M06 | LLM-as-Judge Consistency | P2 | 4h | Calidad |
| SPEC-M07 | Intent Accuracy | P2 | 4h | Cognitiva |
| SPEC-M08 | Semantic Similarity (Relevance) | P2 | 3h | Calidad |
| SPEC-M09 | Topic Drift Detection | P2 | 2h | Diálogo |
| SPEC-M10 | OOD Detection | P2 | 3h | Robustez |
| SPEC-M11 | Adversarial Resistance | P3 | 4h | Robustez |
| SPEC-M12 | Metrics Dashboard | P1 | 4h | Infra |
| SPEC-M13 | Automated Eval Pipeline | P2 | 4h | Infra |

**Tiempo Total: ~38 horas**

---

# SPEC-M00: Setup Métricas
```yaml
id: SPEC-M00
priority: P0
time: 10 minutes
type: setup
```

## Comandos

```bash
# 1. Crear estructura de directorios
mkdir -p backend/metrics
mkdir -p backend/metrics/collectors
mkdir -p backend/metrics/analyzers
mkdir -p backend/metrics/reports
mkdir -p backend/tests/metrics

# 2. Crear archivo base
cat > backend/metrics/__init__.py << 'EOF'
"""
Clonnect Academic Metrics System
Based on 2024-2026 Conversational AI Research
"""
from .base import MetricsCollector, MetricResult
from .dashboard import MetricsDashboard

__all__ = ["MetricsCollector", "MetricResult", "MetricsDashboard"]
EOF

# 3. Crear clase base
cat > backend/metrics/base.py << 'EOF'
"""Base classes for metrics collection."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)

class MetricCategory(Enum):
    COGNITIVE = "cognitive"
    QUALITY = "quality"
    REASONING = "reasoning"
    DIALOGUE = "dialogue"
    UX = "user_experience"
    ROBUSTNESS = "robustness"

@dataclass
class MetricResult:
    """Single metric measurement."""
    name: str
    value: float
    category: MetricCategory
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "value": self.value,
            "category": self.category.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }

class MetricsCollector:
    """Base collector for all metrics."""

    def __init__(self, creator_id: str):
        self.creator_id = creator_id
        self._results: List[MetricResult] = []

    async def collect(self, conversation_id: str) -> List[MetricResult]:
        """Override in subclasses."""
        raise NotImplementedError

    def add_result(self, result: MetricResult):
        self._results.append(result)
        logger.info(f"[Metrics] {result.name}: {result.value:.2f}")

    def get_results(self) -> List[MetricResult]:
        return self._results

    def get_summary(self) -> Dict[str, float]:
        """Get average by metric name."""
        from collections import defaultdict
        sums = defaultdict(list)
        for r in self._results:
            sums[r.name].append(r.value)
        return {k: sum(v)/len(v) for k, v in sums.items()}
EOF

# 4. Commit setup
git add -A
git commit -m "feat(metrics): Setup academic metrics infrastructure"
```

**Criterio de éxito:** Directorios y clases base creados.

---

# SPEC-M01: Task Completion Rate
```yaml
id: SPEC-M01
priority: P1
time: 2 hours
type: metric
category: UX
paper_ref: "Conversation Success Metrics (2024)"
```

## Descripción
Mide el % de conversaciones donde el usuario logró su objetivo (compra, info, resolución).

## Implementación

```python
# backend/metrics/collectors/task_completion.py
"""
Task Completion Rate Collector
Measures: % of conversations where user achieved their goal
"""
import re
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum
import logging

from ..base import MetricsCollector, MetricResult, MetricCategory

logger = logging.getLogger(__name__)

class TaskType(Enum):
    PURCHASE = "purchase"           # Usuario compró
    INFO_REQUEST = "info_request"   # Usuario obtuvo info
    SUPPORT = "support"             # Problema resuelto
    BOOKING = "booking"             # Cita agendada
    LEAD_QUALIFIED = "lead_qualified"  # Lead cualificado
    UNKNOWN = "unknown"

class TaskOutcome(Enum):
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    ESCALATED = "escalated"
    PENDING = "pending"

class TaskCompletionCollector(MetricsCollector):
    """Collects task completion metrics."""

    def __init__(self, creator_id: str):
        super().__init__(creator_id)

        # Patterns to detect task completion
        self.completion_patterns = {
            TaskType.PURCHASE: [
                r'(gracias.*compra|pedido.*confirmado|pago.*recibido)',
                r'(thanks.*purchase|order.*confirmed|payment.*received)',
                r'(ya.*pagué|transferencia.*hecha)',
            ],
            TaskType.INFO_REQUEST: [
                r'(perfecto.*entendido|gracias.*info|me.*queda.*claro)',
                r'(perfect.*understood|thanks.*info|clear.*now)',
                r'(vale.*gracias|ok.*entiendo)',
            ],
            TaskType.BOOKING: [
                r'(cita.*confirmada|reserva.*hecha|agenda.*)',
                r'(appointment.*confirmed|booking.*made)',
                r'(nos.*vemos|quedamos.*entonces)',
            ],
            TaskType.LEAD_QUALIFIED: [
                r'(me.*interesa.*más|quiero.*saber.*precio)',
                r'(cuánto.*cuesta|precio|tarifas)',
                r'(cómo.*empiezo|siguiente.*paso)',
            ],
        }

        # Patterns to detect abandonment
        self.abandonment_patterns = [
            r'(no.*gracias|no.*interesa|demasiado.*caro)',
            r'(bye|adiós|hasta.*luego)(?!.*gracias)',
            r'(lo.*pienso|ya.*veré|otro.*momento)',
        ]

        # Patterns to detect escalation
        self.escalation_patterns = [
            r'(hablar.*humano|persona.*real|agente)',
            r'(no.*entiendes|eres.*bot|máquina)',
            r'(quiero.*hablar.*con)',
        ]

    async def collect(self, conversation_id: str) -> List[MetricResult]:
        """Analyze conversation for task completion."""
        from database import get_db

        async with get_db() as db:
            # Get conversation messages
            messages = await db.fetch_all(
                """
                SELECT content, sender_type, created_at
                FROM messages
                WHERE conversation_id = :conv_id
                ORDER BY created_at ASC
                """,
                {"conv_id": conversation_id}
            )

        if not messages:
            return []

        # Detect task type from first user messages
        task_type = self._detect_task_type(messages)

        # Detect outcome from last messages
        outcome = self._detect_outcome(messages)

        # Calculate completion rate
        is_completed = outcome == TaskOutcome.COMPLETED

        result = MetricResult(
            name="task_completion_rate",
            value=1.0 if is_completed else 0.0,
            category=MetricCategory.UX,
            metadata={
                "conversation_id": conversation_id,
                "task_type": task_type.value,
                "outcome": outcome.value,
                "message_count": len(messages),
            }
        )

        self.add_result(result)
        return [result]

    def _detect_task_type(self, messages: List[Dict]) -> TaskType:
        """Detect what the user was trying to accomplish."""
        # Look at first 3 user messages
        user_messages = [
            m["content"] for m in messages
            if m["sender_type"] == "lead"
        ][:3]

        combined = " ".join(user_messages).lower()

        for task_type, patterns in self.completion_patterns.items():
            for pattern in patterns:
                if re.search(pattern, combined, re.IGNORECASE):
                    return task_type

        return TaskType.UNKNOWN

    def _detect_outcome(self, messages: List[Dict]) -> TaskOutcome:
        """Detect conversation outcome from last messages."""
        # Look at last 5 messages
        last_messages = messages[-5:]
        combined = " ".join(m["content"] or "" for m in last_messages).lower()

        # Check for completion first
        for patterns in self.completion_patterns.values():
            for pattern in patterns:
                if re.search(pattern, combined, re.IGNORECASE):
                    return TaskOutcome.COMPLETED

        # Check for escalation
        for pattern in self.escalation_patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                return TaskOutcome.ESCALATED

        # Check for abandonment
        for pattern in self.abandonment_patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                return TaskOutcome.ABANDONED

        # If conversation is recent, might be pending
        return TaskOutcome.PENDING

    async def get_aggregate_rate(self, days: int = 30) -> float:
        """Get overall task completion rate for period."""
        from database import get_db
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)

        async with get_db() as db:
            conversations = await db.fetch_all(
                """
                SELECT DISTINCT conversation_id
                FROM messages
                WHERE creator_id = :creator_id
                AND created_at > :cutoff
                """,
                {"creator_id": self.creator_id, "cutoff": cutoff}
            )

        if not conversations:
            return 0.0

        completed = 0
        for conv in conversations:
            results = await self.collect(conv["conversation_id"])
            if results and results[0].value == 1.0:
                completed += 1

        return completed / len(conversations)
```

## Tests

```python
# backend/tests/metrics/test_task_completion.py
import pytest
from metrics.collectors.task_completion import (
    TaskCompletionCollector, TaskType, TaskOutcome
)

class TestTaskCompletion:

    @pytest.fixture
    def collector(self):
        return TaskCompletionCollector(creator_id="test")

    def test_detects_purchase_completion(self, collector):
        messages = [
            {"content": "Hola, quiero comprar el curso", "sender_type": "lead"},
            {"content": "Perfecto! Te cuento sobre el programa...", "sender_type": "creator"},
            {"content": "Gracias, ya hice la compra!", "sender_type": "lead"},
        ]

        task_type = collector._detect_task_type(messages)
        outcome = collector._detect_outcome(messages)

        assert outcome == TaskOutcome.COMPLETED

    def test_detects_abandonment(self, collector):
        messages = [
            {"content": "Cuánto cuesta?", "sender_type": "lead"},
            {"content": "El programa tiene un valor de 497€", "sender_type": "creator"},
            {"content": "No gracias, demasiado caro", "sender_type": "lead"},
        ]

        outcome = collector._detect_outcome(messages)
        assert outcome == TaskOutcome.ABANDONED

    def test_detects_escalation(self, collector):
        messages = [
            {"content": "No entiendo", "sender_type": "lead"},
            {"content": "Te explico...", "sender_type": "creator"},
            {"content": "Quiero hablar con una persona real", "sender_type": "lead"},
        ]

        outcome = collector._detect_outcome(messages)
        assert outcome == TaskOutcome.ESCALATED
```

## Commit

```bash
git add -A
git commit -m "feat(metrics): Task Completion Rate collector

- Detects task type (purchase, info, booking, support)
- Detects outcome (completed, abandoned, escalated, pending)
- Pattern matching for ES/EN
- Aggregate rate calculation
- Tests included"
```

---

# SPEC-M02: CSAT Post-Conversación
```yaml
id: SPEC-M02
priority: P1
time: 3 hours
type: metric
category: UX
paper_ref: "Customer Satisfaction in Conversational AI (2024)"
```

## Descripción
Sistema de feedback post-conversación con rating 1-5 y análisis de sentimiento.

## Implementación

```python
# backend/metrics/collectors/csat.py
"""
CSAT (Customer Satisfaction) Collector
Post-conversation satisfaction measurement
"""
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum
import logging

from ..base import MetricsCollector, MetricResult, MetricCategory

logger = logging.getLogger(__name__)

class CSATRating(Enum):
    VERY_DISSATISFIED = 1
    DISSATISFIED = 2
    NEUTRAL = 3
    SATISFIED = 4
    VERY_SATISFIED = 5

class CSATCollector(MetricsCollector):
    """Collects CSAT scores via multiple methods."""

    def __init__(self, creator_id: str):
        super().__init__(creator_id)

        # Sentiment patterns for implicit CSAT
        self.positive_patterns = [
            r'(genial|perfecto|increíble|excelente|gracias|👍|🔥|❤️|😊)',
            r'(great|perfect|amazing|excellent|thanks|awesome)',
            r'(me.*encanta|muy.*útil|super.*bien)',
        ]

        self.negative_patterns = [
            r'(horrible|terrible|pésimo|mal|👎|😡|😤)',
            r'(awful|terrible|bad|useless|waste)',
            r'(no.*sirve|no.*funciona|pérdida.*tiempo)',
        ]

    async def collect_explicit(
        self,
        conversation_id: str,
        rating: int,
        feedback: Optional[str] = None
    ) -> MetricResult:
        """Record explicit CSAT rating (1-5)."""

        # Validate rating
        rating = max(1, min(5, rating))

        result = MetricResult(
            name="csat_explicit",
            value=rating / 5.0,  # Normalize to 0-1
            category=MetricCategory.UX,
            metadata={
                "conversation_id": conversation_id,
                "raw_rating": rating,
                "feedback": feedback,
                "method": "explicit",
            }
        )

        self.add_result(result)

        # Store in DB
        await self._store_rating(conversation_id, rating, feedback)

        return result

    async def collect_implicit(self, conversation_id: str) -> MetricResult:
        """Infer CSAT from conversation sentiment."""
        from database import get_db
        import re

        async with get_db() as db:
            messages = await db.fetch_all(
                """
                SELECT content, sender_type
                FROM messages
                WHERE conversation_id = :conv_id
                AND sender_type = 'lead'
                ORDER BY created_at DESC
                LIMIT 10
                """,
                {"conv_id": conversation_id}
            )

        if not messages:
            return MetricResult(
                name="csat_implicit",
                value=0.6,  # Neutral default
                category=MetricCategory.UX,
                metadata={"conversation_id": conversation_id, "method": "implicit"}
            )

        # Analyze sentiment
        combined = " ".join(m["content"] or "" for m in messages).lower()

        positive_count = sum(
            1 for patterns in self.positive_patterns
            for p in [patterns] if re.search(p, combined, re.IGNORECASE)
        )

        negative_count = sum(
            1 for patterns in self.negative_patterns
            for p in [patterns] if re.search(p, combined, re.IGNORECASE)
        )

        # Calculate score
        if positive_count + negative_count == 0:
            score = 0.6  # Neutral
        else:
            score = (positive_count / (positive_count + negative_count))
            score = 0.3 + (score * 0.6)  # Scale to 0.3-0.9 range

        result = MetricResult(
            name="csat_implicit",
            value=score,
            category=MetricCategory.UX,
            metadata={
                "conversation_id": conversation_id,
                "positive_signals": positive_count,
                "negative_signals": negative_count,
                "method": "implicit",
            }
        )

        self.add_result(result)
        return result

    async def _store_rating(
        self,
        conversation_id: str,
        rating: int,
        feedback: Optional[str]
    ):
        """Store CSAT rating in database."""
        from database import get_db

        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO csat_ratings
                (conversation_id, creator_id, rating, feedback, created_at)
                VALUES (:conv_id, :creator_id, :rating, :feedback, :created_at)
                ON CONFLICT (conversation_id) DO UPDATE
                SET rating = :rating, feedback = :feedback
                """,
                {
                    "conv_id": conversation_id,
                    "creator_id": self.creator_id,
                    "rating": rating,
                    "feedback": feedback,
                    "created_at": datetime.utcnow()
                }
            )

    async def get_average_csat(self, days: int = 30) -> Dict[str, float]:
        """Get average CSAT for period."""
        from database import get_db
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)

        async with get_db() as db:
            result = await db.fetch_one(
                """
                SELECT
                    AVG(rating) as avg_rating,
                    COUNT(*) as count
                FROM csat_ratings
                WHERE creator_id = :creator_id
                AND created_at > :cutoff
                """,
                {"creator_id": self.creator_id, "cutoff": cutoff}
            )

        return {
            "average": result["avg_rating"] or 0,
            "count": result["count"] or 0,
            "normalized": (result["avg_rating"] or 0) / 5.0
        }


def generate_csat_prompt() -> str:
    """Generate message to ask for CSAT."""
    return """
¿Cómo calificarías tu experiencia?

⭐ 1 - Muy insatisfecho
⭐⭐ 2 - Insatisfecho
⭐⭐⭐ 3 - Neutral
⭐⭐⭐⭐ 4 - Satisfecho
⭐⭐⭐⭐⭐ 5 - Muy satisfecho

(Responde con un número del 1 al 5)
"""
```

## DB Migration

```sql
-- migrations/add_csat_ratings.sql
CREATE TABLE IF NOT EXISTS csat_ratings (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(255) UNIQUE NOT NULL,
    creator_id VARCHAR(255) NOT NULL,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    feedback TEXT,
    created_at TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (creator_id) REFERENCES creators(id)
);

CREATE INDEX idx_csat_creator ON csat_ratings(creator_id);
CREATE INDEX idx_csat_created ON csat_ratings(created_at);
```

## Commit

```bash
git add -A
git commit -m "feat(metrics): CSAT collector with explicit + implicit scoring

- Explicit: 1-5 rating with optional feedback
- Implicit: sentiment analysis from conversation
- DB storage for ratings
- Average CSAT calculation
- ES/EN patterns"
```

---

# SPEC-M03: Abandonment Rate
```yaml
id: SPEC-M03
priority: P1
time: 2 hours
type: metric
category: UX
```

## Implementación

```python
# backend/metrics/collectors/abandonment.py
"""
Abandonment Rate Collector
Measures: % of conversations abandoned before resolution
"""
from typing import List, Dict
from datetime import datetime, timedelta
import logging

from ..base import MetricsCollector, MetricResult, MetricCategory

logger = logging.getLogger(__name__)

class AbandonmentCollector(MetricsCollector):
    """Tracks conversation abandonment."""

    def __init__(self, creator_id: str):
        super().__init__(creator_id)
        self.abandonment_threshold_minutes = 30  # No response for 30 min = abandoned
        self.min_messages_for_completion = 4     # Less than 4 messages = likely abandoned

    async def collect(self, conversation_id: str) -> List[MetricResult]:
        """Analyze if conversation was abandoned."""
        from database import get_db

        async with get_db() as db:
            messages = await db.fetch_all(
                """
                SELECT sender_type, created_at
                FROM messages
                WHERE conversation_id = :conv_id
                ORDER BY created_at ASC
                """,
                {"conv_id": conversation_id}
            )

        if not messages:
            return []

        # Check abandonment signals
        is_abandoned, reason = self._check_abandonment(messages)

        result = MetricResult(
            name="abandonment_rate",
            value=1.0 if is_abandoned else 0.0,
            category=MetricCategory.UX,
            metadata={
                "conversation_id": conversation_id,
                "abandoned": is_abandoned,
                "reason": reason,
                "message_count": len(messages),
                "last_sender": messages[-1]["sender_type"] if messages else None,
            }
        )

        self.add_result(result)
        return [result]

    def _check_abandonment(self, messages: List[Dict]) -> tuple[bool, str]:
        """Determine if conversation was abandoned and why."""

        if len(messages) < self.min_messages_for_completion:
            # Check if last message was from bot (user didn't respond)
            if messages[-1]["sender_type"] == "creator":
                return True, "user_no_response_short"
            return False, "too_few_messages"

        # Check time gap at end
        last_msg = messages[-1]
        second_last = messages[-2] if len(messages) > 1 else None

        if second_last:
            gap = (last_msg["created_at"] - second_last["created_at"]).total_seconds() / 60

            # If bot responded and user never came back
            if last_msg["sender_type"] == "creator":
                time_since_last = (datetime.utcnow() - last_msg["created_at"]).total_seconds() / 60
                if time_since_last > self.abandonment_threshold_minutes:
                    return True, "user_no_response_timeout"

        # Check if conversation ended abruptly (user's last message)
        if messages[-1]["sender_type"] == "lead":
            time_since = (datetime.utcnow() - messages[-1]["created_at"]).total_seconds() / 60
            if time_since > self.abandonment_threshold_minutes * 2:
                return True, "conversation_stalled"

        return False, "active"

    async def get_abandonment_rate(self, days: int = 30) -> Dict[str, float]:
        """Get overall abandonment rate."""
        from database import get_db

        cutoff = datetime.utcnow() - timedelta(days=days)

        async with get_db() as db:
            conversations = await db.fetch_all(
                """
                SELECT DISTINCT conversation_id
                FROM messages
                WHERE creator_id = :creator_id
                AND created_at > :cutoff
                """,
                {"creator_id": self.creator_id, "cutoff": cutoff}
            )

        if not conversations:
            return {"rate": 0, "total": 0, "abandoned": 0}

        abandoned_count = 0
        reasons = {}

        for conv in conversations:
            results = await self.collect(conv["conversation_id"])
            if results and results[0].value == 1.0:
                abandoned_count += 1
                reason = results[0].metadata.get("reason", "unknown")
                reasons[reason] = reasons.get(reason, 0) + 1

        return {
            "rate": abandoned_count / len(conversations),
            "total": len(conversations),
            "abandoned": abandoned_count,
            "reasons": reasons,
        }
```

## Commit

```bash
git add -A
git commit -m "feat(metrics): Abandonment Rate collector

- Timeout-based detection (30 min threshold)
- Reason tracking (no_response, timeout, stalled)
- Aggregate rate calculation"
```

---

# SPEC-M04: Response Latency Tracker
```yaml
id: SPEC-M04
priority: P1
time: 1 hour
type: metric
category: UX
```

## Implementación

```python
# backend/metrics/collectors/latency.py
"""
Response Latency Collector
Measures: Time between user message and bot response
"""
from typing import List, Dict
from datetime import datetime
import statistics
import logging

from ..base import MetricsCollector, MetricResult, MetricCategory

logger = logging.getLogger(__name__)

class LatencyCollector(MetricsCollector):
    """Tracks response latency."""

    def __init__(self, creator_id: str):
        super().__init__(creator_id)
        self.latency_threshold_seconds = 5.0  # Target: < 5 seconds

    async def collect(self, conversation_id: str) -> List[MetricResult]:
        """Calculate latencies for conversation."""
        from database import get_db

        async with get_db() as db:
            messages = await db.fetch_all(
                """
                SELECT sender_type, created_at
                FROM messages
                WHERE conversation_id = :conv_id
                ORDER BY created_at ASC
                """,
                {"conv_id": conversation_id}
            )

        if len(messages) < 2:
            return []

        latencies = []

        for i in range(1, len(messages)):
            prev = messages[i-1]
            curr = messages[i]

            # Only measure: user message → bot response
            if prev["sender_type"] == "lead" and curr["sender_type"] == "creator":
                latency = (curr["created_at"] - prev["created_at"]).total_seconds()
                latencies.append(latency)

        if not latencies:
            return []

        avg_latency = statistics.mean(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0]

        result = MetricResult(
            name="response_latency",
            value=avg_latency,
            category=MetricCategory.UX,
            metadata={
                "conversation_id": conversation_id,
                "avg_seconds": avg_latency,
                "p95_seconds": p95_latency,
                "min_seconds": min(latencies),
                "max_seconds": max(latencies),
                "measurements": len(latencies),
                "within_threshold": avg_latency < self.latency_threshold_seconds,
            }
        )

        self.add_result(result)
        return [result]

    async def get_latency_stats(self, days: int = 7) -> Dict[str, float]:
        """Get latency statistics."""
        results = self.get_results()

        if not results:
            return {"avg": 0, "p95": 0, "within_threshold_pct": 0}

        latencies = [r.value for r in results]
        within = [r for r in results if r.metadata.get("within_threshold", False)]

        return {
            "avg": statistics.mean(latencies),
            "p95": sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0],
            "within_threshold_pct": len(within) / len(results) * 100,
        }
```

## Commit

```bash
git add -A
git commit -m "feat(metrics): Response Latency tracker

- Measures user→bot response time
- Avg, P95, min, max calculations
- Threshold tracking (< 5s target)"
```

---

# SPEC-M05: Knowledge Retention Score
```yaml
id: SPEC-M05
priority: P1
time: 2 hours
type: metric
category: Cognitive
paper_ref: "Memory in Conversational Agents (2024)"
```

## Descripción
Mide si el bot recuerda información de turnos anteriores.

## Implementación

```python
# backend/metrics/collectors/knowledge_retention.py
"""
Knowledge Retention Score
Measures: Bot's ability to remember facts from earlier in conversation
"""
from typing import List, Dict, Optional
from datetime import datetime
import re
import logging

from ..base import MetricsCollector, MetricResult, MetricCategory

logger = logging.getLogger(__name__)

class KnowledgeRetentionCollector(MetricsCollector):
    """Measures knowledge retention across conversation."""

    def __init__(self, creator_id: str):
        super().__init__(creator_id)

        # Facts to track
        self.fact_patterns = {
            "name": r'(?:me llamo|soy|my name is)\s+([A-Z][a-záéíóú]+)',
            "location": r'(?:vivo en|soy de|from|live in)\s+([A-Z][a-záéíóú\s]+)',
            "interest": r'(?:me interesa|quiero|interested in)\s+(.+?)(?:\.|$)',
            "budget": r'(?:presupuesto|budget).*?(\d+[€$]|\d+\s*euros?)',
            "goal": r'(?:objetivo|quiero lograr|goal|want to)\s+(.+?)(?:\.|$)',
        }

    async def collect(self, conversation_id: str) -> List[MetricResult]:
        """Analyze knowledge retention in conversation."""
        from database import get_db

        async with get_db() as db:
            messages = await db.fetch_all(
                """
                SELECT content, sender_type, created_at
                FROM messages
                WHERE conversation_id = :conv_id
                ORDER BY created_at ASC
                """,
                {"conv_id": conversation_id}
            )

        if len(messages) < 4:
            return []

        # Extract facts from user messages
        user_facts = self._extract_facts(messages)

        if not user_facts:
            return []

        # Check if bot referenced these facts later
        retention_score = self._calculate_retention(messages, user_facts)

        result = MetricResult(
            name="knowledge_retention",
            value=retention_score,
            category=MetricCategory.COGNITIVE,
            metadata={
                "conversation_id": conversation_id,
                "facts_extracted": len(user_facts),
                "facts_retained": int(retention_score * len(user_facts)),
                "fact_types": list(user_facts.keys()),
            }
        )

        self.add_result(result)
        return [result]

    def _extract_facts(self, messages: List[Dict]) -> Dict[str, str]:
        """Extract facts from user messages."""
        facts = {}

        for msg in messages:
            if msg["sender_type"] != "lead":
                continue

            content = msg["content"] or ""

            for fact_type, pattern in self.fact_patterns.items():
                match = re.search(pattern, content, re.IGNORECASE)
                if match and fact_type not in facts:
                    facts[fact_type] = match.group(1).strip()

        return facts

    def _calculate_retention(
        self,
        messages: List[Dict],
        facts: Dict[str, str]
    ) -> float:
        """Calculate how many facts were retained/referenced."""
        if not facts:
            return 1.0  # No facts to retain

        # Get bot messages from later in conversation (last 50%)
        mid_point = len(messages) // 2
        later_bot_messages = [
            m["content"] or ""
            for m in messages[mid_point:]
            if m["sender_type"] == "creator"
        ]

        combined_bot = " ".join(later_bot_messages).lower()

        retained = 0
        for fact_type, fact_value in facts.items():
            # Check if fact or variant appears in later bot messages
            if fact_value.lower() in combined_bot:
                retained += 1
            # Also check for pronouns/references
            elif fact_type == "name" and any(
                ref in combined_bot
                for ref in ["tu nombre", "your name", fact_value.split()[0].lower()]
            ):
                retained += 1

        return retained / len(facts)
```

## Commit

```bash
git add -A
git commit -m "feat(metrics): Knowledge Retention Score

- Extracts facts from user messages (name, location, interest, budget, goal)
- Measures if bot references facts later
- Score 0-1 based on retention %"
```

---

# SPEC-M06: LLM-as-Judge Consistency
```yaml
id: SPEC-M06
priority: P2
time: 4 hours
type: metric
category: Quality
paper_ref: "LLM-as-a-Judge (2024)"
```

## Implementación

```python
# backend/metrics/collectors/consistency_judge.py
"""
LLM-as-Judge Consistency Checker
Uses LLM to detect contradictions in bot responses
"""
from typing import List, Dict
import logging

from ..base import MetricsCollector, MetricResult, MetricCategory

logger = logging.getLogger(__name__)

JUDGE_PROMPT = """
Analiza las siguientes respuestas del bot en una conversación y detecta contradicciones.

RESPUESTAS DEL BOT:
{responses}

PREGUNTA: ¿El bot se contradijo en algún momento?

Responde en JSON:
{{
    "has_contradiction": true/false,
    "contradictions": ["descripción de contradicción 1", ...],
    "consistency_score": 0.0-1.0
}}

Solo JSON, sin explicación adicional.
"""

class ConsistencyJudgeCollector(MetricsCollector):
    """Uses LLM to judge response consistency."""

    def __init__(self, creator_id: str):
        super().__init__(creator_id)

    async def collect(self, conversation_id: str) -> List[MetricResult]:
        """Analyze consistency using LLM judge."""
        from database import get_db
        from services.llm_service import get_llm
        import json

        async with get_db() as db:
            messages = await db.fetch_all(
                """
                SELECT content, sender_type
                FROM messages
                WHERE conversation_id = :conv_id
                AND sender_type = 'creator'
                ORDER BY created_at ASC
                """,
                {"conv_id": conversation_id}
            )

        if len(messages) < 3:
            return []

        # Format bot responses
        responses = "\n".join([
            f"{i+1}. {m['content']}"
            for i, m in enumerate(messages)
        ])

        # Call LLM judge
        llm = get_llm()
        prompt = JUDGE_PROMPT.format(responses=responses)

        try:
            response = await llm.complete([
                {"role": "system", "content": "Eres un evaluador de consistencia. Responde solo en JSON."},
                {"role": "user", "content": prompt}
            ], max_tokens=500, temperature=0)

            # Parse response
            judgment = json.loads(response)
            score = judgment.get("consistency_score", 0.5)

        except Exception as e:
            logger.error(f"LLM judge failed: {e}")
            score = 0.5  # Neutral on failure
            judgment = {"error": str(e)}

        result = MetricResult(
            name="consistency_llm_judge",
            value=score,
            category=MetricCategory.QUALITY,
            metadata={
                "conversation_id": conversation_id,
                "judgment": judgment,
                "response_count": len(messages),
            }
        )

        self.add_result(result)
        return [result]
```

## Commit

```bash
git add -A
git commit -m "feat(metrics): LLM-as-Judge consistency checker

- Uses LLM to detect contradictions
- Returns consistency score 0-1
- Logs specific contradictions found"
```

---

# SPEC-M12: Metrics Dashboard
```yaml
id: SPEC-M12
priority: P1
time: 4 hours
type: infrastructure
```

## Implementación

```python
# backend/metrics/dashboard.py
"""
Metrics Dashboard - Unified view of all metrics
"""
from typing import Dict, List, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

from .collectors.task_completion import TaskCompletionCollector
from .collectors.csat import CSATCollector
from .collectors.abandonment import AbandonmentCollector
from .collectors.latency import LatencyCollector
from .collectors.knowledge_retention import KnowledgeRetentionCollector

logger = logging.getLogger(__name__)

@dataclass
class DashboardMetrics:
    """All metrics for dashboard display."""
    task_completion_rate: float
    csat_average: float
    abandonment_rate: float
    avg_latency_seconds: float
    knowledge_retention: float
    total_conversations: int
    period_days: int
    generated_at: datetime

class MetricsDashboard:
    """Unified metrics dashboard."""

    def __init__(self, creator_id: str):
        self.creator_id = creator_id
        self.collectors = {
            "task_completion": TaskCompletionCollector(creator_id),
            "csat": CSATCollector(creator_id),
            "abandonment": AbandonmentCollector(creator_id),
            "latency": LatencyCollector(creator_id),
            "retention": KnowledgeRetentionCollector(creator_id),
        }

    async def get_dashboard(self, days: int = 30) -> DashboardMetrics:
        """Get all metrics for dashboard."""

        # Task completion
        task_rate = await self.collectors["task_completion"].get_aggregate_rate(days)

        # CSAT
        csat = await self.collectors["csat"].get_average_csat(days)

        # Abandonment
        abandonment = await self.collectors["abandonment"].get_abandonment_rate(days)

        # Latency
        latency = await self.collectors["latency"].get_latency_stats(days)

        # Knowledge retention (sample from recent conversations)
        retention_results = self.collectors["retention"].get_results()
        retention_avg = (
            sum(r.value for r in retention_results) / len(retention_results)
            if retention_results else 0.5
        )

        return DashboardMetrics(
            task_completion_rate=task_rate,
            csat_average=csat.get("normalized", 0),
            abandonment_rate=abandonment.get("rate", 0),
            avg_latency_seconds=latency.get("avg", 0),
            knowledge_retention=retention_avg,
            total_conversations=abandonment.get("total", 0),
            period_days=days,
            generated_at=datetime.utcnow(),
        )

    def to_dict(self, metrics: DashboardMetrics) -> Dict[str, Any]:
        """Convert to dict for API response."""
        return {
            "metrics": {
                "task_completion_rate": {
                    "value": metrics.task_completion_rate,
                    "label": "Task Completion",
                    "format": "percent",
                    "target": 0.7,
                },
                "csat": {
                    "value": metrics.csat_average,
                    "label": "Customer Satisfaction",
                    "format": "percent",
                    "target": 0.8,
                },
                "abandonment_rate": {
                    "value": metrics.abandonment_rate,
                    "label": "Abandonment Rate",
                    "format": "percent",
                    "target": 0.2,  # Lower is better
                    "inverse": True,
                },
                "latency": {
                    "value": metrics.avg_latency_seconds,
                    "label": "Avg Response Time",
                    "format": "seconds",
                    "target": 3.0,
                    "inverse": True,
                },
                "knowledge_retention": {
                    "value": metrics.knowledge_retention,
                    "label": "Knowledge Retention",
                    "format": "percent",
                    "target": 0.8,
                },
            },
            "summary": {
                "total_conversations": metrics.total_conversations,
                "period_days": metrics.period_days,
                "generated_at": metrics.generated_at.isoformat(),
            },
            "health_score": self._calculate_health_score(metrics),
        }

    def _calculate_health_score(self, m: DashboardMetrics) -> float:
        """Calculate overall health score 0-100."""
        weights = {
            "task_completion": 0.25,
            "csat": 0.25,
            "abandonment": 0.20,  # Inverted
            "latency": 0.15,      # Inverted
            "retention": 0.15,
        }

        # Normalize latency (5s = 0, 0s = 1)
        latency_score = max(0, 1 - (m.avg_latency_seconds / 5))

        # Invert abandonment (0 = good = 1, 1 = bad = 0)
        abandonment_score = 1 - m.abandonment_rate

        score = (
            m.task_completion_rate * weights["task_completion"] +
            m.csat_average * weights["csat"] +
            abandonment_score * weights["abandonment"] +
            latency_score * weights["latency"] +
            m.knowledge_retention * weights["retention"]
        )

        return round(score * 100, 1)
```

## API Endpoint

```python
# backend/api/routers/metrics.py
from fastapi import APIRouter, Depends
from metrics.dashboard import MetricsDashboard

router = APIRouter(prefix="/metrics", tags=["metrics"])

@router.get("/dashboard/{creator_id}")
async def get_metrics_dashboard(creator_id: str, days: int = 30):
    """Get metrics dashboard for creator."""
    dashboard = MetricsDashboard(creator_id)
    metrics = await dashboard.get_dashboard(days)
    return dashboard.to_dict(metrics)

@router.get("/health/{creator_id}")
async def get_health_score(creator_id: str):
    """Get quick health score."""
    dashboard = MetricsDashboard(creator_id)
    metrics = await dashboard.get_dashboard(7)
    return {
        "health_score": dashboard._calculate_health_score(metrics),
        "status": "healthy" if dashboard._calculate_health_score(metrics) > 70 else "needs_attention"
    }
```

## Commit

```bash
git add -A
git commit -m "feat(metrics): Unified Metrics Dashboard

- Aggregates all collectors
- Health score calculation
- API endpoints for dashboard
- Target tracking per metric"
```

---

# EJECUCIÓN FINAL

```bash
# Run all tests
pytest backend/tests/metrics/ -v

# Final commit
git add -A
git commit -m "feat(metrics): Complete Academic Metrics System

Implemented metrics from 2024-2026 research papers:

P1 (Core UX):
- Task Completion Rate
- CSAT (explicit + implicit)
- Abandonment Rate
- Response Latency

P1 (Cognitive):
- Knowledge Retention Score

P2 (Quality):
- LLM-as-Judge Consistency

Infrastructure:
- Unified Dashboard
- Health Score
- API endpoints

Total: 7 collectors, 1 dashboard, ~15 tests"

git push origin main
```

---

# 🎯 MASTER PROMPT PARA CLAUDE CODE

```
Lee CLONNECT_METRICS_ROADMAP.md y ejecuta specs M00-M12 sin preguntar.

MODO BYPASS:
- Ejecuta en orden
- Si falla, continúa
- Genera METRICS_REPORT.md al final

Prioridad: M00 → M01-M04 (P1 UX) → M05 (P1 Cognitive) → M12 (Dashboard) → resto

EMPIEZA AHORA.
```

---

**Tiempo total: ~38 horas**
**Specs: 14 (M00-M13)**
**Prioridad: P1 primero (UX + Dashboard)**
