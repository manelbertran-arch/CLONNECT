import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api, setCreatorId } from '../services/api';
import { Zap } from 'lucide-react';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await api.post('/auth/login', { email, password });
      localStorage.setItem('token', response.data.access_token);

      // P1 FIX: Get creator NAME (not UUID) from user.creators array
      const creatorName = response.data.user?.creators?.[0]?.name || 'stefano_bonanno';
      setCreatorId(creatorName);

      // Verificar onboarding
      const status = await api.get(`/onboarding/${creatorName}/visual-status`);
      if (status.data.onboarding_completed) {
        navigate('/dashboard');
      } else {
        navigate('/onboarding');
      }
    } catch (err) {
      setError('Credenciales incorrectas');
    } finally {
      setLoading(false);
    }
  };

  const handleDemoLogin = async () => {
    setEmail('stefano@stefanobonanno.com');
    setPassword('demo2024');

    setLoading(true);
    try {
      const response = await api.post('/auth/login', {
        email: 'stefano@stefanobonanno.com',
        password: 'demo2024'
      });
      localStorage.setItem('token', response.data.access_token);

      // P1 FIX: Get creator NAME (not UUID) from user.creators array
      const creatorName = response.data.user?.creators?.[0]?.name || 'stefano_bonanno';
      setCreatorId(creatorName);

      const status = await api.get(`/onboarding/${creatorName}/visual-status`);
      if (status.data.onboarding_completed) {
        navigate('/dashboard');
      } else {
        navigate('/onboarding');
      }
    } catch (err) {
      setError('Error en demo login');
    } finally {
      setLoading(false);
    }
  };

  // NO HAY useEffect que verifique sesión
  // NO HAY auto-redirect
  // SIEMPRE mostrar el formulario

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: '#09090b' }}
    >
      {/* Background gradient orbs */}
      <div
        style={{
          position: 'fixed',
          top: '10%',
          left: '10%',
          width: '400px',
          height: '400px',
          background: 'radial-gradient(circle, rgba(168, 85, 247, 0.15) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(60px)',
          pointerEvents: 'none'
        }}
      />
      <div
        style={{
          position: 'fixed',
          bottom: '10%',
          right: '10%',
          width: '300px',
          height: '300px',
          background: 'radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, transparent 70%)',
          borderRadius: '50%',
          filter: 'blur(60px)',
          pointerEvents: 'none'
        }}
      />

      <div
        className="p-8 rounded-2xl w-full max-w-md relative z-10"
        style={{
          background: '#0f0f14',
          border: '1px solid rgba(255, 255, 255, 0.08)'
        }}
      >
        <h1
          className="text-3xl font-bold text-center mb-2"
          style={{
            background: 'linear-gradient(135deg, #a855f7, #6366f1)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent'
          }}
        >
          Clonnect
        </h1>
        <p className="text-center mb-8" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
          Automatiza tus DMs con IA
        </p>

        {error && (
          <div
            className="p-3 rounded-lg mb-4 text-center"
            style={{
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: '#ef4444'
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleLogin}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full p-4 mb-4 rounded-xl text-white outline-none transition-all"
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.08)'
            }}
            onFocus={(e) => e.target.style.borderColor = 'rgba(168, 85, 247, 0.5)'}
            onBlur={(e) => e.target.style.borderColor = 'rgba(255, 255, 255, 0.08)'}
            required
          />
          <input
            type="password"
            placeholder="Contraseña"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full p-4 mb-6 rounded-xl text-white outline-none transition-all"
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.08)'
            }}
            onFocus={(e) => e.target.style.borderColor = 'rgba(168, 85, 247, 0.5)'}
            onBlur={(e) => e.target.style.borderColor = 'rgba(255, 255, 255, 0.08)'}
            required
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full p-4 text-white font-semibold rounded-xl transition-all hover:opacity-90 disabled:opacity-50"
            style={{
              background: 'linear-gradient(135deg, #a855f7, #6366f1)',
              boxShadow: '0 4px 20px rgba(168, 85, 247, 0.3)'
            }}
          >
            {loading ? 'Entrando...' : 'Entrar'}
          </button>
        </form>

        <div className="flex items-center my-6">
          <div className="flex-1 h-px" style={{ background: 'rgba(255, 255, 255, 0.1)' }} />
          <span className="px-4" style={{ color: 'rgba(255, 255, 255, 0.4)' }}>o</span>
          <div className="flex-1 h-px" style={{ background: 'rgba(255, 255, 255, 0.1)' }} />
        </div>

        <button
          onClick={handleDemoLogin}
          disabled={loading}
          className="w-full p-4 font-semibold rounded-xl transition-all hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
          style={{
            background: 'rgba(168, 85, 247, 0.1)',
            border: '1px solid rgba(168, 85, 247, 0.3)',
            color: '#a855f7'
          }}
        >
          <Zap className="w-5 h-5" />
          Demo: Stefano Bonanno
        </button>

        <div className="mt-6 text-center">
          <span style={{ color: 'rgba(255, 255, 255, 0.5)' }}>¿No tienes cuenta? </span>
          <Link
            to="/register"
            className="font-medium hover:opacity-80 transition-opacity"
            style={{ color: '#a855f7' }}
          >
            Regístrate
          </Link>
        </div>

        <div className="mt-5 text-center">
          <Link
            to="/onboarding-intro"
            className="text-base font-medium hover:opacity-80 transition-opacity"
            style={{ color: '#a855f7' }}
          >
            Ver onboarding
          </Link>
        </div>
      </div>
    </div>
  );
}
