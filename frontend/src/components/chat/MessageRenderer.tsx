// Multi-platform Message Renderer
// Supports Instagram, WhatsApp, and Telegram chat themes

import { useState, ReactNode } from 'react';
import { ExternalLink, Play, Image as ImageIcon, Film, Mic, Share2, CheckCheck } from 'lucide-react';

// ========================= EMOTICON CONVERSION =========================

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

function convertEmoticonsToEmoji(text: string): string {
  let result = text;
  const sortedEmoticons = Object.entries(emoticonToEmoji)
    .sort((a, b) => b[0].length - a[0].length);
  for (const [emoticon, emoji] of sortedEmoticons) {
    const escaped = emoticon.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(^|\\s|[^\\w])${escaped}($|\\s|[^\\w])`, 'g');
    result = result.replace(regex, (match, before, after) => `${before}${emoji}${after}`);
  }
  return result;
}

// ========================= HTML ENTITIES =========================

function decodeHtmlEntities(text: string): string {
  const textarea = document.createElement('textarea');
  textarea.innerHTML = text;
  return textarea.value;
}

// ========================= URL DETECTION =========================

const URL_REGEX = /(?:https?:\/\/)?(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_+.~#?&/=]*)/gi;

function renderTextWithLinks(text: string, linkClass: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let keyIndex = 0;

  URL_REGEX.lastIndex = 0;

  while ((match = URL_REGEX.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    let url = match[0];
    const href = url.startsWith('http') ? url : `https://${url}`;
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

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length > 0 ? parts : [text];
}

// ========================= INTERFACES =========================

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
  link?: string;
  emoji?: string;
  thumbnail_url?: string;
  thumbnail_base64?: string;
  preview_url?: string;
  animated_gif_url?: string;
  width?: number;
  height?: number;
  render_as_sticker?: boolean;
  author_username?: string;
  permalink?: string;
  caption?: string;
  platform?: string;
  link_preview?: LinkPreview;
  carousel_items?: CarouselItem[];
  items?: Array<{ url?: string; type?: string }>;
  duration?: number;
  permanent_url?: string;
  reacted_to_mid?: string;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  metadata?: MessageMetadata;
}

interface ReactionBadge {
  emoji: string;
  isOutgoing: boolean;
}

// ========================= PLATFORM THEMES =========================

export type ChatPlatform = 'instagram' | 'whatsapp' | 'telegram';

interface PlatformTheme {
  outgoingBubble: string;
  incomingBubble: string;
  cardBg: string;
  cardBorder: string;
  borderRadius: string;
  lastOutgoingRadius: string;
  lastIncomingRadius: string;
  timestampOutgoing: string;
  timestampIncoming: string;
  linkOutgoing: string;
  linkIncoming: string;
  hasTail: boolean;
  accent: string;
  outgoingColor: string;
  incomingColor: string;
}

// Violet gradient for Instagram outgoing messages
const IG_GRADIENT = 'bg-gradient-to-br from-violet-600 to-purple-600';
const IG_GRADIENT_STORY = 'bg-gradient-to-tr from-violet-500 via-purple-500 to-violet-600';

