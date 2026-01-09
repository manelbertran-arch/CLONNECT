/**
 * Login Page with real email/password authentication
 * Uses JWT tokens for secure authentication
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { API_URL, CREATOR_ID } from "@/services/api";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  // Check onboarding status and navigate accordingly
  const checkOnboardingAndNavigate = async () => {
    try {
      const response = await fetch(`${API_URL}/onboarding/${CREATOR_ID}/visual-status`);
      if (response.ok) {
        const data = await response.json();
        if (data.onboarding_completed) {
          navigate("/dashboard");
        } else {
          navigate("/onboarding");
        }
      } else {
        // If API fails, go to onboarding to be safe
        navigate("/onboarding");
      }
    } catch (err) {
      console.error("Failed to check onboarding status:", err);
      // Default to onboarding if check fails
      navigate("/onboarding");
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email.trim()) {
      setError("Por favor ingresa tu email");
      return;
    }
    if (!password) {
      setError("Por favor ingresa tu contraseña");
      return;
    }

    setIsLoading(true);
    setError("");

    try {
      await login(email.trim(), password);
      await checkOnboardingAndNavigate();
    } catch (err: any) {
      console.error("Login error:", err);
      if (err.message?.includes("Invalid email or password")) {
        setError("Email o contraseña incorrectos");
      } else {
        setError(err.message || "Error al iniciar sesión. Intenta de nuevo.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Demo login for Stefano
  const handleDemoLogin = async () => {
    setEmail("stefano@stefanobonanno.com");
    setPassword("demo2024");
    setIsLoading(true);
    setError("");

    try {
      await login("stefano@stefanobonanno.com", "demo2024");
      await checkOnboardingAndNavigate();
    } catch (err: any) {
      console.error("Demo login error:", err);
      setError("Error en login de demo. El servidor puede estar reiniciando.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-purple-800 to-indigo-900 flex items-center justify-center p-4">
      <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 w-full max-w-md border border-white/20">
        <div className="text-center mb-8">
          <img
            src="/clonnect-logo.png"
            alt="Clonnect"
            className="w-16 h-16 mx-auto mb-4 object-contain"
          />
          <h1 className="text-3xl font-bold text-white mb-2">Clonnect</h1>
          <p className="text-purple-200">Inicia sesión en tu cuenta</p>
        </div>

        {/* Demo quick login */}
        <button
          onClick={handleDemoLogin}
          disabled={isLoading}
          className="w-full p-4 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 rounded-xl border border-white/20 transition-all text-center mb-6 disabled:opacity-50"
        >
          <div className="flex items-center justify-center gap-2">
            {isLoading ? (
              <Loader2 className="w-5 h-5 text-white animate-spin" />
            ) : null}
            <div>
              <p className="text-white font-semibold">Demo: Stefano Bonanno</p>
              <p className="text-purple-200 text-sm">Entrar como demo</p>
            </div>
          </div>
        </button>

        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-white/20"></div>
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-2 bg-transparent text-purple-300">o con tu cuenta</span>
          </div>
        </div>

        {/* Login form */}
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-purple-200 mb-1">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setError("");
              }}
              placeholder="tu@email.com"
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-400"
              disabled={isLoading}
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-purple-200 mb-1">
              Contraseña
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setError("");
                }}
                placeholder="••••••••"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-400 pr-12"
                disabled={isLoading}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-purple-300 hover:text-white transition-colors"
              >
                {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>

          {error && (
            <p className="text-red-400 text-sm bg-red-500/10 rounded-lg p-3">{error}</p>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 bg-purple-600 hover:bg-purple-500 text-white rounded-xl font-semibold transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Entrando...
              </>
            ) : (
              "Entrar"
            )}
          </button>
        </form>

        <p className="text-purple-300 text-xs text-center mt-6">
          Sistema de autenticación seguro con JWT
        </p>
      </div>
    </div>
  );
}
