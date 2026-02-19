// Multi-platform Message Renderer
// Instagram: className-based (Tailwind). WhatsApp/Telegram: inline style={{}} for guaranteed rendering.

import { useState, ReactNode, CSSProperties } from 'react';
import { ExternalLink, Play, Image as ImageIcon, Film, Mic, Share2, CheckCheck, Check } from 'lucide-react';

// ========================= EMOTICON CONVERSION =========================

const emoticonToEmoji: Record<string, string> = {
  ':)': '😊', ':-)': '😊', '(:': '😊', ':(': '😞', ':-(': '😞',
  ':D': '😄', ':-D': '😄', ';)': '😉', ';-)': '😉',
  ':P': '😛', ':-P': '😛', ':p': '😛', ':-p': '😛',
  '<3': '❤️', ':O': '😮', ':-O': '😮', ':o': '😮', ':-o': '😮',
  'XD': '😆', 'xD': '😆', 'xd': '😆',
  ":'(": '😢', ":*(": '😢',
  ':S': '😕', ':s': '😕', ':/': '😕', ':-/': '😕', ':\\': '😕',
  ':*': '😘', ':-*': '😘', 'B)': '😎', '8)': '😎',
  '>:(': '😠', ':@': '😠', '^_^': '😊', '-_-': '😑',
  'o_o': '😳', 'O_O': '😳', ':3': '😺', '</3': '💔',
  ':$': '😳', ':X': '🤐', ':x': '🤐',
};

