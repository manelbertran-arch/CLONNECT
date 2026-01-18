import { useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

export default function Welcome() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center bg-black">
      <div className="text-center px-6">
        {/* Logo */}
        <img
          src="/clonnect-logo.png"
          alt="Clonnect"
          className="w-56 md:w-72 h-auto mx-auto mb-8"
        />

        {/* Subtitle */}
        <p className="text-lg md:text-xl text-white/60 mb-12">
          Automatiza tus DMs con IA
        </p>

        {/* CTA Button */}
        <button
          onClick={() => navigate('/login')}
          className="px-10 py-4 text-lg font-medium text-white rounded-full transition-all duration-200 hover:scale-105 hover:shadow-lg hover:shadow-purple-500/25 flex items-center gap-2 mx-auto"
          style={{
            background: 'linear-gradient(135deg, #a855f7, #ec4899)'
          }}
        >
          Empezar
          <ArrowRight className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
}
