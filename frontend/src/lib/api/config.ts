/**
 * API Configuration for SIH 26011 Cadastral Application
 * Reads from Vite / Next.js compatible environment variables or defaults to standard local FastAPI port.
 */

export const getApiBaseUrl = (): string => {
  // Support Vite client-side env, Next.js style env, or default local FastAPI endpoint
  const envUrl =
    (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) ||
    (typeof import.meta !== 'undefined' && import.meta.env?.NEXT_PUBLIC_API_BASE_URL) ||
    (typeof process !== 'undefined' && process.env?.NEXT_PUBLIC_API_BASE_URL);

  return envUrl || 'http://localhost:8000/api/v1';
};

export const API_BASE_URL = getApiBaseUrl();
