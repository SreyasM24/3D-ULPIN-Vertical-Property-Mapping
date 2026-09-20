import React, { useState, useEffect } from 'react';
import { ParcelProcessJobRequest, LandParcel } from '../../types/api.ts';
import { Play, Database, CheckCircle2, Layers, Building2 } from 'lucide-react';

interface ProcessingFormProps {
  onSubmit: (request: ParcelProcessJobRequest) => void;
  isLoading?: boolean;
  activeParcel?: LandParcel | null;
  availableParcels?: LandParcel[];
  onSelectParcel?: (parcel: LandParcel) => void;
}

export const ProcessingForm: React.FC<ProcessingFormProps> = ({
  onSubmit,
  isLoading = false,
  activeParcel,
  availableParcels = [],
  onSelectParcel,
}) => {
  const [sourceType, setSourceType] = useState<string>('DRONE');
  const [sourceReference, setSourceReference] = useState<string>('');

  // Cadastral Identification Fields
  const [parcelId, setParcelId] = useState<string>(activeParcel?.id || '');
  const [surveyNumber, setSurveyNumber] = useState<string>(activeParcel?.survey_number || '');
  const [stateCode, setStateCode] = useState<string>(activeParcel?.state_code || '');
  const [districtCode, setDistrictCode] = useState<string>(activeParcel?.district_code || '');
  const [villageCode, setVillageCode] = useState<string>(activeParcel?.village_code || '');

  // 3D Strata Parameters (aligned with ParcelProcessJobRequest)
  const [totalHeightM, setTotalHeightM] = useState<number | ''>(18.0);
  const [groundElevationM, setGroundElevationM] = useState<number | ''>(
    activeParcel?.base_elevation_m ?? activeParcel?.ground_elevation_amsl ?? ''
  );
  const [floorCount, setFloorCount] = useState<number | ''>(4);
  const [basementCount, setBasementCount] = useState<number | ''>(1);
  const [unitsPerFloor, setUnitsPerFloor] = useState<number>(2);
  const [autoGenerateStrata, setAutoGenerateStrata] = useState<boolean>(true);

  // Sync state whenever activeParcel updates from backend
  useEffect(() => {
    if (activeParcel) {
      setParcelId(activeParcel.id);
      setSurveyNumber(activeParcel.survey_number);
      if (activeParcel.state_code) setStateCode(activeParcel.state_code);
      if (activeParcel.district_code) setDistrictCode(activeParcel.district_code);
      if (activeParcel.village_code) setVillageCode(activeParcel.village_code);
      if (activeParcel.base_elevation_m != null || activeParcel.ground_elevation_amsl != null) {
        setGroundElevationM(activeParcel.base_elevation_m ?? activeParcel.ground_elevation_amsl ?? '');
      }
    }
  }, [activeParcel]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const payload: ParcelProcessJobRequest = {
      parcel_id: parcelId.trim() || undefined,
      survey_number: surveyNumber.trim() || undefined,
      state_code: stateCode ? (!isNaN(Number(stateCode)) ? Number(stateCode) : stateCode.trim()) : undefined,
      district_code: districtCode.trim() || undefined,
      village_code: villageCode.trim() || undefined,
      total_height_m: totalHeightM !== '' ? Number(totalHeightM) : undefined,
      ground_elevation_m: groundElevationM !== '' ? Number(groundElevationM) : undefined,
      floor_count: floorCount !== '' ? Number(floorCount) : undefined,
      basement_count: basementCount !== '' ? Number(basementCount) : 0,
      units_per_floor: unitsPerFloor || 2,
      auto_generate_strata: autoGenerateStrata,
      source_evidence: {
        source_type: sourceType,
        ...(sourceReference ? { source_reference: sourceReference } : {}),
      },
      ...(activeParcel?.geometry_geojson ? { parcel_geojson: activeParcel.geometry_geojson } : {}),
    };

    onSubmit(payload);
  };

  const handleApplyActiveParcel = () => {
    if (activeParcel) {
      setParcelId(activeParcel.id);
      setSurveyNumber(activeParcel.survey_number);
      setStateCode(activeParcel.state_code || '');
      setDistrictCode(activeParcel.district_code || '');
      setVillageCode(activeParcel.village_code || '');
      setGroundElevationM(activeParcel.base_elevation_m ?? activeParcel.ground_elevation_amsl ?? '');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-[#2d3034]">
        <div>
          <h2 className="text-sm font-semibold text-[#f4f3ef]">Asynchronous Cadastral Orchestration</h2>
          <p className="text-xs text-[#a09f99] mt-0.5">
            Configure 3D volumetric extrusion, strata decomposition, and 3D ULPIN derivation.
          </p>
        </div>

        {activeParcel && (
          <button
            type="button"
            onClick={handleApplyActiveParcel}
            className="text-xs text-[#d97757] hover:underline flex items-center gap-1 font-medium"
          >
            <Database className="w-3.5 h-3.5" />
            Sync Active Parcel
          </button>
        )}
      </div>

      {/* Active Backend Parcel Context Banner */}
      {activeParcel ? (
        <div className="p-3 bg-[#222428] rounded border border-[#2d3034] flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
          <div className="space-y-0.5">
            <div className="text-[10px] uppercase font-mono tracking-wider text-[#6b8e72] flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" />
              <span>Loaded Backend Parcel ({activeParcel.status})</span>
            </div>
            <div className="font-semibold text-[#f4f3ef]">
              Survey #{activeParcel.survey_number} — ULPIN: <span className="font-mono text-[#d97757]">{activeParcel.ulpin}</span>
            </div>
            <div className="text-[11px] text-[#a09f99]">
              {activeParcel.village || activeParcel.village_code || 'Village'}, {activeParcel.district || activeParcel.district_code} ({activeParcel.state || activeParcel.state_code}) • {activeParcel.area_sqm.toFixed(1)} m²
            </div>
          </div>

          {availableParcels.length > 1 && onSelectParcel && (
            <div className="flex items-center gap-1.5 self-end sm:self-auto">
              <label className="text-[#a09f99] text-[11px]">Switch:</label>
              <select
                value={activeParcel.id}
                onChange={(e) => {
                  const target = availableParcels.find((p) => p.id === e.target.value);
                  if (target) onSelectParcel(target);
                }}
                className="bg-[#18191b] border border-[#34373d] text-[#f4f3ef] text-[11px] rounded px-2 py-1 focus:outline-none"
              >
                {availableParcels.map((p) => (
                  <option key={p.id} value={p.id}>
                    SN #{p.survey_number}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      ) : (
        <div className="p-3 bg-[#222428]/60 rounded border border-[#2d3034] text-xs text-[#a09f99]">
          No pre-existing cadastral parcel loaded. The engine will register the boundary and construct the 3D cadastre hierarchy anew.
        </div>
      )}

      {/* Primary Cadastral Identification Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
        <div>
          <label className="text-[#a09f99] block mb-1">Cadastral Survey Number *</label>
          <input
            type="text"
            required
            value={surveyNumber}
            onChange={(e) => setSurveyNumber(e.target.value)}
            className="w-full bg-[#222428] border border-[#34373d] text-[#f4f3ef] rounded p-2 focus:border-[#c86446] focus:outline-none font-mono"
            placeholder="e.g. SN-411001-AUTO"
          />
        </div>

        <div>
          <label className="text-[#a09f99] block mb-1">Target Parcel UUID (Optional)</label>
          <input
            type="text"
            value={parcelId}
            onChange={(e) => setParcelId(e.target.value)}
            className="w-full bg-[#222428] border border-[#34373d] text-[#f4f3ef] rounded p-2 focus:border-[#c86446] focus:outline-none font-mono text-[11px]"
            placeholder="UUID (empty to auto-derive or create)"
          />
        </div>

        <div>
          <label className="text-[#a09f99] block mb-1">State / Province Code *</label>
          <input
            type="text"
            required
            value={stateCode}
            onChange={(e) => setStateCode(e.target.value)}
            className="w-full bg-[#222428] border border-[#34373d] text-[#f4f3ef] rounded p-2 focus:border-[#c86446] focus:outline-none font-mono"
            placeholder="e.g. 27 or MH"
          />
        </div>

        <div>
          <label className="text-[#a09f99] block mb-1">Revenue District Code *</label>
          <input
            type="text"
            required
            value={districtCode}
            onChange={(e) => setDistrictCode(e.target.value)}
            className="w-full bg-[#222428] border border-[#34373d] text-[#f4f3ef] rounded p-2 focus:border-[#c86446] focus:outline-none font-mono uppercase"
            placeholder="e.g. PUN"
          />
        </div>
      </div>

      {/* Volumetric Strata Construction Parameters */}
      <div className="pt-2 border-t border-[#2d3034] space-y-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-[#f4f3ef]">
          <Building2 className="w-4 h-4 text-[#d97757]" />
          <span>Volumetric Building & Strata Construction</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
          <div>
            <label className="text-[#a09f99] block mb-1">Building Height (m)</label>
            <input
              type="number"
              step="0.5"
              min="3"
              max="200"
              value={totalHeightM}
              onChange={(e) => setTotalHeightM(e.target.value === '' ? '' : parseFloat(e.target.value))}
              className="w-full bg-[#222428] border border-[#34373d] text-[#f4f3ef] rounded p-2 focus:border-[#c86446] focus:outline-none font-mono"
              placeholder="e.g. 18.0"
            />
          </div>

          <div>
            <label className="text-[#a09f99] block mb-1">Ground Elevation (m AMSL)</label>
            <input
              type="number"
              step="0.1"
              value={groundElevationM}
              onChange={(e) => setGroundElevationM(e.target.value === '' ? '' : parseFloat(e.target.value))}
              className="w-full bg-[#222428] border border-[#34373d] text-[#f4f3ef] rounded p-2 focus:border-[#c86446] focus:outline-none font-mono"
              placeholder="e.g. 560.0"
            />
          </div>

          <div>
            <label className="text-[#a09f99] block mb-1">Above-Ground Floors</label>
            <input
              type="number"
              min="1"
              max="50"
              value={floorCount}
              onChange={(e) => setFloorCount(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
              className="w-full bg-[#222428] border border-[#34373d] text-[#f4f3ef] rounded p-2 focus:border-[#c86446] focus:outline-none font-mono"
              placeholder="e.g. 4"
            />
          </div>

          <div>
            <label className="text-[#a09f99] block mb-1">Basement Levels</label>
            <input
              type="number"
              min="0"
              max="5"
              value={basementCount}
              onChange={(e) => setBasementCount(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
              className="w-full bg-[#222428] border border-[#34373d] text-[#f4f3ef] rounded p-2 focus:border-[#c86446] focus:outline-none font-mono"
              placeholder="e.g. 1"
            />
          </div>

          <div>
            <label className="text-[#a09f99] block mb-1">Units per Floor Level</label>
            <input
              type="number"
              min="1"
              max="10"
              required
              value={unitsPerFloor}
              onChange={(e) => setUnitsPerFloor(parseInt(e.target.value, 10) || 1)}
              className="w-full bg-[#222428] border border-[#34373d] text-[#f4f3ef] rounded p-2 focus:border-[#c86446] focus:outline-none font-mono"
            />
          </div>

          <div className="flex items-center pt-5">
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoGenerateStrata}
                onChange={(e) => setAutoGenerateStrata(e.target.checked)}
                className="rounded bg-[#222428] border-[#34373d] text-[#c86446] focus:ring-0 focus:outline-none"
              />
              <span className="text-[#f4f3ef] text-[11px]">Auto-generate 3D Strata</span>
            </label>
          </div>
        </div>
      </div>

      {/* Sensor / Source Evidence Metadata */}
      <div className="pt-2 border-t border-[#2d3034] space-y-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-[#f4f3ef]">
          <Layers className="w-4 h-4 text-[#6b8e72]" />
          <span>Survey Source Telemetry</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <div>
            <label className="text-[#a09f99] block mb-1">Source Sensor Type</label>
            <select
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value)}
              className="w-full bg-[#222428] border border-[#34373d] text-[#f4f3ef] rounded p-2 focus:border-[#c86446] focus:outline-none"
            >
              <option value="DRONE">Drone Photogrammetry (Oblique + Nadir)</option>
              <option value="LIDAR">Terrestrial / Aerial LiDAR Point Cloud</option>
              <option value="GEOJSON">Cadastral Vector Boundary (GeoJSON)</option>
              <option value="CAD_FLOOR_PLAN">Architectural CAD / Floor Plan Vectors</option>
            </select>
          </div>

          <div>
            <label className="text-[#a09f99] block mb-1">Dataset Reference / Filename</label>
            <input
              type="text"
              value={sourceReference}
              onChange={(e) => setSourceReference(e.target.value)}
              className="w-full bg-[#222428] border border-[#34373d] text-[#f4f3ef] rounded p-2 focus:border-[#c86446] focus:outline-none font-mono"
              placeholder="e.g. Survey_Sector_14.geojson"
            />
          </div>
        </div>
      </div>

      {/* Submit Button */}
      <div className="pt-2">
        <button
          type="submit"
          disabled={isLoading}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded bg-[#c86446] hover:bg-[#d97757] text-[#f4f3ef] font-medium text-xs shadow-md transition-colors disabled:opacity-50"
        >
          <Play className="w-4 h-4 fill-current" />
          <span>{isLoading ? 'Submitting to Orchestration Queue…' : 'Start Cadastral Survey Processing'}</span>
        </button>
      </div>
    </form>
  );
};
