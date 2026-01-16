// Fluent Emoji Component - Using Microsoft's Fluent Emoji
// SVGs from fluentui-emoji package

import cameraEmoji from 'fluentui-emoji/icons/modern/camera.svg';
import speechBalloonEmoji from 'fluentui-emoji/icons/modern/speech-balloon.svg';
import redHeartEmoji from 'fluentui-emoji/icons/modern/red-heart.svg';
import clapperBoardEmoji from 'fluentui-emoji/icons/modern/clapper-board.svg';
import framedPictureEmoji from 'fluentui-emoji/icons/modern/framed-picture.svg';
import paperclipEmoji from 'fluentui-emoji/icons/modern/paperclip.svg';
import linkEmoji from 'fluentui-emoji/icons/modern/link.svg';

// Map of emoji types to their SVG imports
const emojiMap: Record<string, string> = {
  story_mention: cameraEmoji,
  story_reply: speechBalloonEmoji,
  reaction: redHeartEmoji,
  video: clapperBoardEmoji,
  image: framedPictureEmoji,
  file: paperclipEmoji,
  link: linkEmoji,
  // Fallbacks
  camera: cameraEmoji,
  speech: speechBalloonEmoji,
  heart: redHeartEmoji,
};

interface FluentEmojiProps {
  type: string;
  size?: number;
  className?: string;
}

export function FluentEmoji({ type, size = 20, className = '' }: FluentEmojiProps) {
  const emojiSrc = emojiMap[type] || emojiMap.file;

  return (
    <img
      src={emojiSrc}
      alt={type}
      width={size}
      height={size}
      className={`inline-block ${className}`}
      style={{ verticalAlign: 'middle' }}
    />
  );
}

// Export the emoji map for direct access if needed
export { emojiMap };
