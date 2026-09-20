import React, { useState } from 'react';
import {
  TemporalChangeReport,
  ChangeEvent,
  DigitalTwin,
} from '../../types/api.ts';
import { compareDigitalTwins, getParcelSnapshot } from '../../lib/api/digitalTwin.ts';
import {
  History,
  AlertTriangle,
  ShieldCheck,
  Activity,
  Layers,
  Box,
  TrendingUp,
  RefreshCw,
  CheckCircle2,
  Info,
} from 'lucide-react';

interface TemporalChangePanelProps {
  parcelId?: string;
  initialReport?: TemporalChangeReport | null;
  digitalTwin?: DigitalTwin | null;
}

export const TemporalChangePanel: React.FC<TemporalChangePanelProps> = ({
  parcelId,
  initialReport,
  digitalTwin,
}) => {
  const [report, setReport] = useState<TemporalChangeReport | null>(initialReport || null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRunTemporalAudit = async () => {
    if (!parcelId) {
      setError('Select a registered parcel first to establish baseline.');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      // 1. Fetch baseline snapshot from FastAPI
      const baselineSnap = await getParcelSnapshot(parcelId);

      // 2. Synthesize a controlled resurvey observation (marked TEST_FIXTURE)
      // e.g. An updated survey proposing a 2.5m height delta and +1 vertical unit
      const observationSnap = JSON.parse(JSON.stringify(baselineSnap));
      observationSnap.snapshot_id = `OBS-SURVEY-${Date.now().toString().slice(-6)}`;
      observationSnap.source = 'TEST_FIXTURE_OBSERVATION';
      observationSnap.total_height_m = (observationSnap.total_height_m || 15.0) + 2.5;

      // Add 1 proposed vertical unit
      if (observationSnap.units && observationSnap.units.length > 0) {
        const sampleUnit = observationSnap.units[0];
        observationSnap.units.push({
          ...sampleUnit,
          id: `UNIT-TEST-NEW-${Date.now().toString().slice(-4)}`,
          unit_number: `T-${(observationSnap.units.length + 1) * 100}`,
          volume_cu_m: (sampleUnit.volume_cu_m || 200.0) + 15.0,
        });
      }

      // 3. Post to compare endpoint
      const result = await compareDigitalTwins({
        parcel_id: parcelId,
        new_observation: observationSnap,
        config: {
          is_test_fixture: true,
          height_tolerance_m: 0.5,
          min_iou_threshold: 0.95,
        },
      });

      setReport(result);
    } catch (err: any) {
      console.error('Temporal comparison failed:', err);
      setError(err?.message || 'Failed to execute temporal change comparison.');
    } finally {
      setIsLoading(false);
    }
  };

  const getSeverityBadgeClass = (severity: string) => {
    switch (severity) {
      case 'NONE':
        return 'bg-[#4e8a5b]/20 text-[#4e8a5b] border-[#4e8a5b]/30';
      case 'MINOR':
        return 'bg-[#5c7080]/20 text-[#5c7080] border-[#5c7080]/30';
      case 'MODERATE':
        return 'bg-[#c98a2c]/20 text-[#c98a2c] border-[#c98a2c]/30';
      case 'SIGNIFICANT':
      case 'CRITICAL':
        return 'bg-[#b84d47]/20 text-[#b84d47] border-[#b84d47]/30';
      default:
        return 'bg-[#2d3034] text-[#a09f99] border-[#2d3034]';
    }
  };

  const getClassificationBadgeClass = (cls: string) => {
    switch (cls) {
      case 'TEST_FIXTURE_CHANGE':
        return 'bg-[#d97757]/20 text-[#d97757] border-[#d97757]/40';
      case 'OBSERVED_CHANGE':
        return 'bg-[#4e8a5b]/20 text-[#4e8a5b] border-[#4e8a5b]/30';
      case 'AI_ESTIMATED_CHANGE':
        return 'bg-[#c98a2c]/20 text-[#c98a2c] border-[#c98a2c]/30';
      default:
        return 'bg-[#5c7080]/20 text-[#5c7080] border-[#5c7080]/30';
    }
  };

  return (
    <div className="space-y-3 text-xs">
      {/* Header / Trigger */}
      <div className="flex items-center justify-between bg-[#222428] p-2.5 rounded border border-[#2d3034]">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-[#d97757]" />
          <div>
            <div className="font-semibold text-[#f4f3ef]">3D Temporal Change Audit</div>
            <div className="text-[10px] text-[#a09f99]">Multi-Epoch Resurvey & Intelligence</div>
          </div>
        </div>
        <button
          onClick={handleRunTemporalAudit}
          disabled={isLoading || !parcelId}
          className="flex items-center gap-1.5 px-2.5 py-1 bg-[#d97757]/20 hover:bg-[#d97757]/30 text-[#d97757] border border-[#d97757]/40 rounded text-xs font-medium transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
          {isLoading ? 'Auditing…' : report ? 'Re-Audit' : 'Run Audit'}
        </button>
      </div>

      {error && (
        <div className="p-2 rounded bg-[#b84d47]/10 border border-[#b84d47]/30 text-[#b84d47] text-xs flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* No report state */}
      {!report && !isLoading && !error && (
        <div className="p-3 bg-[#18191b] rounded border border-[#2d3034] text-center text-[#a09f99] space-y-1">
          <Activity className="w-5 h-5 mx-auto text-[#5c7080] stroke-1" />
          <p className="text-[11px]">
            Execute temporal comparison to audit changes between registered cadastral baseline and subsequent survey/AI proposals.
          </p>
        </div>
      )}

      {/* Active Report View */}
      {report && (
        <div className="space-y-2.5">
          {/* Summary Score Card */}
          <div className="p-3 bg-[#18191b] rounded border border-[#2d3034] space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase text-[#a09f99] font-medium">Comparison ID</span>
              <span className="font-mono text-[11px] text-[#f4f3ef]">{report.comparison_id}</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase text-[#a09f99] font-medium">Classification</span>
              <span
                className={`px-1.5 py-0.5 text-[10px] font-medium rounded border ${getClassificationBadgeClass(
                  report.is_test_fixture ? 'TEST_FIXTURE_CHANGE' : 'DETERMINISTIC_CHANGE'
                )}`}
              >
                {report.is_test_fixture ? 'TEST_FIXTURE_CHANGE' : 'DETERMINISTIC_CHANGE'}
              </span>
            </div>

            {/* Score Bar */}
            <div>
              <div className="flex justify-between text-[11px] mb-1">
                <span className="text-[#a09f99]">Technical Change Score:</span>
                <span className="font-mono font-semibold text-[#f4f3ef]">
                  {(report.technical_change_score * 100).toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-[#2d3034] rounded-full h-1.5 overflow-hidden">
                <div
                  className={`h-full ${
                    report.technical_change_score > 0.5
                      ? 'bg-[#b84d47]'
                      : report.technical_change_score > 0.2
                      ? 'bg-[#c98a2c]'
                      : 'bg-[#4e8a5b]'
                  }`}
                  style={{ width: `${Math.max(5, report.technical_change_score * 100)}%` }}
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-1">
              <span className="text-[10px] uppercase text-[#a09f99] font-medium">Severity</span>
              <span
                className={`px-2 py-0.5 text-[10px] font-semibold rounded border ${getSeverityBadgeClass(
                  report.change_severity
                )}`}
              >
                {report.change_severity}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase text-[#a09f99] font-medium">Review Status</span>
              <span
                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${
                  report.requires_cadastral_review
                    ? 'bg-[#c98a2c]/20 text-[#c98a2c]'
                    : 'bg-[#4e8a5b]/20 text-[#4e8a5b]'
                }`}
              >
                {report.requires_cadastral_review ? (
                  <AlertTriangle className="w-3 h-3" />
                ) : (
                  <ShieldCheck className="w-3 h-3" />
                )}
                {report.requires_cadastral_review ? 'Cadastral Review Required' : 'Verified Consistent'}
              </span>
            </div>
          </div>

          {/* Metric Differences Grid */}
          <div className="grid grid-cols-2 gap-1.5 text-[11px]">
            {report.footprint_comparison && (
              <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
                <div className="text-[10px] text-[#a09f99]">Footprint IoU</div>
                <div className="font-mono text-xs font-semibold text-[#f4f3ef] mt-0.5">
                  {(report.footprint_comparison.iou * 100).toFixed(1)}%
                </div>
                <div className="text-[10px] text-[#a09f99]">
                  Δ Area: {report.footprint_comparison.area_delta_sqm.toFixed(1)} m²
                </div>
              </div>
            )}

            {report.height_comparison && (
              <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
                <div className="text-[10px] text-[#a09f99]">Height Delta</div>
                <div className="font-mono text-xs font-semibold text-[#f4f3ef] mt-0.5">
                  {(report.height_comparison.height_delta_m ?? 0) >= 0 ? '+' : ''}
                  {(report.height_comparison.height_delta_m ?? 0).toFixed(2)} m
                </div>
                <div className="text-[10px] text-[#a09f99]">
                  Δ: {(report.height_comparison.height_change_pct ?? 0).toFixed(1)}%
                </div>
              </div>
            )}

            {report.floor_comparison && (
              <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
                <div className="text-[10px] text-[#a09f99]">Floor Strata Delta</div>
                <div className="font-mono text-xs font-semibold text-[#f4f3ef] mt-0.5">
                  {report.floor_comparison.floor_count_delta >= 0 ? '+' : ''}
                  {report.floor_comparison.floor_count_delta} Floors
                </div>
                <div className="text-[10px] text-[#a09f99]">
                  {report.floor_comparison.new_floor_count} Total Levels
                </div>
              </div>
            )}

            {report.unit_comparison && (
              <div className="bg-[#222428] p-2 rounded border border-[#2d3034]">
                <div className="text-[10px] text-[#a09f99]">Vertical Units Delta</div>
                <div className="font-mono text-xs font-semibold text-[#f4f3ef] mt-0.5">
                  {report.unit_comparison.unit_count_delta >= 0 ? '+' : ''}
                  {report.unit_comparison.unit_count_delta} Units
                </div>
                <div className="text-[10px] text-[#a09f99]">
                  {report.unit_comparison.new_unit_count} Total Units
                </div>
              </div>
            )}
          </div>

          {/* Change Events List */}
          {report.change_events && report.change_events.length > 0 && (
            <div className="space-y-1.5">
              <div className="text-[10px] uppercase text-[#a09f99] font-medium">
                Detected Change Events ({report.change_events.length})
              </div>
              <div className="space-y-1 max-h-36 overflow-y-auto">
                {report.change_events.map((ev, idx) => (
                  <div
                    key={idx}
                    className="p-2 bg-[#222428] rounded border border-[#2d3034] text-[11px] space-y-0.5"
                  >
                    <div className="flex items-center justify-between font-medium">
                      <span className="text-[#f4f3ef]">{ev.change_type}</span>
                      <span className="text-[9px] px-1 py-0.5 rounded bg-[#2d3034] text-[#a09f99]">
                        {ev.source}
                      </span>
                    </div>
                    <p className="text-[10px] text-[#a09f99] leading-tight">{ev.explanation}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Mandatory Cadastral Legal Disclaimer */}
          <div className="p-2 rounded bg-[#18191b] border border-[#2d3034] text-[10px] text-[#a09f99] space-y-1">
            <div className="flex items-center gap-1 text-[#d97757] font-semibold text-[10px]">
              <Info className="w-3 h-3 flex-shrink-0" />
              <span>Advisory Notice</span>
            </div>
            <p className="leading-tight">{report.legal_disclaimer}</p>
          </div>
        </div>
      )}
    </div>
  );
};