function convertEmoticonsToEmoji(text: string): string {
  let result = text;
  const sorted = Object.entries(emoticonToEmoji).sort((a, b) => b[0].length - a[0].length);
  for (const [emoticon, emoji] of sorted) {
    const escaped = emoticon.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(^|\\s|[^\\w])${escaped}($|\\s|[^\\w])`, 'g');
    result = result.replace(regex, (_match, before, after) => `${before}${emoji}${after}`);
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

function renderTextWithLinks(text: string, linkClassName: string, linkStyle?: CSSProperties): ReactNode[] {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let keyIndex = 0;
  URL_REGEX.lastIndex = 0;
  while ((match = URL_REGEX.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
    const url = match[0];
    const href = url.startsWith('http') ? url : `https://${url}`;
    parts.push(
      <a key={`link-${keyIndex++}`} href={href} target="_blank" rel="noopener noreferrer"
        className={linkClassName} style={linkStyle} onClick={(e) => e.stopPropagation()}>
        {url}
      </a>
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return parts.length > 0 ? parts : [text];
}

// ========================= INTERFACES =========================

interface LinkPreview {
  url: string; title?: string; description?: string; image?: string; site_name?: string; platform?: string;
}
interface CarouselItem { url: string; type?: 'image' | 'video'; thumbnail_url?: string; }
interface MessageMetadata {
  type?: string; url?: string; link?: string; emoji?: string;
  thumbnail_url?: string; thumbnail_base64?: string; preview_url?: string;
  animated_gif_url?: string; width?: number; height?: number;
  render_as_sticker?: boolean; author_username?: string; permalink?: string;
  caption?: string; platform?: string; link_preview?: LinkPreview;
  carousel_items?: CarouselItem[]; items?: Array<{ url?: string; type?: string }>;
  duration?: number; permanent_url?: string; reacted_to_mid?: string;
}
interface Message { role: 'user' | 'assistant'; content: string; timestamp?: string; metadata?: MessageMetadata; }
interface ReactionBadge { emoji: string; isOutgoing: boolean; }

// ========================= PLATFORM THEMES =========================

export type ChatPlatform = 'instagram' | 'whatsapp' | 'telegram';

// Instagram: keep using Tailwind classes (gradient not possible with inline styles without touching IG)
const IG_GRADIENT = 'bg-gradient-to-br from-violet-600 to-purple-600';
const IG_GRADIENT_STORY = 'bg-gradient-to-tr from-violet-500 via-purple-500 to-violet-600';

// WhatsApp & Telegram: raw hex values for inline styles
interface InlineTheme {
  outgoingBg: string;
  outgoingText: string;
  incomingBg: string;
  incomingText: string;
  borderRadius: string;
  lastRadius: string;
  timestampColor: string;
  linkColor: string;
  hasTail: boolean;
  accent: string;
  checkType: 'double' | 'single';
  cardBg: string;
  cardBorder: string;
}

const INLINE_THEMES: Record<'whatsapp' | 'telegram', InlineTheme> = {
  whatsapp: {
    outgoingBg: '#005c4b', outgoingText: '#e9edef',
    incomingBg: '#202c33', incomingText: '#e9edef',
    borderRadius: '7.5px', lastRadius: '3px',
    timestampColor: 'rgba(255,255,255,0.6)',
    linkColor: '#53bdeb', hasTail: true,
    accent: '#53bdeb', checkType: 'double',
    cardBg: '#2a3942', cardBorder: '#2a3942',
  },
  telegram: {
    outgoingBg: '#2b5278', outgoingText: '#efefef',
    incomingBg: '#182533', incomingText: '#ffffff',
    borderRadius: '12px', lastRadius: '4px',
    timestampColor: '#6d839e',
    linkColor: '#3390ec', hasTail: true,
    accent: '#3390ec', checkType: 'single',
    cardBg: '#1e2c3a', cardBorder: '#1e2c3a',
  },
};

// Helpers
function getInlineTheme(platform: ChatPlatform): InlineTheme | null {
  if (platform === 'instagram') return null;
  return INLINE_THEMES[platform];
}

function makeBubbleProps(platform: ChatPlatform, isOutgoing: boolean, isLastInGroup: boolean): { className: string; style?: CSSProperties } {
  const th = getInlineTheme(platform);
  if (!th) {
    // Instagram: Tailwind classes
    const bg = isOutgoing ? `${IG_GRADIENT} text-white` : 'bg-[#262626] text-white';
    const radius = `rounded-2xl ${isLastInGroup ? (isOutgoing ? 'rounded-br-md' : 'rounded-bl-md') : ''}`;
    return { className: `${bg} ${radius} overflow-hidden` };
  }
  // WA/TG: inline styles
  const style: CSSProperties = {
    backgroundColor: isOutgoing ? th.outgoingBg : th.incomingBg,
    color: isOutgoing ? th.outgoingText : th.incomingText,
    borderRadius: th.borderRadius,
    overflow: 'hidden' as const,
  };
  if (isLastInGroup) {
    if (isOutgoing) style.borderBottomRightRadius = th.lastRadius;
    else style.borderBottomLeftRadius = th.lastRadius;
  }
  return { className: '', style };
}

// WhatsApp message tail
function MessageTail({ isOutgoing, color }: { isOutgoing: boolean; color: string }) {
  return (
    <span style={{ position: 'absolute', top: 0, [isOutgoing ? 'right' : 'left']: '-8px', display: 'block', width: 8, height: 13 }}>
      <svg viewBox="0 0 8 13" width="8" height="13">
        {isOutgoing
          ? <path d="M0 0h1.5c2 4 4.5 8 6.5 13H0z" fill={color} />
          : <path d="M8 0H6.5C4.5 4 2 8 0 13h8z" fill={color} />
        }
      </svg>
    </span>
  );
}

// Inline timestamp for WA/TG (positioned inside the bubble)
function InlineTimestamp({ timestamp, isOutgoing, th }: { timestamp?: string; isOutgoing: boolean; th: InlineTheme }) {
  if (!timestamp) return null;
  const d = new Date(timestamp);
  const time = d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
  return (
    <span style={{
      position: 'absolute', bottom: 5, right: 7,
      fontSize: 11, lineHeight: '15px',
      color: th.timestampColor,
      display: 'flex', alignItems: 'center', gap: 3,
      pointerEvents: 'none',
    }}>
      {time}
      {isOutgoing && th.checkType === 'double' && <CheckCheck style={{ width: 16, height: 16, color: th.accent }} />}
      {isOutgoing && th.checkType === 'single' && <Check style={{ width: 15, height: 15, color: th.accent }} />}
    </span>
  );
}

// Format time for IG timestamps
function formatTimeDisplay(timestamp?: string): string {
  if (!timestamp) return '';
  const d = new Date(timestamp);
  const now = new Date();
  const time = d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === now.toDateString()) return time;
  const diff = Math.floor((now.getTime() - d.getTime()) / 86400000);
  if (diff < 7) return `${d.toLocaleDateString('es', { weekday: 'short' })} ${time}`;
  return `${d.toLocaleDateString('es', { day: 'numeric', month: 'short' })} ${time}`;
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

  let msgType = metadata.type || 'text';
  if (msgType === 'text') {
    const c = (message.content || '').toLowerCase();
    if (c === '[media/attachment]' || c === '[media]' || c === 'sent an attachment'
      || c === 'shared content' || c === 'shared a post' || c === 'shared a reel') msgType = 'share';
    else if (c === 'sent a photo') msgType = 'image';
    else if (c === 'sent a video') msgType = 'video';
    else if (c === 'sent a voice message') msgType = 'audio';
    else if (c === 'sent a gif') msgType = 'gif';
    else if (c === 'sent a sticker') msgType = 'sticker';
  }

  let content: React.ReactNode;
  switch (msgType) {
    case 'story_mention': case 'story_reply': case 'story_reaction':
      content = <StoryMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={isFirstInGroup} platform={platform} />;
      break;
    case 'reaction':
      return <ReactionMessage message={message} isOutgoing={isOutgoing} />;
    case 'image': case 'gif': case 'sticker':
      content = <MediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} type="image" platform={platform} />;
      break;
    case 'video':
      content = <MediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} type="video" platform={platform} />;
      break;
    case 'audio':
      content = <AudioMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={isFirstInGroup} platform={platform} />;
      break;
    case 'share': case 'shared_post': case 'shared_reel': case 'shared_video':
    case 'reel': case 'clip': case 'igtv': case 'link_preview':
      content = <SharedPostMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} platform={platform} />;
      break;
    case 'carousel':
      content = <CarouselMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} platform={platform} />;
      break;
    case 'unknown': case 'unsupported_type': case 'file':
      content = <UnknownMediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={isFirstInGroup} platform={platform} />;
      break;
    default:
      if (metadata.url || metadata.permanent_url || metadata.thumbnail_base64) {
        content = <UnknownMediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={isFirstInGroup} platform={platform} />;
      } else {
        content = <TextMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={isFirstInGroup} platform={platform} />;
      }
  }

  if (reactions && reactions.length > 0) {
    return <div>{content}<ReactionsOverlay reactions={reactions} isOutgoing={isOutgoing} /></div>;
  }
  return <>{content}</>;
}

