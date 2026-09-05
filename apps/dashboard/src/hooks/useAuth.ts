/**
 * Hook utilitaire — expose le token JWT depuis le store Zustand.
 * Permet aux services/pages d'accéder au token sans importer authStore directement.
 */
import { useAuthStore } from '../stores/authStore';

export function useAuth() {
  const user = useAuthStore((s) => s.user);
  const token = useAuthStore((s) => s.token);
  const isAuthenticated = !!user && !!token;

  return { user, token, isAuthenticated };
}
