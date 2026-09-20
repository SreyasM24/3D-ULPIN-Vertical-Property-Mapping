import React from 'react';
import { Compass, Database, Layers } from 'lucide-react';
import { LandParcel } from '../../types/api.ts';

interface TopBarProps {
  onLoadDemo: () => void;
  isBackendConnected?: boolean;
  activeCrs?: string;
  parcelNumber?: string;
  parcels?: LandParcel[];
  selectedParcel?: LandParcel | null;
  onSelectParcel?: (parcel: LandParcel) => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  onLoadDemo,
  isBackendConnected,
  activeCrs,
  parcelNumber,
  parcels = [],
  selectedParcel,
  onSelectParcel,
}) => {
  return (
    <header className="h-16 bg-[#18191b] border-b border-[#2d3034] px-4 md:px-6 flex items-center justify-between z-20">
      {/* Title & Organization Brand */}
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded bg-[#c86446]/15 border border-[#c86446]/40 flex items-center justify-center text-[#d97757]">
          <Compass className="w-4 h-4" />
        </div>
        <div>
          <h1 className="text-sm font-semibold tracking-tight text-[#f4f3ef]">
            3D ULPIN Generation & Vertical Property Mapping
          </h1>
          <p className="text-[11px] text-[#a09f99] hidden md:block">
            National Cadastral Stratification & 3D Land Administration Prototype
          </p>
        </div>
      </div>

      {/* Right Controls: Parcel Switcher & Load Demo */}
      <div className="flex items-center gap-3">
        {parcels.length > 0 && onSelectParcel && (
          <div className="flex items-center gap-1.5 bg-[#222428] border border-[#3e4249] rounded px-2 py-1 text-xs">
            <Layers className="w-3.5 h-3.5 text-[#6b8e72]" />
            <select
              value={selectedParcel?.id || ''}
              onChange={(e) => {
                const found = parcels.find((p) => p.id === e.target.value);
                if (found) onSelectParcel(found);
              }}
              className="bg-transparent text-[#f4f3ef] text-xs font-mono focus:outline-none cursor-pointer"
              title="Switch Cadastral Parcel"
            >
              {parcels.map((p) => (
                <option key={p.id} value={p.id} className="bg-[#222428] text-[#f4f3ef]">
                  #{p.survey_number} ({p.district || p.district_code || 'PUN'})
                </option>
              ))}
            </select>
          </div>
        )}

        <button
          onClick={onLoadDemo}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium bg-[#222428] hover:bg-[#2b2d32] border border-[#3e4249] text-[#f4f3ef] transition-colors shadow-sm"
          title="Reset or reload cadastral dataset"
        >
          <Database className="w-3.5 h-3.5 text-[#d97757]" />
          <span>Load Demo</span>
        </button>
      </div>
    </header>
  );
};
