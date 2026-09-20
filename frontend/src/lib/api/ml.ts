import { apiClient } from './client.ts';
import { AnomalySignal, ApiResponse } from '../../types/api.ts';

export interface AnomalyCheckRequest {
  height_m?: number | null;
  floor_count?: number | null;
  footprint_geojson?: Record<string, any> | null;
}

export async function checkAnomalies(
  payload: AnomalyCheckRequest = {}
): Promise<AnomalySignal[]> {
  const res = await apiClient<any[]>('/ml/anomalies', {
    method: 'POST',
    body: JSON.stringify(payload),
  });

  return (res.data || []).map((item: any, idx: number) => ({
    id: item.anomaly_id || `anomaly-${idx}`,
    target_id: item.target_id || 'PARCEL',
    target_type: item.target_type || 'BUILDING',
    type: item.anomaly_type || item.type || 'STATISTICAL_DEVIATION',
    severity: item.severity || 'WARNING',
    confidence: item.confidence || 'HIGH',
    explanation: item.description || item.explanation || 'Anomaly detected during feature extraction.',
    requires_review: item.requires_human_review ?? true,
    advisory_note: item.suggested_action || item.advisory_note || '',
    detected_at: item.detected_at || new Date().toISOString(),
  }));
}

export async function getMLHealth(): Promise<Record<string, any>> {
  const res = await apiClient<Record<string, any>>('/ml/health');
  return res.data;
}

export async function getMLCapabilities(): Promise<Record<string, any>> {
  const res = await apiClient<Record<string, any>>('/ml/capabilities');
  return res.data;
}

export async function listMLModels(): Promise<any[]> {
  const res = await apiClient<any[]>('/ml/models');
  return res.data;
}

export const mlApi = {
  checkAnomalies: async (
    payload: AnomalyCheckRequest = {}
  ): Promise<ApiResponse<AnomalySignal[]>> => {
    const data = await checkAnomalies(payload);
    return { success: true, data };
  },
  getHealth: async (): Promise<ApiResponse<Record<string, any>>> => {
    const data = await getMLHealth();
    return { success: true, data };
  },
  getCapabilities: async (): Promise<ApiResponse<Record<string, any>>> => {
    const data = await getMLCapabilities();
    return { success: true, data };
  },
  listModels: async (): Promise<ApiResponse<any[]>> => {
    const data = await listMLModels();
    return { success: true, data };
  },
};