// ========================= TEXT MESSAGE =========================

function TextMessage({ message, isOutgoing, isLastInGroup, isFirstInGroup, platform }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; isFirstInGroup: boolean; platform: ChatPlatform;
}) {
  const metadata = message.metadata || {};
  const linkPreview = metadata.link_preview;
  const th = getInlineTheme(platform);
  const isIG = !th;
  const bubble = makeBubbleProps(platform, isOutgoing, isLastInGroup);
  const showTail = isFirstInGroup && th?.hasTail;

  // Link styling
  const linkClassName = isIG ? (isOutgoing ? 'text-blue-200 underline hover:text-white' : 'text-blue-400 underline hover:text-blue-300') : 'underline';
  const linkStyle = th ? { color: th.linkColor } : undefined;

  const rawContent = linkPreview ? message.content.replace(/https?:\/\/[^\s]+/g, '').trim() : message.content;
  const displayContent = convertEmoticonsToEmoji(rawContent);

  // Spacer width for inline timestamps
  const spacerW = th ? (isOutgoing ? 85 : 58) : 0;

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div style={{ position: 'relative', maxWidth: '80%', ...(showTail ? { [isOutgoing ? 'marginRight' : 'marginLeft']: 8 } : {}) }}>
        {showTail && <MessageTail isOutgoing={isOutgoing} color={isOutgoing ? th!.outgoingBg : th!.incomingBg} />}
        <div className={bubble.className} style={bubble.style}>
          {displayContent && (
            <div
              className={isIG ? 'px-4 py-3' : ''}
              style={th ? { padding: '8px 12px 8px 12px', position: 'relative' } : undefined}
            >
              <p className="text-[15px] leading-relaxed whitespace-pre-wrap break-words">
                {renderTextWithLinks(displayContent, linkClassName, linkStyle)}
                {th && <span style={{ display: 'inline-block', width: spacerW, height: 1 }} />}
              </p>
              {th && <InlineTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} th={th} />}
            </div>
          )}
          {linkPreview && <LinkPreviewCard preview={linkPreview} accentColor={th?.accent} />}
          {isIG && <IGTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="px-4 pb-2" />}
        </div>
      </div>
    </div>
  );
}

// ========================= LINK PREVIEW CARD =========================

