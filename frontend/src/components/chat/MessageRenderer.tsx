// Instagram-style Message Renderer
// Renders different message types with Instagram DM look

import { useState } from 'react';
import { ExternalLink, Play, Image as ImageIcon, Film, Mic, Share2 } from 'lucide-react';

// Emoticon to Emoji conversion map
const emoticonToEmoji: Record<string, string> = {
  ':)': '😊',
  ':-)': '😊',
  '(:': '😊',
  ':(': '😞',
  ':-(': '😞',
  ':D': '😄',
  ':-D': '😄',
  ';)': '😉',
  ';-)': '😉',
  ':P': '😛',
  ':-P': '😛',
  ':p': '😛',
  ':-p': '😛',
  '<3': '❤️',
  ':O': '😮',
  ':-O': '😮',
  ':o': '😮',
  ':-o': '😮',
  'XD': '😆',
  'xD': '😆',
  'xd': '😆',
  ":'(": '😢',
  ":*(": '😢',
  ':S': '😕',
  ':s': '😕',
  ':/': '😕',
  ':-/': '😕',
  ':\\': '😕',
  ':*': '😘',
  ':-*': '😘',
  'B)': '😎',
  '8)': '😎',
  '>:(': '😠',
  ':@': '😠',
  '^_^': '😊',
  '-_-': '😑',
  'o_o': '😳',
  'O_O': '😳',
  ':3': '😺',
  '</3': '💔',
  ':$': '😳',
  ':X': '🤐',
  ':x': '🤐',
};

/**
 * Convert text emoticons to emoji
 * Handles emoticons at word boundaries to avoid false matches
 */
function convertEmoticonsToEmoji(text: string): string {
  let result = text;

  // Sort by length (longest first) to match multi-char emoticons before shorter ones
  const sortedEmoticons = Object.entries(emoticonToEmoji)
    .sort((a, b) => b[0].length - a[0].length);

  for (const [emoticon, emoji] of sortedEmoticons) {
    // Escape special regex characters
    const escaped = emoticon.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    // Match emoticon with word boundaries or at start/end of string
    const regex = new RegExp(`(^|\\s|[^\\w])${escaped}($|\\s|[^\\w])`, 'g');
    result = result.replace(regex, (match, before, after) => `${before}${emoji}${after}`);
  }

  return result;
}

/**
 * Decode HTML entities like &#064; -> @, &#x2022; -> •
 */
function decodeHtmlEntities(text: string): string {
  const textarea = document.createElement('textarea');
  textarea.innerHTML = text;
  return textarea.value;
}

interface LinkPreview {
  url: string;
  title?: string;
  description?: string;
  image?: string;
  site_name?: string;
  platform?: string;
}

interface MessageMetadata {
  type?: string;
  url?: string;
  emoji?: string;
  thumbnail_url?: string;
  thumbnail_base64?: string;  // Screenshot base64 for link previews
  preview_url?: string;
  animated_gif_url?: string;
  width?: number;
  height?: number;
  render_as_sticker?: boolean;
  author_username?: string;
  permalink?: string;
  caption?: string;
  platform?: string;  // instagram, youtube, tiktok, web
  link_preview?: LinkPreview;  // Open Graph link preview data
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  metadata?: MessageMetadata;
}

interface MessageRendererProps {
  message: Message;
  isLastInGroup?: boolean;
}

// Violet gradient for outgoing messages (matches UI theme)
const IG_GRADIENT = 'bg-gradient-to-br from-violet-600 to-purple-600';
const IG_GRADIENT_STORY = 'bg-gradient-to-tr from-violet-500 via-purple-500 to-violet-600';