const PLATFORM_THEMES: Record<ChatPlatform, PlatformTheme> = {
  instagram: {
    outgoingBubble: `${IG_GRADIENT} text-white`,
    incomingBubble: 'bg-[#262626] text-white',
    cardBg: 'bg-[#363636]',
    cardBorder: 'border-[#363636]',
    borderRadius: 'rounded-2xl',
    lastOutgoingRadius: 'rounded-br-md',
    lastIncomingRadius: 'rounded-bl-md',
    timestampOutgoing: 'text-white/60',
    timestampIncoming: 'text-gray-500',
    linkOutgoing: 'text-blue-200 underline hover:text-white',
    linkIncoming: 'text-blue-400 underline hover:text-blue-300',
    hasTail: false,
    accent: '',
    outgoingColor: '#7c3aed',
    incomingColor: '#262626',
  },
  whatsapp: {
    outgoingBubble: 'bg-[#005c4b] text-[#e9edef]',
    incomingBubble: 'bg-[#202c33] text-[#e9edef]',
    cardBg: 'bg-[#2a3942]',
    cardBorder: 'border-[#2a3942]',
    borderRadius: 'rounded-[7.5px]',
    lastOutgoingRadius: 'rounded-br-[3px]',
    lastIncomingRadius: 'rounded-bl-[3px]',
    timestampOutgoing: 'text-[#ffffff99]',
    timestampIncoming: 'text-[#ffffff99]',
    linkOutgoing: 'text-[#53bdeb] underline hover:text-[#7dd3fc]',
    linkIncoming: 'text-[#53bdeb] underline hover:text-[#7dd3fc]',
    hasTail: true,
    accent: '#53bdeb',
    outgoingColor: '#005c4b',
    incomingColor: '#202c33',
  },
  telegram: {
    outgoingBubble: 'bg-[#2b5278] text-white',
    incomingBubble: 'bg-[#182533] text-white',
    cardBg: 'bg-[#1e2c3a]',
    cardBorder: 'border-[#1e2c3a]',
    borderRadius: 'rounded-xl',
    lastOutgoingRadius: 'rounded-br-[4px]',
    lastIncomingRadius: 'rounded-bl-[4px]',
    timestampOutgoing: 'text-[#ffffff80]',
    timestampIncoming: 'text-[#ffffff80]',
    linkOutgoing: 'text-[#3390ec] underline hover:text-[#5eadff]',
    linkIncoming: 'text-[#3390ec] underline hover:text-[#5eadff]',
    hasTail: false,
    accent: '#3390ec',
    outgoingColor: '#2b5278',
    incomingColor: '#182533',
  },
};

// Compute bubble + radius classes from theme
function getBubbleStyle(theme: PlatformTheme, isOutgoing: boolean, isLastInGroup: boolean) {
  const bubble = isOutgoing ? theme.outgoingBubble : theme.incomingBubble;
  const radius = `${theme.borderRadius} ${isLastInGroup ? (isOutgoing ? theme.lastOutgoingRadius : theme.lastIncomingRadius) : ''}`;
  return `${bubble} ${radius}`;
}

// WhatsApp-style message tail
function MessageTail({ isOutgoing, color }: { isOutgoing: boolean; color: string }) {
  return (
    <span className={`absolute top-0 ${isOutgoing ? '-right-[8px]' : '-left-[8px]'} block w-2 h-[13px]`}>
      <svg viewBox="0 0 8 13" className="w-full h-full">
        {isOutgoing ? (
          <path d="M0 0h1.5c2 4 4.5 8 6.5 13H0z" fill={color} />
        ) : (
          <path d="M8 0H6.5C4.5 4 2 8 0 13h8z" fill={color} />
        )}
      </svg>
    </span>
  );
}

// ========================= MESSAGE RENDERER =========================

interface MessageRendererProps {
  message: Message;
  isLastInGroup?: boolean;
  isFirstInGroup?: boolean;
  reactions?: ReactionBadge[];
  platform?: ChatPlatform;
}

