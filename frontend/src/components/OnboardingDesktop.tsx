import { useState, useEffect, useCallback } from 'react';
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
  Instagram,
  Send,
  ChevronRight
} from 'lucide-react';
import './Onboarding.css';

interface OnboardingDesktopProps {
  onComplete: () => void;
}

// Chat messages for demo
const chatMessages = [
  { role: 'user', text: 'Hola! Me interesa tu curso de trading 👀', delay: 0 },
  { role: 'bot', text: '¡Hola! Me alegra que te interese 😊 Es un curso con 20h de vídeo, comunidad privada y Q&A semanales. ¿Te cuento más?', delay: 2500 },
  { role: 'user', text: 'Sí! ¿Cuánto cuesta?', delay: 5000 },
  { role: 'bot', text: '297€. Puedes pagar con Bizum, tarjeta o PayPal. ¿Cuál prefieres?', delay: 7500 },
  { role: 'user', text: 'Bizum!', delay: 10000 },
  { role: 'bot', text: '¡Perfecto! Envía 297€ al 639066982. Avísame cuando lo hagas 🚀', delay: 12500 },
  { role: 'user', text: 'Listo, enviado!', delay: 15000 },
  { role: 'bot', text: '¡Recibido! 🎉 Te envío el acceso ahora. ¡Bienvenida al curso!', delay: 17500 },
];

// Timeline steps for demo
const timelineSteps = [
  { label: 'Mensaje', index: 0 },
  { label: 'Interés', index: 2 },
  { label: 'Precio', index: 4 },
  { label: 'Pago', index: 6 },
  { label: 'Venta', index: 7 },
];

