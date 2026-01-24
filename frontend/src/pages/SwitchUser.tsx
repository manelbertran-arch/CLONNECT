import { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { setCreatorId } from '../services/api';

/**
 * Helper page to switch creator and redirect to dashboard.
 * Usage: /switch-user/maki_maki → sets localStorage and redirects to /inbox
 */
export default function SwitchUser() {
  const { creatorId } = useParams<{ creatorId: string }>();
  const navigate = useNavigate();

  useEffect(() => {
    if (creatorId) {
      // Set the creator in localStorage
      setCreatorId(creatorId);

      // Also set in AuthContext key
      localStorage.setItem('clonnect_selected_creator', creatorId);

      // Clear any cached data by doing a hard redirect
      window.location.href = '/inbox';
    } else {
      navigate('/');
    }
  }, [creatorId, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: '#09090b' }}>
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-white">Cambiando a {creatorId}...</p>
      </div>
    </div>
  );
}
