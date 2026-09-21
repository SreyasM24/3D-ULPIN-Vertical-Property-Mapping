import React, { useState, useEffect } from 'react';
import {
  VerticalUnit,
  Building,
  FloorLevel,
  LandParcel,
  UndergroundVolume,
  ElevatedVolume,
  DigitalTwin,
  AnomalySignal,
} from '../../types/api.ts';
import { ULPINDisplay } from './ULPINDisplay.tsx';
import { ProvenancePanel } from '../provenance/ProvenancePanel.tsx';
import { AnomalyPanel } from '../validation/AnomalyPanel.tsx';
import { TemporalChangePanel } from './TemporalChangePanel.tsx';
import {
  Box,
  Layers,
  MapPin,
  ShieldCheck,
  AlertTriangle,
  Info,
  Maximize2,
  ChevronRight,
  Sparkles,
  History,
} from 'lucide-react';

export type SelectedCadastralItem =
  | { type: 'unit'; data: VerticalUnit }
  | { type: 'building'; data: Building }
  | { type: 'floor'; data: FloorLevel }
  | { type: 'parcel'; data: LandParcel }
  | { type: 'underground'; data: UndergroundVolume }
  | { type: 'elevated'; data: ElevatedVolume }
  | null;

interface PropertyInspectorProps {
  selectedItem: SelectedCadastralItem;
  digitalTwin?: DigitalTwin | null;
  anomalies?: AnomalySignal[];
  onClose?: () => void;
  onSelectUnit?: (unitId: string) => void;
}

