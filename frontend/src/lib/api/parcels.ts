import { apiClient } from './client.ts';
import { LandParcel, PaginatedList, ParcelCreate, ApiResponse } from '../../types/api.ts';

export function normalizeParcel(p: any): LandParcel {
  if (!p) return p;
  return {
    ...p,
    state: p.state || p.state_code,
    district: p.district || p.district_code,
    village: p.village || p.village_code,
    ground_elevation_amsl: p.ground_elevation_amsl ?? p.base_elevation_m ?? 0,
    crs: p.crs || (p.spatial_metadata?.optimal_utm_epsg ? `EPSG:${p.spatial_metadata.optimal_utm_epsg}` : 'EPSG:4326'),
    coordinates: p.coordinates || p.geometry_geojson?.coordinates?.[0] || [],
    buildings_count: p.buildings_count ?? p.buildings?.length ?? 0,
    units_count: p.units_count ?? 0,
  };
}

export async function listParcels(
  page: number = 1,
  pageSize: number = 20
): Promise<PaginatedList<LandParcel>> {
  const res = await apiClient<PaginatedList<LandParcel>>(
    `/parcels/?page=${page}&page_size=${pageSize}`
  );
  const data = res.data;
  return {
    ...data,
    items: (data.items || []).map(normalizeParcel),
  };
}

export async function getParcel(parcelId: string): Promise<LandParcel> {
  const res = await apiClient<LandParcel>(`/parcels/${parcelId}`);
  return normalizeParcel(res.data);
}

export async function getParcelByUlpin(ulpin: string): Promise<LandParcel> {
  const res = await apiClient<LandParcel>(`/parcels/ulpin/${ulpin}`);
  return normalizeParcel(res.data);
}

export async function createParcel(payload: ParcelCreate): Promise<LandParcel> {
  const res = await apiClient<LandParcel>('/parcels/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return normalizeParcel(res.data);
}

export const parcelsApi = {
  listParcels: async (page = 1, pageSize = 20): Promise<ApiResponse<PaginatedList<LandParcel>>> => {
    const list = await listParcels(page, pageSize);
    return { success: true, data: list };
  },
  getParcel: async (id: string): Promise<ApiResponse<LandParcel>> => {
    const parcel = await getParcel(id);
    return { success: true, data: parcel };
  },
  getParcelByUlpin: async (ulpin: string): Promise<ApiResponse<LandParcel>> => {
    const parcel = await getParcelByUlpin(ulpin);
    return { success: true, data: parcel };
  },
};
