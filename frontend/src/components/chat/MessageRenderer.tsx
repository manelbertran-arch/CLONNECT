// Instagram-style Message Renderer
// Renders different message types with Instagram DM look

import { useState, ReactNode } from 'react';
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
 * Decode HTML entities in text
 * Handles common entities like &#064; (@), &#x2022; (•), &amp; (&), etc.
 */
function decodeHtmlEntities(text: string): string {
  const textarea = document.createElement('textarea');
  textarea.innerHTML = text;
  return textarea.value;
}

/**
 * URL regex pattern - matches URLs with or without protocol
 * Supports: https://..., http://..., www..., domain.com/path
 */
const URL_REGEX = /(?:https?:\/\/)?(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_+.~#?&/=]*)/gi;

/**
 * Parse text and convert URLs to clickable links
 * Returns an array of React nodes (strings and anchor elements)
 */
function renderTextWithLinks(text: string, isOutgoing: boolean): ReactNode[] {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let keyIndex = 0;

  // Reset regex state
  URL_REGEX.lastIndex = 0;

  while ((match = URL_REGEX.exec(text)) !== null) {
    // Add text before the URL
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    // Get the matched URL
    let url = match[0];

    // Add protocol if missing
    const href = url.startsWith('http') ? url : `https://${url}`;

    // Style: blue for incoming, light blue/white for outgoing (on gradient)
    const linkClass = isOutgoing
      ? 'text-blue-200 underline hover:text-white'
      : 'text-blue-400 underline hover:text-blue-300';

    // Add the clickable link
    parts.push(
      <a
        key={`link-${keyIndex++}`}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={linkClass}
        onClick={(e) => e.stopPropagation()}
      >
        {url}
      </a>
    );

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text after last URL
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length > 0 ? parts : [text];
}

interface LinkPreview {
  url: string;
  title?: string;
  description?: string;
  image?: string;
  site_name?: string;
  platform?: string;
}

interface CarouselItem {
  url: string;
  type?: 'image' | 'video';
  thumbnail_url?: string;
}

interface MessageMetadata {
  type?: string;
  url?: string;
  link?: string;  // Instagram permalink (for stories: link to story, url is CDN video)
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
  carousel_items?: CarouselItem[];  // For carousel/album messages
  items?: Array<{ url?: string; type?: string }>;  // Alternative carousel items
  duration?: number;  // Audio/video duration in seconds
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
  const isOutgoing = message.role === 'assistant';
  const metadata = message.metadata || {};

  // Determine message type: prefer metadata.type, fallback to content-based detection
  // for old messages that lack metadata (e.g. from reconciliation)
  let msgType = metadata.type || 'text';
  if (msgType === 'text') {
    const c = (message.content || '').toLowerCase();
    if (c === '[media/attachment]' || c === '[media]' || c === 'sent an attachment'
      || c === 'shared content' || c === 'shared a post' || c === 'shared a reel') {
      msgType = 'share';
    } else if (c === 'sent a photo') {
      msgType = 'image';
    } else if (c === 'sent a video') {
      msgType = 'video';
    } else if (c === 'sent a voice message') {
      msgType = 'audio';
    } else if (c === 'sent a gif') {
      msgType = 'gif';
    } else if (c === 'sent a sticker') {
      msgType = 'sticker';
    }
  }

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
    case 'reel':
    case 'clip':
    case 'igtv':
    case 'link_preview':
      return <SharedPostMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} />;

    case 'carousel':
      return <CarouselMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} />;

    case 'unknown':
      return <UnknownMediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} />;

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
              {renderTextWithLinks(displayContent, isOutgoing)}
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
      {preview.image && !imageError && (
        <div className="relative">
          {!imageLoaded && (
            <div className="w-full h-40 bg-[#1a1a1a] flex items-center justify-center">
              <ExternalLink className="w-6 h-6 text-gray-600 animate-pulse" />
            </div>
          )}
          <img
            src={decodeHtmlEntities(preview.image)}
            alt={preview.title ? decodeHtmlEntities(preview.title) : 'Preview'}
            className={`w-full h-40 object-cover ${imageLoaded ? '' : 'hidden'}`}
            style={{ imageRendering: 'auto' }}
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

// Helper: Detect if URL has explicit video extension
// NOTE: lookaside.fbsbx.com can return EITHER image or video, so we DON'T assume video
// We try image first, then fallback to video on error
function isExplicitVideoUrl(url?: string): boolean {
  if (!url) return false;
  return /\.(mp4|mov|webm|m4v)($|\?)/i.test(url);
}

// Helper: Check if URL is from Instagram CDN (can be image OR video)
function isCdnUrl(url?: string): boolean {
  if (!url) return false;
  return url.includes('lookaside.fbsbx.com') || url.includes('cdninstagram.com');
}

// Story Message - With gradient border and thumbnail preview
function StoryMessage({ message, isOutgoing, isLastInGroup }: { message: Message; isOutgoing: boolean; isLastInGroup: boolean }) {
  const [mediaLoaded, setMediaLoaded] = useState(false);
  const [useVideoFallback, setUseVideoFallback] = useState(false);
  const [mediaError, setMediaError] = useState(false);
  const metadata = message.metadata || {};
  // Use metadata.link for Instagram permalink, metadata.url for CDN media
  const storyPermalink = metadata.link || metadata.url;  // link is permalink, url may be CDN
  const hasLink = !!storyPermalink;
  const storyType = metadata.type === 'story_reply' ? 'Respuesta a story'
    : metadata.type === 'story_mention' ? 'Mención en story'
    : 'Reacción a story';

  // Contextual header text based on story type and direction
  const storyHeader = isOutgoing
    ? (metadata.type === 'story_reply' ? 'Respondiste a su historia'
      : metadata.type === 'story_mention' ? 'Te mencionaron en su historia'
      : 'Reaccionaste a su historia')
    : (metadata.type === 'story_reply' ? 'Respondió a tu historia'
      : metadata.type === 'story_mention' ? 'Te mencionó en su historia'
      : 'Reaccionó a tu historia');

  // For thumbnails: use CDN URL, permanent URL, or base64
  // NOTE: We DON'T assume CDN URLs are video - try image first, fallback to video
  const thumbnailSrc = metadata.url  // CDN URL (can be image OR video)
    || metadata.permanent_url
    || (metadata.thumbnail_base64
      ? (metadata.thumbnail_base64.startsWith('data:') ? metadata.thumbnail_base64 : `data:image/jpeg;base64,${metadata.thumbnail_base64}`)
      : metadata.thumbnail_url);
  const hasSavedThumbnail = !!metadata.thumbnail_base64 || !!metadata.permanent_url;

  // Only use video if: explicit video extension, OR image failed (useVideoFallback)
  const isVideo = isExplicitVideoUrl(thumbnailSrc) || useVideoFallback;

  const bubbleClass = isOutgoing
    ? `${IG_GRADIENT} text-white`
    : 'bg-[#262626] text-white';

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[75%] ${bubbleClass} rounded-2xl ${isLastInGroup ? (isOutgoing ? 'rounded-br-md' : 'rounded-bl-md') : ''} overflow-hidden`}>
        {/* Contextual header */}
        <div className="px-3 pt-2">
          <p className="text-xs text-gray-400">{storyHeader}</p>
        </div>
        {/* Story Preview with gradient border and thumbnail */}
        {/* Show preview if we have a thumbnail or a link (even if thumbnail fails) */}
        {(thumbnailSrc || hasLink) && (
          <a href={storyPermalink || '#'} target="_blank" rel="noopener noreferrer" className="block">
            <div className="p-2">
              <div className={`${IG_GRADIENT_STORY} p-[2px] rounded-xl`}>
                <div className="bg-black rounded-xl overflow-hidden">
                  {/* Show thumbnail/video if available and not errored */}
                  {thumbnailSrc && !mediaError && (
                    <div className="relative">
                      {!mediaLoaded && (
                        <div className="w-full h-32 bg-[#1a1a1a] flex items-center justify-center">
                          <Film className="w-8 h-8 text-gray-600 animate-pulse" />
                        </div>
                      )}
                      {/* Try image first, fallback to video if image fails */}
                      {isVideo ? (
                        // Video fallback: image failed, try as video
                        <video
                          src={thumbnailSrc}
                          className={`w-full max-h-64 object-cover ${mediaLoaded ? '' : 'hidden'}`}
                          muted
                          playsInline
                          autoPlay
                          loop
                          onLoadedData={() => setMediaLoaded(true)}
                          onError={() => { setMediaError(true); setMediaLoaded(true); }}  // Video also failed
                        />
                      ) : (
                        // Try as image first
                        <img
                          src={thumbnailSrc}
                          alt={storyType}
                          className={`w-full max-h-64 object-cover ${mediaLoaded ? '' : 'hidden'}`}
                          style={{ imageRendering: 'auto' }}
                          onLoad={() => setMediaLoaded(true)}
                          onError={() => setUseVideoFallback(true)}  // Image failed, try as video
                        />
                      )}
                      {/* Overlay with story type */}
                      {!isVideo && (
                        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-3">
                          <p className="text-white text-sm font-medium">{storyType}</p>
                          <p className="text-gray-300 text-xs flex items-center gap-1">
                            Toca para ver <ExternalLink className="w-3 h-3" />
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                  {/* Fallback if no thumbnail or media failed to load */}
                  {/* Fallback when no thumbnail or media failed to load */}
                  {/* IMPORTANT: If we have a URL (hasLink), show "Toca para ver" - URLs work when clicked even if inline rendering fails */}
                  {(!thumbnailSrc || mediaError) && (
                    <div className="p-3 flex items-center gap-3">
                      <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center">
                        <Film className="w-6 h-6 text-white" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-white text-sm font-medium">{storyType}</p>
                        <p className="text-gray-400 text-xs flex items-center gap-1">
                          {/* If we have a link, show "Toca para ver" - URL works even if inline rendering failed (CORS etc) */}
                          {hasLink ? 'Toca para ver' : (hasSavedThumbnail ? 'Toca para ver' : 'Story no disponible')}
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
            <p className="text-[15px]">{renderTextWithLinks(convertEmoticonsToEmoji(message.content), isOutgoing)}</p>
          </div>
        )}

        {/* Emoji reaction */}
        {metadata.emoji && (
          <div className="px-4 py-2 text-2xl">
            {metadata.emoji}
          </div>
        )}

        {/* No URL or thumbnail available - show nice placeholder matching story style */}
        {!thumbnailSrc && !metadata.url && (
          <div className="p-2">
            <div className={`${IG_GRADIENT_STORY} p-[2px] rounded-xl`}>
              <div className="bg-black rounded-xl overflow-hidden">
                <div className="p-3 flex items-center gap-3">
                  <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center">
                    <Film className="w-6 h-6 text-white" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm font-medium">{storyType}</p>
                    <p className="text-gray-400 text-xs">Story no disponible</p>
                  </div>
                </div>
              </div>
            </div>
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
      <div className="inline-flex items-center justify-center p-2 rounded-full bg-[#262626]">
        <span className="text-2xl" style={{ filter: 'none', color: 'initial' }}>
          {emoji}
        </span>
      </div>
    </div>
  );
}

// Unknown Media Message - Nice placeholder for media that couldn't be loaded
function UnknownMediaMessage({ message, isOutgoing, isLastInGroup }: { message: Message; isOutgoing: boolean; isLastInGroup: boolean }) {
  const metadata = message.metadata || {};
  const mediaUrl = metadata.url;

  // If we have a renderable media URL (not an Instagram permalink), try to display it
  if (mediaUrl && !isInstagramPermalink(mediaUrl)) {
    return <MediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} type="image" />;
  }

  // If we have an Instagram permalink, render as shared post
  if (mediaUrl && isInstagramPermalink(mediaUrl)) {
    return <SharedPostMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} />;
  }

  // No URL - show nice placeholder
  const bubbleClass = isOutgoing
    ? `${IG_GRADIENT} text-white`
    : 'bg-[#262626] text-white';

  const radiusClass = isOutgoing
    ? `rounded-2xl ${isLastInGroup ? 'rounded-br-md' : ''}`
    : `rounded-2xl ${isLastInGroup ? 'rounded-bl-md' : ''}`;

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[75%] ${bubbleClass} ${radiusClass} overflow-hidden`}>
        <div className="p-3">
          <div className="bg-black/20 rounded-lg p-4 flex items-center gap-3">
            <svg className="w-6 h-6 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <span className="text-gray-300 text-sm">Contenido multimedia no disponible</span>
          </div>
        </div>
        <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="px-4 pb-2" />
      </div>
    </div>
  );
}