function LinkPreviewCard({ preview, accentColor }: { preview: LinkPreview; accentColor?: string }) {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const domain = (() => { try { return new URL(preview.url).hostname.replace('www.', ''); } catch { return preview.site_name || 'Link'; } })();
  return (
    <a href={preview.url} target="_blank" rel="noopener noreferrer" className="block border-t border-white/10 bg-black/20 hover:bg-black/30 transition-colors">
      {preview.image && !imageError && (
        <div className="relative">
          {!imageLoaded && <div className="w-full h-40 bg-[#1a1a1a] flex items-center justify-center"><ExternalLink className="w-6 h-6 text-gray-600 animate-pulse" /></div>}
          <img src={decodeHtmlEntities(preview.image)} alt={preview.title ? decodeHtmlEntities(preview.title) : 'Preview'}
            className={`w-full h-40 object-cover ${imageLoaded ? '' : 'hidden'}`} style={{ imageRendering: 'auto' }}
            onLoad={() => setImageLoaded(true)} onError={() => setImageError(true)} />
        </div>
      )}
      <div className="p-3">
        {preview.title && <p className="text-sm font-medium text-white line-clamp-2">{decodeHtmlEntities(preview.title)}</p>}
        {preview.description && <p className="text-xs text-gray-400 mt-1 line-clamp-2">{decodeHtmlEntities(preview.description)}</p>}
        <p className="text-xs mt-2 flex items-center gap-1" style={accentColor ? { color: accentColor } : undefined}>
          <span className={accentColor ? '' : 'text-violet-400'}>{domain}</span>
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

// ========================= STORY MESSAGE =========================

function StoryMessage({ message, isOutgoing, isLastInGroup, isFirstInGroup, platform }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; isFirstInGroup: boolean; platform: ChatPlatform;
}) {
  const [mediaLoaded, setMediaLoaded] = useState(false);
  const [useVideoFallback, setUseVideoFallback] = useState(false);
  const [mediaError, setMediaError] = useState(false);
  const metadata = message.metadata || {};
  const th = getInlineTheme(platform);
  const isIG = !th;
  const storyPermalink = metadata.link || metadata.url;
  const hasLink = !!storyPermalink;
  const storyType = metadata.type === 'story_reply' ? 'Respuesta a story' : metadata.type === 'story_mention' ? 'Mención en story' : 'Reacción a story';
  const storyHeader = isOutgoing
    ? (metadata.type === 'story_reply' ? 'Respondiste a su historia' : metadata.type === 'story_mention' ? 'Te mencionaron en su historia' : 'Reaccionaste a su historia')
    : (metadata.type === 'story_reply' ? 'Respondió a tu historia' : metadata.type === 'story_mention' ? 'Te mencionó en su historia' : 'Reaccionó a tu historia');
  const thumbnailSrc = metadata.url || metadata.permanent_url || (metadata.thumbnail_base64 ? (metadata.thumbnail_base64.startsWith('data:') ? metadata.thumbnail_base64 : `data:image/jpeg;base64,${metadata.thumbnail_base64}`) : metadata.thumbnail_url);
  const hasSavedThumbnail = !!metadata.thumbnail_base64 || !!metadata.permanent_url;
  const isVideo = isExplicitVideoUrl(thumbnailSrc) || useVideoFallback;
  const bubble = makeBubbleProps(platform, isOutgoing, isLastInGroup);
  const showTail = isFirstInGroup && th?.hasTail;
  const linkClassName = isIG ? (isOutgoing ? 'text-blue-200 underline hover:text-white' : 'text-blue-400 underline hover:text-blue-300') : 'underline';
  const linkStyle = th ? { color: th.linkColor } : undefined;

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div style={{ position: 'relative', maxWidth: '80%', ...(showTail ? { [isOutgoing ? 'marginRight' : 'marginLeft']: 8 } : {}) }}>
        {showTail && <MessageTail isOutgoing={isOutgoing} color={isOutgoing ? th!.outgoingBg : th!.incomingBg} />}
        <div className={bubble.className} style={bubble.style}>
          <div className="px-3 pt-2"><p className="text-xs text-gray-400">{storyHeader}</p></div>
          {(thumbnailSrc || hasLink) && (
            <a href={storyPermalink || '#'} target="_blank" rel="noopener noreferrer" className="block">
              <div className="p-2">
                <div className={`${IG_GRADIENT_STORY} p-[2px] rounded-xl`}>
                  <div className="bg-black rounded-xl overflow-hidden">
                    {thumbnailSrc && !mediaError && (
                      <div className="relative">
                        {!mediaLoaded && <div className="w-full h-32 bg-[#1a1a1a] flex items-center justify-center"><Film className="w-8 h-8 text-gray-600 animate-pulse" /></div>}
                        {isVideo ? (
                          <video src={thumbnailSrc} className={`w-full max-h-64 object-cover ${mediaLoaded ? '' : 'hidden'}`} muted playsInline autoPlay loop onLoadedData={() => setMediaLoaded(true)} onError={() => { setMediaError(true); setMediaLoaded(true); }} />
                        ) : (
                          <img src={thumbnailSrc} alt={storyType} className={`w-full max-h-64 object-cover ${mediaLoaded ? '' : 'hidden'}`} style={{ imageRendering: 'auto' }} onLoad={() => setMediaLoaded(true)} onError={() => setUseVideoFallback(true)} />
                        )}
                        {!isVideo && <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-3"><p className="text-white text-sm font-medium">{storyType}</p><p className="text-gray-300 text-xs flex items-center gap-1">Toca para ver <ExternalLink className="w-3 h-3" /></p></div>}
                      </div>
                    )}
                    {(!thumbnailSrc || mediaError) && (
                      <div className="p-3 flex items-center gap-3">
                        <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center"><Film className="w-6 h-6 text-white" /></div>
                        <div className="flex-1 min-w-0"><p className="text-white text-sm font-medium">{storyType}</p><p className="text-gray-400 text-xs flex items-center gap-1">{hasLink ? 'Toca para ver' : (hasSavedThumbnail ? 'Toca para ver' : 'Story no disponible')}<ExternalLink className="w-3 h-3" /></p></div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </a>
          )}
          {message.content && !message.content.includes('story') && (
            <div className="px-4 py-2"><p className="text-[15px]">{renderTextWithLinks(convertEmoticonsToEmoji(message.content), linkClassName, linkStyle)}</p></div>
          )}
          {metadata.emoji && <div className="px-4 py-2 text-2xl">{metadata.emoji}</div>}
          {!thumbnailSrc && !metadata.url && (
            <div className="p-2"><div className={`${IG_GRADIENT_STORY} p-[2px] rounded-xl`}><div className="bg-black rounded-xl overflow-hidden"><div className="p-3 flex items-center gap-3"><div className="w-12 h-12 rounded-lg bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center"><Film className="w-6 h-6 text-white" /></div><div className="flex-1 min-w-0"><p className="text-white text-sm font-medium">{storyType}</p><p className="text-gray-400 text-xs">Story no disponible</p></div></div></div></div></div>
          )}
          {th ? (
            <div style={{ padding: '2px 8px 6px', position: 'relative' }}>
              <InlineTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} th={th} />
              <span style={{ display: 'inline-block', width: 50, height: 15 }} />
            </div>
          ) : (
            <IGTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="px-4 pb-2" />
          )}
        </div>
      </div>
    </div>
  );
}

// ========================= REACTION / REACTIONS OVERLAY =========================

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

function ReactionsOverlay({ reactions, isOutgoing }: { reactions: ReactionBadge[]; isOutgoing: boolean }) {
  const grouped = new Map<string, number>();
  for (const r of reactions) grouped.set(r.emoji, (grouped.get(r.emoji) || 0) + 1);
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

function isInstagramPermalink(url?: string): boolean {
  if (!url) return false;
  return /^https?:\/\/(www\.)?(instagram\.com|instagr\.am)\//i.test(url);
}

function UnknownMediaMessage({ message, isOutgoing, isLastInGroup, isFirstInGroup, platform }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; isFirstInGroup: boolean; platform: ChatPlatform;
}) {
  const metadata = message.metadata || {};
  const mediaUrl = metadata.url;
  if (mediaUrl && !isInstagramPermalink(mediaUrl)) return <MediaMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} type="image" platform={platform} />;
  if (mediaUrl && isInstagramPermalink(mediaUrl)) return <SharedPostMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} platform={platform} />;

  const th = getInlineTheme(platform);
  const bubble = makeBubbleProps(platform, isOutgoing, isLastInGroup);
  const showTail = isFirstInGroup && th?.hasTail;

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div style={{ position: 'relative', maxWidth: '80%', ...(showTail ? { [isOutgoing ? 'marginRight' : 'marginLeft']: 8 } : {}) }}>
        {showTail && <MessageTail isOutgoing={isOutgoing} color={isOutgoing ? th!.outgoingBg : th!.incomingBg} />}
        <div className={bubble.className} style={bubble.style}>
          <div className="p-3">
            <div className="bg-black/20 rounded-lg p-4 flex items-center gap-3">
              <svg className="w-6 h-6 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
              <span className="text-gray-300 text-sm">Contenido multimedia no disponible</span>
            </div>
          </div>
          {th ? (
            <div style={{ padding: '0 8px 6px', position: 'relative' }}><InlineTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} th={th} /><span style={{ display: 'inline-block', width: 50, height: 15 }} /></div>
          ) : (
            <IGTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="px-4 pb-2" />
          )}
        </div>
      </div>
    </div>
  );
}

