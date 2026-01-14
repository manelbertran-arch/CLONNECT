import { useState } from 'react';
import {
  MessageCircle,
  Sparkles,
  Zap,
  Rocket,
  Settings,
  Home,
  Inbox,
  Users,
  Package,
  CheckCircle2,
  Send,
  ChevronRight,
  ChevronLeft
} from 'lucide-react';
import './OnboardingMobile.css';

interface OnboardingMobileProps {
  onComplete: () => void;
}

// Simplified slides for mobile - same content, simpler presentation
const slides = [
  {
    id: 'intro',
    title: 'Clonnect',
    subtitle: 'Tu clon de IA que vende 24/7',
    isIntro: true,
  },
  {
    id: 'welcome',
    title: 'Bienvenido',
    content: 'Has dado el primer paso para automatizar tu negocio y vender 24/7 sin perder tu toque personal.',
  },
  {
    id: 'what-is',
    title: '¿Qué es Clonnect?',
    content: 'Un clon de IA que responde a tus seguidores exactamente como lo harías tú.',
    features: [
      { icon: MessageCircle, title: 'Detecta intención', desc: 'Identifica quién quiere comprar' },
      { icon: Sparkles, title: 'Tu estilo', desc: 'Usa tu tono y vocabulario' },
      { icon: Zap, title: 'Vende 24/7', desc: 'Convierte mientras duermes' },
    ],
  },
  {
    id: 'demo',
    title: 'Demo en vivo',
    content: 'Mira cómo tu clon cierra una venta automáticamente',
    demo: true,
  },
  {
    id: 'steps',
    title: '4 pasos simples',
    content: 'Configura tu clon en minutos',
    steps: [
      { icon: Send, title: 'Conecta canal', desc: 'Instagram, Telegram o WhatsApp' },
      { icon: Package, title: 'Añade productos', desc: 'Cursos, mentorías, servicios' },
      { icon: Sparkles, title: 'Personalidad', desc: 'Tu tono y estilo' },
      { icon: Zap, title: 'Activa', desc: 'Empieza a vender' },
    ],
  },
  {
    id: 'home',
    title: 'Dashboard: Home',
    icon: Home,
    content: 'Tu centro de control con métricas en tiempo real',
    highlights: ['🔥 Hot Leads', '📊 Métricas', '💰 Revenue'],
  },
  {
    id: 'inbox',
    title: 'Dashboard: Inbox',
    icon: Inbox,
    content: 'Todas las conversaciones en un solo lugar',
    highlights: ['💬 Chat unificado', '🎮 Toma el control', '🏷️ Badges automáticos'],
  },
  {
    id: 'leads',
    title: 'Dashboard: Leads',
    icon: Users,
    content: 'Gestiona tu pipeline de ventas visualmente',
    highlights: ['📋 Kanban visual', '🎯 Score automático', '📱 Multi-plataforma'],
  },
  {
    id: 'nurturing',
    title: 'Dashboard: Nurturing',
    icon: Sparkles,
    content: 'Secuencias automáticas que recuperan ventas',
    highlights: ['🛒 Carritos abandonados', '🔥 Leads fríos', '⏰ Timing inteligente'],
  },
  {
    id: 'products',
    title: 'Dashboard: Products',
    icon: Package,
    content: 'Tu catálogo de productos y servicios',
    highlights: ['📦 Gestión fácil', '💳 Links de pago', '📈 Métricas de ventas'],
  },
  {
    id: 'settings',
    title: 'Dashboard: Settings',
    icon: Settings,
    content: 'Configura la personalidad de tu clon',
    highlights: ['🎭 Presets', '🔗 Conexiones', '🧠 Knowledge base'],
  },
  {
    id: 'ready',
    title: '¡Estás listo!',
    content: 'Ahora configura tu clon y empieza a vender',
    isReady: true,
    checklist: [
      'Conectar un canal',
      'Añadir un producto',
      'Configurar personalidad',
      'Activar el bot',
    ],
  },
];

