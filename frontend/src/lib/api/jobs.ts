import { apiClient } from './client.ts';
import {
  JobRead,
  JobListResponse,
  JobResultResponse,
  ParcelProcessJobRequest,
  SurveyIngestJobRequest,
  CreateSurveyJobRequest,
  ApiResponse,
} from '../../types/api.ts';
import { resolveNumericStateCode, resolveEvidenceSourceType } from '../cadastralCodes.ts';

export async function submitParcelProcessingJob(
  payload: ParcelProcessJobRequest
): Promise<JobRead> {
  const district = payload.district_code || payload.revenue_district_code || 'PUN';
  const rawSourceType = payload.source_evidence?.source_type;
  const rawSourceRef = payload.source_evidence?.source_reference || payload.source_evidence?.source_reference_uri || 'demo_26011_drone_survey.geojson';

  const normalizedSourceEvidence = payload.source_evidence ? {
    ...payload.source_evidence,
    source_type: resolveEvidenceSourceType(rawSourceType),
    source_reference: rawSourceRef,
  } : {
    source_type: 'DRONE_PHOTOGRAMMETRY',
    source_reference: 'demo_26011_drone_survey.geojson',
  };

  const cleanParcelId = (payload.parcel_id && typeof payload.parcel_id === 'string' && payload.parcel_id.trim()) ? payload.parcel_id.trim() : undefined;
  const finalPayload: ParcelProcessJobRequest = {
    ...payload,
    parcel_id: cleanParcelId,
    state_code: resolveNumericStateCode(payload.state_code),
    district_code: district,
    revenue_district_code: district,
    source_evidence: normalizedSourceEvidence,
  };
  const res = await apiClient<JobRead>('/jobs/process-parcel', {
    method: 'POST',
    body: JSON.stringify(finalPayload),
  });
  return res.data;
}

export async function submitSurveyIngestionJob(
  payload: SurveyIngestJobRequest
): Promise<JobRead> {
  const res = await apiClient<JobRead>('/jobs/ingestion', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return res.data;
}

export async function createSurveyJob(request: ParcelProcessJobRequest | CreateSurveyJobRequest): Promise<JobRead> {
  const district = request.district_code || (request as any).revenue_district_code || (request as any).district?.substring(0, 3)?.toUpperCase() || 'PUN';
  const rawSourceType = request.source_evidence?.source_type || (request as any).survey_source_type;
  const rawSourceRef = request.source_evidence?.source_reference || (request as any).source_reference_uri || 'demo_26011_drone_survey.geojson';

  const normalizedSourceEvidence = (request.source_evidence || (request as any).survey_source_type) ? {
    ...(request.source_evidence || {}),
    source_type: resolveEvidenceSourceType(rawSourceType),
    source_reference: rawSourceRef,
    ...((request as any).crs ? { crs: (request as any).crs } : {}),
    ...((request as any).notes ? { notes: (request as any).notes } : {}),
  } : {
    source_type: 'DRONE_PHOTOGRAMMETRY',
    source_reference: 'demo_26011_drone_survey.geojson',
  };

  const cleanReqParcelId = (request.parcel_id && typeof request.parcel_id === 'string' && request.parcel_id.trim()) ? request.parcel_id.trim() : undefined;
  const processPayload: ParcelProcessJobRequest = {
    parcel_id: cleanReqParcelId,
    survey_number: request.survey_number,
    district_code: district,
    revenue_district_code: district,
    state_code: resolveNumericStateCode(request.state_code),
    village_code: request.village_code,
    parcel_geojson: request.parcel_geojson,
    building_footprint_geojson: request.building_footprint_geojson,
    total_height_m: request.total_height_m,
    ground_elevation_m: request.ground_elevation_m,
    floor_count: request.floor_count,
    basement_count: request.basement_count ?? 0,
    units_per_floor: request.units_per_floor ?? 2,
    auto_generate_strata: request.auto_generate_strata ?? true,
    source_evidence: normalizedSourceEvidence,
  };

  return submitParcelProcessingJob(processPayload);
}

export async function getJob(jobId: string): Promise<JobRead> {
  const res = await apiClient<JobRead>(`/jobs/${jobId}`);
  return res.data;
}

export async function getJobResult(jobId: string): Promise<JobResultResponse> {
  const res = await apiClient<JobResultResponse>(`/jobs/${jobId}/result`);
  return res.data;
}

export async function listJobs(
  status?: string,
  jobType?: string,
  limit: number = 50,
  offset: number = 0
): Promise<JobListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (status) params.append('status', status);
  if (jobType) params.append('job_type', jobType);

  const res = await apiClient<JobListResponse>(`/jobs?${params.toString()}`);
  return res.data;
}

export async function cancelJob(
  jobId: string,
  reason: string = 'Cancelled by user'
): Promise<JobRead> {
  const res = await apiClient<JobRead>(
    `/jobs/${jobId}/cancel?reason=${encodeURIComponent(reason)}`,
    {
      method: 'POST',
    }
  );
  return res.data;
}

export const jobsApi = {
  createJob: async (payload: ParcelProcessJobRequest | CreateSurveyJobRequest): Promise<ApiResponse<JobRead>> => {
    const job = await createSurveyJob(payload);
    return { success: true, data: job };
  },
  submitParcelProcessingJob: async (
    payload: ParcelProcessJobRequest
  ): Promise<ApiResponse<JobRead>> => {
    const job = await submitParcelProcessingJob(payload);
    return { success: true, data: job };
  },
  submitSurveyIngestionJob: async (
    payload: SurveyIngestJobRequest
  ): Promise<ApiResponse<JobRead>> => {
    const job = await submitSurveyIngestionJob(payload);
    return { success: true, data: job };
  },
  getJobStatus: async (jobId: string): Promise<ApiResponse<JobRead>> => {
    const job = await getJob(jobId);
    return { success: true, data: job };
  },
  getJobResult: async (jobId: string): Promise<ApiResponse<JobResultResponse>> => {
    const result = await getJobResult(jobId);
    return { success: true, data: result };
  },
  listJobs: async (
    status?: string,
    jobType?: string,
    limit?: number,
    offset?: number
  ): Promise<ApiResponse<JobListResponse>> => {
    const data = await listJobs(status, jobType, limit, offset);
    return { success: true, data };
  },
  cancelJob: async (jobId: string, reason?: string): Promise<ApiResponse<JobRead>> => {
    const job = await cancelJob(jobId, reason);
    return { success: true, data: job };
  },
};