// ========================= MEDIA MESSAGE =========================

function MediaMessage({ message, isOutgoing, isLastInGroup, type, platform }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; type: 'image' | 'video'; platform: ChatPlatform;
}) {
  const [loaded, setLoaded] = useState(false);
  const [useVideoFallback, setUseVideoFallback] = useState(false);
  const metadata = message.metadata || {};
  const mediaUrl = metadata.permanent_url || metadata.thumbnail_base64 || metadata.url || metadata.preview_url || metadata.animated_gif_url || metadata.thumbnail_url;
  const isSticker = metadata.render_as_sticker;
  const isPlayableVideo = (type === 'video' || useVideoFallback || isExplicitVideoUrl(mediaUrl)) && mediaUrl;
  const th = getInlineTheme(platform);

  if (!mediaUrl) return <TextMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={false} platform={platform} />;

  const borderRadius = th ? th.borderRadius : '16px';

  if (isPlayableVideo) {
    return (
      <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
        <div style={{ maxWidth: '70%', borderRadius, overflow: 'hidden', backgroundColor: 'black' }}>
          {!loaded && <div style={{ width: 192, height: 192, backgroundColor: th?.incomingBg || '#262626', borderRadius, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Film className="w-8 h-8 text-gray-500 animate-pulse" /></div>}
          <video src={mediaUrl} style={{ maxWidth: '100%', maxHeight: 384, borderRadius, display: loaded ? undefined : 'none' }} muted playsInline autoPlay loop onLoadedData={() => setLoaded(true)} onError={() => setLoaded(true)} />
          {th ? <div style={{ padding: '2px 8px 4px', position: 'relative' }}><InlineTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} th={th} /><span style={{ display: 'inline-block', width: 50, height: 15 }} /></div>
            : <IGTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="mt-1" />}
        </div>
      </div>
    );
  }

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div style={{ maxWidth: '70%', ...(isSticker ? {} : { borderRadius, overflow: 'hidden' }) }}>
        <a href={mediaUrl} target="_blank" rel="noopener noreferrer" className="block relative cursor-pointer hover:opacity-90 transition-opacity">
          {!loaded && <div style={{ width: 192, height: 192, backgroundColor: th?.incomingBg || '#262626', borderRadius, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><ImageIcon className="w-8 h-8 text-gray-500 animate-pulse" /></div>}
          <img src={mediaUrl} alt={type} style={{ maxWidth: '100%', ...(isSticker ? { maxHeight: 128 } : { maxHeight: 384, borderRadius }), imageRendering: 'auto', display: loaded ? undefined : 'none' }} onLoad={() => setLoaded(true)} onError={() => setUseVideoFallback(true)} />
          {type === 'video' && !useVideoFallback && <div className="absolute inset-0 flex items-center justify-center"><div className="w-12 h-12 rounded-full bg-black/60 flex items-center justify-center"><Play className="w-6 h-6 text-white ml-1" /></div></div>}
        </a>
        {th ? <div style={{ padding: '2px 8px 4px', position: 'relative' }}><InlineTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} th={th} /><span style={{ display: 'inline-block', width: 50, height: 15 }} /></div>
          : <IGTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="mt-1" />}
      </div>
    </div>
  );
}

// ========================= AUDIO MESSAGE =========================

function AudioMessage({ message, isOutgoing, isLastInGroup, isFirstInGroup, platform }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; isFirstInGroup: boolean; platform: ChatPlatform;
}) {
  const metadata = message.metadata || {};
  const audioUrl = metadata.url;
  const duration = metadata.duration;
  const transcription = (metadata as Record<string, unknown>).transcription as string | undefined;
  const th = getInlineTheme(platform);
  const bubble = makeBubbleProps(platform, isOutgoing, isLastInGroup);
  const showTail = isFirstInGroup && th?.hasTail;

  const formatDuration = (s?: number) => { if (!s) return '0:00'; return `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}`; };

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div style={{ position: 'relative', ...(showTail ? { [isOutgoing ? 'marginRight' : 'marginLeft']: 8 } : {}) }}>
        {showTail && <MessageTail isOutgoing={isOutgoing} color={isOutgoing ? th!.outgoingBg : th!.incomingBg} />}
        <div className={bubble.className} style={{ ...bubble.style, padding: '12px 16px', minWidth: 200, maxWidth: 340 }}>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0"><Mic className="w-5 h-5 text-white" /></div>
            <div className="flex-1">
              {audioUrl ? (
                <audio src={audioUrl} controls preload="metadata" className="w-full h-8" style={{ filter: isOutgoing ? 'invert(1) hue-rotate(180deg)' : 'invert(1)', opacity: 0.9 }}>Your browser does not support audio playback.</audio>
              ) : (
                <><div className="h-1 bg-white/30 rounded-full w-32"><div className="h-1 bg-white rounded-full w-1/3"></div></div><p className="text-xs text-white/70 mt-1">{formatDuration(duration)}</p></>
              )}
            </div>
          </div>
          {transcription && (
            <p className="text-sm text-white/80 italic mt-2 leading-snug">
              &ldquo;{transcription}&rdquo;
            </p>
          )}
          {th ? <div style={{ position: 'relative', marginTop: 4 }}><InlineTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} th={th} /><span style={{ display: 'inline-block', width: 50, height: 15 }} /></div>
            : <IGTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} />}
        </div>
      </div>
    </div>
  );
}