// Media Message - Image/GIF/Sticker/Video with video fallback
function MediaMessage({ message, isOutgoing, isLastInGroup, type }: { message: Message; isOutgoing: boolean; isLastInGroup: boolean; type: 'image' | 'video' }) {
  const [loaded, setLoaded] = useState(false);
  const [useVideoFallback, setUseVideoFallback] = useState(false);
  const metadata = message.metadata || {};
  // Priority: permanent_url (Cloudinary) > thumbnail_base64 > url > preview_url > thumbnail_url
  const mediaUrl = metadata.permanent_url
    || metadata.thumbnail_base64
    || metadata.url
    || metadata.preview_url
    || metadata.animated_gif_url
    || metadata.thumbnail_url;
  const isSticker = metadata.render_as_sticker;

  // Check if URL is a playable video (explicit extension, or fallback from failed image)
  // NOTE: CDN URLs can be image OR video, so we try image first
  const isPlayableVideo = (type === 'video' || useVideoFallback || isExplicitVideoUrl(mediaUrl)) && mediaUrl;

  if (!mediaUrl) {
    return <TextMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} />;
  }

  // Render inline video player if we have a direct video URL or fallback triggered
  if (isPlayableVideo) {
    return (
      <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
        <div className="max-w-[70%] rounded-2xl overflow-hidden bg-black">
          {!loaded && (
            <div className="w-48 h-48 bg-[#262626] rounded-2xl flex items-center justify-center">
              <Film className="w-8 h-8 text-gray-500 animate-pulse" />
            </div>
          )}
          <video
            src={mediaUrl}
            className={`max-w-full max-h-96 rounded-2xl ${loaded ? '' : 'hidden'}`}
            muted
            playsInline
            autoPlay
            loop
            onLoadedData={() => setLoaded(true)}
            onError={() => setLoaded(true)}
          />
          <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="mt-1" />
        </div>
      </div>
    );
  }

  // Show image with fallback to video on error
  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[70%] ${isSticker ? '' : 'rounded-2xl overflow-hidden'}`}>
        <a href={mediaUrl} target="_blank" rel="noopener noreferrer" className="block relative cursor-pointer hover:opacity-90 transition-opacity">
          {!loaded && (
            <div className="w-48 h-48 bg-[#262626] rounded-2xl flex items-center justify-center">
              <ImageIcon className="w-8 h-8 text-gray-500 animate-pulse" />
            </div>
          )}
          <img
            src={mediaUrl}
            alt={type}
            className={`max-w-full ${isSticker ? 'max-h-32' : 'max-h-96 rounded-2xl'} ${loaded ? '' : 'hidden'}`}
            style={{ imageRendering: 'auto' }}
            onLoad={() => setLoaded(true)}
            onError={() => setUseVideoFallback(true)}  // Fallback: try as video
          />
          {type === 'video' && !useVideoFallback && (
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

// Audio Message - with inline playback support
function AudioMessage({ message, isOutgoing, isLastInGroup }: { message: Message; isOutgoing: boolean; isLastInGroup: boolean }) {
  const metadata = message.metadata || {};
  const audioUrl = metadata.url;
  const duration = metadata.duration;
  const bubbleClass = isOutgoing ? IG_GRADIENT : 'bg-[#262626]';

  // Format duration as mm:ss
  const formatDuration = (seconds?: number) => {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`${bubbleClass} rounded-2xl ${isLastInGroup ? (isOutgoing ? 'rounded-br-md' : 'rounded-bl-md') : ''} px-4 py-3 min-w-[200px]`}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0">
            <Mic className="w-5 h-5 text-white" />
          </div>
          <div className="flex-1">
            {audioUrl ? (
              // Playable audio with native controls
              <audio
                src={audioUrl}
                controls
                preload="metadata"
                className="w-full h-8 audio-player"
                style={{
                  filter: isOutgoing ? 'invert(1) hue-rotate(180deg)' : 'invert(1)',
                  opacity: 0.9,
                }}
              >
                Your browser does not support audio playback.
              </audio>
            ) : (
              // Fallback: decorative waveform for messages without playable URL
              <>
                <div className="h-1 bg-white/30 rounded-full w-32">
                  <div className="h-1 bg-white rounded-full w-1/3"></div>
                </div>
                <p className="text-xs text-white/70 mt-1">{formatDuration(duration)}</p>
              </>
            )}
          </div>
        </div>
        <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} />
      </div>
    </div>
  );
}

// Helper: Check if URL is an Instagram permalink (not renderable as media)
function isInstagramPermalink(url?: string): boolean {
  if (!url) return false;
  return /^https?:\/\/(www\.)?(instagram\.com|instagr\.am)\//i.test(url);
}

// Shared Post/Reel Message
function SharedPostMessage({ message, isOutgoing, isLastInGroup }: { message: Message; isOutgoing: boolean; isLastInGroup: boolean }) {
  const [mediaLoaded, setMediaLoaded] = useState(false);
  const [useVideoFallback, setUseVideoFallback] = useState(false);
  const [mediaError, setMediaError] = useState(false);
  const [sourceIndex, setSourceIndex] = useState(0);
  const metadata = message.metadata || {};

  // Build ordered list of media sources to try (cascade on failure)
  // Skip Instagram permalinks — they're not renderable as img/video
  const rawUrl = metadata.url;
  const mediaSources: string[] = [];
  if (rawUrl && !isInstagramPermalink(rawUrl)) mediaSources.push(rawUrl);
  if (metadata.permanent_url) mediaSources.push(metadata.permanent_url);
  if (metadata.thumbnail_base64) {
    mediaSources.push(
      metadata.thumbnail_base64.startsWith('data:') ? metadata.thumbnail_base64 : `data:image/jpeg;base64,${metadata.thumbnail_base64}`
    );
  }
  if (metadata.thumbnail_url) mediaSources.push(metadata.thumbnail_url);
  if (metadata.preview_url) mediaSources.push(metadata.preview_url);

  // Current source to try (advances on failure via sourceIndex)
  const thumbnailSrc = mediaSources[sourceIndex] || undefined;

  // When all sources exhausted, show placeholder
  const allSourcesFailed = mediaError || sourceIndex >= mediaSources.length;

  // Permalink: explicit permalink field, or Instagram URL, or fallback to media URL
  const permalink = metadata.permalink || (isInstagramPermalink(rawUrl) ? rawUrl : undefined) || metadata.url;
  const authorUsername = metadata.author_username;
  const isReel = metadata.type === 'shared_reel' || metadata.type === 'reel';

  // Detect video: by type, explicit extension, data:video URI, or fallback from failed image
  const isVideo = metadata.type === 'shared_video' || isReel || metadata.type === 'clip' || metadata.type === 'igtv'
    || isExplicitVideoUrl(thumbnailSrc) || thumbnailSrc?.startsWith('data:video/') || useVideoFallback;

  // Advance to next source when current one fails
  const handleImageError = () => {
    if (useVideoFallback) {
      // Video also failed — try next source
      setUseVideoFallback(false);
      setMediaLoaded(false);
      if (sourceIndex + 1 < mediaSources.length) {
        setSourceIndex(sourceIndex + 1);
      } else {
        setMediaError(true);
        setMediaLoaded(true);
      }
    } else {
      // Image failed — try as video first
      setUseVideoFallback(true);
    }
  };

  const handleVideoError = () => {
    // Video failed — try next source
    setUseVideoFallback(false);
    setMediaLoaded(false);
    if (sourceIndex + 1 < mediaSources.length) {
      setSourceIndex(sourceIndex + 1);
    } else {
      setMediaError(true);
      setMediaLoaded(true);
    }
  };

  // Platform-specific label
  const platformLabel = metadata.platform === 'youtube' ? 'YouTube'
    : metadata.platform === 'tiktok' ? 'TikTok'
    : 'Instagram';

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[75%] bg-[#262626] rounded-2xl ${isLastInGroup ? (isOutgoing ? 'rounded-br-md' : 'rounded-bl-md') : ''} overflow-hidden`}>
        {/* Post Preview */}
        <a href={permalink} target="_blank" rel="noopener noreferrer" className="block">
          {thumbnailSrc && !allSourcesFailed ? (
            <div className="relative">
              {!mediaLoaded && (
                <div className="w-full h-48 bg-[#363636] flex items-center justify-center">
                  <Share2 className="w-8 h-8 text-gray-500 animate-pulse" />
                </div>
              )}
              {/* Video player for video URLs (autoplay for reels/videos) */}
              {isVideo ? (
                <video
                  src={thumbnailSrc}
                  className={`w-full max-h-80 object-cover ${mediaLoaded ? '' : 'hidden'}`}
                  muted
                  playsInline
                  autoPlay
                  loop
                  onLoadedData={() => setMediaLoaded(true)}
                  onError={handleVideoError}
                />
              ) : (
                <img
                  src={thumbnailSrc}
                  alt="Post preview"
                  className={`w-full max-h-80 object-cover ${mediaLoaded ? '' : 'hidden'}`}
                  style={{ imageRendering: 'auto' }}
                  onLoad={() => setMediaLoaded(true)}
                  onError={handleImageError}
                />
              )}
              {isReel && !isVideo && (
                <div className="absolute top-2 right-2 bg-black/60 rounded px-2 py-1">
                  <Film className="w-4 h-4 text-white" />
                </div>
              )}
            </div>
          ) : (
            <div className="h-32 bg-[#363636] flex items-center justify-center flex-col gap-2">
              <Share2 className="w-8 h-8 text-gray-500" />
              {/* If we have a permalink, show "Toca para ver" - URL works even if inline rendering failed */}
              <p className="text-xs text-gray-400 flex items-center gap-1">
                {permalink ? 'Toca para ver' : 'Media no disponible'}
                {permalink && <ExternalLink className="w-3 h-3" />}
              </p>
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
              Ver en {platformLabel} <ExternalLink className="w-3 h-3" />
            </p>
          </div>
        </a>

        <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="px-3 pb-2" />
      </div>
    </div>
  );
}