export function OnboardingDesktop({ onComplete }: OnboardingDesktopProps) {
  const [currentSlide, setCurrentSlide] = useState(0);
  const [isStarted, setIsStarted] = useState(false);
  const [visibleMessages, setVisibleMessages] = useState<number[]>([]);
  const [typingVisible, setTypingVisible] = useState(false);
  const [showSaleNotification, setShowSaleNotification] = useState(false);
  const [countersAnimated, setCountersAnimated] = useState(false);

  const totalSlides = 12; // 0 (intro) + 11 slides

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!isStarted && (e.key === ' ' || e.key === 'Enter')) {
      e.preventDefault();
      setIsStarted(true);
      setCurrentSlide(1);
      return;
    }

    if (!isStarted) return;

    if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      if (currentSlide < totalSlides - 1) {
        setCurrentSlide(prev => prev + 1);
      } else {
        onComplete();
      }
    } else if (e.key === 'ArrowLeft' && currentSlide > 1) {
      e.preventDefault();
      setCurrentSlide(prev => prev - 1);
    }
  }, [isStarted, currentSlide, onComplete]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // Chat demo animation for slide 3
  useEffect(() => {
    if (currentSlide !== 3) {
      setVisibleMessages([]);
      setTypingVisible(false);
      setShowSaleNotification(false);
      return;
    }

    setVisibleMessages([]);
    setTypingVisible(false);
    setShowSaleNotification(false);

    const timeouts: NodeJS.Timeout[] = [];

    chatMessages.forEach((msg, index) => {
      // Show typing indicator before bot messages
      if (msg.role === 'bot') {
        timeouts.push(setTimeout(() => {
          setTypingVisible(true);
        }, msg.delay - 1000));
      }

      timeouts.push(setTimeout(() => {
        setTypingVisible(false);
        setVisibleMessages(prev => [...prev, index]);

        // Show sale notification after last message
        if (index === chatMessages.length - 1) {
          setTimeout(() => setShowSaleNotification(true), 500);
        }
      }, msg.delay));
    });

    return () => timeouts.forEach(clearTimeout);
  }, [currentSlide]);

  // Counter animation for slide 5
  useEffect(() => {
    if (currentSlide === 5 && !countersAnimated) {
      setCountersAnimated(true);
    }
  }, [currentSlide, countersAnimated]);

  const handleNext = () => {
    if (currentSlide < totalSlides - 1) {
      setCurrentSlide(prev => prev + 1);
    } else {
      onComplete();
    }
  };

  const handleStart = () => {
    setIsStarted(true);
    setCurrentSlide(1);
  };

  // Get current timeline step based on visible messages
  const getCurrentTimelineStep = () => {
    const lastVisibleIndex = visibleMessages[visibleMessages.length - 1] ?? -1;
    for (let i = timelineSteps.length - 1; i >= 0; i--) {
      if (lastVisibleIndex >= timelineSteps[i].index) {
        return i;
      }
    }
    return -1;
  };

  // Animated counter component
  const AnimatedCounter = ({ target, suffix = '' }: { target: number; suffix?: string }) => {
    const [count, setCount] = useState(0);

    useEffect(() => {
      if (!countersAnimated || currentSlide !== 5) return;

      const duration = 1500;
      const steps = 60;
      const increment = target / steps;
      let current = 0;

      const timer = setInterval(() => {
        current += increment;
        if (current >= target) {
          setCount(target);
          clearInterval(timer);
        } else {
          setCount(Math.floor(current));
        }
      }, duration / steps);

      return () => clearInterval(timer);
    }, [target, countersAnimated]);

    return <span>{count}{suffix}</span>;
  };

  // Render intro slide (slide 0)
  if (!isStarted) {
    return (
      <div className="onboarding-overlay">
        <div className="onboarding-orbs">
          <div className="orb orb-purple" />
          <div className="orb orb-indigo" />
          <div className="orb orb-green" />
        </div>

        <div className="intro-content" onClick={handleStart}>
          <div className="intro-logo">
            <div className="logo-glow">
              <svg viewBox="0 0 40 40" className="logo-icon">
                <circle cx="20" cy="20" r="18" fill="none" stroke="currentColor" strokeWidth="2" />
                <circle cx="20" cy="20" r="8" fill="currentColor" />
              </svg>
            </div>
          </div>

          <h1 className="intro-title">
            <span className="gradient-text-onboarding">Clonnect</span>
          </h1>

          <p className="intro-subtitle">Tu clon de IA que vende 24/7</p>

          <button className="intro-button bounce-animation" onClick={handleStart}>
            Comenzar
            <ChevronRight className="w-5 h-5" />
          </button>

          <p className="intro-hint">Pulsa espacio o haz click para empezar</p>
        </div>
      </div>
    );
  }

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-orbs">
        <div className="orb orb-purple" />
        <div className="orb orb-indigo" />
        <div className="orb orb-green" />
      </div>

      {/* Progress bar */}
      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${(currentSlide / (totalSlides - 1)) * 100}%` }}
        />
      </div>

      {/* Slide content */}
      <div className="slide-container">
        {/* Slide 1: Welcome */}
        {currentSlide === 1 && (
          <div className="slide slide-center">
            <div className="slide-logo-small">
              <svg viewBox="0 0 40 40" className="logo-icon-small">
                <circle cx="20" cy="20" r="18" fill="none" stroke="currentColor" strokeWidth="2" />
                <circle cx="20" cy="20" r="8" fill="currentColor" />
              </svg>
            </div>
            <h2 className="slide-title">Bienvenido a <span className="gradient-text-onboarding">Clonnect</span></h2>
            <p className="slide-text">
              Has dado el primer paso para automatizar tu negocio y vender 24/7 sin perder tu toque personal.
            </p>
            <p className="slide-text-secondary">
              En los próximos minutos te mostraremos cómo funciona y cómo configurar tu clon de IA.
            </p>
          </div>
        )}

        {/* Slide 2: What is Clonnect */}
        {currentSlide === 2 && (
          <div className="slide slide-split">
            <div className="slide-left">
              <h2 className="slide-title">¿Qué es <span className="gradient-text-onboarding">Clonnect</span>?</h2>
              <p className="slide-text">
                Un clon de IA que responde a tus seguidores exactamente como lo harías tú, pero sin que tengas que estar pendiente.
              </p>

              <div className="features-list">
                <div className="feature-item">
                  <div className="feature-icon">
                    <MessageCircle className="w-5 h-5" />
                  </div>
                  <div>
                    <h4>Detecta intención</h4>
                    <p>Identifica quién quiere comprar y quién solo pregunta</p>
                  </div>
                </div>

                <div className="feature-item">
                  <div className="feature-icon">
                    <Sparkles className="w-5 h-5" />
                  </div>
                  <div>
                    <h4>Responde con tu estilo</h4>
                    <p>Usa tu tono, vocabulario y forma de hablar</p>
                  </div>
                </div>

                <div className="feature-item">
                  <div className="feature-icon">
                    <Zap className="w-5 h-5" />
                  </div>
                  <div>
                    <h4>Cierra ventas 24/7</h4>
                    <p>Convierte seguidores en clientes mientras duermes</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="slide-right">
              <div className="phone-mockup">
                <div className="phone-notch" />
                <div className="phone-screen">
                  <div className="phone-header">
                    <div className="phone-avatar" />
                    <span>Tu Clon IA</span>
                  </div>
                  <div className="phone-chat">
                    <div className="chat-bubble user">Hola, me interesa tu curso</div>
                    <div className="chat-bubble bot">¡Hola! Claro, te cuento todo 😊</div>
                    <div className="chat-bubble user">¿Cuánto cuesta?</div>
                    <div className="chat-bubble bot">297€ con acceso de por vida 🚀</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Slide 3: Live Demo */}
        {currentSlide === 3 && (
          <div className="slide slide-demo">
            <div className="demo-header">
              <h2 className="slide-title">Demo en <span className="gradient-text-onboarding">vivo</span></h2>
              <p className="slide-text">Mira cómo tu clon cierra una venta automáticamente</p>
            </div>

            <div className="demo-content">
              {/* Timeline */}
              <div className="demo-timeline">
                {timelineSteps.map((step, index) => (
                  <div
                    key={step.label}
                    className={`timeline-step ${index <= getCurrentTimelineStep() ? 'active' : ''} ${index < getCurrentTimelineStep() ? 'done' : ''}`}
                  >
                    <div className="timeline-dot" />
                    <span>{step.label}</span>
                  </div>
                ))}
              </div>

              {/* Phone with chat */}
              <div className="demo-phone">
                <div className="phone-mockup large">
                  <div className="phone-notch" />
                  <div className="phone-screen">
                    <div className="phone-header">
                      <Instagram className="w-4 h-4" />
                      <span>Instagram DM</span>
                    </div>
                    <div className="phone-chat demo-chat">
                      {chatMessages.map((msg, index) => (
                        visibleMessages.includes(index) && (
                          <div
                            key={index}
                            className={`chat-bubble ${msg.role} fade-in`}
                          >
                            {msg.text}
                          </div>
                        )
                      ))}
                      {typingVisible && (
                        <div className="typing-indicator">
                          <span /><span /><span />
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Sale notification */}
                {showSaleNotification && (
                  <div className="sale-notification">
                    <div className="sale-icon">💰</div>
                    <div className="sale-text">
                      <span className="sale-label">Nueva venta</span>
                      <span className="sale-amount">+€297</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Slide 4: 4 Steps */}
        {currentSlide === 4 && (
          <div className="slide slide-center">
            <h2 className="slide-title">Configura tu clon en <span className="gradient-text-onboarding">4 pasos</span></h2>
            <p className="slide-text">Es más fácil de lo que piensas</p>

            <div className="steps-grid">
              <div className="step-card">
                <div className="step-number">1</div>
                <div className="step-icon"><Send className="w-6 h-6" /></div>
                <h4>Conecta tu canal</h4>
                <p>Instagram, Telegram o WhatsApp</p>
              </div>

              <div className="step-card">
                <div className="step-number">2</div>
                <div className="step-icon"><Package className="w-6 h-6" /></div>
                <h4>Añade productos</h4>
                <p>Cursos, mentorías, servicios...</p>
              </div>

              <div className="step-card">
                <div className="step-number">3</div>
                <div className="step-icon"><Sparkles className="w-6 h-6" /></div>
                <h4>Configura personalidad</h4>
                <p>Tu tono, estilo y vocabulario</p>
              </div>

              <div className="step-card">
                <div className="step-number">4</div>
                <div className="step-icon"><Zap className="w-6 h-6" /></div>
                <h4>Activa el bot</h4>
                <p>Y empieza a vender 24/7</p>
              </div>
            </div>
          </div>
        )}

        {/* Slide 5: Tour - Home */}
        {currentSlide === 5 && (
          <div className="slide slide-tour">
            <div className="tour-badge">📍 Tour del Dashboard</div>
            <h2 className="slide-title"><Home className="inline w-8 h-8 mr-2" /> Home</h2>
            <p className="slide-text">Tu centro de control con métricas en tiempo real</p>

            <div className="tour-features">
              <div className="tour-feature">
                <span className="tour-feature-icon">🔥</span>
                <span>Hot Leads en tiempo real</span>
              </div>
              <div className="tour-feature">
                <span className="tour-feature-icon">📊</span>
                <span>Métricas de conversión</span>
              </div>
              <div className="tour-feature">
                <span className="tour-feature-icon">💰</span>
                <span>Revenue del bot</span>
              </div>
            </div>

            <div className="dashboard-mockup">
              <div className="browser-chrome">
                <div className="browser-dots">
                  <span className="dot red" />
                  <span className="dot yellow" />
                  <span className="dot green" />
                </div>
                <span className="browser-url">app.clonnect.io/dashboard</span>
              </div>
              <div className="browser-content">
                <div className="mock-sidebar">
                  <div className="mock-nav-item active"><Home className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Inbox className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Users className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Package className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Settings className="w-4 h-4" /></div>
                </div>
                <div className="mock-main">
                  <div className="mock-metrics">
                    <div className="mock-metric">
                      <span className="mock-metric-label">Hot Leads</span>
                      <span className="mock-metric-value">
                        {currentSlide === 5 ? <AnimatedCounter target={24} /> : '24'}
                      </span>
                    </div>
                    <div className="mock-metric">
                      <span className="mock-metric-label">Followers</span>
                      <span className="mock-metric-value">
                        {currentSlide === 5 ? <AnimatedCounter target={1847} /> : '1,847'}
                      </span>
                    </div>
                    <div className="mock-metric">
                      <span className="mock-metric-label">Conversion</span>
                      <span className="mock-metric-value">
                        {currentSlide === 5 ? <AnimatedCounter target={12} suffix="%" /> : '12%'}
                      </span>
                    </div>
                  </div>
                  <div className="mock-chart">
                    <div className="chart-bars">
                      <div className="chart-bar" style={{ '--h': '40%' } as React.CSSProperties} />
                      <div className="chart-bar" style={{ '--h': '65%' } as React.CSSProperties} />
                      <div className="chart-bar" style={{ '--h': '45%' } as React.CSSProperties} />
                      <div className="chart-bar" style={{ '--h': '80%' } as React.CSSProperties} />
                      <div className="chart-bar" style={{ '--h': '55%' } as React.CSSProperties} />
                      <div className="chart-bar" style={{ '--h': '90%' } as React.CSSProperties} />
                      <div className="chart-bar" style={{ '--h': '70%' } as React.CSSProperties} />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Slide 6: Tour - Inbox */}
        {currentSlide === 6 && (
          <div className="slide slide-tour">
            <div className="tour-badge">📍 Tour del Dashboard</div>
            <h2 className="slide-title"><Inbox className="inline w-8 h-8 mr-2" /> Inbox</h2>
            <p className="slide-text">Todas las conversaciones en un solo lugar</p>

            <div className="tour-features">
              <div className="tour-feature">
                <span className="tour-feature-icon">💬</span>
                <span>Chat unificado multi-plataforma</span>
              </div>
              <div className="tour-feature">
                <span className="tour-feature-icon">🎮</span>
                <span>Toma el control cuando quieras</span>
              </div>
              <div className="tour-feature">
                <span className="tour-feature-icon">🏷️</span>
                <span>Badges HOT, NEW automáticos</span>
              </div>
            </div>

            <div className="dashboard-mockup">
              <div className="browser-chrome">
                <div className="browser-dots">
                  <span className="dot red" />
                  <span className="dot yellow" />
                  <span className="dot green" />
                </div>
                <span className="browser-url">app.clonnect.io/inbox</span>
              </div>
              <div className="browser-content">
                <div className="mock-sidebar">
                  <div className="mock-nav-item"><Home className="w-4 h-4" /></div>
                  <div className="mock-nav-item active"><Inbox className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Users className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Package className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Settings className="w-4 h-4" /></div>
                </div>
                <div className="mock-main inbox-layout">
                  <div className="inbox-list">
                    <div className="inbox-item">
                      <div className="inbox-avatar">M</div>
                      <div className="inbox-info">
                        <span className="inbox-name">María García</span>
                        <span className="inbox-preview">Listo, enviado!</span>
                      </div>
                      <span className="inbox-badge hot">HOT</span>
                    </div>
                    <div className="inbox-item">
                      <div className="inbox-avatar">P</div>
                      <div className="inbox-info">
                        <span className="inbox-name">Pedro López</span>
                        <span className="inbox-preview">¿Cuánto cuesta?</span>
                      </div>
                      <span className="inbox-badge new">NEW</span>
                    </div>
                    <div className="inbox-item">
                      <div className="inbox-avatar">A</div>
                      <div className="inbox-info">
                        <span className="inbox-name">Ana Martínez</span>
                        <span className="inbox-preview">Gracias!</span>
                      </div>
                    </div>
                  </div>
                  <div className="inbox-chat">
                    <div className="chat-bubble user small">Me interesa el curso</div>
                    <div className="chat-bubble bot small">¡Genial! Te cuento...</div>
                    <button className="take-control-btn">Tomar control</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Slide 7: Tour - Leads */}
        {currentSlide === 7 && (
          <div className="slide slide-tour">
            <div className="tour-badge">📍 Tour del Dashboard</div>
            <h2 className="slide-title"><Users className="inline w-8 h-8 mr-2" /> Leads</h2>
            <p className="slide-text">Gestiona tu pipeline de ventas visualmente</p>

            <div className="tour-features">
              <div className="tour-feature">
                <span className="tour-feature-icon">📋</span>
                <span>Kanban visual drag & drop</span>
              </div>
              <div className="tour-feature">
                <span className="tour-feature-icon">🎯</span>
                <span>Score de intención automático</span>
              </div>
              <div className="tour-feature">
                <span className="tour-feature-icon">📱</span>
                <span>Multi-plataforma unificado</span>
              </div>
            </div>

            <div className="dashboard-mockup">
              <div className="browser-chrome">
                <div className="browser-dots">
                  <span className="dot red" />
                  <span className="dot yellow" />
                  <span className="dot green" />
                </div>
                <span className="browser-url">app.clonnect.io/leads</span>
              </div>
              <div className="browser-content">
                <div className="mock-sidebar">
                  <div className="mock-nav-item"><Home className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Inbox className="w-4 h-4" /></div>
                  <div className="mock-nav-item active"><Users className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Package className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Settings className="w-4 h-4" /></div>
                </div>
                <div className="mock-main kanban-layout">
                  <div className="kanban-column">
                    <div className="kanban-header">New <span className="kanban-count">3</span></div>
                    <div className="kanban-card">
                      <div className="kanban-avatar">J</div>
                      <span>Juan</span>
                      <span className="kanban-score">25%</span>
                    </div>
                  </div>
                  <div className="kanban-column">
                    <div className="kanban-header">Active <span className="kanban-count">5</span></div>
                    <div className="kanban-card">
                      <div className="kanban-avatar">L</div>
                      <span>Laura</span>
                      <span className="kanban-score">45%</span>
                    </div>
                  </div>
                  <div className="kanban-column hot">
                    <div className="kanban-header">Hot <span className="kanban-count">2</span></div>
                    <div className="kanban-card">
                      <div className="kanban-avatar">M</div>
                      <span>María</span>
                      <span className="kanban-score hot">78%</span>
                    </div>
                  </div>
                  <div className="kanban-column success">
                    <div className="kanban-header">Customer <span className="kanban-count">8</span></div>
                    <div className="kanban-card">
                      <div className="kanban-avatar">P</div>
                      <span>Pedro</span>
                      <span className="kanban-score success">✓</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Slide 8: Tour - Nurturing */}
        {currentSlide === 8 && (
          <div className="slide slide-tour">
            <div className="tour-badge">📍 Tour del Dashboard</div>
            <h2 className="slide-title"><Sparkles className="inline w-8 h-8 mr-2" /> Nurturing</h2>
            <p className="slide-text">Secuencias automáticas que recuperan ventas perdidas</p>

            <div className="tour-features">
              <div className="tour-feature">
                <span className="tour-feature-icon">🛒</span>
                <span>Recupera carritos abandonados</span>
              </div>
              <div className="tour-feature">
                <span className="tour-feature-icon">🔥</span>
                <span>Reactiva leads fríos</span>
              </div>
              <div className="tour-feature">
                <span className="tour-feature-icon">⏰</span>
                <span>Timing inteligente</span>
              </div>
            </div>

            <div className="dashboard-mockup">
              <div className="browser-chrome">
                <div className="browser-dots">
                  <span className="dot red" />
                  <span className="dot yellow" />
                  <span className="dot green" />
                </div>
                <span className="browser-url">app.clonnect.io/nurturing</span>
              </div>
              <div className="browser-content">
                <div className="mock-sidebar">
                  <div className="mock-nav-item"><Home className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Inbox className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Users className="w-4 h-4" /></div>
                  <div className="mock-nav-item active"><Sparkles className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Settings className="w-4 h-4" /></div>
                </div>
                <div className="mock-main nurturing-layout">
                  <div className="nurturing-sequence">
                    <div className="sequence-header">
                      <span>🛒 Carrito Abandonado</span>
                      <div className="toggle on" />
                    </div>
                    <div className="sequence-steps">1h → 24h → 72h</div>
                    <div className="sequence-stats">12 pending · 45 sent</div>
                  </div>
                  <div className="nurturing-sequence">
                    <div className="sequence-header">
                      <span>❄️ Interés Frío</span>
                      <div className="toggle on" />
                    </div>
                    <div className="sequence-steps">24h → 72h → 7d</div>
                    <div className="sequence-stats">8 pending · 23 sent</div>
                  </div>
                  <div className="nurturing-sequence">
                    <div className="sequence-header">
                      <span>🔄 Reactivación</span>
                      <div className="toggle off" />
                    </div>
                    <div className="sequence-steps">7d → 14d → 30d</div>
                    <div className="sequence-stats">0 pending · 0 sent</div>
                  </div>
                  <div className="nurturing-sequence">
                    <div className="sequence-header">
                      <span>🎁 Post Compra</span>
                      <div className="toggle on" />
                    </div>
                    <div className="sequence-steps">1d → 7d → 30d</div>
                    <div className="sequence-stats">5 pending · 18 sent</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Slide 9: Tour - Products */}
        {currentSlide === 9 && (
          <div className="slide slide-tour">
            <div className="tour-badge">📍 Tour del Dashboard</div>
            <h2 className="slide-title"><Package className="inline w-8 h-8 mr-2" /> Products</h2>
            <p className="slide-text">Tu catálogo de productos y servicios</p>

            <div className="tour-features">
              <div className="tour-feature">
                <span className="tour-feature-icon">📦</span>
                <span>Gestión de productos fácil</span>
              </div>
              <div className="tour-feature">
                <span className="tour-feature-icon">💳</span>
                <span>Links de pago integrados</span>
              </div>
              <div className="tour-feature">
                <span className="tour-feature-icon">📈</span>
                <span>Métricas de ventas</span>
              </div>
            </div>

            <div className="dashboard-mockup">
              <div className="browser-chrome">
                <div className="browser-dots">
                  <span className="dot red" />
                  <span className="dot yellow" />
                  <span className="dot green" />
                </div>
                <span className="browser-url">app.clonnect.io/products</span>
              </div>
              <div className="browser-content">
                <div className="mock-sidebar">
                  <div className="mock-nav-item"><Home className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Inbox className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Users className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Sparkles className="w-4 h-4" /></div>
                  <div className="mock-nav-item active"><Package className="w-4 h-4" /></div>
                </div>
                <div className="mock-main products-layout">
                  <div className="product-row">
                    <div className="product-icon">📚</div>
                    <div className="product-info">
                      <span className="product-name">Curso Trading Pro</span>
                      <span className="product-type">Curso</span>
                    </div>
                    <span className="product-price">€297</span>
                    <span className="product-sales">24 ventas</span>
                    <span className="product-revenue">€7,128</span>
                  </div>
                  <div className="product-row">
                    <div className="product-icon">🎯</div>
                    <div className="product-info">
                      <span className="product-name">Mentoría 1:1</span>
                      <span className="product-type">Servicio</span>
                    </div>
                    <span className="product-price">€497</span>
                    <span className="product-sales">8 ventas</span>
                    <span className="product-revenue">€3,976</span>
                  </div>
                  <div className="product-row">
                    <div className="product-icon">📖</div>
                    <div className="product-info">
                      <span className="product-name">eBook Starter</span>
                      <span className="product-type">Digital</span>
                    </div>
                    <span className="product-price">€47</span>
                    <span className="product-sales">67 ventas</span>
                    <span className="product-revenue">€3,149</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Slide 10: Tour - Settings */}
        {currentSlide === 10 && (
          <div className="slide slide-tour">
            <div className="tour-badge">📍 Tour del Dashboard</div>
            <h2 className="slide-title"><Settings className="inline w-8 h-8 mr-2" /> Settings</h2>
            <p className="slide-text">Configura la personalidad de tu clon</p>

            <div className="tour-features">
              <div className="tour-feature">
                <span className="tour-feature-icon">🎭</span>
                <span>Presets de personalidad</span>
              </div>
              <div className="tour-feature">
                <span className="tour-feature-icon">🔗</span>
                <span>Conexiones de canales</span>
              </div>
              <div className="tour-feature">
                <span className="tour-feature-icon">🧠</span>
                <span>Base de conocimiento</span>
              </div>
            </div>

            <div className="dashboard-mockup">
              <div className="browser-chrome">
                <div className="browser-dots">
                  <span className="dot red" />
                  <span className="dot yellow" />
                  <span className="dot green" />
                </div>
                <span className="browser-url">app.clonnect.io/settings</span>
              </div>
              <div className="browser-content">
                <div className="mock-sidebar">
                  <div className="mock-nav-item"><Home className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Inbox className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Users className="w-4 h-4" /></div>
                  <div className="mock-nav-item"><Sparkles className="w-4 h-4" /></div>
                  <div className="mock-nav-item active"><Settings className="w-4 h-4" /></div>
                </div>
                <div className="mock-main settings-layout">
                  <div className="settings-tabs">
                    <span className="tab active">Personalidad</span>
                    <span className="tab">Conexiones</span>
                    <span className="tab">Knowledge</span>
                  </div>
                  <div className="personality-presets">
                    <div className="preset-card active">
                      <span className="preset-icon">😊</span>
                      <span className="preset-name">Amigo</span>
                    </div>
                    <div className="preset-card">
                      <span className="preset-icon">🎓</span>
                      <span className="preset-name">Mentor</span>
                    </div>
                    <div className="preset-card">
                      <span className="preset-icon">💼</span>
                      <span className="preset-name">Vendedor</span>
                    </div>
                    <div className="preset-card">
                      <span className="preset-icon">⚡</span>
                      <span className="preset-name">Pro</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Slide 11: Ready */}
        {currentSlide === 11 && (
          <div className="slide slide-center slide-ready">
            <div className="ready-icon celebrate-animation">
              <Rocket className="w-16 h-16" />
            </div>

            <h2 className="slide-title">¡Estás <span className="gradient-text-onboarding">listo</span>!</h2>
            <p className="slide-text">Ahora configura tu clon y empieza a vender</p>

            <div className="checklist">
              <div className="checklist-item">
                <CheckCircle2 className="w-5 h-5 text-green-500" />
                <span>Conectar un canal (Instagram, Telegram o WhatsApp)</span>
              </div>
              <div className="checklist-item">
                <CheckCircle2 className="w-5 h-5 text-green-500" />
                <span>Añadir al menos un producto</span>
              </div>
              <div className="checklist-item">
                <CheckCircle2 className="w-5 h-5 text-green-500" />
                <span>Configurar la personalidad de tu clon</span>
              </div>
              <div className="checklist-item">
                <CheckCircle2 className="w-5 h-5 text-green-500" />
                <span>Activar el bot</span>
              </div>
            </div>

            <p className="time-estimate">⏱️ Tiempo estimado: 5 minutos</p>
          </div>
        )}
      </div>

      {/* Footer navigation */}
      <div className="slide-footer">
        <span className="slide-counter">
          Paso {currentSlide} de {totalSlides - 1}
        </span>
        <button className="next-button" onClick={handleNext}>
          {currentSlide === totalSlides - 1 ? 'Empezar a configurar' : 'Continuar'}
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}

export default OnboardingDesktop;
