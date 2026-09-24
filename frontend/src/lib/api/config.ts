/**
 * API Configuration for SIH 26011 Cadastral Application
 * Reads from Vite / Next.js compatible environment variables or defaults to standard local FastAPI port.
 */

export const getApiBaseUrl = (): string => {
  const envUrl =
    import.meta.env.VITE_API_BASE_URL ||
    import.meta.env.NEXT_PUBLIC_API_BASE_URL;

  return (envUrl && envUrl.trim() !== '') ? envUrl : 'http://localhost:8000/api/v1';
};

export const API_BASE_URL = getApiBaseUrl();
