import { apiClient } from './client.ts';
import { SystemCapabilities, SystemHealth, ApiResponse } from '../../types/api.ts';

export async function getHealth(): Promise<SystemHealth> {
  const res = await apiClient<SystemHealth>('/health', { timeoutMs: 4000 });
  return res.data;
}

export async function getCapabilities(): Promise<SystemCapabilities> {
  const res = await apiClient<SystemCapabilities>('/capabilities', { timeoutMs: 4000 });
  return res.data;
}

export const healthApi = {
  checkHealth: async (): Promise<ApiResponse<SystemHealth>> => {
    return apiClient<SystemHealth>('/health', { timeoutMs: 4000 });
  },
  getCapabilities: async (): Promise<ApiResponse<SystemCapabilities>> => {
    return apiClient<SystemCapabilities>('/capabilities', { timeoutMs: 4000 });
  },
};
