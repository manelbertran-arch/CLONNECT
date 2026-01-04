import { useState, useEffect, useCallback } from "react";
import { Rocket, MessageCircle, Users, Sparkles, ShoppingBag, Settings, Home, Zap, Target, Clock, Check, ArrowRight } from "lucide-react";

interface OnboardingProps {
  onComplete: () => void;
}

// Chat messages for the demo
const chatMessages = [
  { role: "user", text: "Hola! Me interesa tu curso de trading 👀" },
  { role: "bot", text: "¡Hola! Me alegra que te interese 😊 Es un curso con 20h de vídeo, comunidad privada y Q&A semanales. ¿Te cuento más?" },
  { role: "user", text: "Sí! ¿Cuánto cuesta?" },
  { role: "bot", text: "297€. Puedes pagar con Bizum, tarjeta o PayPal. ¿Cuál prefieres?" },
  { role: "user", text: "Bizum!" },
  { role: "bot", text: "¡Perfecto! Envía 297€ al 639066982. Avísame cuando lo hagas 🚀" },
  { role: "user", text: "Listo, enviado!" },
  { role: "bot", text: "¡Recibido! 🎉 Te envío el acceso ahora. ¡Bienvenida al curso!" },
];

const timelineSteps = ["Mensaje", "Interés", "Precio", "Pago", "Venta"];

