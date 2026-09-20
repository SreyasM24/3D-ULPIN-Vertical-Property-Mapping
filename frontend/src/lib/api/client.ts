import { API_BASE_URL } from './config.ts';
import { ApiResponse } from '../../types/api.ts';

export class ApiError extends Error {
  public statusCode?: number;
  public requestId?: string;
  public isNetworkError: boolean;
  public details?: unknown;

  constructor(
    message: string,
    options?: {
      statusCode?: number;
      requestId?: string;
      isNetworkError?: boolean;
      details?: unknown;
    }
  ) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = options?.statusCode;
    this.requestId = options?.requestId;
    this.isNetworkError = options?.isNetworkError || false;
    this.details = options?.details;
  }
}

export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

export async function apiClient<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<ApiResponse<T>> {
  const { timeoutMs = 12000, ...fetchOptions } = options;
  const url = `${API_BASE_URL.replace(/\/+$/, '')}/${endpoint.replace(/^\/+/, '')}`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const headers: Record<string, string> = {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    };

    const response = await fetch(url, {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    const contentType = response.headers.get('content-type');
    let json: any = null;

    if (contentType && contentType.includes('application/json')) {
      json = await response.json();
    } else {
      const text = await response.text();
      try {
        json = JSON.parse(text);
      } catch {
        json = { data: text };
      }
    }

    if (!response.ok) {
      const errorMsg =
        typeof json?.error === 'string'
          ? json.error
          : json?.error?.message ||
            json?.detail ||
            `Server responded with status ${response.status}`;

      throw new ApiError(errorMsg, {
        statusCode: response.status,
        requestId: json?.request_id,
        details: json?.error?.details || json,
      });
    }

    // Support both standardized envelope { success, data, error, request_id } and raw FastAPI responses
    if (json && typeof json === 'object' && 'data' in json && 'success' in json) {
      return json as ApiResponse<T>;
    }

    return {
      success: true,
      data: json as T,
      request_id: json?.request_id,
    };
  } catch (error: any) {
    clearTimeout(timeoutId);

    if (error instanceof ApiError) {
      throw error;
    }

    if (error.name === 'AbortError') {
      throw new ApiError('Request timed out while waiting for cadastral engine.', {
        isNetworkError: true,
      });
    }

    throw new ApiError(
      'Unable to connect to cadastral backend. Please verify FastAPI service is running.',
      {
        isNetworkError: true,
        details: error?.message,
      }
    );
  }
}