// ========================= SHARED POST MESSAGE =========================

function SharedPostMessage({ message, isOutgoing, isLastInGroup, platform }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; platform: ChatPlatform;
}) {
  const [mediaLoaded, setMediaLoaded] = useState(false);
  const [useVideoFallback, setUseVideoFallback] = useState(false);
  const [mediaError, setMediaError] = useState(false);
  const [sourceIndex, setSourceIndex] = useState(0);
  const metadata = message.metadata || {};
  const th = getInlineTheme(platform);

  const rawUrl = metadata.url;
  const mediaSources: string[] = [];
  if (rawUrl && !isInstagramPermalink(rawUrl)) mediaSources.push(rawUrl);
  if (metadata.permanent_url) mediaSources.push(metadata.permanent_url);
  if (metadata.thumbnail_base64) mediaSources.push(metadata.thumbnail_base64.startsWith('data:') ? metadata.thumbnail_base64 : `data:image/jpeg;base64,${metadata.thumbnail_base64}`);
  if (metadata.thumbnail_url) mediaSources.push(metadata.thumbnail_url);
  if (metadata.preview_url) mediaSources.push(metadata.preview_url);

  const thumbnailSrc = mediaSources[sourceIndex] || undefined;
  const allSourcesFailed = mediaError || sourceIndex >= mediaSources.length;
  const permalink = metadata.permalink || (isInstagramPermalink(rawUrl) ? rawUrl : undefined) || metadata.url;
  const authorUsername = metadata.author_username;
  const isReel = metadata.type === 'shared_reel' || metadata.type === 'reel';
  const isVideo = metadata.type === 'shared_video' || isReel || metadata.type === 'clip' || metadata.type === 'igtv' || isExplicitVideoUrl(thumbnailSrc) || thumbnailSrc?.startsWith('data:video/') || useVideoFallback;

  const handleImageError = () => { if (useVideoFallback) { setUseVideoFallback(false); setMediaLoaded(false); if (sourceIndex + 1 < mediaSources.length) setSourceIndex(sourceIndex + 1); else { setMediaError(true); setMediaLoaded(true); } } else setUseVideoFallback(true); };
  const handleVideoError = () => { setUseVideoFallback(false); setMediaLoaded(false); if (sourceIndex + 1 < mediaSources.length) setSourceIndex(sourceIndex + 1); else { setMediaError(true); setMediaLoaded(true); } };

  const platformLabel = metadata.platform === 'youtube' ? 'YouTube' : metadata.platform === 'tiktok' ? 'TikTok' : 'Instagram';

  // Container: for IG use className, for WA/TG use inline style
  const containerClass = !th ? `bg-[#262626] text-white rounded-2xl ${isLastInGroup ? (isOutgoing ? 'rounded-br-md' : 'rounded-bl-md') : ''} overflow-hidden` : 'overflow-hidden';
  const containerStyle: CSSProperties | undefined = th ? {
    backgroundColor: th.incomingBg, color: th.incomingText,
    borderRadius: th.borderRadius,
    ...(isLastInGroup && isOutgoing && { borderBottomRightRadius: th.lastRadius }),
    ...(isLastInGroup && !isOutgoing && { borderBottomLeftRadius: th.lastRadius }),
  } : undefined;
  const cardBg = th ? th.cardBg : '#363636';
  const cardBorder = th ? th.cardBorder : '#363636';

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div className={containerClass} style={{ maxWidth: '80%', ...containerStyle }}>
        <a href={permalink} target="_blank" rel="noopener noreferrer" className="block">
          {thumbnailSrc && !allSourcesFailed ? (
            <div className="relative">
              {!mediaLoaded && <div style={{ width: '100%', height: 192, backgroundColor: cardBg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Share2 className="w-8 h-8 text-gray-500 animate-pulse" /></div>}
              {isVideo ? <video src={thumbnailSrc} className={`w-full max-h-80 object-cover ${mediaLoaded ? '' : 'hidden'}`} muted playsInline autoPlay loop onLoadedData={() => setMediaLoaded(true)} onError={handleVideoError} />
                : <img src={thumbnailSrc} alt="Post preview" className={`w-full max-h-80 object-cover ${mediaLoaded ? '' : 'hidden'}`} style={{ imageRendering: 'auto' }} onLoad={() => setMediaLoaded(true)} onError={handleImageError} />}
              {isReel && !isVideo && <div className="absolute top-2 right-2 bg-black/60 rounded px-2 py-1"><Film className="w-4 h-4 text-white" /></div>}
            </div>
          ) : (
            <div style={{ height: 128, backgroundColor: cardBg, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 8 }}>
              <Share2 className="w-8 h-8 text-gray-500" />
              <p className="text-xs text-gray-400 flex items-center gap-1">{permalink ? 'Toca para ver' : 'Media no disponible'}{permalink && <ExternalLink className="w-3 h-3" />}</p>
            </div>
          )}
          <div style={{ padding: 12, borderTop: `1px solid ${cardBorder}` }}>
            <div className="flex items-center gap-2"><div className="w-6 h-6 rounded-full bg-gradient-to-br from-violet-600 to-purple-600" /><span className="text-white text-sm font-medium">{authorUsername || platformLabel}</span></div>
            {metadata.caption && <p className="text-gray-400 text-xs mt-2 line-clamp-2">{metadata.caption}</p>}
            <p className="text-xs mt-2 flex items-center gap-1" style={th ? { color: th.accent } : undefined}><span className={th ? '' : 'text-blue-400'}>Ver en {platformLabel}</span> <ExternalLink className="w-3 h-3" /></p>
          </div>
        </a>
        {th ? <div style={{ padding: '0 8px 6px', position: 'relative' }}><InlineTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} th={th} /><span style={{ display: 'inline-block', width: 50, height: 15 }} /></div>
          : <IGTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="px-3 pb-2" />}
      </div>
    </div>
  );
}