export function MessageRenderer({ message, isLastInGroup = true }: MessageRendererProps) {
  // In CRM context: assistant = Stefan/bot (outgoing/right), user = follower (incoming/left)
  const isOutgoing = message.role === 'assistant';
  const metadata = message.metadata || {};
  const msgType = metadata.type || 'text';

  // Determine which component to render based on type
  switch (msgType) {
    case 'story_mention':
    case 'story_reply':
    case 'story_reaction':
      return <StoryMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} />;

    case 'reaction':
      return <ReactionMessage message={message} isOutgoing={isOutgoing} />;

    case 'image':
    case 'gif':
    case 'sticker':
      return <MediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} type="image" />;

    case 'video':
      return <MediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} type="video" />;

    case 'audio':
      return <AudioMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} />;

    case 'share':
    case 'shared_post':
    case 'shared_reel':
    case 'shared_video':
    case 'link_preview':
      return <SharedPostMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} />;

    default:
      return <TextMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} />;
  }
}

// Text Message - Instagram style bubble
function TextMessage({ message, isOutgoing, isLastInGroup }: { message: Message; isOutgoing: boolean; isLastInGroup: boolean }) {
  const metadata = message.metadata || {};
  const linkPreview = metadata.link_preview;

  const bubbleClass = isOutgoing
    ? `${IG_GRADIENT} text-white`
    : 'bg-[#262626] text-white';

  const radiusClass = isOutgoing
    ? `rounded-2xl ${isLastInGroup ? 'rounded-br-md' : ''}`
    : `rounded-2xl ${isLastInGroup ? 'rounded-bl-md' : ''}`;

  // If there's a link preview, remove the URL from displayed text
  // This makes the message cleaner - the URL is shown in the preview card
  const rawContent = linkPreview
    ? message.content.replace(/https?:\/\/[^\s]+/g, '').trim()
    : message.content;

  // Convert text emoticons to emojis
  const displayContent = convertEmoticonsToEmoji(rawContent);

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[75%] ${bubbleClass} ${radiusClass} overflow-hidden`}>
        {displayContent && (
          <div className="px-4 py-2.5">
            <p className="text-[15px] leading-relaxed whitespace-pre-wrap break-words">
              {displayContent}
            </p>
          </div>
        )}
        {linkPreview && <LinkPreviewCard preview={linkPreview} />}
        <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="px-4 pb-2" />
      </div>
    </div>
  );
}

// Link Preview Card - Shows Open Graph metadata
function LinkPreviewCard({ preview }: { preview: LinkPreview }) {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);

  // Decode HTML entities in image URL (e.g., &amp; -> &)
  const imageUrl = preview.image ? decodeHtmlEntities(preview.image) : undefined;

  // Extract domain from URL
  const domain = (() => {
    try {
      return new URL(preview.url).hostname.replace('www.', '');
    } catch {
      return preview.site_name || 'Link';
    }
  })();

  return (
    <a
      href={preview.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block border-t border-white/10 bg-black/20 hover:bg-black/30 transition-colors"
    >
      {imageUrl && !imageError && (
        <div className="relative">
          {!imageLoaded && (
            <div className="w-full h-32 bg-[#1a1a1a] flex items-center justify-center">
              <ExternalLink className="w-6 h-6 text-gray-600 animate-pulse" />
            </div>
          )}
          <img
            src={imageUrl}
            alt={preview.title ? decodeHtmlEntities(preview.title) : 'Preview'}
            className={`w-full h-32 object-cover ${imageLoaded ? '' : 'hidden'}`}
            onLoad={() => setImageLoaded(true)}
            onError={() => setImageError(true)}
          />
        </div>
      )}
      <div className="p-3">
        {preview.title && (
          <p className="text-sm font-medium text-white line-clamp-2">{decodeHtmlEntities(preview.title)}</p>
        )}
        {preview.description && (
          <p className="text-xs text-gray-400 mt-1 line-clamp-2">{decodeHtmlEntities(preview.description)}</p>
        )}
        <p className="text-xs text-violet-400 mt-2 flex items-center gap-1">
          {domain}
          <ExternalLink className="w-3 h-3" />
        </p>
      </div>
    </a>
  );
}

// Story Message - With gradient border and thumbnail preview
function StoryMessage({ message, isOutgoing, isLastInGroup }: { message: Message; isOutgoing: boolean; isLastInGroup: boolean }) {
  const [mediaLoaded, setMediaLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const [isVideo, setIsVideo] = useState(false);
  const metadata = message.metadata || {};
  const hasLink = !!metadata.url;
  const storyType = metadata.type === 'story_reply' ? 'Respuesta a story'
    : metadata.type === 'story_mention' ? 'Mención en story'
    : 'Reacción a story';

  // Prefer saved base64 thumbnail (never expires), fallback to CDN URL (may expire)
  const thumbnailSrc = metadata.thumbnail_base64 || metadata.thumbnail_url || metadata.url;
  const hasSavedThumbnail = !!metadata.thumbnail_base64;

  // Handle image load error - try as video
  const handleImageError = () => {
    if (!isVideo) {
      setIsVideo(true); // Try loading as video instead
    } else {
      setImageError(true); // Video also failed
    }
  };

  const bubbleClass = isOutgoing
    ? `${IG_GRADIENT} text-white`
    : 'bg-[#262626] text-white';

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[75%] ${bubbleClass} rounded-2xl ${isLastInGroup ? (isOutgoing ? 'rounded-br-md' : 'rounded-bl-md') : ''} overflow-hidden`}>
        {/* Story Preview with gradient border and thumbnail */}
        {hasLink && (
          <a href={metadata.url} target="_blank" rel="noopener noreferrer" className="block cursor-pointer hover:opacity-90 transition-opacity">
            <div className="p-2">
              <div className={`${IG_GRADIENT_STORY} p-[2px] rounded-xl`}>
                <div className="bg-black rounded-xl overflow-hidden">
                  {/* Show thumbnail/video if available and not errored */}
                  {thumbnailSrc && !imageError && (
                    <div className="relative">
                      {!mediaLoaded && (
                        <div className="w-full h-32 bg-[#1a1a1a] flex items-center justify-center">
                          <Film className="w-8 h-8 text-gray-600 animate-pulse" />
                        </div>
                      )}
                      {!isVideo ? (
                        <img
                          src={thumbnailSrc}
                          alt={storyType}
                          className={`w-full max-h-48 object-cover ${mediaLoaded ? '' : 'hidden'}`}
                          onLoad={() => setMediaLoaded(true)}
                          onError={handleImageError}
                        />
                      ) : (
                        <video
                          src={thumbnailSrc}
                          className={`w-full max-h-48 object-cover ${mediaLoaded ? '' : 'hidden'}`}
                          onLoadedData={() => setMediaLoaded(true)}
                          onError={() => setImageError(true)}
                          muted
                          playsInline
                          autoPlay
                          loop
                        />
                      )}
                      {/* Overlay with story type */}
                      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-3">
                        <p className="text-white text-sm font-medium">{storyType}</p>
                        <p className="text-gray-300 text-xs flex items-center gap-1">
                          Toca para ver <ExternalLink className="w-3 h-3" />
                        </p>
                      </div>
                    </div>
                  )}
                  {/* Fallback if image fails or no thumbnail - Story expired */}
                  {(imageError || !thumbnailSrc) && (
                    <div className="p-3 flex items-center gap-3">
                      <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center">
                        <Film className="w-6 h-6 text-white" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-white text-sm font-medium">{storyType}</p>
                        <p className="text-gray-400 text-xs flex items-center gap-1">
                          {hasSavedThumbnail ? 'Toca para ver' : 'Story expirada'}
                          <ExternalLink className="w-3 h-3" />
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </a>
        )}

        {/* Message text if any */}
        {message.content && !message.content.includes('story') && (
          <div className="px-4 py-2">
            <p className="text-[15px]">{convertEmoticonsToEmoji(message.content)}</p>
          </div>
        )}

        {/* Emoji reaction */}
        {metadata.emoji && (
          <div className="px-4 py-2 text-2xl">
            {metadata.emoji}
          </div>
        )}

        {!hasLink && (
          <div className="px-4 py-2.5">
            <p className="text-[15px] text-gray-300">{storyType}</p>
            <p className="text-xs text-gray-500 mt-1">Story no disponible</p>
          </div>
        )}

        <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="px-4 pb-2" />
      </div>
    </div>
  );
}