export function OnboardingMobile({ onComplete }: OnboardingMobileProps) {
  const [currentSlide, setCurrentSlide] = useState(0);

  const slide = slides[currentSlide];
  const isFirst = currentSlide === 0;
  const isLast = currentSlide === slides.length - 1;
  const progress = ((currentSlide + 1) / slides.length) * 100;

  const handleNext = () => {
    if (isLast) {
      onComplete();
    } else {
      setCurrentSlide(prev => prev + 1);
    }
  };

  const handlePrev = () => {
    if (!isFirst) {
      setCurrentSlide(prev => prev - 1);
    }
  };

  return (
    <div className="mobile-onboarding">
      {/* Background */}
      <div className="mobile-bg">
        <div className="mobile-orb mobile-orb-1" />
        <div className="mobile-orb mobile-orb-2" />
      </div>

      {/* Progress bar */}
      {!slide.isIntro && (
        <div className="mobile-progress">
          <div className="mobile-progress-fill" style={{ width: `${progress}%` }} />
        </div>
      )}

      {/* Content */}
      <div className="mobile-content">
        {/* Intro slide */}
        {slide.isIntro && (
          <div className="mobile-intro">
            <h1 className="mobile-intro-title" style={{ fontSize: '2.5rem' }}>{slide.title}</h1>
            <p className="mobile-intro-subtitle">{slide.subtitle}</p>
          </div>
        )}

        {/* Ready slide */}
        {slide.isReady && (
          <div className="mobile-ready">
            <div className="mobile-ready-icon">
              <Rocket className="w-12 h-12" />
            </div>
            <h2 className="mobile-slide-title">{slide.title}</h2>
            <p className="mobile-slide-text">{slide.content}</p>
            <div className="mobile-checklist">
              {slide.checklist?.map((item, i) => (
                <div key={i} className="mobile-checklist-item">
                  <CheckCircle2 className="w-5 h-5 text-green-500" />
                  <span>{item}</span>
                </div>
              ))}
            </div>
            <p className="mobile-time">⏱️ 5 minutos</p>
          </div>
        )}

        {/* Regular slides */}
        {!slide.isIntro && !slide.isReady && (
          <div className="mobile-slide">
            {/* Icon for dashboard slides */}
            {slide.icon && (
              <div className="mobile-slide-icon">
                <slide.icon className="w-8 h-8" />
              </div>
            )}

            <h2 className="mobile-slide-title">{slide.title}</h2>
            <p className="mobile-slide-text">{slide.content}</p>

            {/* Features list */}
            {slide.features && (
              <div className="mobile-features">
                {slide.features.map((feature, i) => (
                  <div key={i} className="mobile-feature">
                    <div className="mobile-feature-icon">
                      <feature.icon className="w-5 h-5" />
                    </div>
                    <div>
                      <h4>{feature.title}</h4>
                      <p>{feature.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Steps grid */}
            {slide.steps && (
              <div className="mobile-steps">
                {slide.steps.map((step, i) => (
                  <div key={i} className="mobile-step">
                    <div className="mobile-step-num">{i + 1}</div>
                    <div className="mobile-step-icon">
                      <step.icon className="w-5 h-5" />
                    </div>
                    <h4>{step.title}</h4>
                    <p>{step.desc}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Demo */}
            {slide.demo && (
              <div className="mobile-demo">
                <div className="mobile-chat">
                  <div className="mobile-chat-bubble user">Hola! Me interesa tu curso 👀</div>
                  <div className="mobile-chat-bubble bot">¡Hola! Me alegra que te interese 😊</div>
                  <div className="mobile-chat-bubble user">¿Cuánto cuesta?</div>
                  <div className="mobile-chat-bubble bot">297€. ¿Bizum, tarjeta o PayPal?</div>
                  <div className="mobile-chat-bubble user">Bizum!</div>
                  <div className="mobile-chat-bubble bot">¡Perfecto! 🚀</div>
                </div>
                <div className="mobile-sale">
                  💰 <span>Nueva venta +€297</span>
                </div>
              </div>
            )}

            {/* Highlights */}
            {slide.highlights && (
              <div className="mobile-highlights">
                {slide.highlights.map((h, i) => (
                  <div key={i} className="mobile-highlight">{h}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="mobile-nav">
        {!isFirst && (
          <button className="mobile-nav-btn mobile-nav-prev" onClick={handlePrev}>
            <ChevronLeft className="w-5 h-5" />
          </button>
        )}

        <button className="mobile-nav-btn mobile-nav-next" onClick={handleNext}>
          {isLast ? 'Empezar' : isFirst ? 'Comenzar' : 'Continuar'}
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

      {/* Slide indicator */}
      {!slide.isIntro && (
        <div className="mobile-dots">
          {slides.slice(1).map((_, i) => (
            <div
              key={i}
              className={`mobile-dot ${i + 1 === currentSlide ? 'active' : ''}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default OnboardingMobile;
