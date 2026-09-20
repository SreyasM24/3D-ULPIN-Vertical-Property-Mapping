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

export async function submitParcelProcessingJob(
  payload: ParcelProcessJobRequest
): Promise<JobRead> {
  const res = await apiClient<JobRead>('/jobs/process-parcel', {
    method: 'POST',
    body: JSON.stringify(payload),
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
  const processPayload: ParcelProcessJobRequest = {
    parcel_id: request.parcel_id || undefined,
    survey_number: request.survey_number,
    district_code: request.district_code || (request as any).district?.substring(0, 3)?.toUpperCase() || undefined,
    state_code: request.state_code ?? undefined,
    village_code: request.village_code,
    parcel_geojson: request.parcel_geojson,
    building_footprint_geojson: request.building_footprint_geojson,
    total_height_m: request.total_height_m,
    ground_elevation_m: request.ground_elevation_m,
    floor_count: request.floor_count,
    basement_count: request.basement_count ?? 0,
    units_per_floor: request.units_per_floor ?? 2,
    auto_generate_strata: request.auto_generate_strata ?? true,
    source_evidence: request.source_evidence || ((request as any).survey_source_type ? {
      source_type: (request as any).survey_source_type,
      source_reference_uri: (request as any).source_reference_uri,
      crs: (request as any).crs,
      notes: (request as any).notes,
    } : undefined),
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