export function MessageRenderer({ message, isLastInGroup = true, isFirstInGroup = false, reactions, platform = 'instagram' }: MessageRendererProps) {
  const isOutgoing = message.role === 'assistant';
  const metadata = message.metadata || {};
  const theme = PLATFORM_THEMES[platform];

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

  let content: React.ReactNode;
  switch (msgType) {
    case 'story_mention':
    case 'story_reply':
    case 'story_reaction':
      content = <StoryMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={isFirstInGroup} theme={theme} />;
      break;

    case 'reaction':
      return <ReactionMessage message={message} isOutgoing={isOutgoing} />;

    case 'image':
    case 'gif':
    case 'sticker':
      content = <MediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} type="image" theme={theme} />;
      break;

    case 'video':
      content = <MediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} type="video" theme={theme} />;
      break;

    case 'audio':
      content = <AudioMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={isFirstInGroup} theme={theme} />;
      break;

    case 'share':
    case 'shared_post':
    case 'shared_reel':
    case 'shared_video':
    case 'reel':
    case 'clip':
    case 'igtv':
    case 'link_preview':
      content = <SharedPostMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} theme={theme} />;
      break;

    case 'carousel':
      content = <CarouselMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} theme={theme} />;
      break;

    case 'unknown':
    case 'unsupported_type':
    case 'file':
      content = <UnknownMediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={isFirstInGroup} theme={theme} />;
      break;

    default:
      if (metadata.url || metadata.permanent_url || metadata.thumbnail_base64) {
        content = <UnknownMediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={isFirstInGroup} theme={theme} />;
      } else {
        content = <TextMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={isFirstInGroup} theme={theme} />;
      }
  }

  if (reactions && reactions.length > 0) {
    return (
      <div>
        {content}
        <ReactionsOverlay reactions={reactions} isOutgoing={isOutgoing} />
      </div>
    );
  }

  return <>{content}</>;
}

// ========================= TEXT MESSAGE =========================

function TextMessage({ message, isOutgoing, isLastInGroup, isFirstInGroup, theme }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; isFirstInGroup: boolean; theme: PlatformTheme;
}) {
  const metadata = message.metadata || {};
  const linkPreview = metadata.link_preview;
  const bubbleStyle = getBubbleStyle(theme, isOutgoing, isLastInGroup);
  const linkClass = isOutgoing ? theme.linkOutgoing : theme.linkIncoming;
  const showTail = isFirstInGroup && theme.hasTail;

  const rawContent = linkPreview
    ? message.content.replace(/https?:\/\/[^\s]+/g, '').trim()
    : message.content;

  const displayContent = convertEmoticonsToEmoji(rawContent);

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`relative max-w-[75%] ${showTail ? (isOutgoing ? 'mr-2' : 'ml-2') : ''}`}>
        {showTail && (
          <MessageTail isOutgoing={isOutgoing} color={isOutgoing ? theme.outgoingColor : theme.incomingColor} />
        )}
        <div className={`${bubbleStyle} overflow-hidden`}>
          {displayContent && (
            <div className="px-4 py-2.5">
              <p className="text-[15px] leading-relaxed whitespace-pre-wrap break-words">
                {renderTextWithLinks(displayContent, linkClass)}
              </p>
            </div>
          )}
          {linkPreview && <LinkPreviewCard preview={linkPreview} accentColor={theme.accent} />}
          <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} theme={theme} className="px-4 pb-2" />
        </div>
      </div>
    </div>
  );
}

// ========================= LINK PREVIEW CARD =========================

function LinkPreviewCard({ preview, accentColor }: { preview: LinkPreview; accentColor?: string }) {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);

  const domain = (() => {
    try {
      return new URL(preview.url).hostname.replace('www.', '');
    } catch {
      return preview.site_name || 'Link';
    }
  })();

  const domainColor = accentColor ? `text-[${accentColor}]` : 'text-violet-400';

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
        <p className={`text-xs mt-2 flex items-center gap-1 ${domainColor}`}>
          {domain}
          <ExternalLink className="w-3 h-3" />
        </p>
      </div>
    </a>
  );
}

// ========================= MEDIA HELPERS =========================

function isExplicitVideoUrl(url?: string): boolean {
  if (!url) return false;
  return /\.(mp4|mov|webm|m4v)($|\?)/i.test(url);
}

function isCdnUrl(url?: string): boolean {
  if (!url) return false;
  return url.includes('lookaside.fbsbx.com') || url.includes('cdninstagram.com');
}

// ========================= STORY MESSAGE =========================

