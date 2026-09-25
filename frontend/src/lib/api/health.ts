import { apiClient } from './client.ts';
import { SystemCapabilities, SystemHealth, ApiResponse } from '../../types/api.ts';

export async function getHealth(timeoutMs = 8000): Promise<SystemHealth> {
  const res = await apiClient<SystemHealth>('/health', { timeoutMs });
  return res.data;
}

export async function getCapabilities(timeoutMs = 8000): Promise<SystemCapabilities> {
  const res = await apiClient<SystemCapabilities>('/capabilities', { timeoutMs });
  return res.data;
}

export const healthApi = {
  checkHealth: async (timeoutMs = 8000): Promise<ApiResponse<SystemHealth>> => {
    return apiClient<SystemHealth>('/health', { timeoutMs });
  },
  getCapabilities: async (timeoutMs = 8000): Promise<ApiResponse<SystemCapabilities>> => {
    return apiClient<SystemCapabilities>('/capabilities', { timeoutMs });
  },
};
