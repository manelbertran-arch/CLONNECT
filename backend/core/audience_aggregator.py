"""
AudienceAggregator - Aggregates audience data for "Tu Audiencia" page

SPRINT4-T4.1: Aggregation logic for 7 tabs
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from collections import Counter

from sqlalchemy.orm import Session

from api.schemas.audiencia import (
    TopicsResponse,
    TopicAggregation,
    ObjectionsResponse,
    ObjectionAggregation,
    CompetitionResponse,
    CompetitionMention,
    TrendsResponse,
    TrendItem,
    ContentRequestsResponse,
    ContentRequest,
    PerceptionResponse,
    PerceptionItem,
)

logger = logging.getLogger(__name__)

# Objection suggestions mapping
OBJECTION_SUGGESTIONS = {
    "precio": "Ofrece plan de pagos o destaca el ROI",
    "caro": "Ofrece plan de pagos o destaca el ROI",
    "dinero": "Ofrece plan de pagos o destaca el ROI",
    "tiempo": "Destaca el formato flexible y autoguiado",
    "ahora no": "Programa un seguimiento para más adelante",
    "pensarlo": "Envía caso de éxito o testimonios",
    "duda": "Ofrece una llamada de clarificación",
    "no sé": "Ofrece una llamada de clarificación",
    "funciona": "Comparte resultados de otros clientes",
    "garantía": "Explica tu política de devolución",
}

# Purchase-related objection keywords
PURCHASE_OBJECTION_KEYWORDS = [
    "precio", "caro", "dinero", "pagar", "cuesta", "coste",
    "ahora no", "después", "más adelante", "pensarlo",
    "duda", "no sé si", "funciona", "garantía", "gratis",
]


class AudienceAggregator:
    """
    Aggregates audience data for the "Tu Audiencia" page.
    Uses optimized queries over follower_memories and messages.
    """

    def __init__(self, creator_id: str, db: Session):
        """
        Initialize AudienceAggregator.

        Args:
            creator_id: Creator identifier
            db: SQLAlchemy session
        """
        self.creator_id = creator_id
        self.db = db

    def get_topics(self, limit: int = 10) -> TopicsResponse:
        """
        Tab 1: De qué hablan
        Aggregates interests from follower_memories.
        """
        try:
            from api.models import FollowerMemoryDB

            # Get all followers with interests
            query = self.db.query(FollowerMemoryDB).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.interests.isnot(None),
            )

            followers = query.all()
            total_conversations = len(followers)

            # Aggregate interests
            interest_data: Dict[str, Dict] = {}

            for follower in followers:
                if not follower.interests:
                    continue

                for interest in follower.interests:
                    if interest not in interest_data:
                        interest_data[interest] = {
                            "count": 0,
                            "users": [],
                            "quotes": [],
                        }

                    interest_data[interest]["count"] += 1
                    if follower.username and follower.username not in interest_data[interest]["users"]:
                        interest_data[interest]["users"].append(follower.username)

                    # Extract quote from last messages
                    if follower.last_messages:
                        for msg in follower.last_messages[-3:]:
                            if isinstance(msg, dict) and msg.get("role") == "user":
                                content = msg.get("content", "")
                                if interest.lower() in content.lower() and len(interest_data[interest]["quotes"]) < 5:
                                    interest_data[interest]["quotes"].append(content[:150])
                                    break

            # Sort by count and limit
            sorted_topics = sorted(interest_data.items(), key=lambda x: x[1]["count"], reverse=True)[:limit]

            # Calculate percentages and build response
            total_mentions = sum(data["count"] for _, data in sorted_topics)
            topics = []

            for topic, data in sorted_topics:
                percentage = (data["count"] / total_mentions * 100) if total_mentions > 0 else 0
                topics.append(TopicAggregation(
                    topic=topic,
                    count=data["count"],
                    percentage=round(percentage, 1),
                    quotes=data["quotes"][:5],
                    users=data["users"][:10],
                ))

            return TopicsResponse(
                total_conversations=total_conversations,
                topics=topics,
            )

        except Exception as e:
            logger.error(f"Error getting topics: {e}")
            return TopicsResponse(total_conversations=0, topics=[])

    def get_passions(self, limit: int = 10) -> TopicsResponse:
        """
        Tab 2: Qué les apasiona
        Topics with high engagement (long messages, deep questions).
        """
        try:
            from api.models import FollowerMemoryDB

            # Get followers with high engagement
            query = self.db.query(FollowerMemoryDB).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.total_messages >= 5,  # High engagement threshold
            )

            followers = query.all()
            total_conversations = len(followers)

            # Aggregate topics from long messages
            passion_data: Dict[str, Dict] = {}

            for follower in followers:
                if not follower.last_messages:
                    continue

                # Look for long, passionate messages
                for msg in follower.last_messages:
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        content = msg.get("content", "")
                        # Consider messages > 100 chars as "passionate"
                        if len(content) > 100:
                            # Extract key topics (interests that appear in long messages)
                            if follower.interests:
                                for interest in follower.interests:
                                    if interest.lower() in content.lower():
                                        if interest not in passion_data:
                                            passion_data[interest] = {
                                                "count": 0,
                                                "users": [],
                                                "quotes": [],
                                            }
                                        passion_data[interest]["count"] += 1
                                        if follower.username and follower.username not in passion_data[interest]["users"]:
                                            passion_data[interest]["users"].append(follower.username)
                                        if len(passion_data[interest]["quotes"]) < 5:
                                            passion_data[interest]["quotes"].append(content[:200])

            # Sort and build response
            sorted_passions = sorted(passion_data.items(), key=lambda x: x[1]["count"], reverse=True)[:limit]
            total_mentions = sum(data["count"] for _, data in sorted_passions)

            topics = []
            for topic, data in sorted_passions:
                percentage = (data["count"] / total_mentions * 100) if total_mentions > 0 else 0
                topics.append(TopicAggregation(
                    topic=topic,
                    count=data["count"],
                    percentage=round(percentage, 1),
                    quotes=data["quotes"][:5],
                    users=data["users"][:10],
                ))

            return TopicsResponse(
                total_conversations=total_conversations,
                topics=topics,
            )

        except Exception as e:
            logger.error(f"Error getting passions: {e}")
            return TopicsResponse(total_conversations=0, topics=[])

    def get_frustrations(self, limit: int = 10) -> ObjectionsResponse:
        """
        Tab 3: Qué les frustra
        Aggregates objections raised by followers.
        """
        try:
            from api.models import FollowerMemoryDB

            query = self.db.query(FollowerMemoryDB).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.objections_raised.isnot(None),
            )

            followers = query.all()
            total_with_objections = len([f for f in followers if f.objections_raised])

            # Aggregate objections
            objection_data: Dict[str, Dict] = {}

            for follower in followers:
                if not follower.objections_raised:
                    continue

                for objection in follower.objections_raised:
                    objection_lower = objection.lower()
                    if objection_lower not in objection_data:
                        objection_data[objection_lower] = {
                            "count": 0,
                            "quotes": [],
                            "resolved": 0,
                            "pending": 0,
                        }

                    objection_data[objection_lower]["count"] += 1

                    # Check if resolved (customer status)
                    if follower.is_customer:
                        objection_data[objection_lower]["resolved"] += 1
                    else:
                        objection_data[objection_lower]["pending"] += 1

                    # Get quote from messages
                    if follower.last_messages and len(objection_data[objection_lower]["quotes"]) < 5:
                        for msg in follower.last_messages:
                            if isinstance(msg, dict) and msg.get("role") == "user":
                                content = msg.get("content", "")
                                if objection_lower in content.lower():
                                    objection_data[objection_lower]["quotes"].append(content[:150])
                                    break

            # Sort and build response
            sorted_objections = sorted(objection_data.items(), key=lambda x: x[1]["count"], reverse=True)[:limit]
            total_mentions = sum(data["count"] for _, data in sorted_objections)

            objections = []
            for obj, data in sorted_objections:
                percentage = (data["count"] / total_mentions * 100) if total_mentions > 0 else 0

                # Get suggestion
                suggestion = ""
                for keyword, sugg in OBJECTION_SUGGESTIONS.items():
                    if keyword in obj:
                        suggestion = sugg
                        break

                objections.append(ObjectionAggregation(
                    objection=obj.capitalize(),
                    count=data["count"],
                    percentage=round(percentage, 1),
                    quotes=data["quotes"][:5],
                    suggestion=suggestion,
                    resolved_count=data["resolved"],
                    pending_count=data["pending"],
                ))

            return ObjectionsResponse(
                total_with_objections=total_with_objections,
                objections=objections,
            )

        except Exception as e:
            logger.error(f"Error getting frustrations: {e}")
            return ObjectionsResponse(total_with_objections=0, objections=[])

    def get_competition(self, limit: int = 10) -> CompetitionResponse:
        """
        Tab 4: Qué competencia mencionan
        Finds @mentions in messages that aren't the creator.
        """
        try:
            from api.models import FollowerMemoryDB

            query = self.db.query(FollowerMemoryDB).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.last_messages.isnot(None),
            )

            followers = query.all()

            # Find @mentions
            mention_pattern = re.compile(r'@([a-zA-Z0-9_]+)')
            competitor_data: Dict[str, Dict] = {}

            for follower in followers:
                if not follower.last_messages:
                    continue

                for msg in follower.last_messages:
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        content = msg.get("content", "")
                        mentions = mention_pattern.findall(content)

                        for mention in mentions:
                            mention_lower = mention.lower()
                            # Skip if it's the creator
                            if mention_lower == self.creator_id.lower():
                                continue

                            if mention_lower not in competitor_data:
                                competitor_data[mention_lower] = {
                                    "count": 0,
                                    "context": [],
                                    "sentiment_scores": [],
                                }

                            competitor_data[mention_lower]["count"] += 1
                            if len(competitor_data[mention_lower]["context"]) < 5:
                                competitor_data[mention_lower]["context"].append(content[:150])

                            # Simple sentiment analysis
                            content_lower = content.lower()
                            if any(word in content_lower for word in ["mejor", "genial", "bueno", "recomiendo"]):
                                competitor_data[mention_lower]["sentiment_scores"].append(1)
                            elif any(word in content_lower for word in ["malo", "peor", "no me gustó", "caro"]):
                                competitor_data[mention_lower]["sentiment_scores"].append(-1)
                            else:
                                competitor_data[mention_lower]["sentiment_scores"].append(0)

            # Sort and build response
            sorted_competitors = sorted(competitor_data.items(), key=lambda x: x[1]["count"], reverse=True)[:limit]
            total_mentions = sum(data["count"] for _, data in sorted_competitors)

            competitors = []
            for comp, data in sorted_competitors:
                # Calculate overall sentiment
                scores = data["sentiment_scores"]
                avg_sentiment = sum(scores) / len(scores) if scores else 0

                if avg_sentiment > 0.3:
                    sentiment = "positivo"
                    suggestion = f"@{comp} tiene buena reputación. Diferénciate con tu propuesta única."
                elif avg_sentiment < -0.3:
                    sentiment = "negativo"
                    suggestion = f"Hay insatisfacción con @{comp}. Destaca cómo tu oferta es diferente."
                else:
                    sentiment = "neutral"
                    suggestion = f"Investiga qué ofrece @{comp} y cómo puedes diferenciarte."

                competitors.append(CompetitionMention(
                    competitor=f"@{comp}",
                    count=data["count"],
                    sentiment=sentiment,
                    context=data["context"][:5],
                    suggestion=suggestion,
                ))

            return CompetitionResponse(
                total_mentions=total_mentions,
                competitors=competitors,
            )

        except Exception as e:
            logger.error(f"Error getting competition: {e}")
            return CompetitionResponse(total_mentions=0, competitors=[])

    def get_trends(self, limit: int = 10) -> TrendsResponse:
        """
        Tab 5: Qué tendencias emergen
        Compares term frequency this week vs last week.
        """
        try:
            from api.models import FollowerMemoryDB

            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)
            two_weeks_ago = now - timedelta(days=14)

            # This week's data
            this_week_query = self.db.query(FollowerMemoryDB).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.last_contact >= week_ago.isoformat(),
            )

            # Last week's data
            last_week_query = self.db.query(FollowerMemoryDB).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.last_contact >= two_weeks_ago.isoformat(),
                FollowerMemoryDB.last_contact < week_ago.isoformat(),
            )

            this_week_terms: Counter = Counter()
            last_week_terms: Counter = Counter()
            term_quotes: Dict[str, List[str]] = {}

            # Process this week
            for follower in this_week_query.all():
                if follower.products_discussed:
                    for product in follower.products_discussed:
                        this_week_terms[product] += 1
                        if product not in term_quotes:
                            term_quotes[product] = []
                if follower.interests:
                    for interest in follower.interests:
                        this_week_terms[interest] += 1
                        if interest not in term_quotes:
                            term_quotes[interest] = []

                # Get quotes
                if follower.last_messages:
                    for msg in follower.last_messages[-3:]:
                        if isinstance(msg, dict) and msg.get("role") == "user":
                            content = msg.get("content", "")
                            for term in this_week_terms:
                                if term.lower() in content.lower() and len(term_quotes.get(term, [])) < 3:
                                    if term not in term_quotes:
                                        term_quotes[term] = []
                                    term_quotes[term].append(content[:100])

            # Process last week
            for follower in last_week_query.all():
                if follower.products_discussed:
                    for product in follower.products_discussed:
                        last_week_terms[product] += 1
                if follower.interests:
                    for interest in follower.interests:
                        last_week_terms[interest] += 1

            # Calculate growth and build response
            trends = []
            for term, count_this_week in this_week_terms.most_common(limit * 2):
                count_last_week = last_week_terms.get(term, 0)

                if count_last_week == 0:
                    growth = 100.0  # New term
                else:
                    growth = ((count_this_week - count_last_week) / count_last_week) * 100

                if growth > 0:  # Only show growing trends
                    trends.append(TrendItem(
                        term=term,
                        count_this_week=count_this_week,
                        count_last_week=count_last_week,
                        growth_percentage=round(growth, 1),
                        quotes=term_quotes.get(term, [])[:3],
                    ))

            # Sort by growth and limit
            trends.sort(key=lambda x: x.growth_percentage, reverse=True)
            trends = trends[:limit]

            return TrendsResponse(
                period="week",
                trends=trends,
            )

        except Exception as e:
            logger.error(f"Error getting trends: {e}")
            return TrendsResponse(trends=[])

    def get_content_requests(self, limit: int = 10) -> ContentRequestsResponse:
        """
        Tab 6: Qué contenido piden
        Groups questions by topic.
        """
        try:
            from api.models import FollowerMemoryDB

            query = self.db.query(FollowerMemoryDB).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.last_messages.isnot(None),
            )

            followers = query.all()

            # Find questions and group by topic
            topic_questions: Dict[str, List[str]] = {}
            question_pattern = re.compile(r'[¿?]')

            for follower in followers:
                if not follower.last_messages:
                    continue

                follower_interests = follower.interests or []

                for msg in follower.last_messages:
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        content = msg.get("content", "")

                        # Check if it's a question
                        if question_pattern.search(content) or content.strip().endswith("?"):
                            # Categorize by interest
                            categorized = False
                            for interest in follower_interests:
                                if interest.lower() in content.lower():
                                    if interest not in topic_questions:
                                        topic_questions[interest] = []
                                    if len(topic_questions[interest]) < 10:
                                        topic_questions[interest].append(content[:200])
                                    categorized = True
                                    break

                            # If not categorized, put in "General"
                            if not categorized and len(content) > 20:
                                if "General" not in topic_questions:
                                    topic_questions["General"] = []
                                if len(topic_questions["General"]) < 10:
                                    topic_questions["General"].append(content[:200])

            # Build response
            requests = []
            total_requests = 0

            for topic, questions in sorted(topic_questions.items(), key=lambda x: len(x[1]), reverse=True)[:limit]:
                count = len(questions)
                total_requests += count

                requests.append(ContentRequest(
                    topic=topic,
                    count=count,
                    questions=questions[:5],
                    suggestion=f"Crea contenido respondiendo las preguntas sobre {topic}",
                ))

            return ContentRequestsResponse(
                total_requests=total_requests,
                requests=requests,
            )

        except Exception as e:
            logger.error(f"Error getting content requests: {e}")
            return ContentRequestsResponse(total_requests=0, requests=[])

    def get_purchase_objections(self, limit: int = 10) -> ObjectionsResponse:
        """
        Tab 7: Por qué no compran
        Only purchase-related objections.
        """
        try:
            from api.models import FollowerMemoryDB

            query = self.db.query(FollowerMemoryDB).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.objections_raised.isnot(None),
                FollowerMemoryDB.is_customer == False,
            )

            followers = query.all()
            total_with_objections = 0

            # Filter purchase-related objections
            objection_data: Dict[str, Dict] = {}

            for follower in followers:
                if not follower.objections_raised:
                    continue

                for objection in follower.objections_raised:
                    objection_lower = objection.lower()

                    # Check if purchase-related
                    is_purchase_related = any(keyword in objection_lower for keyword in PURCHASE_OBJECTION_KEYWORDS)

                    if is_purchase_related:
                        total_with_objections += 1

                        if objection_lower not in objection_data:
                            objection_data[objection_lower] = {
                                "count": 0,
                                "quotes": [],
                            }

                        objection_data[objection_lower]["count"] += 1

                        # Get quote
                        if follower.last_messages and len(objection_data[objection_lower]["quotes"]) < 5:
                            for msg in follower.last_messages:
                                if isinstance(msg, dict) and msg.get("role") == "user":
                                    content = msg.get("content", "")
                                    if objection_lower in content.lower():
                                        objection_data[objection_lower]["quotes"].append(content[:150])
                                        break

            # Sort and build response
            sorted_objections = sorted(objection_data.items(), key=lambda x: x[1]["count"], reverse=True)[:limit]
            total_mentions = sum(data["count"] for _, data in sorted_objections)

            objections = []
            for obj, data in sorted_objections:
                percentage = (data["count"] / total_mentions * 100) if total_mentions > 0 else 0

                # Get suggestion
                suggestion = "Ofrece más información o resuelve la duda"
                for keyword, sugg in OBJECTION_SUGGESTIONS.items():
                    if keyword in obj:
                        suggestion = sugg
                        break

                objections.append(ObjectionAggregation(
                    objection=obj.capitalize(),
                    count=data["count"],
                    percentage=round(percentage, 1),
                    quotes=data["quotes"][:5],
                    suggestion=suggestion,
                    resolved_count=0,
                    pending_count=data["count"],
                ))

            return ObjectionsResponse(
                total_with_objections=total_with_objections,
                objections=objections,
            )

        except Exception as e:
            logger.error(f"Error getting purchase objections: {e}")
            return ObjectionsResponse(total_with_objections=0, objections=[])

    def get_perception(self) -> PerceptionResponse:
        """
        Tab 8: Qué piensan de ti
        Analyzes sentiment about the creator.
        """
        try:
            from api.models import FollowerMemoryDB, Creator

            # Get creator name for searching
            creator = self.db.query(Creator).filter(
                Creator.name == self.creator_id
            ).first()

            creator_names = [self.creator_id.lower()]
            if creator:
                if creator.clone_name:
                    creator_names.append(creator.clone_name.lower())
                if creator.name:
                    creator_names.append(creator.name.lower())

            query = self.db.query(FollowerMemoryDB).filter(
                FollowerMemoryDB.creator_id == self.creator_id,
                FollowerMemoryDB.last_messages.isnot(None),
            )

            followers = query.all()
            total_analyzed = 0

            # Perception aspects
            aspects = {
                "expertise": {"positive": [], "negative": []},
                "precio": {"positive": [], "negative": []},
                "atencion": {"positive": [], "negative": []},
                "contenido": {"positive": [], "negative": []},
            }

            positive_words = ["genial", "increíble", "excelente", "gracias", "ayudó", "útil", "bueno", "mejor"]
            negative_words = ["malo", "caro", "no responde", "tardó", "decepcionado", "no funciona"]

            for follower in followers:
                if not follower.last_messages:
                    continue

                for msg in follower.last_messages:
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        content = msg.get("content", "")
                        content_lower = content.lower()

                        # Check if mentions creator
                        mentions_creator = any(name in content_lower for name in creator_names)
                        if not mentions_creator:
                            continue

                        total_analyzed += 1

                        # Analyze sentiment per aspect
                        is_positive = any(word in content_lower for word in positive_words)
                        is_negative = any(word in content_lower for word in negative_words)

                        # Categorize
                        if "experto" in content_lower or "sabe" in content_lower or "profesional" in content_lower:
                            if is_positive:
                                aspects["expertise"]["positive"].append(content[:150])
                            elif is_negative:
                                aspects["expertise"]["negative"].append(content[:150])

                        if "precio" in content_lower or "caro" in content_lower or "barato" in content_lower:
                            if is_positive or "barato" in content_lower:
                                aspects["precio"]["positive"].append(content[:150])
                            elif is_negative or "caro" in content_lower:
                                aspects["precio"]["negative"].append(content[:150])

                        if "responde" in content_lower or "atención" in content_lower or "rápido" in content_lower:
                            if is_positive:
                                aspects["atencion"]["positive"].append(content[:150])
                            elif is_negative:
                                aspects["atencion"]["negative"].append(content[:150])

                        if "contenido" in content_lower or "video" in content_lower or "curso" in content_lower:
                            if is_positive:
                                aspects["contenido"]["positive"].append(content[:150])
                            elif is_negative:
                                aspects["contenido"]["negative"].append(content[:150])

            # Build response
            perceptions = []
            for aspect, data in aspects.items():
                perceptions.append(PerceptionItem(
                    aspect=aspect,
                    positive_count=len(data["positive"]),
                    negative_count=len(data["negative"]),
                    quotes_positive=data["positive"][:5],
                    quotes_negative=data["negative"][:5],
                ))

            return PerceptionResponse(
                total_analyzed=total_analyzed,
                perceptions=perceptions,
            )

        except Exception as e:
            logger.error(f"Error getting perception: {e}")
            return PerceptionResponse(total_analyzed=0, perceptions=[])