// ========================= CAROUSEL MESSAGE =========================

function CarouselMessage({ message, isOutgoing, isLastInGroup, platform }: {
  message: Message; isOutgoing: boolean; isLastInGroup: boolean; platform: ChatPlatform;
}) {
  const [loaded, setLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const metadata = message.metadata || {};
  const th = getInlineTheme(platform);
  const items = metadata.carousel_items || metadata.items || [];
  const totalCount = items.length;
  const firstItem = items[0];
  const imageUrl = firstItem?.url || metadata.url || metadata.thumbnail_url;

  if (!imageUrl) return <TextMessage message={message} isOutgoing={isOutgoing} isLastInGroup={isLastInGroup} isFirstInGroup={false} platform={platform} />;

  const borderRadius = th ? th.borderRadius : '16px';
  const placeholderBg = th ? th.incomingBg : '#262626';

  return (
    <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
      <div style={{ maxWidth: '70%', borderRadius, overflow: 'hidden' }}>
        <a href={metadata.permalink || imageUrl} target="_blank" rel="noopener noreferrer" className="block relative cursor-pointer hover:opacity-90 transition-opacity">
          {!loaded && !imageError && <div style={{ width: 192, height: 192, backgroundColor: placeholderBg, borderRadius, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><ImageIcon className="w-8 h-8 text-gray-500 animate-pulse" /></div>}
          {imageError ? <div style={{ width: 192, height: 192, backgroundColor: placeholderBg, borderRadius, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><ImageIcon className="w-8 h-8 text-gray-500" /></div>
            : <img src={imageUrl} alt="Carousel" style={{ maxWidth: '100%', maxHeight: 384, borderRadius, imageRendering: 'auto', display: loaded ? undefined : 'none' }} onLoad={() => setLoaded(true)} onError={() => { setImageError(true); setLoaded(true); }} />}
          {totalCount > 1 && <div className="absolute top-2 right-2 bg-black/70 text-white text-xs px-2 py-1 rounded-full">1/{totalCount}</div>}
          {firstItem?.type === 'video' && <div className="absolute inset-0 flex items-center justify-center"><div className="w-12 h-12 rounded-full bg-black/60 flex items-center justify-center"><Play className="w-6 h-6 text-white ml-1" /></div></div>}
        </a>
        {th ? <div style={{ padding: '2px 8px 4px', position: 'relative' }}><InlineTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} th={th} /><span style={{ display: 'inline-block', width: 50, height: 15 }} /></div>
          : <IGTimestamp timestamp={message.timestamp} isOutgoing={isOutgoing} className="mt-1" />}
      </div>
    </div>
  );
}

// ========================= INSTAGRAM TIMESTAMP (className-based, unchanged) =========================

function IGTimestamp({ timestamp, isOutgoing, className = '' }: { timestamp?: string; isOutgoing: boolean; className?: string }) {
  if (!timestamp) return null;
  const display = formatTimeDisplay(timestamp);
  return <p className={`text-[10px] ${isOutgoing ? 'text-white/60' : 'text-gray-500'} text-right ${className}`}>{display}</p>;
}

export default MessageRenderer;
