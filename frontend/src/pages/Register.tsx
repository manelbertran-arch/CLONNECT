import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api, setCreatorId } from '../services/api';

export default function Register() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    // Client-side validation
    if (password.length < 6) {
      setError('La contraseña debe tener al menos 6 caracteres');
      setLoading(false);
      return;
    }

    try {
      const response = await api.post('/auth/register', { name, email, password });
      localStorage.setItem('token', response.data.access_token);

      // Get creator NAME from user.creators array and store it
      const creatorName = response.data.user?.creators?.[0]?.name;
      if (creatorName) {
        setCreatorId(creatorName);
      }

      // New users go directly to clone creation
      navigate('/onboarding');
    } catch (err: any) {
      // Handle specific error messages from backend
      const message = err.message || 'Error al crear la cuenta';
      if (message.includes('Email already registered')) {
        setError('Este email ya está registrado');
      } else if (message.includes('Password must be at least')) {
        setError('La contraseña debe tener al menos 6 caracteres');
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  };

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
          Crear cuenta
        </h1>
        <p className="text-center mb-8" style={{ color: 'rgba(255, 255, 255, 0.5)' }}>
          Empieza a automatizar tus DMs hoy
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

        <form onSubmit={handleRegister}>
          <input
            type="text"
            placeholder="Nombre completo"
            value={name}
            onChange={(e) => setName(e.target.value)}
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
            placeholder="Contraseña (mínimo 6 caracteres)"
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
            minLength={6}
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
            {loading ? 'Creando cuenta...' : 'Crear cuenta'}
          </button>
        </form>

        <div className="mt-6 text-center">
          <span style={{ color: 'rgba(255, 255, 255, 0.5)' }}>¿Ya tienes cuenta? </span>
          <Link
            to="/login"
            className="font-medium hover:opacity-80 transition-opacity"
            style={{ color: '#a855f7' }}
          >
            Inicia sesión
          </Link>
        </div>
      </div>
    </div>
  );
}
