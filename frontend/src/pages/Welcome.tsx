import { useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

export default function Welcome() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center bg-black">
      <div className="text-center px-6">
        {/* Logo (incluye CLONNECT + FROM FOLLOW TO HELLO) */}
        <img
          src="/clonnect-logo.png"
          alt="Clonnect"
          className="w-56 md:w-64 h-auto mx-auto"
        />

        {/* Subtitle - pegado al logo */}
        <p className="text-2xl md:text-3xl text-gray-400 -mt-2 mb-10">
          Automatiza tus DMs con IA
        </p>

        {/* CTA Button - mismo gradient que botón Entrar */}
        <button
          onClick={() => navigate('/login')}
          className="px-10 py-4 text-lg font-semibold text-white rounded-xl transition-all duration-200 hover:opacity-90 hover:shadow-[0_8px_32px_rgba(168,85,247,0.4)] flex items-center gap-2 mx-auto"
          style={{
            background: 'linear-gradient(135deg, #a855f7, #6366f1)',
            boxShadow: '0 4px 20px rgba(168, 85, 247, 0.3)'
          }}
        >
          Empezar
          <ArrowRight className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
