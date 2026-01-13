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

      // New users always go to onboarding
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
    <div className="min-h-screen flex items-center justify-center bg-gray-900">
      <div className="bg-gray-800 p-8 rounded-lg w-full max-w-md">
        <h1 className="text-2xl font-bold text-white mb-6">Crear cuenta</h1>

        {error && <div className="bg-red-500 text-white p-2 rounded mb-4">{error}</div>}

        <form onSubmit={handleRegister}>
          <input
            type="text"
            placeholder="Nombre completo"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full p-3 mb-4 bg-gray-700 text-white rounded"
            required
          />
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
            placeholder="Contraseña (mínimo 6 caracteres)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full p-3 mb-4 bg-gray-700 text-white rounded"
            required
            minLength={6}
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full p-3 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Creando cuenta...' : 'Crear cuenta'}
          </button>
        </form>

        <div className="mt-6 text-center">
          <span className="text-gray-400">¿Ya tienes cuenta? </span>
          <Link to="/login" className="text-blue-400 hover:text-blue-300">
            Inicia sesión
          </Link>
        </div>
      </div>
    </div>
  );
}