function StoryMessage({ message, isOutgoing, isLastInGroup, isFirstInGroup, theme }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; isFirstInGroup: boolean; theme: PlatformTheme;
}) {
  const [mediaLoaded, setMediaLoaded] = useState(false);
  const [useVideoFallback, setUseVideoFallback] = useState(false);
  const [mediaError, setMediaError] = useState(false);
  const metadata = message.metadata || {};
  const storyPermalink = metadata.link || metadata.url;
  const hasLink = !!storyPermalink;
  const storyType = metadata.type === 'story_reply' ? 'Respuesta a story'
    : metadata.type === 'story_mention' ? 'Mención en story'
    : 'Reacción a story';

  const storyHeader = isOutgoing
    ? (metadata.type === 'story_reply' ? 'Respondiste a su historia'
      : metadata.type === 'story_mention' ? 'Te mencionaron en su historia'
      : 'Reaccionaste a su historia')
    : (metadata.type === 'story_reply' ? 'Respondió a tu historia'
      : metadata.type === 'story_mention' ? 'Te mencionó en su historia'
      : 'Reaccionó a tu historia');

  const thumbnailSrc = metadata.url
    || metadata.permanent_url
    || (metadata.thumbnail_base64
      ? (metadata.thumbnail_base64.startsWith('data:') ? metadata.thumbnail_base64 : `data:image/jpeg;base64,${metadata.thumbnail_base64}`)
      : metadata.thumbnail_url);
  const hasSavedThumbnail = !!metadata.thumbnail_base64 || !!metadata.permanent_url;
  const isVideo = isExplicitVideoUrl(thumbnailSrc) || useVideoFallback;

  const bubbleStyle = getBubbleStyle(theme, isOutgoing, isLastInGroup);
  const showTail = isFirstInGroup && theme.hasTail;
  const linkClass = isOutgoing ? theme.linkOutgoing : theme.linkIncoming;

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`relative max-w-[75%] ${showTail ? (isOutgoing ? 'mr-2' : 'ml-2') : ''}`}>
        {showTail && (
          <MessageTail isOutgoing={isOutgoing} color={isOutgoing ? theme.outgoingColor : theme.incomingColor} />
        )}
        <div className={`${bubbleStyle} overflow-hidden`}>
          <div className="px-3 pt-2">
            <p className="text-xs text-gray-400">{storyHeader}</p>
          </div>
          {(thumbnailSrc || hasLink) && (
            <a href={storyPermalink || '#'} target="_blank" rel="noopener noreferrer" className="block">
              <div className="p-2">
                <div className={`${IG_GRADIENT_STORY} p-[2px] rounded-xl`}>
                  <div className="bg-black rounded-xl overflow-hidden">
                    {thumbnailSrc && !mediaError && (
                      <div className="relative">
                        {!mediaLoaded && (
                          <div className="w-full h-32 bg-[#1a1a1a] flex items-center justify-center">
                            <Film className="w-8 h-8 text-gray-600 animate-pulse" />
                          </div>
                        )}
                        {isVideo ? (
                          <video
                            src={thumbnailSrc}
                            className={`w-full max-h-64 object-cover ${mediaLoaded ? '' : 'hidden'}`}
                            muted
                            playsInline
                            autoPlay
                            loop
                            onLoadedData={() => setMediaLoaded(true)}
                            onError={() => { setMediaError(true); setMediaLoaded(true); }}
                          />
                        ) : (
                          <img
                            src={thumbnailSrc}
                            alt={storyType}
                            className={`w-full max-h-64 object-cover ${mediaLoaded ? '' : 'hidden'}`}
                            style={{ imageRendering: 'auto' }}
                            onLoad={() => setMediaLoaded(true)}
                            onError={() => setUseVideoFallback(true)}
                          />
                        )}
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
                    {(!thumbnailSrc || mediaError) && (
                      <div className="p-3 flex items-center gap-3">
                        <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center">
                          <Film className="w-6 h-6 text-white" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-white text-sm font-medium">{storyType}</p>
                          <p className="text-gray-400 text-xs flex items-center gap-1">
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

          {message.content && !message.content.includes('story') && (
            <div className="px-4 py-2">
              <p className="text-[15px]">{renderTextWithLinks(convertEmoticonsToEmoji(message.content), linkClass)}</p>
            </div>
          )}

          {metadata.emoji && (
            <div className="px-4 py-2 text-2xl">
              {metadata.emoji}
            </div>
          )}

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

          <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} theme={theme} className="px-4 pb-2" />
        </div>
      </div>
    </div>
  );
}

// ========================= REACTION MESSAGE =========================

function ReactionMessage({ message, isOutgoing }: { message: Message; isOutgoing: boolean }) {
  const emoji = message.metadata?.emoji || '❤️';
  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#262626]/60 text-xs text-zinc-400">
        <span className="text-base" style={{ filter: 'none', color: 'initial' }}>{emoji}</span>
        <span>Reaccionó a un mensaje</span>
      </div>
    </div>
  );
}

// ========================= REACTIONS OVERLAY =========================

function ReactionsOverlay({ reactions, isOutgoing }: { reactions: ReactionBadge[]; isOutgoing: boolean }) {
  const grouped = new Map<string, number>();
  for (const r of reactions) {
    grouped.set(r.emoji, (grouped.get(r.emoji) || 0) + 1);
  }

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'} -mt-2 ${isOutgoing ? 'mr-1' : 'ml-1'}`}>
      <div className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-[#262626] border border-[#363636] shadow-sm">
        {Array.from(grouped.entries()).map(([emoji, count]) => (
          <span key={emoji} className="inline-flex items-center">
            <span className="text-sm" style={{ filter: 'none', color: 'initial' }}>{emoji}</span>
            {count > 1 && <span className="text-[10px] text-zinc-400 ml-0.5">{count}</span>}
          </span>
        ))}
      </div>
    </div>
  );
}

// ========================= UNKNOWN MEDIA MESSAGE =========================

function UnknownMediaMessage({ message, isOutgoing, isLastInGroup, isFirstInGroup, theme }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; isFirstInGroup: boolean; theme: PlatformTheme;
}) {
  const metadata = message.metadata || {};
  const mediaUrl = metadata.url;

  if (mediaUrl && !isInstagramPermalink(mediaUrl)) {
    return <MediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} type="image" theme={theme} />;
  }

  if (mediaUrl && isInstagramPermalink(mediaUrl)) {
    return <SharedPostMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} theme={theme} />;
  }

  const bubbleStyle = getBubbleStyle(theme, isOutgoing, isLastInGroup);
  const showTail = isFirstInGroup && theme.hasTail;

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`relative max-w-[75%] ${showTail ? (isOutgoing ? 'mr-2' : 'ml-2') : ''}`}>
        {showTail && (
          <MessageTail isOutgoing={isOutgoing} color={isOutgoing ? theme.outgoingColor : theme.incomingColor} />
        )}
        <div className={`${bubbleStyle} overflow-hidden`}>
          <div className="p-3">
            <div className="bg-black/20 rounded-lg p-4 flex items-center gap-3">
              <svg className="w-6 h-6 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <span className="text-gray-300 text-sm">Contenido multimedia no disponible</span>
            </div>
          </div>
          <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} theme={theme} className="px-4 pb-2" />
        </div>
      </div>
    </div>
  );
}

