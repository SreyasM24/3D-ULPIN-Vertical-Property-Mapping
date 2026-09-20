import React, { useState } from 'react';
import { VerticalUnit, LandParcel } from '../../types/api.ts';
import { ULPINDisplay } from '../digital-twin/ULPINDisplay.tsx';
import { Search, Box, ChevronRight, ShieldCheck, AlertTriangle } from 'lucide-react';

interface PropertyListProps {
  units: VerticalUnit[];
  parcel: LandParcel;
  onSelectUnit: (unit: VerticalUnit) => void;
}

export const PropertyList: React.FC<PropertyListProps> = ({
  units,
  parcel,
  onSelectUnit,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [stageFilter, setStageFilter] = useState('ALL');

  const availableStages = Array.from(
    new Set(units.map((u) => u.data_stage || u.stage).filter(Boolean))
  ) as string[];

  const filteredUnits = units.filter((unit) => {
    const matchesSearch =
      (unit.ulpin_3d || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (unit.unit_number || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (unit.classification || unit.unit_type || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (unit.level_code || '').toLowerCase().includes(searchQuery.toLowerCase());

    const unitStage = unit.data_stage || unit.stage;
    const matchesStage = stageFilter === 'ALL' || unitStage === stageFilter;

    return matchesSearch && matchesStage;
  });

  const locationStr = [
    parcel.village || parcel.village_code,
    parcel.district || parcel.district_code,
    parcel.state || parcel.state_code,
  ]
    .filter(Boolean)
    .join(', ');

  return (
    <div className="space-y-6">
      {/* Header and Parcel Association */}
      <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#2d3034]">
          <div>
            <div className="text-[10px] uppercase font-mono tracking-wider text-[#a09f99]">
              Base Parcel Association
            </div>
            <h2 className="text-base font-semibold text-[#f4f3ef] mt-0.5">
              Survey No. {parcel.survey_number}{locationStr ? ` — ${locationStr}` : ''}
            </h2>
          </div>
          <div className="bg-[#222428] px-3 py-1.5 rounded border border-[#34373d]">
            <span className="text-[10px] uppercase text-[#a09f99] block">Base Parcel ULPIN</span>
            <span className="font-mono text-xs font-semibold text-[#f4f3ef]">{parcel.ulpin}</span>
          </div>
        </div>

        {/* Filter and Search Bar */}
        <div className="pt-4 flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-[#a09f99] absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search by 3D ULPIN, Unit #, Level, or Classification..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 bg-[#222428] border border-[#34373d] text-xs text-[#f4f3ef] rounded focus:border-[#c86446] focus:outline-none font-mono"
            />
          </div>

          <select
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
            className="bg-[#222428] border border-[#34373d] text-xs text-[#f4f3ef] rounded px-3 py-2 focus:border-[#c86446] focus:outline-none"
          >
            <option value="ALL">All Lifecycle Stages ({units.length})</option>
            {availableStages.map((stg) => (
              <option key={stg} value={stg}>
                {stg.replace(/_/g, ' ')}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Property Units Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredUnits.map((unit) => (
          <div
            key={unit.id}
            onClick={() => onSelectUnit(unit)}
            className="bg-[#1c1d20] border border-[#2d3034] hover:border-[#c86446]/60 rounded-lg p-4 cursor-pointer transition-all duration-200 hover:shadow-lg space-y-3 group"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <span className="text-[10px] uppercase tracking-wider text-[#a09f99] font-medium">
                  {unit.level_code} • Unit {unit.unit_number}
                </span>
                <h3 className="text-sm font-semibold text-[#f4f3ef] group-hover:text-[#d97757] transition-colors">
                  {unit.classification}
                </h3>
              </div>

              <span
                className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded ${
                  unit.validation_status === 'PASSED'
                    ? 'bg-[#4e8a5b]/15 text-[#5a9e69]'
                    : 'bg-[#c98a2c]/15 text-[#d49438]'
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

            <ULPINDisplay ulpin3d={unit.ulpin_3d} compact />

            <div className="grid grid-cols-3 gap-2 text-xs pt-1 text-[#a09f99]">
              <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
                <div className="text-[10px] uppercase">Floor Area</div>
                <div className="font-mono text-xs font-medium text-[#f4f3ef] mt-0.5">
                  {(unit.area_sqm ?? unit.carpet_area_sqm ?? 0).toFixed(1)} m²
                </div>
              </div>

              <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
                <div className="text-[10px] uppercase">Volume</div>
                <div className="font-mono text-xs font-medium text-[#f4f3ef] mt-0.5">
                  {(unit.volume_cum ?? unit.volume_cu_m ?? 0).toFixed(1)} m³
                </div>
              </div>

              <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
                <div className="text-[10px] uppercase">Elevation Range</div>
                <div className="font-mono text-xs font-medium text-[#d97757] mt-0.5">
                  {(() => {
                    const zMin = unit.vertical_range?.z_min ?? unit.elevation_min_m ?? 0;
                    const zMax = unit.vertical_range?.z_max ?? unit.elevation_max_m ?? 0;
                    return `${zMin >= 0 ? `+${zMin.toFixed(1)}` : zMin.toFixed(1)} to ${zMax.toFixed(1)}m`;
                  })()}
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-[#2d3034] text-xs text-[#a09f99]">
              <span>Stage: <span className="font-mono text-[#f4f3ef]">{unit.data_stage}</span></span>
              <span className="text-[#d97757] font-medium flex items-center gap-1 group-hover:translate-x-0.5 transition-transform">
                View in 3D Twin <ChevronRight className="w-3.5 h-3.5" />
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
