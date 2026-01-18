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
          className="w-72 md:w-96 h-auto mx-auto"
        />

        {/* Subtitle - pegado al logo con margin negativo */}
        <p
          className="text-xl md:text-2xl text-gray-400 mb-10"
          style={{ marginTop: '-25px' }}
        >
          Automatiza tus DMs con IA
        </p>

        {/* CTA Button - estilo outline púrpura con pulse glow */}
        <button
          onClick={() => navigate('/login')}
          className="group px-10 py-4 text-lg font-semibold rounded-full transition-all duration-300 hover:scale-105 flex items-center gap-2 mx-auto animate-pulse-glow"
          style={{
            background: 'rgba(168, 85, 247, 0.1)',
            border: '2px solid rgba(168, 85, 247, 0.5)',
            color: '#a855f7'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = 'rgba(168, 85, 247, 0.8)';
            e.currentTarget.style.background = 'rgba(168, 85, 247, 0.15)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'rgba(168, 85, 247, 0.5)';
            e.currentTarget.style.background = 'rgba(168, 85, 247, 0.1)';
          }}
        >
          Empezar
          <ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-1" />
        </button>
      </div>

      {/* CSS Animation for pulse glow */}
      <style>{`
        @keyframes pulse-glow {
          0%, 100% {
            box-shadow: 0 0 15px rgba(168, 85, 247, 0.3);
          }
          50% {
            box-shadow: 0 0 30px rgba(168, 85, 247, 0.6);
          }
        }
        .animate-pulse-glow {
          animation: pulse-glow 2s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}
