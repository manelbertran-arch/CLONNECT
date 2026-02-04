"""
MessageSplitter - Splits long responses into multiple messages like Stefan.

Based on analysis: Stefan's messages are SHORT (median 22 chars, mean 37.6).
When the bot generates longer responses, we split them to match this pattern.

Part of PHASE-5: Multi-Message.
"""

import re
from dataclasses import dataclass
from typing import List, Optional

from services.timing_service import TimingService, get_timing_service


@dataclass
class SplitConfig:
    """Configuration for message splitting."""

    # Thresholds
    min_length_to_split: int = 80  # Don't split messages shorter than this
    target_length: int = 40  # Ideal message length (Stefan's mean ~37)
    max_length: int = 120  # Maximum length per message

    # Delays between parts (seconds)
    inter_message_delay_min: float = 1.0  # Fast typing for continuation
    inter_message_delay_max: float = 3.0  # Max delay between parts

    # Splitting behavior
    max_parts: int = 4  # Maximum number of messages to split into
    preserve_emoji_with_text: bool = True  # Keep trailing emoji with text


@dataclass
class MessagePart:
    """A single part of a split message."""

    text: str
    delay_before: float  # Seconds to wait before sending this part
    is_first: bool = False
    is_last: bool = False


class MessageSplitter:
    """Service that splits long messages into multiple shorter ones."""

    def __init__(
        self,
        config: SplitConfig = None,
        timing_service: TimingService = None,
    ):
        self.config = config or SplitConfig()
        self.timing = timing_service or get_timing_service()

    def should_split(self, message: str) -> bool:
        """
        Determine if a message should be split.

        Args:
            message: The message to evaluate.

        Returns:
            True if message should be split.
        """
        if len(message) < self.config.min_length_to_split:
            return False

        # Check for natural split points
        split_indicators = [
            "\n\n",  # Paragraph break
            ". ",  # Sentence end
            "! ",  # Exclamation end
            "? ",  # Question end
        ]

        has_split_point = any(ind in message for ind in split_indicators)
        return has_split_point

    def split(self, message: str, incoming_message: str = "") -> List[MessagePart]:
        """
        Split a message into multiple parts.

        Args:
            message: The message to split.
            incoming_message: The user's message (for timing calculation).

        Returns:
            List of MessagePart objects.
        """
        if not self.should_split(message):
            # Single message with normal delay
            delay = self.timing.get_delay_for_response(message, incoming_message)
            return [
                MessagePart(
                    text=message.strip(),
                    delay_before=delay,
                    is_first=True,
                    is_last=True,
                )
            ]

        # Split the message
        parts = self._split_into_parts(message)

        # Limit to max_parts
        if len(parts) > self.config.max_parts:
            parts = self._merge_to_max_parts(parts)

        # Create MessagePart objects with delays
        result = []
        for i, text in enumerate(parts):
            is_first = i == 0
            is_last = i == len(parts) - 1

            if is_first:
                # First message: full delay (reading + thinking + typing)
                delay = self.timing.get_delay_for_response(text, incoming_message)
            else:
                # Subsequent messages: short typing delay
                delay = self._calculate_inter_delay(text)

            result.append(
                MessagePart(
                    text=text.strip(),
                    delay_before=delay,
                    is_first=is_first,
                    is_last=is_last,
                )
            )

        return result

    def _split_into_parts(self, message: str) -> List[str]:
        """
        Split message at natural boundaries.

        Priority:
        1. Paragraph breaks (\\n\\n)
        2. Line breaks (\\n)
        3. Sentence endings (. ! ?)
        """
        # First try paragraph splits
        if "\n\n" in message:
            parts = [p.strip() for p in message.split("\n\n") if p.strip()]
            if len(parts) > 1:
                return self._refine_parts(parts)

        # Then try line breaks
        if "\n" in message:
            parts = [p.strip() for p in message.split("\n") if p.strip()]
            if len(parts) > 1:
                return self._refine_parts(parts)

        # Finally, split by sentences
        return self._split_by_sentences(message)

    def _split_by_sentences(self, message: str) -> List[str]:
        """Split by sentence boundaries, keeping emoji with text."""
        # Pattern to split at sentence endings, keeping the punctuation
        # Handles: . ! ? and combinations like !! ??
        pattern = r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ])"

        sentences = re.split(pattern, message)

        if len(sentences) <= 1:
            # No clean sentence breaks, try splitting at long commas
            return self._split_at_commas(message)

        return self._refine_parts(sentences)

    def _split_at_commas(self, message: str) -> List[str]:
        """
        Last resort: split at commas for very long messages.
        Only if segments would be reasonably sized.
        """
        if "," not in message:
            # Can't split, return as is
            return [message]

        parts = message.split(",")

        # Reconstruct into reasonable chunks
        result = []
        current = ""

        for part in parts:
            part = part.strip()
            if not part:
                continue

            test = f"{current}, {part}" if current else part

            if len(test) <= self.config.max_length:
                current = test
            else:
                if current:
                    result.append(current)
                current = part

        if current:
            result.append(current)

        return result if len(result) > 1 else [message]

    def _refine_parts(self, parts: List[str]) -> List[str]:
        """
        Refine parts to optimal sizes.

        - Merge very short parts with neighbors
        - Split parts that are still too long
        """
        result = []

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # If part is too short, try to merge with previous
            if len(part) < 15 and result:
                # Merge with previous if combined is reasonable
                combined = f"{result[-1]} {part}"
                if len(combined) <= self.config.max_length:
                    result[-1] = combined
                    continue

            # If part is too long, split it further
            if len(part) > self.config.max_length:
                sub_parts = self._split_by_sentences(part)
                result.extend(sub_parts)
            else:
                result.append(part)

        return result

    def _merge_to_max_parts(self, parts: List[str]) -> List[str]:
        """Merge parts to stay within max_parts limit."""
        while len(parts) > self.config.max_parts:
            # Find two shortest consecutive parts to merge
            min_combined_len = float("inf")
            min_idx = 0

            for i in range(len(parts) - 1):
                combined = len(parts[i]) + len(parts[i + 1])
                if combined < min_combined_len:
                    min_combined_len = combined
                    min_idx = i

            # Merge the two parts
            merged = f"{parts[min_idx]} {parts[min_idx + 1]}"
            parts = parts[:min_idx] + [merged] + parts[min_idx + 2 :]

        return parts

    def _calculate_inter_delay(self, text: str) -> float:
        """
        Calculate delay between message parts.

        Shorter than normal delay since it's a continuation.
        """
        import random

        # Base: typing time for this part
        typing_time = len(text) / 50.0  # ~50 chars/sec

        # Add small random variation
        variation = random.uniform(0.8, 1.2)
        delay = typing_time * variation

        # Clamp to configured range
        delay = max(self.config.inter_message_delay_min, delay)
        delay = min(self.config.inter_message_delay_max, delay)

        return round(delay, 1)

    def get_total_delay(self, parts: List[MessagePart]) -> float:
        """Get total delay for all parts."""
        return sum(p.delay_before for p in parts)

    def format_for_debug(self, parts: List[MessagePart]) -> str:
        """Format parts for debugging/logging."""
        lines = [f"Split into {len(parts)} parts:"]
        for i, part in enumerate(parts):
            lines.append(
                f"  [{i+1}] ({part.delay_before:.1f}s) "
                f'"{part.text[:50]}{"..." if len(part.text) > 50 else ""}"'
            )
        return "\n".join(lines)


# Singleton
_splitter: Optional[MessageSplitter] = None


def get_message_splitter() -> MessageSplitter:
    """Get global MessageSplitter instance."""
    global _splitter
    if _splitter is None:
        _splitter = MessageSplitter()
    return _splitter
