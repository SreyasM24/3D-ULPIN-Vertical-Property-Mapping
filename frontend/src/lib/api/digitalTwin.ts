import { apiClient } from './client.ts';
import {
  CadastralDigitalTwin,
  DigitalTwin,
  VerticalUnit,
  Building,
  FloorLevel,
  ApiResponse,
  AnomalySignal,
  TemporalChangeReport,
} from '../../types/api.ts';
import { normalizeParcel } from './parcels.ts';

/**
 * Normalizes backend CadastralDigitalTwin response into a structured model
 * consumable by UI components and 3D viewers.
 */
export function normalizeDigitalTwin(raw: any): DigitalTwin {
  if (!raw) return raw;

  const rawParcel = raw.parcel || raw;
  const rawSummary = raw.summary || {};
  const rawBuildings = rawParcel.buildings || raw.buildings || [];

  const buildings: Building[] = rawBuildings.map((b: any) => ({
    id: b.id,
    parcel_id: b.parcel_id || rawParcel.id,
    building_name: b.building_name,
    building_code: b.building_code,
    structure_type: b.structure_type || 'REINFORCED_CONCRETE',
    floors_above_ground: b.floors_above_ground ?? 0,
    basement_floors: b.basement_floors ?? 0,
    total_height_m: b.total_height_m ?? 0,
    ground_elevation_m: b.ground_elevation_m ?? 0,
    footprint_geojson: b.footprint_geojson,
    footprint_area_sqm: b.footprint_area_sqm ?? 0,
    gross_volume_cu_m: b.volume_cu_m ?? b.gross_volume_cu_m ?? 0,
    is_within_parcel: b.is_within_parcel ?? true,
    total_height: b.total_height_m ?? 0,
    ground_elevation: b.ground_elevation_m ?? 0,
    levels_above_ground: b.floors_above_ground ?? 0,
    levels_below_ground: b.basement_floors ?? 0,
    classification: b.structure_type || 'MIXED_USE',
  }));

  const floors: FloorLevel[] = [];
  const units: VerticalUnit[] = [];

  rawBuildings.forEach((b: any) => {
    (b.floors || []).forEach((f: any) => {
      floors.push({
        id: f.id,
        building_id: f.building_id || b.id,
        level_number: f.level_number ?? 0,
        level_code: f.level_code,
        level_type: f.level_type,
        elevation_min_m: f.z_min ?? f.elevation_min_m ?? 0,
        elevation_max_m: f.z_max ?? f.elevation_max_m ?? 0,
        floor_height_m: f.floor_height_m ?? ((f.z_max ?? 0) - (f.z_min ?? 0)),
        is_basement: f.level_number < 0 || (f.z_min ?? 0) < 0,
        elevation_bottom: f.z_min ?? f.elevation_min_m ?? 0,
        elevation_top: f.z_max ?? f.elevation_max_m ?? 0,
        height: f.floor_height_m ?? ((f.z_max ?? 0) - (f.z_min ?? 0)),
        is_underground: f.level_number < 0 || (f.z_min ?? 0) < 0,
        level_name: `${f.level_code} (${f.level_type || 'Level'})`,
        units_count: f.unit_count ?? f.units?.length ?? 0,
      });

      (f.units || []).forEach((u: any) => {
        const zMin = u.z_min ?? u.elevation_min_m ?? 0;
        const zMax = u.z_max ?? u.elevation_max_m ?? 0;
        const area = u.carpet_area_sqm ?? 0;
        const vol = u.volume_cu_m ?? 0;

        units.push({
          id: u.id,
          floor_id: u.floor_id || f.id,
          building_id: b.id,
          parcel_id: rawParcel.id,
          unit_number: u.unit_number || u.unit_code,
          unit_code: u.unit_code,
          unit_type: u.unit_type || 'APARTMENT',
          ulpin_3d: u.ulpin_3d,
          ulpin_status: u.ulpin_status || 'PROVISIONAL',
          base_ulpin: rawParcel.ulpin,
          level_code: f.level_code,
          checksum: u.ulpin_3d?.split('-')?.pop() || '',
          footprint_geojson: u.footprint_geojson,
          elevation_min_m: zMin,
          elevation_max_m: zMax,
          carpet_area_sqm: area,
          builtup_area_sqm: u.builtup_area_sqm ?? area,
          volume_cu_m: vol,
          is_clash_free: u.is_clash_free ?? true,
          is_multi_floor: u.is_multi_floor ?? false,
          floor_span: u.floor_span,
          vertical_classification: u.vertical_classification,
          status: u.status || 'ACTIVE',
          confidence: u.confidence != null ? (typeof u.confidence === 'number' ? (u.confidence > 0.8 ? 'HIGH' : u.confidence > 0.5 ? 'MEDIUM' : 'LOW') : String(u.confidence)) : null,
          provenance: u.provenance || u.ml_provenance || null,
          anomalies: u.anomalies || [],
          ownership_records: u.ownership_records || [],
          vertical_range: { z_min: zMin, z_max: zMax },
          area_sqm: area,
          volume_cum: vol,
          classification: u.unit_type || 'Residential Unit',
          data_stage: u.stage || 'VALIDATED',
          validation_status: (u.is_clash_free ?? true) ? 'PASSED' : 'WARNING',
          geometry_3d: {
            footprint: u.footprint_geojson?.coordinates?.[0] || [],
            z_min: zMin,
            z_max: zMax,
          },
        });
      });
    });
  });
  const detectedAnomalies: AnomalySignal[] = (rawSummary.anomalies_detected || []).map((a: any, idx: number) => ({
    id: a.id || `anom-${idx}`,
    target_id: a.target_id || rawParcel.id,
    target_type: a.target_type || 'PARCEL',
    type: a.anomaly_type || a.type || 'CADASTRAL_ANOMALY',
    severity: (a.severity || 'ADVISORY').toUpperCase(),
    confidence: typeof a.confidence === 'number' ? (a.confidence >= 0.85 ? 'HIGH' : a.confidence >= 0.65 ? 'MEDIUM' : 'LOW') : (a.confidence || 'MEDIUM'),
    explanation: a.explanation || a.message || '',
    requires_review: a.requires_review ?? true,
    advisory_note: a.advisory_note,
    detected_at: a.detected_at || raw.assembled_at || new Date().toISOString(),
  }));

  return {
    parcel: normalizeParcel(rawParcel),
    buildings,
    floors,
    units,
    summary: rawSummary,
    anomalies: detectedAnomalies,
    metadata: {
      crs: rawParcel.spatial_metadata?.optimal_utm_epsg ? `EPSG:${rawParcel.spatial_metadata.optimal_utm_epsg}` : 'EPSG:4326',
      datum: 'WGS84 / Projected Metric UTM',
      generated_at: raw.assembled_at || new Date().toISOString(),
      version: '1.0.0',
      cadastral_engine_version: 'SIH 26011 v1.0',
      total_volume_cum: rawSummary.total_volume_cu_m ?? 0,
      total_vertical_units: rawSummary.total_units ?? units.length,
    },
  };
}

