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

// Only 2 intro slides, then go to clone creation
const slides = [
  {
    id: 'welcome',
    title: 'Bienvenido a Clonnect',
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
      <div className="mobile-progress">
        <div className="mobile-progress-fill" style={{ width: `${progress}%` }} />
      </div>

      {/* Content */}
      <div className="mobile-content">
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
          {isLast ? 'Empezar' : 'Continuar'}
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

      {/* Slide indicator */}
      <div className="mobile-dots">
        {slides.map((_, i) => (
          <div
            key={i}
            className={`mobile-dot ${i === currentSlide ? 'active' : ''}`}
          />
        ))}
      </div>
    </div>
  );
}

export default OnboardingMobile;