// Reaction Message - Small emoji bubble
function ReactionMessage({ message, isOutgoing }: { message: Message; isOutgoing: boolean }) {
  const emoji = message.metadata?.emoji || '❤️';

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className="bg-[#262626] rounded-full px-4 py-2 flex items-center gap-2">
        <span className="text-2xl">{emoji}</span>
        {message.content && !message.content.includes('Reacción') && (
          <span className="text-white text-sm">{message.content}</span>
        )}
      </div>
    </div>
  );
}

// Media Message - Image/GIF/Sticker
function MediaMessage({ message, isOutgoing, isLastInGroup, type }: { message: Message; isOutgoing: boolean; isLastInGroup: boolean; type: 'image' | 'video' }) {
  const [loaded, setLoaded] = useState(false);
  const metadata = message.metadata || {};
  const imageUrl = metadata.url || metadata.preview_url || metadata.animated_gif_url || metadata.thumbnail_url;
  const isSticker = metadata.render_as_sticker;

  if (!imageUrl) {
    return <TextMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} />;
  }

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[70%] ${isSticker ? '' : 'rounded-2xl overflow-hidden'}`}>
        <a href={imageUrl} target="_blank" rel="noopener noreferrer" className="block relative cursor-pointer hover:opacity-90 transition-opacity">
          {!loaded && (
            <div className="w-48 h-48 bg-[#262626] rounded-2xl flex items-center justify-center">
              <ImageIcon className="w-8 h-8 text-gray-500 animate-pulse" />
            </div>
          )}
          <img
            src={imageUrl}
            alt={type}
            className={`max-w-full ${isSticker ? 'max-h-32' : 'max-h-64 rounded-2xl'} ${loaded ? '' : 'hidden'}`}
            onLoad={() => setLoaded(true)}
            onError={() => setLoaded(true)}
          />
          {type === 'video' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-12 h-12 rounded-full bg-black/60 flex items-center justify-center">
                <Play className="w-6 h-6 text-white ml-1" />
              </div>
            </div>
          )}
        </a>
        <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="mt-1" />
      </div>
    </div>
  );
}

// Audio Message
function AudioMessage({ message, isOutgoing, isLastInGroup }: { message: Message; isOutgoing: boolean; isLastInGroup: boolean }) {
  const bubbleClass = isOutgoing ? IG_GRADIENT : 'bg-[#262626]';

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`${bubbleClass} rounded-2xl ${isLastInGroup ? (isOutgoing ? 'rounded-br-md' : 'rounded-bl-md') : ''} px-4 py-3`}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
            <Mic className="w-5 h-5 text-white" />
          </div>
          <div className="flex-1">
            <div className="h-1 bg-white/30 rounded-full w-32">
              <div className="h-1 bg-white rounded-full w-1/3"></div>
            </div>
            <p className="text-xs text-white/70 mt-1">0:12</p>
          </div>
        </div>
        <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} />
      </div>
    </div>
  );
}

// Shared Post/Reel Message
function SharedPostMessage({ message, isOutgoing, isLastInGroup }: { message: Message; isOutgoing: boolean; isLastInGroup: boolean }) {
  const [mediaLoaded, setMediaLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const [tryVideo, setTryVideo] = useState(false);
  const metadata = message.metadata || {};

  // Support both URL and base64 thumbnails
  // For "share" type, the URL might be in metadata.url directly
  const thumbnailBase64 = metadata.thumbnail_base64;
  const thumbnailUrl = metadata.thumbnail_url || metadata.preview_url || metadata.url;
  const thumbnailSrc = thumbnailBase64
    ? `data:image/jpeg;base64,${thumbnailBase64}`
    : thumbnailUrl;

  const permalink = metadata.permalink || metadata.url;
  const authorUsername = metadata.author_username;
  const isReel = metadata.type === 'shared_reel';
  const isVideo = metadata.type === 'shared_video' || isReel || tryVideo;

  // Platform-specific label
  const isShareType = metadata.type === 'share';
  const platformLabel = metadata.platform === 'youtube' ? 'YouTube'
    : metadata.platform === 'tiktok' ? 'TikTok'
    : isShareType ? 'Contenido compartido'
    : 'Instagram';

  // Handle image error - try as video for CDN URLs
  const handleImageError = () => {
    if (!tryVideo && thumbnailUrl?.includes('lookaside.fbsbx.com')) {
      setTryVideo(true); // CDN might serve video, try loading as video
    } else {
      setImageError(true);
    }
  };

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[75%] bg-[#262626] rounded-2xl ${isLastInGroup ? (isOutgoing ? 'rounded-br-md' : 'rounded-bl-md') : ''} overflow-hidden`}>
        {/* Post Preview */}
        <a href={permalink} target="_blank" rel="noopener noreferrer" className="block cursor-pointer hover:opacity-90 transition-opacity">
          {thumbnailSrc && !imageError ? (
            <div className="relative">
              {!mediaLoaded && (
                <div className="w-full h-48 bg-[#363636] flex items-center justify-center">
                  <Share2 className="w-8 h-8 text-gray-500 animate-pulse" />
                </div>
              )}
              {!tryVideo ? (
                <img
                  src={thumbnailSrc}
                  alt="Post preview"
                  className={`w-full max-h-64 object-cover ${mediaLoaded ? '' : 'hidden'}`}
                  onLoad={() => setMediaLoaded(true)}
                  onError={handleImageError}
                />
              ) : (
                <video
                  src={thumbnailSrc}
                  className={`w-full max-h-64 object-cover ${mediaLoaded ? '' : 'hidden'}`}
                  onLoadedData={() => setMediaLoaded(true)}
                  onError={() => setImageError(true)}
                  muted
                  playsInline
                  autoPlay
                  loop
                />
              )}
              {isVideo && mediaLoaded && !tryVideo && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/20">
                  <div className="w-12 h-12 rounded-full bg-black/60 flex items-center justify-center">
                    <Play className="w-6 h-6 text-white ml-1" />
                  </div>
                </div>
              )}
              {isReel && !isVideo && (
                <div className="absolute top-2 right-2 bg-black/60 rounded px-2 py-1">
                  <Film className="w-4 h-4 text-white" />
                </div>
              )}
            </div>
          ) : (
            <div className="h-32 bg-[#363636] flex items-center justify-center">
              <Share2 className="w-8 h-8 text-gray-500" />
            </div>
          )}

          {/* Post Info */}
          <div className="p-3 border-t border-[#363636]">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full bg-gradient-to-br from-violet-600 to-purple-600"></div>
              <span className="text-white text-sm font-medium">
                {authorUsername || platformLabel}
              </span>
            </div>
            {metadata.caption && (
              <p className="text-gray-400 text-xs mt-2 line-clamp-2">{metadata.caption}</p>
            )}
            <p className="text-blue-400 text-xs mt-2 flex items-center gap-1">
              {isShareType ? 'Toca para ver' : `Ver en ${platformLabel}`} <ExternalLink className="w-3 h-3" />
            </p>
          </div>
        </a>

        <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="px-3 pb-2" />
      </div>
    </div>
  );
}

// Timestamp component
function Timestamp({ timestamp, isOutgoing, className = '' }: { timestamp?: string; isOutgoing: boolean; className?: string }) {
  if (!timestamp) return null;

  const time = new Date(timestamp).toLocaleTimeString('es', {
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <p className={`text-[10px] ${isOutgoing ? 'text-white/60' : 'text-gray-500'} text-right ${className}`}>
      {time}
    </p>
  );
}

export default MessageRenderer;
