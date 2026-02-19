/**
 * CET/CEST timezone formatting utilities for Clonnect.
 * All timestamps display in Europe/Madrid timezone.
 */

export function formatTimeCET(iso: string): string {
  return new Date(iso).toLocaleTimeString("es-ES", {
    timeZone: "Europe/Madrid",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDateTimeCET(iso: string): string {
  return new Date(iso).toLocaleString("es-ES", {
    timeZone: "Europe/Madrid",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatFullDateTimeCET(iso: string): string {
  return new Date(iso).toLocaleString("es-ES", {
    timeZone: "Europe/Madrid",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatSessionLabel(isoStr: string): string {
  const date = new Date(isoStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffDays === 0) return "Hoy";
  if (diffDays === 1) return "Ayer";
  if (diffDays < 7) return `Hace ${diffDays} dias`;
  const diffWeeks = Math.floor(diffDays / 7);
  if (diffWeeks < 5) return `Hace ${diffWeeks} semana${diffWeeks > 1 ? "s" : ""}`;
  const diffMonths = Math.floor(diffDays / 30);
  return `Hace ${diffMonths} mes${diffMonths > 1 ? "es" : ""}`;
}