// Carousel Message - Shows first image with count indicator
function CarouselMessage({ message, isOutgoing, isLastInGroup }: { message: Message; isOutgoing: boolean; isLastInGroup: boolean }) {
  const [loaded, setLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const metadata = message.metadata || {};

  // Support both carousel_items and items arrays
  const items = metadata.carousel_items || metadata.items || [];
  const totalCount = items.length;

  // Get first item for preview
  const firstItem = items[0];
  const imageUrl = firstItem?.url || metadata.url || metadata.thumbnail_url;

  if (!imageUrl) {
    return <TextMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} />;
  }

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className="max-w-[70%] rounded-2xl overflow-hidden">
        <a href={metadata.permalink || imageUrl} target="_blank" rel="noopener noreferrer" className="block relative cursor-pointer hover:opacity-90 transition-opacity">
          {!loaded && !imageError && (
            <div className="w-48 h-48 bg-[#262626] rounded-2xl flex items-center justify-center">
              <ImageIcon className="w-8 h-8 text-gray-500 animate-pulse" />
            </div>
          )}
          {imageError ? (
            <div className="w-48 h-48 bg-[#262626] rounded-2xl flex items-center justify-center">
              <ImageIcon className="w-8 h-8 text-gray-500" />
            </div>
          ) : (
            <img
              src={imageUrl}
              alt="Carousel"
              className={`max-w-full max-h-96 rounded-2xl ${loaded ? '' : 'hidden'}`}
              style={{ imageRendering: 'auto' }}
              onLoad={() => setLoaded(true)}
              onError={() => { setImageError(true); setLoaded(true); }}
            />
          )}
          {/* Carousel indicator */}
          {totalCount > 1 && (
            <div className="absolute top-2 right-2 bg-black/70 text-white text-xs px-2 py-1 rounded-full">
              1/{totalCount}
            </div>
          )}
          {/* Video indicator if first item is video */}
          {firstItem?.type === 'video' && (
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

// Timestamp component - shows day for non-today messages
function Timestamp({ timestamp, isOutgoing, className = '' }: { timestamp?: string; isOutgoing: boolean; className?: string }) {
  if (!timestamp) return null;

  const msgDate = new Date(timestamp);
  const now = new Date();

  // Get time part (always shown)
  const time = msgDate.toLocaleTimeString('es', {
    hour: '2-digit',
    minute: '2-digit',
  });

  // Check if same day
  const isToday = msgDate.toDateString() === now.toDateString();

  // Check if within last 7 days
  const diffMs = now.getTime() - msgDate.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  const isThisWeek = diffDays < 7;

  let display: string;
  if (isToday) {
    // Today: just time "10:32"
    display = time;
  } else if (isThisWeek) {
    // This week: "lun 10:32"
    const dayName = msgDate.toLocaleDateString('es', { weekday: 'short' });
    display = `${dayName} ${time}`;
  } else {
    // Older: "15 ene 10:32"
    const dateStr = msgDate.toLocaleDateString('es', { day: 'numeric', month: 'short' });
    display = `${dateStr} ${time}`;
  }

  return (
    <p className={`text-[10px] ${isOutgoing ? 'text-white/60' : 'text-gray-500'} text-right ${className}`}>
      {display}
    </p>
  );
}

export default MessageRenderer;
