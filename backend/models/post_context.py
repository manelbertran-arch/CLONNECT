"""PostContext model for temporal state from Instagram posts.

Stores analyzed context from recent posts including:
- Active promotions/launches
- Recent topics discussed
- Availability hints
- Generated instructions for bot

Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class PostContext:
    """Context extracted from creator's recent Instagram posts.

    This context is cached and used to make bot responses more relevant
    to what the creator is currently promoting or discussing.
    """

    # Required fields
    creator_id: str
    context_instructions: str
    expires_at: datetime

    # Promotion fields
    active_promotion: Optional[str] = None
    promotion_deadline: Optional[datetime] = None
    promotion_urgency: Optional[str] = None

    # Topics and products
    recent_topics: List[str] = field(default_factory=list)
    recent_products: List[str] = field(default_factory=list)

    # Availability
    availability_hint: Optional[str] = None

    # Metadata
    posts_analyzed: int = 0
    analyzed_at: Optional[datetime] = None
    source_posts: List[str] = field(default_factory=list)

    def is_expired(self) -> bool:
        """Check if this context has expired and needs refresh."""
        now = datetime.now(timezone.utc)
        # Handle naive datetime
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return now > expires

    def has_active_promotion(self) -> bool:
        """Check if there's an active promotion."""
        return self.active_promotion is not None and len(self.active_promotion) > 0

    def to_prompt_addition(self) -> str:
        """Generate text to add to bot prompt with current context.

        Returns:
            String to append to system prompt with relevant context.
        """
        sections = []

        # Add promotion section
        if self.has_active_promotion():
            promo_text = f"PROMOCIÓN ACTIVA: {self.active_promotion}"
            if self.promotion_urgency:
                promo_text += f" (Urgencia: {self.promotion_urgency})"
            sections.append(promo_text)

        # Add availability hint
        if self.availability_hint:
            sections.append(f"DISPONIBILIDAD: {self.availability_hint}")

        # Add recent topics
        if self.recent_topics:
            topics_str = ", ".join(self.recent_topics[:5])
            sections.append(f"TEMAS RECIENTES: {topics_str}")

        # Add recent products
        if self.recent_products:
            products_str = ", ".join(self.recent_products[:3])
            sections.append(f"PRODUCTOS MENCIONADOS: {products_str}")

        # Always add instructions
        sections.append(f"INSTRUCCIONES: {self.context_instructions}")

        return "\n".join(sections)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "creator_id": self.creator_id,
            "active_promotion": self.active_promotion,
            "promotion_deadline": (
                self.promotion_deadline.isoformat() if self.promotion_deadline else None
            ),
            "promotion_urgency": self.promotion_urgency,
            "recent_topics": self.recent_topics,
            "recent_products": self.recent_products,
            "availability_hint": self.availability_hint,
            "context_instructions": self.context_instructions,
            "posts_analyzed": self.posts_analyzed,
            "analyzed_at": (
                self.analyzed_at.isoformat() if self.analyzed_at else None
            ),
            "expires_at": self.expires_at.isoformat(),
            "source_posts": self.source_posts,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PostContext":
        """Create PostContext from dictionary."""
        return cls(
            creator_id=data["creator_id"],
            active_promotion=data.get("active_promotion"),
            promotion_deadline=(
                datetime.fromisoformat(data["promotion_deadline"])
                if data.get("promotion_deadline")
                else None
            ),
            promotion_urgency=data.get("promotion_urgency"),
            recent_topics=data.get("recent_topics", []),
            recent_products=data.get("recent_products", []),
            availability_hint=data.get("availability_hint"),
            context_instructions=data["context_instructions"],
            posts_analyzed=data.get("posts_analyzed", 0),
            analyzed_at=(
                datetime.fromisoformat(data["analyzed_at"])
                if data.get("analyzed_at")
                else None
            ),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            source_posts=data.get("source_posts", []),
        )