export const PropertyInspector: React.FC<PropertyInspectorProps> = ({
  selectedItem,
  digitalTwin,
  anomalies,
  onClose,
  onSelectUnit,
}) => {
  const [activeTab, setActiveTab] = useState<'provenance' | 'details' | 'anomalies' | 'temporal'>('provenance');

  useEffect(() => {
    setActiveTab('provenance');
  }, [selectedItem?.data?.id]);

  const propertyAnomalies = anomalies || digitalTwin?.anomalies || [];

  if (!selectedItem) {
    return (
      <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-5 space-y-4">
        <div className="text-center text-[#a09f99] space-y-2">
          <Box className="w-8 h-8 text-[#5c7080] mx-auto stroke-1" />
          <div className="font-medium text-[#f4f3ef] text-sm">No Cadastral Feature Selected</div>
          <p className="text-xs max-w-xs mx-auto leading-relaxed">
            Select any parcel boundary, building envelope, floor slab, or vertical 3D unit in the viewport to inspect its geometric and legal attribution.
          </p>
        </div>

        {/* 3D Temporal Change Intelligence */}
        <div className="border-t border-[#2d3034] pt-3">
          <TemporalChangePanel
            parcelId={digitalTwin?.parcel?.id}
            digitalTwin={digitalTwin}
          />
        </div>

        {/* Cadastral Anomaly Findings for Property */}
        <div className="border-t border-[#2d3034] pt-3">
          <AnomalyPanel anomalies={propertyAnomalies} />
        </div>
      </div>
    );
  }

  // Render for Vertical Unit (Primary Innovation)
  if (selectedItem.type === 'unit') {
    const unit = selectedItem.data;
    const unitAnomalies = (unit.anomalies && unit.anomalies.length > 0) ? unit.anomalies : propertyAnomalies;
    const hasAnomalies = unitAnomalies.length > 0;
    const hasProvenance = Boolean(unit.provenance);

    return (
      <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg overflow-hidden flex flex-col max-h-[82vh]">
        {/* Header */}
        <div className="p-4 border-b border-[#2d3034] bg-[#222428] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded bg-[#c86446]/20 text-[#d97757]">
              <Box className="w-4 h-4" />
            </span>
            <div>
              <div className="text-xs uppercase tracking-wider text-[#a09f99] font-medium">Vertical Unit</div>
              <h3 className="text-sm font-semibold text-[#f4f3ef]">{unit.classification}</h3>
            </div>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="text-[#a09f99] hover:text-[#f4f3ef] text-xs px-2 py-1 rounded hover:bg-[#2b2d32]"
            >
              Close
            </button>
          )}
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-[#2d3034] bg-[#18191b] px-4 text-xs font-medium">
          <button
            onClick={() => setActiveTab('provenance')}
            className={`py-2 px-3 border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'provenance'
                ? 'border-[#c86446] text-[#f4f3ef]'
                : 'border-transparent text-[#a09f99] hover:text-[#f4f3ef]'
            }`}
          >
            Provenance
          </button>
          <button
            onClick={() => setActiveTab('details')}
            className={`py-2 px-3 border-b-2 transition-colors ${
              activeTab === 'details'
                ? 'border-[#c86446] text-[#f4f3ef]'
                : 'border-transparent text-[#a09f99] hover:text-[#f4f3ef]'
            }`}
          >
            Attributes
          </button>
          {hasAnomalies && (
            <button
              onClick={() => setActiveTab('anomalies')}
              className={`py-2 px-3 border-b-2 transition-colors flex items-center gap-1.5 ${
                activeTab === 'anomalies'
                  ? 'border-[#c86446] text-[#f4f3ef]'
                  : 'border-transparent text-[#a09f99] hover:text-[#f4f3ef]'
              }`}
            >
              Cadastral Anomaly Findings
              <span className="w-4 h-4 rounded-full bg-[#c98a2c]/20 text-[#c98a2c] text-[10px] inline-flex items-center justify-center">
                {unitAnomalies.length}
              </span>
            </button>
          )}
          <button
            onClick={() => setActiveTab('temporal')}
            className={`py-2 px-3 border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'temporal'
                ? 'border-[#c86446] text-[#f4f3ef]'
                : 'border-transparent text-[#a09f99] hover:text-[#f4f3ef]'
            }`}
          >
            <History className="w-3.5 h-3.5" />
            Temporal Change
          </button>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto">
          {activeTab === 'details' && (
            <>
              {/* 3D ULPIN Card */}
              <ULPINDisplay
                ulpin3d={unit.ulpin_3d}
                baseUlpin={unit.base_ulpin}
                levelCode={unit.level_code}
                unitNumber={unit.unit_number}
                checksum={unit.checksum}
              />

              {/* Cadastral & Geometric Metrics */}
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-[#222428] p-2.5 rounded border border-[#2d3034]">
                  <div className="text-[10px] uppercase text-[#a09f99] font-medium">Floor Level</div>
                  <div className="text-sm font-semibold text-[#f4f3ef] mt-0.5">{unit.level_code}</div>
                  <div className="text-[11px] text-[#a09f99]">Unit #{unit.unit_number}</div>
                </div>

                <div className="bg-[#222428] p-2.5 rounded border border-[#2d3034]">
                  <div className="text-[10px] uppercase text-[#a09f99] font-medium">Vertical Range</div>
                  <div className="text-sm font-semibold text-[#f4f3ef] mt-0.5 font-mono">
                    {(() => {
                      const zMin = unit.vertical_range?.z_min ?? unit.elevation_min_m ?? 0;
                      const zMax = unit.vertical_range?.z_max ?? unit.elevation_max_m ?? 0;
                      return `${zMin >= 0 ? `+${zMin.toFixed(2)}` : zMin.toFixed(2)}m to ${zMax >= 0 ? `+${zMax.toFixed(2)}` : zMax.toFixed(2)}m`;
                    })()}
                  </div>
                  <div className="text-[11px] text-[#a09f99]">
                    Height: {(((unit.vertical_range?.z_max ?? unit.elevation_max_m ?? 0) - (unit.vertical_range?.z_min ?? unit.elevation_min_m ?? 0))).toFixed(2)} m
                  </div>
                </div>

                <div className="bg-[#222428] p-2.5 rounded border border-[#2d3034]">
                  <div className="text-[10px] uppercase text-[#a09f99] font-medium">Unit Floor Area</div>
                  <div className="text-sm font-semibold text-[#f4f3ef] mt-0.5 font-mono">
                    {unit.area_sqm != null ? unit.area_sqm.toFixed(1) : '—'} sq.m
                  </div>
                </div>

                <div className="bg-[#222428] p-2.5 rounded border border-[#2d3034]">
                  <div className="text-[10px] uppercase text-[#a09f99] font-medium">3D Enclosed Volume</div>
                  <div className="text-sm font-semibold text-[#f4f3ef] mt-0.5 font-mono">
                    {unit.volume_cum != null ? unit.volume_cum.toFixed(1) : '—'} cu.m
                  </div>
                </div>
              </div>

              {/* Primary Evidence & Quality Metrics */}
              <div className="space-y-2 text-xs">
                {/* Evidence Used Card */}
                <div className="p-2.5 rounded bg-[#222428] border border-[#2d3034] flex items-center justify-between">
                  <div>
                    <span className="text-[10px] uppercase text-[#a09f99] font-medium block">Height Evidence Used:</span>
                    <span className="font-mono text-xs font-semibold text-[#f4f3ef]">
                      {unit.provenance?.selected_evidence || unit.provenance?.source_type || 'DETERMINISTIC_STRATA'}
                    </span>
                  </div>
                  <div className="text-right">
                    <span className={`px-2 py-0.5 text-[9px] font-mono font-bold rounded border ${
                      unit.provenance?.evidence_tier === 'OBSERVED' ? 'bg-[#4e8a5b]/20 text-[#5a9e69] border-[#4e8a5b]/40' :
                      unit.provenance?.evidence_tier === 'AI_INFERENCE' ? 'bg-[#7c3aed]/20 text-[#c084fc] border-[#7c3aed]/40' :
                      'bg-[#3b82f6]/20 text-[#60a5fa] border-[#3b82f6]/40'
                    }`}>
                      {unit.provenance?.evidence_tier || 'DETERMINISTIC'}
                    </span>
                    {unit.provenance?.uncertainty_m !== undefined && (
                      <span className="text-[#d97757] font-mono text-[10px] block mt-0.5">
                        ±{unit.provenance.uncertainty_m.toFixed(2)} m
                      </span>
                    )}
                  </div>
                </div>

                {/* Validation Status */}
                <div className="flex items-center justify-between p-2 rounded bg-[#222428] border border-[#2d3034]">
                  <span className="text-[#a09f99]">Validation Status:</span>
                  <span
                    className={`inline-flex items-center gap-1 font-medium px-2 py-0.5 rounded text-[11px] ${
                      unit.validation_status === 'PASSED'
                        ? 'bg-[#4e8a5b]/20 text-[#4e8a5b]'
                        : unit.validation_status === 'WARNING'
                        ? 'bg-[#c98a2c]/20 text-[#c98a2c]'
                        : 'bg-[#b84d47]/20 text-[#b84d47]'
                    }`}
                  >
                    {unit.validation_status === 'PASSED' ? (
                      <ShieldCheck className="w-3 h-3" />
                    ) : (
                      <AlertTriangle className="w-3 h-3" />
                    )}
                    {unit.validation_status}
                  </span>
                </div>

                {/* Vertical Classification */}
                <div className="flex items-center justify-between p-2 rounded bg-[#222428] border border-[#2d3034]">
                  <span className="text-[#a09f99]">Vertical Classification:</span>
                  <span className="font-mono text-[#f4f3ef] font-medium">
                    {unit.vertical_classification || unit.classification || 'ELEVATED'}
                  </span>
                </div>

                {/* Data Stage */}
                <div className="flex items-center justify-between p-2 rounded bg-[#222428] border border-[#2d3034]">
                  <span className="text-[#a09f99]">Data Lifecycle Stage:</span>
                  <span className="font-mono text-[#f4f3ef] font-medium">{unit.data_stage}</span>
                </div>

                {(unit.is_multi_floor || unit.unit_type === 'DUPLEX' || (unit.floor_span && unit.floor_span.length > 1)) && (
                  <div className="flex items-center justify-between p-2 rounded bg-[#c86446]/10 border border-[#c86446]/30">
                    <span className="text-[#d97757] font-medium">Duplex / Multi-Floor:</span>
                    <span className="font-mono text-[#f4f3ef] text-[11px]">
                      Spans: {unit.floor_span?.join(' + ') || 'Multiple levels'}
                    </span>
                  </div>
                )}
              </div>
            </>
          )}

          {activeTab === 'provenance' && (
            <ProvenancePanel provenance={unit.provenance} />
          )}

          {activeTab === 'anomalies' && (
            <AnomalyPanel anomalies={unitAnomalies} />
          )}

          {activeTab === 'temporal' && (
            <TemporalChangePanel
              parcelId={digitalTwin?.parcel?.id}
              digitalTwin={digitalTwin}
            />
          )}
        </div>
      </div>
    );
  }

  // Render for Building
  if (selectedItem.type === 'building') {
    const bld = selectedItem.data;
    return (
      <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-4 space-y-4">
        <div className="flex items-center justify-between border-b border-[#2d3034] pb-2">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded bg-[#5c7080]/20 text-[#5c7080]">
              <Box className="w-4 h-4" />
            </span>
            <div>
              <div className="text-[10px] uppercase text-[#a09f99] font-medium">Building Envelope</div>
              <h3 className="text-sm font-semibold text-[#f4f3ef]">{bld.building_name}</h3>
            </div>
          </div>
          {onClose && (
            <button onClick={onClose} className="text-[#a09f99] hover:text-[#f4f3ef] text-xs">
              Close
            </button>
          )}
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-[#222428] p-2.5 rounded border border-[#2d3034]">
            <div className="text-[10px] uppercase text-[#a09f99]">Ground Elevation</div>
            <div className="font-mono text-sm font-semibold text-[#f4f3ef] mt-0.5">
              {(bld.ground_elevation ?? bld.ground_elevation_m ?? 0).toFixed(1)} m AMSL
            </div>
          </div>
          <div className="bg-[#222428] p-2.5 rounded border border-[#2d3034]">
            <div className="text-[10px] uppercase text-[#a09f99]">Total Height</div>
            <div className="font-mono text-sm font-semibold text-[#f4f3ef] mt-0.5">
              {(bld.total_height ?? bld.total_height_m ?? 0).toFixed(1)} m
            </div>
          </div>
          <div className="bg-[#222428] p-2.5 rounded border border-[#2d3034]">
            <div className="text-[10px] uppercase text-[#a09f99]">Levels Above Ground</div>
            <div className="text-sm font-semibold text-[#f4f3ef] mt-0.5">
              {bld.levels_above_ground ?? bld.floors_above_ground ?? 0} Floors
            </div>
          </div>
          <div className="bg-[#222428] p-2.5 rounded border border-[#2d3034]">
            <div className="text-[10px] uppercase text-[#a09f99]">Levels Below Ground</div>
            <div className="text-sm font-semibold text-[#f4f3ef] mt-0.5">
              {bld.levels_below_ground ?? bld.basement_floors ?? 0} Sub-levels
            </div>
          </div>
        </div>

        <div className="text-xs space-y-1.5 border-t border-[#2d3034] pt-2 text-[#a09f99]">
          <div className="flex justify-between">
            <span>Classification:</span>
            <span className="text-[#f4f3ef] font-medium">{bld.classification || bld.structure_type || 'COMMERCIAL_RESIDENTIAL'}</span>
          </div>
          <div className="flex justify-between">
            <span>Height Source:</span>
            <span className="font-mono text-[#d97757] font-medium">
              {bld.ml_provenance?.height_source || 'OBSERVED_SURVEY_METADATA'}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Floor Count Source:</span>
            <span className="font-mono text-[#f4f3ef] font-medium">
              {bld.ml_provenance?.floor_source || 'DETERMINISTIC_BASELINE'}
            </span>
          </div>
          {bld.ml_provenance?.requires_review && (
            <div className="flex items-center gap-1 text-[#c98a2c] text-[11px] bg-[#c98a2c]/10 p-1.5 rounded border border-[#c98a2c]/30 mt-1">
              <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
              <span>Requires Cadastral Engineering Review</span>
            </div>
          )}
          <div className="flex justify-between">
            <span>Roof Type:</span>
            <span className="text-[#f4f3ef] font-medium">{bld.roof_type || 'Terrace'}</span>
          </div>
        </div>

        {/* Cadastral Anomaly Findings for Building */}
        <div className="border-t border-[#2d3034] pt-3">
          <AnomalyPanel anomalies={propertyAnomalies} />
        </div>
      </div>
    );
  }

  // Render for Floor Level
  if (selectedItem.type === 'floor') {
    const floor = selectedItem.data;
    return (
      <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between border-b border-[#2d3034] pb-2">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded bg-[#a09f99]/20 text-[#a09f99]">
              <Layers className="w-4 h-4" />
            </span>
            <div>
              <div className="text-[10px] uppercase text-[#a09f99] font-medium">Floor Slab Plane</div>
              <h3 className="text-sm font-semibold text-[#f4f3ef]">{floor.level_name}</h3>
            </div>
          </div>
          {onClose && (
            <button onClick={onClose} className="text-[#a09f99] hover:text-[#f4f3ef] text-xs">
              Close
            </button>
          )}
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
            <div className="text-[10px] uppercase text-[#a09f99]">Level Code</div>
            <div className="font-mono text-sm font-semibold text-[#d97757] mt-0.5">{floor.level_code}</div>
          </div>
          <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
            <div className="text-[10px] uppercase text-[#a09f99]">Floor Height</div>
            <div className="font-mono text-sm font-semibold text-[#f4f3ef] mt-0.5">
              {(floor.height ?? floor.floor_height_m ?? 0).toFixed(2)} m
            </div>
          </div>
          <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
            <div className="text-[10px] uppercase text-[#a09f99]">Z-Bottom</div>
            <div className="font-mono text-xs font-semibold text-[#f4f3ef] mt-0.5">
              {(() => {
                const zBottom = floor.elevation_bottom ?? floor.elevation_min_m ?? 0;
                return `${zBottom >= 0 ? `+${zBottom.toFixed(2)}` : zBottom.toFixed(2)} m`;
              })()}
            </div>
          </div>
          <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
            <div className="text-[10px] uppercase text-[#a09f99]">Z-Top</div>
            <div className="font-mono text-xs font-semibold text-[#f4f3ef] mt-0.5">
              {(() => {
                const zTop = floor.elevation_top ?? floor.elevation_max_m ?? 0;
                return `${zTop >= 0 ? `+${zTop.toFixed(2)}` : zTop.toFixed(2)} m`;
              })()}
            </div>
          </div>
        </div>

        <div className="text-xs text-[#a09f99] flex justify-between pt-1">
          <span>Stratification Type:</span>
          <span className="text-[#f4f3ef] font-medium">{floor.is_underground ? 'Sub-surface' : 'Super-structure'}</span>
        </div>
      </div>
    );
  }

  // Render for Land Parcel
  if (selectedItem.type === 'parcel') {
    const parcel = selectedItem.data;
    return (
      <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between border-b border-[#2d3034] pb-2">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded bg-[#6b8e72]/20 text-[#6b8e72]">
              <MapPin className="w-4 h-4" />
            </span>
            <div>
              <div className="text-[10px] uppercase text-[#a09f99] font-medium">Base Ground Parcel</div>
              <h3 className="text-sm font-semibold text-[#f4f3ef]">Survey #{parcel.survey_number}</h3>
            </div>
          </div>
          {onClose && (
            <button onClick={onClose} className="text-[#a09f99] hover:text-[#f4f3ef] text-xs">
              Close
            </button>
          )}
        </div>

        <div className="p-2.5 bg-[#222428] rounded border border-[#2d3034]">
          <div className="text-[10px] uppercase text-[#a09f99] font-medium">Base Parcel ULPIN</div>
          <div className="font-mono text-sm font-semibold text-[#f4f3ef] tracking-wider mt-0.5">
            {parcel.ulpin}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
            <div className="text-[10px] uppercase text-[#a09f99]">Area</div>
            <div className="font-mono text-sm font-semibold text-[#f4f3ef] mt-0.5">{parcel.area_sqm != null ? parcel.area_sqm.toFixed(1) : '—'} sq.m</div>
          </div>
          <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
            <div className="text-[10px] uppercase text-[#a09f99]">Perimeter</div>
            <div className="font-mono text-sm font-semibold text-[#f4f3ef] mt-0.5">{parcel.perimeter_m != null ? parcel.perimeter_m.toFixed(1) : '—'} m</div>
          </div>
          <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
            <div className="text-[10px] uppercase text-[#a09f99]">Datum Elevation</div>
            <div className="font-mono text-sm font-semibold text-[#f4f3ef] mt-0.5">
              {(parcel.ground_elevation_amsl ?? parcel.base_elevation_m ?? 0).toFixed(1)} m AMSL
            </div>
          </div>
          <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
            <div className="text-[10px] uppercase text-[#a09f99]">Projected CRS</div>
            <div className="font-mono text-xs font-semibold text-[#6b8e72] mt-0.5">
              {parcel.crs || parcel.spatial_metadata?.projected_crs || parcel.spatial_metadata?.source_crs || 'EPSG:4326'}
            </div>
          </div>
        </div>

        <div className="text-xs space-y-1 border-t border-[#2d3034] pt-2 text-[#a09f99]">
          <div className="flex justify-between">
            <span>Jurisdiction:</span>
            <span className="text-[#f4f3ef] font-medium">
              {[parcel.village || parcel.village_code, parcel.district || parcel.district_code, parcel.state || parcel.state_code].filter(Boolean).join(', ') || 'Cadastral Unit'}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Cadastral Status:</span>
            <span className="text-[#4e8a5b] font-medium">{parcel.status}</span>
          </div>
        </div>

        {/* Cadastral Anomaly Findings for Parcel */}
        <div className="border-t border-[#2d3034] pt-3">
          <AnomalyPanel anomalies={propertyAnomalies} />
        </div>
      </div>
    );
  }

  // Render for Underground / Elevated volume
  return (
    <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between border-b border-[#2d3034] pb-2">
        <div>
          <div className="text-[10px] uppercase text-[#a09f99] font-medium">Spatial Volume</div>
          <h3 className="text-sm font-semibold text-[#f4f3ef]">{selectedItem.data.name}</h3>
        </div>
        {onClose && (
          <button onClick={onClose} className="text-[#a09f99] hover:text-[#f4f3ef] text-xs">
            Close
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
          <div className="text-[10px] uppercase text-[#a09f99]">Type</div>
          <div className="font-medium text-[#f4f3ef] mt-0.5">{selectedItem.data.type}</div>
        </div>
        <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
          <div className="text-[10px] uppercase text-[#a09f99]">Volume</div>
          <div className="font-mono text-sm font-semibold text-[#f4f3ef] mt-0.5">{selectedItem.data.volume_cum.toFixed(1)} cu.m</div>
        </div>
        <div className="bg-[#222428] p-2 rounded border border-[#2d3034] col-span-2">
          <div className="text-[10px] uppercase text-[#a09f99]">Vertical Range</div>
          <div className="font-mono text-xs font-semibold text-[#f4f3ef] mt-0.5">
            {selectedItem.data.vertical_range.z_min.toFixed(2)}m to {selectedItem.data.vertical_range.z_max.toFixed(2)}m
          </div>
        </div>
      </div>
    </div>
  );
};