// ========================= MEDIA MESSAGE =========================

function MediaMessage({ message, isOutgoing, isLastInGroup, type, theme }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; type: 'image' | 'video'; theme: PlatformTheme;
}) {
  const [loaded, setLoaded] = useState(false);
  const [useVideoFallback, setUseVideoFallback] = useState(false);
  const metadata = message.metadata || {};
  const mediaUrl = metadata.permanent_url
    || metadata.thumbnail_base64
    || metadata.url
    || metadata.preview_url
    || metadata.animated_gif_url
    || metadata.thumbnail_url;
  const isSticker = metadata.render_as_sticker;
  const isPlayableVideo = (type === 'video' || useVideoFallback || isExplicitVideoUrl(mediaUrl)) && mediaUrl;

  if (!mediaUrl) {
    return <TextMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={false} theme={theme} />;
  }

  const placeholderBg = theme.incomingBubble.split(' ')[0] || 'bg-[#262626]';

  if (isPlayableVideo) {
    return (
      <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
        <div className={`max-w-[70%] ${theme.borderRadius} overflow-hidden bg-black`}>
          {!loaded && (
            <div className={`w-48 h-48 ${placeholderBg} ${theme.borderRadius} flex items-center justify-center`}>
              <Film className="w-8 h-8 text-gray-500 animate-pulse" />
            </div>
          )}
          <video
            src={mediaUrl}
            className={`max-w-full max-h-96 ${theme.borderRadius} ${loaded ? '' : 'hidden'}`}
            muted
            playsInline
            autoPlay
            loop
            onLoadedData={() => setLoaded(true)}
            onError={() => setLoaded(true)}
          />
          <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} theme={theme} className="mt-1" />
        </div>
      </div>
    );
  }

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[70%] ${isSticker ? '' : `${theme.borderRadius} overflow-hidden`}`}>
        <a href={mediaUrl} target="_blank" rel="noopener noreferrer" className="block relative cursor-pointer hover:opacity-90 transition-opacity">
          {!loaded && (
            <div className={`w-48 h-48 ${placeholderBg} ${theme.borderRadius} flex items-center justify-center`}>
              <ImageIcon className="w-8 h-8 text-gray-500 animate-pulse" />
            </div>
          )}
          <img
            src={mediaUrl}
            alt={type}
            className={`max-w-full ${isSticker ? 'max-h-32' : `max-h-96 ${theme.borderRadius}`} ${loaded ? '' : 'hidden'}`}
            style={{ imageRendering: 'auto' }}
            onLoad={() => setLoaded(true)}
            onError={() => setUseVideoFallback(true)}
          />
          {type === 'video' && !useVideoFallback && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-12 h-12 rounded-full bg-black/60 flex items-center justify-center">
                <Play className="w-6 h-6 text-white ml-1" />
              </div>
            </div>
          )}
        </a>
        <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} theme={theme} className="mt-1" />
      </div>
    </div>
  );
}

// ========================= AUDIO MESSAGE =========================

function AudioMessage({ message, isOutgoing, isLastInGroup, isFirstInGroup, theme }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; isFirstInGroup: boolean; theme: PlatformTheme;
}) {
  const metadata = message.metadata || {};
  const audioUrl = metadata.url;
  const duration = metadata.duration;
  const bubbleClass = isOutgoing ? theme.outgoingBubble : theme.incomingBubble;
  const showTail = isFirstInGroup && theme.hasTail;

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const radiusClass = `${theme.borderRadius} ${isLastInGroup ? (isOutgoing ? theme.lastOutgoingRadius : theme.lastIncomingRadius) : ''}`;

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`relative ${showTail ? (isOutgoing ? 'mr-2' : 'ml-2') : ''}`}>
        {showTail && (
          <MessageTail isOutgoing={isOutgoing} color={isOutgoing ? theme.outgoingColor : theme.incomingColor} />
        )}
        <div className={`${bubbleClass} ${radiusClass} px-4 py-3 min-w-[200px]`}>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0">
              <Mic className="w-5 h-5 text-white" />
            </div>
            <div className="flex-1">
              {audioUrl ? (
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
                <>
                  <div className="h-1 bg-white/30 rounded-full w-32">
                    <div className="h-1 bg-white rounded-full w-1/3"></div>
                  </div>
                  <p className="text-xs text-white/70 mt-1">{formatDuration(duration)}</p>
                </>
              )}
            </div>
          </div>
          <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} theme={theme} />
        </div>
      </div>
    </div>
  );
}

// ========================= SHARED POST MESSAGE =========================

function isInstagramPermalink(url?: string): boolean {
  if (!url) return false;
  return /^https?:\/\/(www\.)?(instagram\.com|instagr\.am)\//i.test(url);
}

function SharedPostMessage({ message, isOutgoing, isLastInGroup, theme }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; theme: PlatformTheme;
}) {
  const [mediaLoaded, setMediaLoaded] = useState(false);
  const [useVideoFallback, setUseVideoFallback] = useState(false);
  const [mediaError, setMediaError] = useState(false);
  const [sourceIndex, setSourceIndex] = useState(0);
  const metadata = message.metadata || {};

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

  const thumbnailSrc = mediaSources[sourceIndex] || undefined;
  const allSourcesFailed = mediaError || sourceIndex >= mediaSources.length;
  const permalink = metadata.permalink || (isInstagramPermalink(rawUrl) ? rawUrl : undefined) || metadata.url;
  const authorUsername = metadata.author_username;
  const isReel = metadata.type === 'shared_reel' || metadata.type === 'reel';

  const isVideo = metadata.type === 'shared_video' || isReel || metadata.type === 'clip' || metadata.type === 'igtv'
    || isExplicitVideoUrl(thumbnailSrc) || thumbnailSrc?.startsWith('data:video/') || useVideoFallback;

  const handleImageError = () => {
    if (useVideoFallback) {
      setUseVideoFallback(false);
      setMediaLoaded(false);
      if (sourceIndex + 1 < mediaSources.length) {
        setSourceIndex(sourceIndex + 1);
      } else {
        setMediaError(true);
        setMediaLoaded(true);
      }
    } else {
      setUseVideoFallback(true);
    }
  };

  const handleVideoError = () => {
    setUseVideoFallback(false);
    setMediaLoaded(false);
    if (sourceIndex + 1 < mediaSources.length) {
      setSourceIndex(sourceIndex + 1);
    } else {
      setMediaError(true);
      setMediaLoaded(true);
    }
  };

  const platformLabel = metadata.platform === 'youtube' ? 'YouTube'
    : metadata.platform === 'tiktok' ? 'TikTok'
    : 'Instagram';

  const containerBubble = theme.incomingBubble;
  const radiusClass = `${theme.borderRadius} ${isLastInGroup ? (isOutgoing ? theme.lastOutgoingRadius : theme.lastIncomingRadius) : ''}`;
  const accentLink = theme.accent ? `text-[${theme.accent}]` : 'text-blue-400';

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[75%] ${containerBubble} ${radiusClass} overflow-hidden`}>
        <a href={permalink} target="_blank" rel="noopener noreferrer" className="block">
          {thumbnailSrc && !allSourcesFailed ? (
            <div className="relative">
              {!mediaLoaded && (
                <div className={`w-full h-48 ${theme.cardBg} flex items-center justify-center`}>
                  <Share2 className="w-8 h-8 text-gray-500 animate-pulse" />
                </div>
              )}
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
            <div className={`h-32 ${theme.cardBg} flex items-center justify-center flex-col gap-2`}>
              <Share2 className="w-8 h-8 text-gray-500" />
              <p className="text-xs text-gray-400 flex items-center gap-1">
                {permalink ? 'Toca para ver' : 'Media no disponible'}
                {permalink && <ExternalLink className="w-3 h-3" />}
              </p>
            </div>
          )}

          <div className={`p-3 border-t ${theme.cardBorder}`}>
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full bg-gradient-to-br from-violet-600 to-purple-600"></div>
              <span className="text-white text-sm font-medium">
                {authorUsername || platformLabel}
              </span>
            </div>
            {metadata.caption && (
              <p className="text-gray-400 text-xs mt-2 line-clamp-2">{metadata.caption}</p>
            )}
            <p className={`text-xs mt-2 flex items-center gap-1 ${accentLink}`}>
              Ver en {platformLabel} <ExternalLink className="w-3 h-3" />
            </p>
          </div>
        </a>

        <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} theme={theme} className="px-3 pb-2" />
      </div>
    </div>
  );
}

