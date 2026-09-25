import React from 'react';
import {
  SystemHealth,
  SystemCapabilities,
  LandParcel,
  ProcessingJob,
} from '../../types/api.ts';
import {
  Activity,
  Layers,
  Box,
  ShieldCheck,
  Cpu,
} from 'lucide-react';

interface SystemStatusProps {
  health?: SystemHealth | null;
  capabilities?: SystemCapabilities | null;
  parcels: LandParcel[];
  activeJob?: ProcessingJob | null;
  totalUnitsCount?: number;
  validationStatusSummary?: string;
  isBackendConnected: boolean;
  isConnecting?: boolean;
  qualityScore?: number | null;
  qualityGrade?: string | null;
  rulesCount?: number | null;
}

export const SystemStatus: React.FC<SystemStatusProps> = ({
  health,
  capabilities,
  parcels,
  activeJob,
  totalUnitsCount = 0,
  validationStatusSummary,
  isBackendConnected,
  isConnecting = false,
  qualityScore,
  qualityGrade,
  rulesCount,
}) => {
  const displayScore = qualityScore != null ? `${qualityScore.toFixed(1)} Quality Score` : (validationStatusSummary || 'Awaiting Audit');
  const displayGrade = qualityGrade || (isBackendConnected ? 'AUDIT READY' : (isConnecting ? 'INITIALIZING' : 'OFFLINE'));
  const displayRules = rulesCount != null ? `${rulesCount} Rules` : (capabilities?.deterministic_rules_count ? `${capabilities.deterministic_rules_count} Rules` : (isConnecting ? 'Connecting…' : 'Active Engine'));
  const displayVersion = capabilities?.version || health?.version || (isConnecting ? 'Connecting…' : 'FastAPI v1');

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-[#a09f99]">
          Cadastral Engine Runtime Status
        </h2>
      </div>

      {/* Useful system information grid */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
        {/* 1. Processing Status */}
        <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-3.5 space-y-1">
          <div className="flex items-center justify-between text-[#a09f99]">
            <span className="text-[10px] uppercase font-medium">Processing Status</span>
            <Activity className="w-3.5 h-3.5 text-[#d97757]" />
          </div>
          <div className="text-sm font-semibold text-[#f4f3ef] font-mono">
            {activeJob ? activeJob.status : 'STANDBY'}
          </div>
          <div className="text-[11px] text-[#a09f99] truncate">
            {activeJob ? activeJob.current_stage : 'Queue idle'}
          </div>
        </div>

        {/* 2. Parcels Processed */}
        <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-3.5 space-y-1">
          <div className="flex items-center justify-between text-[#a09f99]">
            <span className="text-[10px] uppercase font-medium">Parcels Processed</span>
            <Layers className="w-3.5 h-3.5 text-[#6b8e72]" />
          </div>
          <div className="text-sm font-semibold text-[#f4f3ef] font-mono">
            {parcels.length}
          </div>
          <div className="text-[11px] text-[#a09f99] truncate">
            {parcels.length > 0 ? `Survey ${parcels[0].survey_number}` : 'No active parcels'}
          </div>
        </div>

        {/* 3. 3D Units */}
        <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-3.5 space-y-1">
          <div className="flex items-center justify-between text-[#a09f99]">
            <span className="text-[10px] uppercase font-medium">3D Stratified Units</span>
            <Box className="w-3.5 h-3.5 text-[#d97757]" />
          </div>
          <div className="text-sm font-semibold text-[#f4f3ef] font-mono">
            {totalUnitsCount} Units
          </div>
          <div className="text-[11px] text-[#a09f99]">Sub-surface to Air Rights</div>
        </div>

        {/* 4. Validation Status */}
        <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-3.5 space-y-1">
          <div className="flex items-center justify-between text-[#a09f99]">
            <span className="text-[10px] uppercase font-medium">Validation Status</span>
            <ShieldCheck className="w-3.5 h-3.5 text-[#4e8a5b]" />
          </div>
          <div className="text-sm font-semibold text-[#f4f3ef]">
            {displayScore}
          </div>
          <div className="text-[11px] text-[#5a9e69] font-medium uppercase truncate">
            {displayGrade}
          </div>
        </div>

        {/* 5. System Capability */}
        <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-3.5 space-y-1 col-span-2 md:col-span-1">
          <div className="flex items-center justify-between text-[#a09f99]">
            <span className="text-[10px] uppercase font-medium">Engine Capability</span>
            <Cpu className="w-3.5 h-3.5 text-[#5c7080]" />
          </div>
          <div className="text-sm font-semibold text-[#f4f3ef] font-mono">
            {displayRules}
          </div>
          <div className="text-[11px] text-[#a09f99] truncate font-mono">
            {displayVersion}
          </div>
        </div>
      </div>
    </div>
  );
};