export async function getDigitalTwin(parcelId: string): Promise<DigitalTwin> {
  const res = await apiClient<CadastralDigitalTwin>(`/parcels/${parcelId}/digital-twin`);
  return normalizeDigitalTwin(res.data);
}

export async function getDigitalTwinGeoJSON3D(parcelId: string): Promise<any> {
  const res = await apiClient<any>(`/parcels/${parcelId}/digital-twin/geojson3d`);
  return res.data;
}

export async function getUnitDetails(unitId: string): Promise<VerticalUnit> {
  const res = await apiClient<VerticalUnit>(`/units/${unitId}`);
  return res.data;
}

export async function getBuildingGeoJSON3D(buildingId: string): Promise<any> {
  const res = await apiClient<any>(`/spatial/geojson3d/building/${buildingId}`);
  return res.data;
}

export async function getBuildingClashes(buildingId: string): Promise<any> {
  const res = await apiClient<any>(`/spatial/clashes/building/${buildingId}`);
  return res.data;
}

export async function getParcelSnapshot(parcelId: string): Promise<any> {
  const res = await apiClient<any>(`/digital-twin/parcels/${parcelId}/snapshot`);
  return res.data;
}

export async function compareDigitalTwins(payload: {
  parcel_id?: string;
  baseline_snapshot?: any;
  new_observation: any;
  config?: any;
}): Promise<TemporalChangeReport> {
  const res = await apiClient<TemporalChangeReport>(`/digital-twin/compare`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return res.data;
}

export const digitalTwinApi = {
  getDigitalTwin: async (parcelId: string): Promise<ApiResponse<DigitalTwin>> => {
    const data = await getDigitalTwin(parcelId);
    return { success: true, data };
  },
  getDigitalTwinGeoJSON3D: async (parcelId: string): Promise<ApiResponse<any>> => {
    const data = await getDigitalTwinGeoJSON3D(parcelId);
    return { success: true, data };
  },
  getUnitDetails: async (unitId: string): Promise<ApiResponse<VerticalUnit>> => {
    const data = await getUnitDetails(unitId);
    return { success: true, data };
  },
  getBuildingClashes: async (buildingId: string): Promise<ApiResponse<any>> => {
    const data = await getBuildingClashes(buildingId);
    return { success: true, data };
  },
  getParcelSnapshot: async (parcelId: string): Promise<ApiResponse<any>> => {
    const data = await getParcelSnapshot(parcelId);
    return { success: true, data };
  },
  compareDigitalTwins: async (payload: {
    parcel_id?: string;
    baseline_snapshot?: any;
    new_observation: any;
    config?: any;
  }): Promise<ApiResponse<TemporalChangeReport>> => {
    const data = await compareDigitalTwins(payload);
    return { success: true, data };
  },
};

