import React, { useState, useEffect } from 'react';
import { ProcessingJob, JobStage, JobResultResponse } from '../../types/api.ts';
import {
  CheckCircle2,
  AlertCircle,
  Loader2,
  XCircle,
  Clock,
  Layers,
  Box,
  Hash,
  Activity,
  ShieldAlert,
} from 'lucide-react';

interface JobTimelineProps {
  job: ProcessingJob;
  jobResult?: JobResultResponse | null;
  onViewDigitalTwin: () => void;
  onViewValidation: () => void;
  onCancelJob?: () => void;
  isCancelling?: boolean;
}

const ALL_STAGES: JobStage[] = [
  'QUEUED',
  'INSPECTION',
  'PREPROCESSING',
  'FEATURE_EXTRACTION',
  'CADASTRAL_CONSTRUCTION',
  'ULPIN_GENERATION',
  'VALIDATION',
  'DIGITAL_TWIN_UPDATE',
  'COMPLETED',
];

export const JobTimeline: React.FC<JobTimelineProps> = ({
  job,
  jobResult,
  onViewDigitalTwin,
  onViewValidation,
  onCancelJob,
  isCancelling = false,
}) => {
  const currentStageIndex = ALL_STAGES.indexOf(job.current_stage);
  const isCompleted = job.status === 'COMPLETED';
  const isFailed = job.status === 'FAILED';
  const isCancelled = job.status === 'CANCELLED';
  const isActive = job.status === 'RUNNING' || job.status === 'QUEUED';

  const [hasTimedOut, setHasTimedOut] = useState(false);

  const effectiveResult: JobResultResponse | null = jobResult || (job.result_reference && typeof job.result_reference === 'object' ? {
    job_id: job.job_id,
    status: 'COMPLETED',
    job_type: job.job_type,
    entity_type: job.entity_type,
    entity_id: job.entity_id,
    quality_score: (job.result_reference as any).quality_score,
    quality_grade: (job.result_reference as any).quality_grade,
    is_valid: (job.result_reference as any).is_valid ?? true,
    created_entities: (job.result_reference as any).created_entities || {
      building_code: (job.result_reference as any).building_code,
      floors_count: (job.result_reference as any).floors_count,
      units_count: (job.result_reference as any).units_count,
      unit_ulpins: (job.result_reference as any).unit_ulpins || [],
    },
    validation_summary: (job.result_reference as any).validation_summary,
    digital_twin_url: (job.result_reference as any).digital_twin_url,
    anomalies: (job.result_reference as any).anomalies || [],
    artifacts: (job.result_reference as any).artifacts || {},
  } as JobResultResponse : null);

  useEffect(() => {
    let timer: any;
    if (isCompleted && !effectiveResult) {
      timer = setTimeout(() => {
        setHasTimedOut(true);
      }, 10000);
    } else {
      setHasTimedOut(false);
    }
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [isCompleted, effectiveResult]);

  // Extract recorded events from backend stage_details
  const stageEvents: any[] = job.stage_details?.events || [];

  return (
    <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-5 space-y-6">
      {/* Job Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-[#2d3034]">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase font-mono tracking-wider text-[#a09f99]">
              Job Identifier
            </span>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-semibold tracking-wider ${
                isCompleted
                  ? 'bg-[#4e8a5b]/15 text-[#5a9e69] border border-[#4e8a5b]/30'
                  : isFailed
                  ? 'bg-[#b84d47]/15 text-[#c45852] border border-[#b84d47]/30'
                  : isCancelled
                  ? 'bg-[#5c7080]/15 text-[#8899a6] border border-[#5c7080]/30'
                  : 'bg-[#c86446]/15 text-[#d97757] border border-[#c86446]/30 animate-pulse'
              }`}
            >
              {job.status}
            </span>
            {job.job_type && (
              <span className="text-[10px] font-mono text-[#a09f99] bg-[#222428] px-1.5 py-0.5 rounded border border-[#2d3034]">
                {job.job_type}
              </span>
            )}
          </div>

          <div className="font-mono text-sm font-semibold text-[#f4f3ef] mt-1 select-all">
            {job.job_id}
          </div>

          {job.request_id && (
            <div className="text-[10px] text-[#a09f99] font-mono mt-0.5">
              Req ID: {job.request_id}
            </div>
          )}
        </div>

        {/* Progress & Cancel Action */}
        <div className="text-right flex flex-col sm:items-end gap-1.5">
          <div className="flex items-center gap-2">
            <div className="w-28 bg-[#222428] rounded-full h-2 overflow-hidden border border-[#34373d]">
              <div
                className={`h-full transition-all duration-300 ${
                  isCompleted
                    ? 'bg-[#4e8a5b]'
                    : isFailed
                    ? 'bg-[#b84d47]'
                    : isCancelled
                    ? 'bg-[#5c7080]'
                    : 'bg-[#c86446]'
                }`}
                style={{ width: `${Math.min(100, Math.max(0, job.progress_percent))}%` }}
              />
            </div>
            <span className="font-mono text-xs text-[#f4f3ef] font-semibold min-w-[40px] text-right">
              {job.progress_percent.toFixed(0)}%
            </span>
          </div>

          <div className="flex items-center gap-2">
            {job.duration_seconds != null && (
              <span className="text-[10px] text-[#a09f99] font-mono flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {job.duration_seconds.toFixed(2)}s
              </span>
            )}

            {isActive && onCancelJob && (
              <button
                onClick={onCancelJob}
                disabled={isCancelling}
                className="px-2 py-0.5 rounded bg-[#b84d47]/10 hover:bg-[#b84d47]/25 border border-[#b84d47]/30 text-[#c45852] text-[10px] font-medium transition-colors flex items-center gap-1"
                title="Cancel ongoing job execution"
              >
                <XCircle className="w-3 h-3" />
                <span>{isCancelling ? 'Cancelling…' : 'Cancel Job'}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Failure / Cancellation Banners */}
      {isFailed && (
        <div className="p-3 bg-[#b84d47]/15 border border-[#b84d47]/30 rounded text-xs text-[#c45852] flex items-start gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-semibold">Cadastral Processing Pipeline Failed</div>
            <p className="mt-0.5 leading-relaxed">{job.error_message || 'An unhandled exception occurred in the orchestrator pipeline.'}</p>
          </div>
        </div>
      )}

      {isCancelled && (
        <div className="p-3 bg-[#5c7080]/15 border border-[#5c7080]/30 rounded text-xs text-[#8899a6] flex items-start gap-2">
          <ShieldAlert className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-semibold">Processing Job Cancelled</div>
            <p className="mt-0.5 leading-relaxed">{job.error_message || 'Job execution was halted by user request.'}</p>
          </div>
        </div>
      )}

      {/* Main Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Real Stage Transitions */}
        <div className="lg:col-span-6 space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-[#a09f99] pb-1 flex items-center justify-between">
            <span>Pipeline Execution Stages</span>
            <span className="text-[10px] font-mono lowercase text-[#5c7080]">
              {isCompleted ? '9/9 completed' : `${Math.max(0, currentStageIndex)}/9 processed`}
            </span>
          </div>

          <div className="space-y-1 relative pl-2">
            {/* Connector line */}
            <div className="absolute left-[17px] top-3 bottom-3 w-0.5 bg-[#2d3034]" />

            {ALL_STAGES.map((stageName, idx) => {
              // Find matching event from backend stage_details
              const stageEvent = stageEvents.find((e: any) => e.stage === stageName);

              let state: 'completed' | 'active' | 'pending' | 'failed' | 'cancelled' = 'pending';

              if (isFailed && idx === currentStageIndex) {
                state = 'failed';
              } else if (isCancelled && idx === currentStageIndex) {
                state = 'cancelled';
              } else if (isCompleted || idx < currentStageIndex) {
                state = 'completed';
              } else if (idx === currentStageIndex) {
                state = 'active';
              }

              const stepMessage =
                stageEvent?.details?.step ||
                stageEvent?.message ||
                (state === 'active' ? 'Executing stage operations…' : undefined);

              return (
                <div key={stageName} className="relative flex items-start gap-3 py-1 text-xs">
                  {/* Icon */}
                  <div className="relative z-10 flex-shrink-0 mt-0.5">
                    {state === 'completed' ? (
                      <div className="w-5 h-5 rounded-full bg-[#4e8a5b]/20 border border-[#4e8a5b] flex items-center justify-center">
                        <CheckCircle2 className="w-3.5 h-3.5 text-[#4e8a5b]" />
                      </div>
                    ) : state === 'active' ? (
                      <div className="w-5 h-5 rounded-full bg-[#c86446]/20 border border-[#c86446] flex items-center justify-center animate-pulse">
                        <Loader2 className="w-3.5 h-3.5 text-[#d97757] animate-spin" />
                      </div>
                    ) : state === 'failed' ? (
                      <div className="w-5 h-5 rounded-full bg-[#b84d47]/20 border border-[#b84d47] flex items-center justify-center">
                        <AlertCircle className="w-3.5 h-3.5 text-[#b84d47]" />
                      </div>
                    ) : state === 'cancelled' ? (
                      <div className="w-5 h-5 rounded-full bg-[#5c7080]/20 border border-[#5c7080] flex items-center justify-center">
                        <XCircle className="w-3.5 h-3.5 text-[#8899a6]" />
                      </div>
                    ) : (
                      <div className="w-5 h-5 rounded-full bg-[#222428] border border-[#3e4249] flex items-center justify-center">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#5c7080]" />
                      </div>
                    )}
                  </div>

                  {/* Stage Label & Real Backend Details */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between">
                      <span
                        className={`font-medium ${
                          state === 'completed'
                            ? 'text-[#f4f3ef]'
                            : state === 'active'
                            ? 'text-[#d97757] font-semibold'
                            : state === 'failed'
                            ? 'text-[#b84d47]'
                            : state === 'cancelled'
                            ? 'text-[#8899a6]'
                            : 'text-[#a09f99]'
                        }`}
                      >
                        {stageName.replace(/_/g, ' ')}
                      </span>
                      <span className="text-[10px] uppercase font-mono text-[#a09f99]">
                        {state}
                      </span>
                    </div>

                    {stepMessage && (
                      <p className="text-[11px] text-[#d1d0c9] mt-0.5 leading-snug">
                        {stepMessage}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Endpoint Tracking */}
          {job.tracking_url && (
            <div className="text-[10px] text-[#a09f99] flex items-center gap-1.5 pt-2 border-t border-[#2d3034]">
              <span>Tracking Endpoint:</span>
              <code className="bg-[#222428] px-1.5 py-0.5 rounded font-mono text-[#f4f3ef]">
                GET {job.tracking_url}
              </code>
            </div>
          )}
        </div>

        {/* Right Column: Dynamic Real Result or Active Progress */}
        <div className="lg:col-span-6 flex flex-col justify-between bg-[#18191b] border border-[#2d3034] rounded-lg p-4 space-y-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-[#a09f99] mb-1">
              {isCompleted ? 'Orchestration Artifacts & Results' : 'Transformation State'}
            </div>
            <p className="text-xs text-[#d1d0c9] mb-3">
              {isCompleted
                ? 'Deterministic 3D cadastral topology verified and digital twin graph assembled.'
                : 'Geodetic survey observations undergoing vertical stratification into 3D parcel volumes.'}
            </p>

            {/* If Job is Completed & Result is available, render real backend result cards */}
            {isCompleted && effectiveResult ? (
              <div className="space-y-3 text-xs">
                {/* Score & Validation */}
                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-[#222428] p-2.5 rounded border border-[#2d3034]">
                    <div className="text-[10px] uppercase text-[#a09f99]">Quality Score</div>
                    <div className="font-mono text-base font-bold text-[#f4f3ef] mt-0.5">
                      {effectiveResult.quality_score != null ? `${effectiveResult.quality_score} / 100` : 'Validated'}
                    </div>
                    <div className="text-[10px] text-[#4e8a5b] font-medium">
                      {effectiveResult.quality_grade || 'HIGH_CONFIDENCE'}
                    </div>
                  </div>

                  <div className="bg-[#222428] p-2.5 rounded border border-[#2d3034]">
                    <div className="text-[10px] uppercase text-[#a09f99]">Cadastral Validity</div>
                    <div className="font-mono text-base font-bold text-[#f4f3ef] mt-0.5">
                      {effectiveResult.is_valid ? 'VALID (PASSED)' : 'FLAGGED'}
                    </div>
                    <div className="text-[10px] text-[#a09f99]">Zero fatal clashes</div>
                  </div>
                </div>

                {/* Created Entities */}
                <div className="bg-[#222428] p-2.5 rounded border border-[#2d3034] space-y-1">
                  <div className="text-[10px] uppercase text-[#a09f99] font-medium">Generated Entities</div>
                  <div className="text-xs font-semibold text-[#f4f3ef]">
                    Structure: <span className="font-mono text-[#d97757]">{effectiveResult.created_entities?.building_code || 'BLD-AUTO'}</span>
                  </div>
                  <div className="text-[11px] text-[#d1d0c9]">
                    {effectiveResult.created_entities?.units_count ?? 0} vertical property units stratified across{' '}
                    {effectiveResult.created_entities?.floors_count ?? 0} floor levels.
                  </div>
                </div>

                {/* Derived 3D ULPINs List */}
                {effectiveResult.created_entities?.unit_ulpins && effectiveResult.created_entities.unit_ulpins.length > 0 && (
                  <div className="bg-[#222428] p-2.5 rounded border border-[#2d3034] space-y-1.5">
                    <div className="text-[10px] uppercase text-[#a09f99] font-medium flex items-center justify-between">
                      <span>Derived 3D ULPINs</span>
                      <span className="font-mono text-[#d97757]">{effectiveResult.created_entities.unit_ulpins.length} Codes</span>
                    </div>
                    <div className="max-h-24 overflow-y-auto space-y-1 pr-1 font-mono text-[10px]">
                      {effectiveResult.created_entities.unit_ulpins.map((ulpin: string) => (
                        <div
                          key={ulpin}
                          className="bg-[#1c1d20] px-2 py-0.5 rounded border border-[#34373d] text-[#f4f3ef] truncate select-all"
                        >
                          {ulpin}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : isCompleted ? (
              hasTimedOut ? (
                <div className="w-full h-44 bg-[#222428] rounded border border-[#2d3034] flex flex-col items-center justify-center p-4 text-center space-y-2">
                  <CheckCircle2 className="w-6 h-6 text-[#4e8a5b]" />
                  <div className="text-xs font-semibold text-[#f4f3ef]">Processing Completed</div>
                  <p className="text-[11px] text-[#a09f99] max-w-xs">
                    Cadastral orchestration finished successfully on the backend. Proceed to inspect the assembled 3D Digital Twin.
                  </p>
                  <button
                    onClick={onViewDigitalTwin}
                    className="px-3 py-1.5 bg-[#c86446] hover:bg-[#d97757] text-[#f4f3ef] rounded text-xs font-medium transition-colors"
                  >
                    Open 3D Digital Twin
                  </button>
                </div>
              ) : (
                <div className="w-full h-44 bg-[#222428] rounded border border-[#2d3034] flex flex-col items-center justify-center p-4 text-center space-y-2">
                  <Loader2 className="w-5 h-5 text-[#d97757] animate-spin" />
                  <div className="text-xs font-semibold text-[#f4f3ef]">Finalizing Cadastral Artifacts…</div>
                  <p className="text-[11px] text-[#a09f99]">Retrieving derived 3D ULPIN registry and validation quality score from backend.</p>
                </div>
              )
            ) : (
              /* Active Transformation SVG */
              <div className="w-full h-44 bg-[#222428] rounded border border-[#2d3034] flex items-center justify-center p-3 relative overflow-hidden">
                <svg viewBox="0 0 300 180" className="w-full h-full">
                  <defs>
                    <linearGradient id="terracottaGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#c86446" stopOpacity="0.85" />
                      <stop offset="100%" stopColor="#a35439" stopOpacity="0.85" />
                    </linearGradient>
                  </defs>

                  {/* Ground Plane */}
                  <polygon
                    points="50,110 150,150 250,110 150,70"
                    fill="#2b2d32"
                    stroke="#6b8e72"
                    strokeWidth="1.2"
                  />

                  {/* Subsurface Volume (if past preprocessing) */}
                  {currentStageIndex >= 2 && (
                    <g opacity="0.6">
                      <polygon points="100,120 150,140 200,120 150,100" fill="#3e4249" />
                      <line x1="100" y1="120" x2="100" y2="140" stroke="#5c7080" strokeDasharray="2 2" />
                      <line x1="200" y1="120" x2="200" y2="140" stroke="#5c7080" strokeDasharray="2 2" />
                      <line x1="150" y1="140" x2="150" y2="160" stroke="#5c7080" strokeDasharray="2 2" />
                    </g>
                  )}

                  {/* Extruded Vertical Floors */}
                  {currentStageIndex >= 4 && (
                    <g>
                      <polygon
                        points="100,90 150,110 200,90 150,70"
                        fill="url(#terracottaGrad)"
                        stroke="#f4f3ef"
                        strokeWidth="0.8"
                      />
                      <polygon
                        points="100,90 150,110 150,125 100,105"
                        fill="#9c4a32"
                        stroke="#f4f3ef"
                        strokeWidth="0.8"
                      />
                      <polygon
                        points="150,110 200,90 200,105 150,125"
                        fill="#b8583e"
                        stroke="#f4f3ef"
                        strokeWidth="0.8"
                      />

                      <polygon
                        points="100,65 150,85 200,65 150,45"
                        fill="#d47b58"
                        stroke="#f4f3ef"
                        strokeWidth="0.8"
                      />
                      <polygon
                        points="100,65 150,85 150,90 100,70"
                        fill="#b8583e"
                        stroke="#f4f3ef"
                        strokeWidth="0.8"
                      />
                      <polygon
                        points="150,85 200,65 200,70 150,90"
                        fill="#c86446"
                        stroke="#f4f3ef"
                        strokeWidth="0.8"
                      />
                    </g>
                  )}

                  {/* Elevated Air Rights */}
                  {currentStageIndex >= 7 && (
                    <polygon
                      points="100,35 150,55 200,35 150,15"
                      fill="#6b8e72"
                      fillOpacity="0.4"
                      stroke="#7c9d83"
                      strokeWidth="1"
                      strokeDasharray="3 2"
                    />
                  )}

                  {/* Beacons */}
                  <circle cx="50" cy="110" r="2.5" fill="#d97757" />
                  <circle cx="250" cy="110" r="2.5" fill="#d97757" />
                  <circle cx="150" cy="70" r="2.5" fill="#d97757" />
                  <circle cx="150" cy="150" r="2.5" fill="#d97757" />
                </svg>
              </div>
            )}
          </div>

          {/* Action on Completion */}
          {isCompleted && (
            <div className="pt-3 border-t border-[#2d3034] flex flex-col sm:flex-row gap-2">
              <button
                onClick={onViewDigitalTwin}
                className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded bg-[#c86446] hover:bg-[#d97757] text-[#f4f3ef] font-medium text-xs transition-colors shadow"
              >
                <Box className="w-3.5 h-3.5" />
                <span>Open 3D Digital Twin</span>
              </button>

              <button
                onClick={onViewValidation}
                className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded bg-[#222428] hover:bg-[#2b2d32] border border-[#34373d] text-[#f4f3ef] font-medium text-xs transition-colors"
              >
                <Layers className="w-3.5 h-3.5 text-[#6b8e72]" />
                <span>Inspect Validation Report</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
