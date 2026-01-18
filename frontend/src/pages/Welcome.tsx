import { useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';

export default function Welcome() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center bg-black">
      <div className="text-center px-6 flex flex-col items-center gap-6" style={{ marginTop: '-80px' }}>
        {/* Logo - tamaño grande como antes */}
        <img
          src="/clonnect-logo.png"
          alt="Clonnect"
          className="w-72 md:w-96 h-auto"
        />

        {/* CTA Button - prominente y visible */}
        <button
          onClick={() => navigate('/login')}
          className="group px-8 py-4 text-lg font-semibold rounded-full transition-all duration-300 hover:scale-105 flex items-center gap-3 animate-pulse-glow"
          style={{
            background: 'rgba(168, 85, 247, 0.1)',
            border: '2px solid rgba(168, 85, 247, 0.6)',
            color: '#c084fc'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = '#a855f7';
            e.currentTarget.style.background = 'rgba(168, 85, 247, 0.2)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'rgba(168, 85, 247, 0.6)';
            e.currentTarget.style.background = 'rgba(168, 85, 247, 0.1)';
          }}
        >
          Empezar
          <ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-1" />
        </button>
      </div>

      <style>{`
        @keyframes pulse-glow {
          0%, 100% { box-shadow: 0 0 20px rgba(168, 85, 247, 0.4); }
          50% { box-shadow: 0 0 35px rgba(168, 85, 247, 0.7); }
        }
        .animate-pulse-glow { animation: pulse-glow 2s ease-in-out infinite; }
      `}</style>
    </div>
  );
}