export function Onboarding({ onComplete }: OnboardingProps) {
  const [currentSlide, setCurrentSlide] = useState(0);
  const [started, setStarted] = useState(false);
  const [visibleMessages, setVisibleMessages] = useState<number[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [currentTimelineStep, setCurrentTimelineStep] = useState(0);
  const [showSaleNotification, setShowSaleNotification] = useState(false);
  const [animatedCounters, setAnimatedCounters] = useState<Record<string, number>>({});

  const totalSlides = 12; // 0 = intro, 1-11 = content slides

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!started && (e.key === " " || e.key === "Enter")) {
        e.preventDefault();
        setStarted(true);
        setCurrentSlide(1);
      } else if (started) {
        if (e.key === "ArrowRight" || e.key === " " || e.key === "Enter") {
          e.preventDefault();
          nextSlide();
        } else if (e.key === "ArrowLeft") {
          e.preventDefault();
          prevSlide();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [started, currentSlide]);

  // Chat demo animation (Slide 3)
  useEffect(() => {
    if (currentSlide === 3 && started) {
      setVisibleMessages([]);
      setCurrentTimelineStep(0);
      setShowSaleNotification(false);
      setIsTyping(false);

      let messageIndex = 0;
      const showNextMessage = () => {
        if (messageIndex < chatMessages.length) {
          setIsTyping(true);
          setTimeout(() => {
            setIsTyping(false);
            setVisibleMessages(prev => [...prev, messageIndex]);

            // Update timeline based on message
            if (messageIndex === 0) setCurrentTimelineStep(1);
            if (messageIndex === 2) setCurrentTimelineStep(2);
            if (messageIndex === 4) setCurrentTimelineStep(3);
            if (messageIndex === 6) setCurrentTimelineStep(4);
            if (messageIndex === 7) {
              setCurrentTimelineStep(5);
              setTimeout(() => setShowSaleNotification(true), 500);
            }

            messageIndex++;
            setTimeout(showNextMessage, 1500);
          }, 800);
        }
      };

      const timer = setTimeout(showNextMessage, 1000);
      return () => clearTimeout(timer);
    }
  }, [currentSlide, started]);

  // Counter animation (Slide 5)
  useEffect(() => {
    if (currentSlide === 5 && started) {
      const targets = { hotLeads: 24, followers: 1847, conversion: 12 };
      const duration = 1500;
      const steps = 30;
      const interval = duration / steps;

      Object.entries(targets).forEach(([key, target]) => {
        let current = 0;
        const increment = target / steps;
        const timer = setInterval(() => {
          current += increment;
          if (current >= target) {
            current = target;
            clearInterval(timer);
          }
          setAnimatedCounters(prev => ({ ...prev, [key]: Math.round(current) }));
        }, interval);
      });
    }
  }, [currentSlide, started]);

  const nextSlide = useCallback(() => {
    if (currentSlide < totalSlides - 1) {
      setCurrentSlide(prev => prev + 1);
    } else {
      onComplete();
    }
  }, [currentSlide, onComplete]);

  const prevSlide = useCallback(() => {
    if (currentSlide > 1) {
      setCurrentSlide(prev => prev - 1);
    }
  }, [currentSlide]);

  const handleStart = () => {
    setStarted(true);
    setCurrentSlide(1);
  };

  const progressPercent = started ? ((currentSlide) / (totalSlides - 1)) * 100 : 0;

  // Intro Slide (Slide 0)
  if (!started) {
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden cursor-pointer"
        onClick={handleStart}
        style={{ background: "#09090b" }}
      >
        {/* Animated Orbs */}
        <div className="absolute inset-0 overflow-hidden">
          <div
            className="absolute w-[600px] h-[600px] rounded-full opacity-40 blur-[120px]"
            style={{
              background: "#a855f7",
              top: "10%",
              left: "10%",
              animation: "float 20s ease-in-out infinite",
            }}
          />
          <div
            className="absolute w-[500px] h-[500px] rounded-full opacity-40 blur-[120px]"
            style={{
              background: "#6366f1",
              top: "50%",
              right: "10%",
              animation: "float 25s ease-in-out infinite reverse",
            }}
          />
          <div
            className="absolute w-[400px] h-[400px] rounded-full opacity-40 blur-[120px]"
            style={{
              background: "#22c55e",
              bottom: "10%",
              left: "30%",
              animation: "float 18s ease-in-out infinite",
              animationDelay: "-5s",
            }}
          />
        </div>

        {/* Content */}
        <div className="relative z-10 text-center">
          {/* Logo with glow */}
          <div
            className="mx-auto mb-8 w-32 h-32 rounded-3xl flex items-center justify-center"
            style={{
              background: "linear-gradient(135deg, #a855f7, #6366f1)",
              animation: "glow 3s ease-in-out infinite",
            }}
          >
            <Zap className="w-16 h-16 text-white" />
          </div>

          {/* Title */}
          <h1
            className="text-6xl font-bold mb-4"
            style={{
              fontFamily: "'Space Grotesk', sans-serif",
              background: "linear-gradient(135deg, #a855f7, #6366f1)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            Clonnect
          </h1>

          {/* Subtitle */}
          <p className="text-xl text-white/60 mb-12">
            Tu clon de IA que vende 24/7
          </p>

          {/* CTA Button */}
          <button
            className="px-8 py-4 rounded-xl text-lg font-semibold text-white transition-all"
            style={{
              background: "linear-gradient(135deg, #a855f7, #6366f1)",
              animation: "bounce 2s ease-in-out infinite",
            }}
          >
            Comenzar
          </button>

          <p className="mt-6 text-sm text-white/40">
            Pulsa Enter o haz click para empezar
          </p>
        </div>

        {/* Keyframes */}
        <style>{`
          @keyframes float {
            0%, 100% { transform: translate(0, 0) scale(1); }
            33% { transform: translate(30px, -30px) scale(1.05); }
            66% { transform: translate(-20px, 20px) scale(0.95); }
          }
          @keyframes glow {
            0%, 100% { box-shadow: 0 0 60px rgba(168, 85, 247, 0.5); }
            50% { box-shadow: 0 0 100px rgba(168, 85, 247, 0.8); }
          }
          @keyframes bounce {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-8px); }
          }
          @keyframes celebrate {
            0%, 100% { transform: scale(1) rotate(0deg); }
            25% { transform: scale(1.1) rotate(-5deg); }
            75% { transform: scale(1.1) rotate(5deg); }
          }
          @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
          }
          @keyframes grow {
            from { height: 0; }
            to { height: var(--target-height); }
          }
          @keyframes slideIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
          }
          @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
          }
          @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
        `}</style>
      </div>
    );
  }

  // Content Slides
  return (
    <div
      className="fixed inset-0 z-50 flex flex-col overflow-hidden"
      style={{ background: "#09090b" }}
    >
      {/* Progress Bar */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-white/10">
        <div
          className="h-full transition-all duration-500 ease-out"
          style={{
            width: `${progressPercent}%`,
            background: "linear-gradient(90deg, #a855f7, #6366f1)",
          }}
        />
      </div>

      {/* Main Content */}
      <div className="flex-1 flex items-center justify-center p-8 overflow-auto">
        <div className="w-full max-w-5xl">
          {/* Slide 1: Welcome */}
          {currentSlide === 1 && (
            <div className="text-center animate-fade-in">
              <div
                className="mx-auto mb-6 w-20 h-20 rounded-2xl flex items-center justify-center"
                style={{
                  background: "linear-gradient(135deg, #a855f7, #6366f1)",
                  animation: "glow 3s ease-in-out infinite",
                }}
              >
                <Zap className="w-10 h-10 text-white" />
              </div>
              <h2 className="text-4xl font-bold text-white mb-4" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                Bienvenido a Clonnect
              </h2>
              <p className="text-lg text-white/60 max-w-xl mx-auto">
                Vamos a mostrarte cómo tu clon de IA puede responder mensajes,
                detectar oportunidades de venta y cerrar ventas mientras tú duermes.
              </p>
            </div>
          )}

          {/* Slide 2: What is Clonnect */}
          {currentSlide === 2 && (
            <div className="grid grid-cols-2 gap-12 items-center animate-fade-in">
              <div>
                <h2 className="text-3xl font-bold text-white mb-6" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                  ¿Qué es Clonnect?
                </h2>
                <p className="text-white/60 mb-8">
                  Un clon de IA que habla exactamente como tú, responde a tus seguidores
                  y convierte conversaciones en ventas.
                </p>
                <div className="space-y-4">
                  {[
                    { icon: Target, title: "Detecta intención", desc: "Identifica quién quiere comprar" },
                    { icon: MessageCircle, title: "Responde con tu estilo", desc: "Usa tu tono y vocabulario" },
                    { icon: Clock, title: "Cierra ventas 24/7", desc: "Nunca pierdas una oportunidad" },
                  ].map((item, i) => (
                    <div key={i} className="flex items-start gap-4 p-4 rounded-xl bg-white/5 border border-white/10">
                      <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center flex-shrink-0">
                        <item.icon className="w-5 h-5 text-purple-400" />
                      </div>
                      <div>
                        <h4 className="font-semibold text-white">{item.title}</h4>
                        <p className="text-sm text-white/50">{item.desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Phone Mockup */}
              <div className="flex justify-center">
                <div
                  className="relative w-72 h-[580px] rounded-[3rem] p-3 transition-transform hover:scale-105"
                  style={{
                    background: "linear-gradient(145deg, #1a1a1f, #0d0d10)",
                    border: "3px solid #2a2a30",
                    transform: "perspective(1200px) rotateY(-5deg) rotateX(5deg)",
                  }}
                >
                  <div className="w-full h-full rounded-[2.5rem] bg-[#0f0f14] overflow-hidden">
                    <div className="h-8 bg-[#1a1a1f] flex items-center justify-center">
                      <div className="w-20 h-5 bg-black rounded-full" />
                    </div>
                    <div className="p-4 space-y-3">
                      {[1, 2, 3].map((_, i) => (
                        <div key={i} className={`p-3 rounded-xl ${i % 2 === 0 ? 'bg-white/5 ml-auto w-3/4' : 'bg-purple-500/20 mr-auto w-3/4'}`}>
                          <div className="h-3 bg-white/20 rounded w-full mb-2" />
                          <div className="h-3 bg-white/10 rounded w-2/3" />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Slide 3: Live Demo */}
          {currentSlide === 3 && (
            <div className="grid grid-cols-2 gap-12 items-start animate-fade-in">
              {/* Phone with Chat */}
              <div className="flex justify-center">
                <div
                  className="relative w-80 rounded-[2rem] p-3"
                  style={{
                    background: "linear-gradient(145deg, #1a1a1f, #0d0d10)",
                    border: "2px solid #2a2a30",
                  }}
                >
                  <div className="rounded-[1.5rem] bg-[#0f0f14] overflow-hidden">
                    {/* Phone Header */}
                    <div className="h-14 bg-[#1a1a1f] flex items-center px-4 gap-3 border-b border-white/10">
                      <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-indigo-500" />
                      <div>
                        <div className="text-white font-medium text-sm">Tu Clon de IA</div>
                        <div className="text-green-400 text-xs flex items-center gap-1">
                          <span className="w-2 h-2 bg-green-400 rounded-full" />
                          Online
                        </div>
                      </div>
                    </div>

                    {/* Chat Messages */}
                    <div className="p-4 space-y-3 h-[400px] overflow-y-auto">
                      {chatMessages.map((msg, i) => (
                        visibleMessages.includes(i) && (
                          <div
                            key={i}
                            className={`max-w-[85%] p-3 rounded-2xl text-sm ${
                              msg.role === 'user'
                                ? 'ml-auto bg-purple-500 text-white rounded-br-sm'
                                : 'mr-auto bg-white/10 text-white rounded-bl-sm'
                            }`}
                            style={{ animation: "slideIn 0.3s ease-out" }}
                          >
                            {msg.text}
                          </div>
                        )
                      ))}
                      {isTyping && (
                        <div className="flex gap-1 p-3 bg-white/10 rounded-2xl rounded-bl-sm w-16">
                          <span className="w-2 h-2 bg-white/50 rounded-full" style={{ animation: "pulse 1s infinite" }} />
                          <span className="w-2 h-2 bg-white/50 rounded-full" style={{ animation: "pulse 1s infinite 0.2s" }} />
                          <span className="w-2 h-2 bg-white/50 rounded-full" style={{ animation: "pulse 1s infinite 0.4s" }} />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Timeline */}
              <div>
                <h2 className="text-3xl font-bold text-white mb-2" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                  Demo en vivo
                </h2>
                <p className="text-white/50 mb-8">
                  Mira cómo tu clon convierte una conversación en una venta
                </p>

                <div className="space-y-4">
                  {timelineSteps.map((step, i) => (
                    <div
                      key={i}
                      className={`flex items-center gap-4 p-4 rounded-xl transition-all duration-300 ${
                        currentTimelineStep > i
                          ? 'bg-green-500/20 border border-green-500/30'
                          : currentTimelineStep === i
                            ? 'bg-purple-500/20 border border-purple-500/30'
                            : 'bg-white/5 border border-white/10'
                      }`}
                    >
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                        currentTimelineStep > i
                          ? 'bg-green-500 text-white'
                          : currentTimelineStep === i
                            ? 'bg-purple-500 text-white'
                            : 'bg-white/20 text-white/50'
                      }`}>
                        {currentTimelineStep > i ? <Check className="w-4 h-4" /> : i + 1}
                      </div>
                      <span className={`font-medium ${
                        currentTimelineStep >= i ? 'text-white' : 'text-white/40'
                      }`}>
                        {step}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Sale Notification */}
                {showSaleNotification && (
                  <div
                    className="mt-6 p-4 rounded-xl bg-green-500/20 border border-green-500/30"
                    style={{ animation: "slideIn 0.5s ease-out" }}
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 rounded-full bg-green-500 flex items-center justify-center">
                        <Check className="w-6 h-6 text-white" />
                      </div>
                      <div>
                        <div className="text-green-400 font-bold text-lg">+€297</div>
                        <div className="text-green-400/70 text-sm">¡Venta completada!</div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Slide 4: 4 Steps */}
          {currentSlide === 4 && (
            <div className="animate-fade-in">
              <h2 className="text-3xl font-bold text-white text-center mb-2" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                4 pasos para empezar
              </h2>
              <p className="text-white/50 text-center mb-10">
                Configura tu clon en minutos
              </p>

              <div className="grid grid-cols-2 gap-6">
                {[
                  { num: 1, icon: MessageCircle, title: "Conecta un canal", desc: "Instagram, Telegram o WhatsApp" },
                  { num: 2, icon: ShoppingBag, title: "Añade productos", desc: "Lo que vendes y sus precios" },
                  { num: 3, icon: Sparkles, title: "Configura personalidad", desc: "Cómo habla tu clon" },
                  { num: 4, icon: Zap, title: "Activa", desc: "¡Y listo para vender!" },
                ].map((step, i) => (
                  <div
                    key={i}
                    className="p-6 rounded-2xl bg-white/5 border border-white/10 hover:border-purple-500/50 transition-all hover:-translate-y-1"
                  >
                    <div className="flex items-start gap-4">
                      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500 to-indigo-500 flex items-center justify-center text-xl font-bold text-white">
                        {step.num}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <step.icon className="w-5 h-5 text-purple-400" />
                          <h4 className="font-semibold text-white">{step.title}</h4>
                        </div>
                        <p className="text-sm text-white/50">{step.desc}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Slides 5-10: Dashboard Tour */}
          {currentSlide >= 5 && currentSlide <= 10 && (
            <div className="animate-fade-in">
              {/* Tour Badge */}
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-500/20 border border-purple-500/30 text-purple-400 text-sm mb-6">
                <span>📍</span> Tour del Dashboard
              </div>

              {renderDashboardTourSlide(currentSlide, animatedCounters)}
            </div>
          )}

          {/* Slide 11: Ready */}
          {currentSlide === 11 && (
            <div className="text-center animate-fade-in">
              <div
                className="mx-auto mb-6 w-24 h-24 rounded-full bg-gradient-to-br from-purple-500 to-indigo-500 flex items-center justify-center"
                style={{ animation: "celebrate 1s ease-in-out infinite" }}
              >
                <Rocket className="w-12 h-12 text-white" />
              </div>

              <h2 className="text-4xl font-bold text-white mb-4" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
                ¡Estás listo!
              </h2>
              <p className="text-lg text-white/60 mb-10 max-w-lg mx-auto">
                Tu clon de IA está esperando. Sigue estos pasos para empezar a vender.
              </p>

              <div className="max-w-md mx-auto space-y-3 text-left mb-10">
                {[
                  "Conecta tu canal de mensajes",
                  "Añade tu primer producto",
                  "Configura la personalidad de tu clon",
                  "Activa el bot y empieza a vender",
                ].map((item, i) => (
                  <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-white/5 border border-white/10">
                    <div className="w-6 h-6 rounded-full border-2 border-purple-500 flex items-center justify-center text-xs text-purple-400">
                      {i + 1}
                    </div>
                    <span className="text-white/80">{item}</span>
                  </div>
                ))}
              </div>

              <p className="text-sm text-white/40 mb-4">
                ⏱️ Tiempo estimado: 5 minutos
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Footer Navigation */}
      <div className="p-6 border-t border-white/10">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <span className="text-white/50 text-sm">
            Paso {currentSlide} de {totalSlides - 1}
          </span>

          <div className="flex items-center gap-4">
            {currentSlide > 1 && (
              <button
                onClick={prevSlide}
                className="px-4 py-2 text-white/60 hover:text-white transition-colors"
              >
                ← Anterior
              </button>
            )}
            <button
              onClick={currentSlide === 11 ? onComplete : nextSlide}
              className="px-6 py-3 rounded-xl font-semibold text-white flex items-center gap-2 transition-all hover:scale-105"
              style={{ background: "linear-gradient(135deg, #a855f7, #6366f1)" }}
            >
              {currentSlide === 11 ? (
                <>Empezar a configurar <ArrowRight className="w-5 h-5" /></>
              ) : (
                <>Continuar <ArrowRight className="w-5 h-5" /></>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Global Styles */}
      <style>{`
        @keyframes float {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(30px, -30px) scale(1.05); }
          66% { transform: translate(-20px, 20px) scale(0.95); }
        }
        @keyframes glow {
          0%, 100% { box-shadow: 0 0 60px rgba(168, 85, 247, 0.5); }
          50% { box-shadow: 0 0 100px rgba(168, 85, 247, 0.8); }
        }
        @keyframes bounce {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-8px); }
        }
        @keyframes celebrate {
          0%, 100% { transform: scale(1) rotate(0deg); }
          25% { transform: scale(1.1) rotate(-5deg); }
          75% { transform: scale(1.1) rotate(5deg); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        @keyframes slideIn {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in {
          animation: slideIn 0.5s ease-out;
        }
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
      `}</style>
    </div>
  );
}

// Dashboard Tour Slide Content
function renderDashboardTourSlide(slide: number, counters: Record<string, number>) {
  const slides: Record<number, { emoji: string; title: string; desc: string; features: string[]; mockupType: string }> = {
    5: {
      emoji: "🏠",
      title: "Home",
      desc: "Tu centro de control con todas las métricas importantes de un vistazo.",
      features: ["Métricas en tiempo real", "Revenue del bot", "Gráfico de actividad"],
      mockupType: "home",
    },
    6: {
      emoji: "💬",
      title: "Inbox",
      desc: "Todas las conversaciones de tus canales en un solo lugar.",
      features: ["Lista de conversaciones", "Vista de chat en tiempo real", "Botón 'Tomar control'"],
      mockupType: "inbox",
    },
    7: {
      emoji: "👥",
      title: "Leads",
      desc: "Pipeline visual para ver el estado de cada lead.",
      features: ["Kanban con 4 columnas", "Score de compra", "Drag & drop para mover"],
      mockupType: "leads",
    },
    8: {
      emoji: "✨",
      title: "Nurturing",
      desc: "Secuencias automáticas para nutrir leads que no compran de inmediato.",
      features: ["4 secuencias predefinidas", "Toggles on/off", "Mensajes programados"],
      mockupType: "nurturing",
    },
    9: {
      emoji: "🛍️",
      title: "Products",
      desc: "Gestiona todos tus productos y servicios.",
      features: ["Lista de productos", "Precios y ventas", "Revenue por producto"],
      mockupType: "products",
    },
    10: {
      emoji: "⚙️",
      title: "Settings",
      desc: "Configura tu clon, conexiones y base de conocimiento.",
      features: ["Personalidad del clon", "Conexiones de canales", "FAQs y About"],
      mockupType: "settings",
    },
  };

  const current = slides[slide];
  if (!current) return null;

  return (
    <div className="grid grid-cols-2 gap-12 items-center">
      <div>
        <h2 className="text-3xl font-bold text-white mb-2 flex items-center gap-3" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>
          <span>{current.emoji}</span> {current.title}
        </h2>
        <p className="text-white/60 mb-8">{current.desc}</p>

        <div className="space-y-3">
          {current.features.map((feature, i) => (
            <div key={i} className="flex items-center gap-3 text-white/80">
              <Check className="w-5 h-5 text-green-400" />
              <span>{feature}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Dashboard Mockup */}
      <div className="flex justify-center">
        <DashboardMockup type={current.mockupType} counters={counters} />
      </div>
    </div>
  );
}

// Dashboard Mockup Component
function DashboardMockup({ type, counters }: { type: string; counters: Record<string, number> }) {
  return (
    <div
      className="w-full max-w-lg rounded-xl overflow-hidden border border-white/10"
      style={{
        background: "#0f0f14",
        transform: "perspective(2000px) rotateY(-3deg) rotateX(2deg)",
      }}
    >
      {/* Browser Chrome */}
      <div className="h-8 bg-[#1a1a1f] flex items-center px-3 gap-2">
        <div className="w-3 h-3 rounded-full bg-red-500" />
        <div className="w-3 h-3 rounded-full bg-yellow-500" />
        <div className="w-3 h-3 rounded-full bg-green-500" />
        <div className="flex-1 mx-4 h-5 bg-white/5 rounded" />
      </div>

      <div className="flex">
        {/* Sidebar */}
        <div className="w-14 bg-[#0a0a0d] border-r border-white/10 p-2 space-y-2">
          {[Home, MessageCircle, Users, Sparkles, ShoppingBag, Settings].map((Icon, i) => (
            <div
              key={i}
              className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                (type === 'home' && i === 0) ||
                (type === 'inbox' && i === 1) ||
                (type === 'leads' && i === 2) ||
                (type === 'nurturing' && i === 3) ||
                (type === 'products' && i === 4) ||
                (type === 'settings' && i === 5)
                  ? 'bg-purple-500/20 text-purple-400'
                  : 'text-white/30 hover:text-white/50'
              }`}
            >
              <Icon className="w-5 h-5" />
            </div>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 p-4 min-h-[280px]">
          {type === 'home' && (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-2">
                <div className="p-3 rounded-lg bg-white/5 text-center">
                  <div className="text-xs text-white/50">Hot Leads</div>
                  <div className="text-lg font-bold text-red-400">{counters.hotLeads || 0}</div>
                </div>
                <div className="p-3 rounded-lg bg-white/5 text-center">
                  <div className="text-xs text-white/50">Followers</div>
                  <div className="text-lg font-bold text-white">{counters.followers || 0}</div>
                </div>
                <div className="p-3 rounded-lg bg-white/5 text-center">
                  <div className="text-xs text-white/50">Conversion</div>
                  <div className="text-lg font-bold text-green-400">{counters.conversion || 0}%</div>
                </div>
              </div>
              <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/20">
                <div className="text-xs text-green-400/70">Bot Revenue</div>
                <div className="text-2xl font-bold text-green-400">€2,847</div>
              </div>
              <div className="flex gap-1 items-end h-16">
                {[40, 65, 45, 80, 55, 70, 90].map((h, i) => (
                  <div
                    key={i}
                    className="flex-1 bg-purple-500/50 rounded-t"
                    style={{ height: `${h}%` }}
                  />
                ))}
              </div>
            </div>
          )}

          {type === 'inbox' && (
            <div className="flex gap-3 h-full">
              <div className="w-1/3 space-y-2">
                {['María G.', 'Carlos R.', 'Ana M.'].map((name, i) => (
                  <div key={i} className={`p-2 rounded-lg ${i === 0 ? 'bg-purple-500/20' : 'bg-white/5'}`}>
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-indigo-500" />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-white truncate">{name}</div>
                        <div className="text-[10px] text-white/40 truncate">Último mensaje...</div>
                      </div>
                      {i === 0 && <span className="px-1.5 py-0.5 text-[8px] bg-red-500 text-white rounded">HOT</span>}
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex-1 bg-white/5 rounded-lg p-2 space-y-2">
                <div className="p-2 bg-white/10 rounded-lg text-xs text-white/70 max-w-[80%]">Hola! Me interesa...</div>
                <div className="p-2 bg-purple-500/30 rounded-lg text-xs text-white/70 max-w-[80%] ml-auto">¡Claro! Te cuento...</div>
              </div>
            </div>
          )}

          {type === 'leads' && (
            <div className="flex gap-2">
              {['New', 'Active', 'Hot', 'Customer'].map((col, i) => (
                <div key={i} className="flex-1">
                  <div className="text-[10px] text-white/50 mb-2 text-center">{col}</div>
                  <div className="space-y-1">
                    {[1, 2].slice(0, col === 'Hot' ? 1 : 2).map((_, j) => (
                      <div key={j} className="p-2 rounded bg-white/5 border border-white/10">
                        <div className="w-6 h-6 rounded-full bg-gradient-to-br from-purple-500 to-indigo-500 mb-1" />
                        <div className="h-2 w-12 bg-white/20 rounded mb-1" />
                        <div className="text-[8px] text-green-400">{30 + i * 20}%</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {type === 'nurturing' && (
            <div className="space-y-2">
              {['Carrito Abandonado', 'Interés Frío', 'Reactivación', 'Post Compra'].map((seq, i) => (
                <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-white/5">
                  <div className="flex items-center gap-2">
                    <div className={`w-8 h-4 rounded-full ${i < 2 ? 'bg-green-500' : 'bg-white/20'}`}>
                      <div className={`w-4 h-4 rounded-full bg-white transition-all ${i < 2 ? 'translate-x-4' : ''}`} />
                    </div>
                    <span className="text-xs text-white/70">{seq}</span>
                  </div>
                  <div className="flex gap-1">
                    {['1h', '24h', '72h'].map((t, j) => (
                      <span key={j} className="text-[8px] px-1 py-0.5 bg-white/10 rounded text-white/50">{t}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {type === 'products' && (
            <div className="space-y-2">
              {[
                { name: 'Curso Trading Pro', price: '€297', sales: 45 },
                { name: 'Mentoría 1:1', price: '€997', sales: 12 },
                { name: 'Comunidad VIP', price: '€47/mes', sales: 89 },
              ].map((p, i) => (
                <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-white/5">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded bg-gradient-to-br from-purple-500 to-indigo-500" />
                    <div>
                      <div className="text-xs text-white">{p.name}</div>
                      <div className="text-[10px] text-white/50">{p.price}</div>
                    </div>
                  </div>
                  <div className="text-xs text-green-400">{p.sales} ventas</div>
                </div>
              ))}
            </div>
          )}

          {type === 'settings' && (
            <div className="space-y-3">
              <div className="flex gap-2 border-b border-white/10 pb-2">
                {['Personalidad', 'Conexiones', 'Knowledge'].map((tab, i) => (
                  <span key={i} className={`text-xs px-2 py-1 rounded ${i === 0 ? 'bg-purple-500/20 text-purple-400' : 'text-white/40'}`}>
                    {tab}
                  </span>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-2">
                {['Amigo', 'Mentor', 'Vendedor', 'Pro'].map((preset, i) => (
                  <div key={i} className={`p-2 rounded-lg text-center text-xs ${i === 0 ? 'bg-purple-500/20 border border-purple-500/30 text-purple-400' : 'bg-white/5 text-white/50'}`}>
                    {preset}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Onboarding;
