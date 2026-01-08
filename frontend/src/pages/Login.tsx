/**
 * Simple Login / Creator Selector Page
 * For demo purposes - allows selecting which creator account to use
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

// Known creators for quick selection
const KNOWN_CREATORS = [
  { id: "stefano_auto", name: "Stefano Bonanno", description: "Coach de bienestar" },
  { id: "manel", name: "Manel", description: "Demo account" },
];

export default function Login() {
  const [customId, setCustomId] = useState("");
  const [error, setError] = useState("");
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleLogin = (creatorId: string) => {
    if (!creatorId.trim()) {
      setError("Por favor ingresa un ID de creador");
      return;
    }
    login(creatorId.trim());
    navigate("/");
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-purple-800 to-indigo-900 flex items-center justify-center p-4">
      <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 w-full max-w-md border border-white/20">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Clonnect</h1>
          <p className="text-purple-200">Selecciona tu cuenta de creador</p>
        </div>

        {/* Quick select buttons */}
        <div className="space-y-3 mb-6">
          {KNOWN_CREATORS.map((creator) => (
            <button
              key={creator.id}
              onClick={() => handleLogin(creator.id)}
              className="w-full p-4 bg-white/10 hover:bg-white/20 rounded-xl border border-white/20 transition-all text-left group"
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-semibold">{creator.name}</p>
                  <p className="text-purple-300 text-sm">{creator.description}</p>
                </div>
                <span className="text-purple-300 group-hover:text-white transition-colors">
                  &rarr;
                </span>
              </div>
            </button>
          ))}
        </div>

        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-white/20"></div>
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-2 bg-transparent text-purple-300">o ingresa manualmente</span>
          </div>
        </div>

        {/* Custom ID input */}
        <div className="space-y-4">
          <input
            type="text"
            value={customId}
            onChange={(e) => {
              setCustomId(e.target.value);
              setError("");
            }}
            placeholder="ID de creador (ej: mi_cuenta)"
            className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-400"
            onKeyDown={(e) => e.key === "Enter" && handleLogin(customId)}
          />

          {error && (
            <p className="text-red-400 text-sm">{error}</p>
          )}

          <button
            onClick={() => handleLogin(customId)}
            className="w-full py-3 bg-purple-600 hover:bg-purple-500 text-white rounded-xl font-semibold transition-colors"
          >
            Entrar
          </button>
        </div>

        <p className="text-purple-300 text-xs text-center mt-6">
          Demo mode - en producción usarás email/password
        </p>
      </div>
    </div>
  );
}