// ========================= CAROUSEL MESSAGE =========================

function CarouselMessage({ message, isOutgoing, isLastInGroup, theme }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; theme: PlatformTheme;
}) {
  const [loaded, setLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const metadata = message.metadata || {};

  const items = metadata.carousel_items || metadata.items || [];
  const totalCount = items.length;

  const firstItem = items[0];
  const imageUrl = firstItem?.url || metadata.url || metadata.thumbnail_url;

  if (!imageUrl) {
    return <TextMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={false} theme={theme} />;
  }

  const placeholderBg = theme.incomingBubble.split(' ')[0] || 'bg-[#262626]';

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[70%] ${theme.borderRadius} overflow-hidden`}>
        <a href={metadata.permalink || imageUrl} target="_blank" rel="noopener noreferrer" className="block relative cursor-pointer hover:opacity-90 transition-opacity">
          {!loaded && !imageError && (
            <div className={`w-48 h-48 ${placeholderBg} ${theme.borderRadius} flex items-center justify-center`}>
              <ImageIcon className="w-8 h-8 text-gray-500 animate-pulse" />
            </div>
          )}
          {imageError ? (
            <div className={`w-48 h-48 ${placeholderBg} ${theme.borderRadius} flex items-center justify-center`}>
              <ImageIcon className="w-8 h-8 text-gray-500" />
            </div>
          ) : (
            <img
              src={imageUrl}
              alt="Carousel"
              className={`max-w-full max-h-96 ${theme.borderRadius} ${loaded ? '' : 'hidden'}`}
              style={{ imageRendering: 'auto' }}
              onLoad={() => setLoaded(true)}
              onError={() => { setImageError(true); setLoaded(true); }}
            />
          )}
          {totalCount > 1 && (
            <div className="absolute top-2 right-2 bg-black/70 text-white text-xs px-2 py-1 rounded-full">
              1/{totalCount}
            </div>
          )}
          {firstItem?.type === 'video' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-12 h-12 rounded-full bg-black/60 flex items-center justify-center">
                <Play className="w-6 h-6 text-white ml-1" />
              </div>
            </div>
          )}
        </a>
        <Timestamp timestamp={message.timestamp} isOutgoing={isOutgoing} theme={theme} className="mt-1" />
      </div>
    </div>
  );
}

// ========================= TIMESTAMP =========================

function Timestamp({ timestamp, isOutgoing, theme, className = '' }: {
  timestamp?: string; isOutgoing: boolean; theme: PlatformTheme; className?: string;
}) {
  if (!timestamp) return null;

  const msgDate = new Date(timestamp);
  const now = new Date();

  const time = msgDate.toLocaleTimeString('es', {
    hour: '2-digit',
    minute: '2-digit',
  });

  const isToday = msgDate.toDateString() === now.toDateString();
  const diffMs = now.getTime() - msgDate.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  const isThisWeek = diffDays < 7;

  let display: string;
  if (isToday) {
    display = time;
  } else if (isThisWeek) {
    const dayName = msgDate.toLocaleDateString('es', { weekday: 'short' });
    display = `${dayName} ${time}`;
  } else {
    const dateStr = msgDate.toLocaleDateString('es', { day: 'numeric', month: 'short' });
    display = `${dateStr} ${time}`;
  }

  const colorClass = isOutgoing ? theme.timestampOutgoing : theme.timestampIncoming;

  return (
    <p className={`text-[10px] ${colorClass} text-right flex items-center justify-end gap-1 ${className}`}>
      {display}
      {isOutgoing && theme.accent && (
        <CheckCheck className="w-3.5 h-3.5" style={{ color: theme.accent }} />
      )}
    </p>
  );
}

export default MessageRenderer;
