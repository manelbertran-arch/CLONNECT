import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api, setCreatorId } from '../services/api';

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
      const creatorName = response.data.user?.creators?.[0]?.name || 'stefano_auto';
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
      const creatorName = response.data.user?.creators?.[0]?.name || 'stefano_auto';
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
    <div className="min-h-screen flex items-center justify-center bg-gray-900">
      <div className="bg-gray-800 p-8 rounded-lg w-full max-w-md">
        <h1 className="text-2xl font-bold text-white mb-6">Clonnect</h1>

        {error && <div className="bg-red-500 text-white p-2 rounded mb-4">{error}</div>}

        <form onSubmit={handleLogin}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full p-3 mb-4 bg-gray-700 text-white rounded"
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full p-3 mb-4 bg-gray-700 text-white rounded"
            required
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full p-3 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            {loading ? 'Entrando...' : 'Entrar'}
          </button>
        </form>

        <div className="mt-4 text-center text-gray-400">o</div>

        <button
          onClick={handleDemoLogin}
          disabled={loading}
          className="w-full mt-4 p-3 bg-purple-600 text-white rounded hover:bg-purple-700"
        >
          Demo: Stefano Bonanno
        </button>

        <div className="mt-6 text-center">
          <span className="text-gray-400">¿No tienes cuenta? </span>
          <Link to="/register" className="text-blue-400 hover:text-blue-300">
            Regístrate
          </Link>
        </div>
      </div>
    </div>
  );
}
