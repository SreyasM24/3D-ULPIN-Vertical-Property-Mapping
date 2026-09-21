import React, { useState, useEffect, useCallback } from 'react';
import { AppShell } from './components/layout/AppShell.tsx';
import { OverviewHero } from './components/overview/OverviewHero.tsx';
import { SystemStatus } from './components/overview/SystemStatus.tsx';
import { ProcessingForm } from './components/processing/ProcessingForm.tsx';
import { JobTimeline } from './components/processing/JobTimeline.tsx';
import { DigitalTwinViewer } from './components/digital-twin/DigitalTwinViewer.tsx';
import { LayerControl, LayerVisibilityState } from './components/digital-twin/LayerControl.tsx';
import { PropertyInspector, SelectedCadastralItem } from './components/digital-twin/PropertyInspector.tsx';
import { ValidationSummary } from './components/validation/ValidationSummary.tsx';
import { ValidationIssues } from './components/validation/ValidationIssues.tsx';
import { PropertyList } from './components/property/PropertyList.tsx';

import {
  NavigationTab,
  LandParcel,
  DigitalTwin,
  DigitalTwinValidationReport,
  ProcessingJob,
  JobResultResponse,
  ParcelProcessJobRequest,
  SystemHealth,
  SystemCapabilities,
  CreateSurveyJobRequest,
  VerticalUnit,
} from './types/api.ts';

import { healthApi } from './lib/api/health.ts';
import { parcelsApi } from './lib/api/parcels.ts';
import { digitalTwinApi } from './lib/api/digitalTwin.ts';
import { validationApi } from './lib/api/validation.ts';
import { jobsApi } from './lib/api/jobs.ts';
import { AlertCircle, RefreshCw, Box, ShieldCheck, Layers } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState<NavigationTab>('overview');
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Dynamic Cadastral Data State (initialized to null/empty)
  const [parcels, setParcels] = useState<LandParcel[]>([]);
  const [selectedParcel, setSelectedParcel] = useState<LandParcel | null>(null);
  const [digitalTwin, setDigitalTwin] = useState<DigitalTwin | null>(null);
  const [validationReport, setValidationReport] = useState<DigitalTwinValidationReport | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [capabilities, setCapabilities] = useState<SystemCapabilities | null>(null);

  // Active Job, Polling & Result State
  const [activeJob, setActiveJob] = useState<ProcessingJob | null>(null);
  const [jobResult, setJobResult] = useState<JobResultResponse | null>(null);
  const [isSubmittingJob, setIsSubmittingJob] = useState<boolean>(false);
  const [isCancellingJob, setIsCancellingJob] = useState<boolean>(false);

  // 3D Digital Twin Viewer Controls & Selection
  const [layers, setLayers] = useState<LayerVisibilityState>({
    parcel: true,
    building: true,
    floors: true,
    units: true,
    underground: true,
    sharedCommon: true,
  });
  const [wireframe, setWireframe] = useState<boolean>(false);
  const [selectedItem, setSelectedItem] = useState<SelectedCadastralItem>(null);
  const [resetViewTrigger, setResetViewTrigger] = useState<number>(0);

  // Bounded timeout promise wrapper preventing hanging network calls
  const withTimeout = <T,>(promise: Promise<T>, ms = 10000): Promise<T> => {
    let timer: any;
    const timeout = new Promise<T>((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Request timed out after ${ms}ms`)), ms);
    });
    return Promise.race([promise, timeout]).finally(() => {
      if (timer) clearTimeout(timer);
    });
  };

  // Fetch digital twin and validation data for a given parcel in parallel
  const loadParcelDetails = useCallback(async (parcel: LandParcel) => {
    // Clear previous parcel details immediately so stale data is never preserved
    setDigitalTwin(null);
    setValidationReport(null);
    setSelectedItem(null);

    try {
      const [twinOutcome, valOutcome] = await Promise.allSettled([
        withTimeout(digitalTwinApi.getDigitalTwin(parcel.id), 10000),
        withTimeout(validationApi.getValidationReport(parcel.id), 10000),
      ]);

      if (twinOutcome.status === 'fulfilled' && twinOutcome.value.success && twinOutcome.value.data) {
        setDigitalTwin(twinOutcome.value.data);
        if (twinOutcome.value.data.units && twinOutcome.value.data.units.length > 0) {
          setSelectedItem({
            type: 'unit',
            data: twinOutcome.value.data.units[0],
          });
        }
      }

      if (valOutcome.status === 'fulfilled' && valOutcome.value.success && valOutcome.value.data) {
        setValidationReport(valOutcome.value.data);
      }
    } catch (err: any) {
      console.warn('Error loading parcel details:', err?.message);
    }
  }, []);

  // System Initialization: Probe health, capabilities, and dynamic parcels in parallel
  const initSystem = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const [healthRes, capsRes, parcelsRes] = await Promise.all([
        healthApi.checkHealth(),
        healthApi.getCapabilities(),
        parcelsApi.listParcels(1, 20),
      ]);

      if (healthRes.success && healthRes.data) {
        setHealth(healthRes.data);
        setIsBackendConnected(true);
      } else {
        setIsBackendConnected(false);
        setHealth(null);
        setCapabilities(null);
        setParcels([]);
        setSelectedParcel(null);
        setDigitalTwin(null);
        setValidationReport(null);
        setSelectedItem(null);
        return;
      }

      if (capsRes.success && capsRes.data) {
        setCapabilities(capsRes.data);
      }

      if (parcelsRes.success && parcelsRes.data) {
        const parcelList = parcelsRes.data.items || [];
        setParcels(parcelList);

        if (parcelList.length > 0) {
          const firstParcel = parcelList[0];
          setSelectedParcel(firstParcel);
          await loadParcelDetails(firstParcel);
        } else {
          setSelectedParcel(null);
          setDigitalTwin(null);
          setValidationReport(null);
          setSelectedItem(null);
        }
      }
    } catch (err: any) {
      console.error('Failed to initialize cadastral data from FastAPI backend:', err);
      setIsBackendConnected(false);
      setHealth(null);
      setCapabilities(null);
      setParcels([]);
      setSelectedParcel(null);
      setDigitalTwin(null);
      setValidationReport(null);
      setSelectedItem(null);
      setErrorMessage(err?.message || 'Unable to connect to FastAPI cadastral service.');
    } finally {
      setIsLoading(false);
    }
  }, [loadParcelDetails]);

  useEffect(() => {
    initSystem();
  }, [initSystem]);

  // Safely fetch completed job artifacts with bounded timeouts and fallbacks
  const fetchCompletionArtifacts = useCallback(
    async (job: ProcessingJob) => {
      try {
        const [resultSettled, parcelsSettled] = await Promise.allSettled([
          withTimeout(jobsApi.getJobResult(job.job_id), 8000),
          withTimeout(parcelsApi.listParcels(1, 20), 8000),
        ]);

        if (resultSettled.status === 'fulfilled' && resultSettled.value.success && resultSettled.value.data) {
          setJobResult(resultSettled.value.data);
        } else if (job.result_reference) {
          // Fallback immediately to inline result_reference so UI never hangs
          setJobResult(job.result_reference as any);
        }

        if (parcelsSettled.status === 'fulfilled' && parcelsSettled.value.success && parcelsSettled.value.data) {
          const items = parcelsSettled.value.data.items || [];
          setParcels(items);
          const targetId =
            job.entity_id ||
            job.result_reference?.parcel_id ||
            (resultSettled.status === 'fulfilled' && resultSettled.value.data?.created_entities?.parcel_id);
          const matching = items.find((p) => p.id === targetId) || items[0];
          if (matching) {
            setSelectedParcel(matching);
            await loadParcelDetails(matching);
          }
        }
      } catch (fetchErr) {
        console.error('Error fetching completed job artifacts:', fetchErr);
        if (job.result_reference) {
          setJobResult(job.result_reference as any);
        }
      }
    },
    [loadParcelDetails]
  );

  // Real-time Job Status Polling (Adaptive with fast initial tick & immediate termination)
  useEffect(() => {
    if (!activeJob) return;

    const jobId = activeJob.job_id;

    if (activeJob.status === 'COMPLETED') {
      if (!jobResult) {
        fetchCompletionArtifacts(activeJob);
      }
      return;
    }

    if (activeJob.status === 'FAILED' || activeJob.status === 'CANCELLED') {
      return;
    }

    let isSubscribed = true;
    let timerId: ReturnType<typeof setTimeout> | null = null;

    const pollJob = async () => {
      if (!isSubscribed) return;

      try {
        const res = await jobsApi.getJobStatus(jobId);
        if (!isSubscribed || !res.success || !res.data) return;

        const updated = res.data;
        setActiveJob(updated);

        if (updated.status === 'COMPLETED') {
          // Terminal COMPLETED state: stop polling loop and fetch artifacts with fallback
          await fetchCompletionArtifacts(updated);
          return;
        } else if (updated.status === 'FAILED') {
          if (isSubscribed) {
            setErrorMessage(updated.error_message || 'Processing job failed during execution.');
          }
          return;
        } else if (updated.status === 'CANCELLED') {
          return;
        }

        // Reschedule next poll while actively processing
        if (isSubscribed) {
          timerId = setTimeout(pollJob, 400);
        }
      } catch (pollErr: any) {
        console.error('Job polling error:', pollErr);
        if (isSubscribed) {
          timerId = setTimeout(pollJob, 800);
        }
      }
    };

    // Fast initial tick: 100ms catches rapid 0.19s backend completion immediately!
    timerId = setTimeout(pollJob, 100);

    return () => {
      isSubscribed = false;
      if (timerId) clearTimeout(timerId);
    };
  }, [activeJob?.job_id, activeJob?.status, jobResult, fetchCompletionArtifacts]);

  // Handle Survey Processing Job Submission
  const handleStartJob = async (request: ParcelProcessJobRequest | CreateSurveyJobRequest) => {
    setIsSubmittingJob(true);
    setErrorMessage(null);
    setJobResult(null);
    try {
      const res = await jobsApi.createJob(request);
      if (res.success && res.data) {
        setActiveJob(res.data);
        setActiveTab('survey');
      }
    } catch (e: any) {
      console.error('Error creating processing job:', e);
      setErrorMessage(e?.message || 'Failed to submit processing job.');
    } finally {
      setIsSubmittingJob(false);
    }
  };

  // Handle Ongoing Job Cancellation
  const handleCancelJob = async () => {
    if (!activeJob) return;
    setIsCancellingJob(true);
    try {
      const res = await jobsApi.cancelJob(activeJob.job_id);
      if (res.success && res.data) {
        setActiveJob(res.data);
      }
    } catch (e: any) {
      console.error('Error cancelling processing job:', e);
      setErrorMessage(e?.message || 'Failed to cancel processing job.');
    } finally {
      setIsCancellingJob(false);
    }
  };

  // Layer toggle handler
  const handleToggleLayer = (layerKey: keyof LayerVisibilityState) => {
    setLayers((prev) => ({
      ...prev,
      [layerKey]: !prev[layerKey],
    }));
  };

  // Load / Reload actual backend demo dataset
  const handleLoadDemo = async () => {
    await initSystem();
    setActiveTab('digital-twin');
  };

  // Select Unit from Property List to view in 3D Twin
  const handleSelectUnitFromList = (unit: VerticalUnit) => {
    setSelectedItem({
      type: 'unit',
      data: unit,
    });
    setActiveTab('digital-twin');
  };

  // Select parcel and immediately clear old state before fetching details
  const handleSelectParcel = async (parcel: LandParcel) => {
    setSelectedParcel(parcel);
    await loadParcelDetails(parcel);
  };

  return (
    <AppShell
      activeTab={activeTab}
      onNavigate={setActiveTab}
      onLoadDemo={handleLoadDemo}
      isBackendConnected={isBackendConnected}
      activeCrs={selectedParcel?.crs || 'EPSG:4326'}
      parcelNumber={selectedParcel?.survey_number || (isLoading ? 'Loading…' : 'None')}
      validationBadge={validationReport ? String(validationReport.total_rules_executed ?? validationReport.evaluated_rules?.length ?? 'OK') : undefined}
      parcels={parcels}
      selectedParcel={selectedParcel}
      onSelectParcel={handleSelectParcel}
    >
      {/* Backend Connection Alert Banner if disconnected */}
      {!isBackendConnected && !isLoading && (
        <div className="mb-6 p-3 rounded-lg bg-[#b84d47]/15 border border-[#b84d47]/30 flex items-center justify-between text-xs text-[#c45852]">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>FastAPI backend is unreachable at <code>http://localhost:8000/api/v1</code>. Ensure the service is running.</span>
          </div>
          <button
            onClick={initSystem}
            className="flex items-center gap-1 px-2.5 py-1 rounded bg-[#222428] hover:bg-[#2b2d32] border border-[#3e4249] text-[#f4f3ef] transition-colors"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Retry Connection</span>
          </button>
        </div>
      )}

      {/* 1. OVERVIEW VIEW */}
      {activeTab === 'overview' && (
        <div className="space-y-8 sm:space-y-10 animate-fadeIn pb-6">
          <OverviewHero
            onStartSurvey={() => setActiveTab('survey')}
            onViewDemoDigitalTwin={handleLoadDemo}
          />

          <SystemStatus
            health={health}
            capabilities={capabilities}
            parcels={parcels}
            activeJob={activeJob}
            totalUnitsCount={digitalTwin?.units?.length || 0}
            isBackendConnected={isBackendConnected}
            qualityScore={validationReport?.quality_score?.total_score}
            qualityGrade={validationReport?.quality_score?.grade}
            rulesCount={validationReport?.total_rules_executed}
          />
        </div>
      )}

      {/* 2. SURVEY / PROCESSING WORKFLOW VIEW */}
      {activeTab === 'survey' && (
        <div className="space-y-6 animate-fadeIn">
          <div>
            <h1 className="text-xl font-semibold text-[#f4f3ef]">
              Survey Ingestion & Cadastral Processing
            </h1>
            <p className="text-xs text-[#a09f99] mt-0.5">
              Transform spatial observation telemetry into stratified 3D vertical units and prototype ULPINs.
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-6">
              <ProcessingForm
                onSubmit={handleStartJob}
                isLoading={isSubmittingJob}
                activeParcel={selectedParcel}
                availableParcels={parcels}
                onSelectParcel={handleSelectParcel}
              />
            </div>

            <div className="lg:col-span-6">
              {activeJob ? (
                <JobTimeline
                  job={activeJob}
                  jobResult={jobResult}
                  onViewDigitalTwin={() => setActiveTab('digital-twin')}
                  onViewValidation={() => setActiveTab('validation')}
                  onCancelJob={handleCancelJob}
                  isCancelling={isCancellingJob}
                />
              ) : (
                <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-8 text-center space-y-3">
                  <div className="w-10 h-10 rounded-full bg-[#222428] border border-[#34373d] flex items-center justify-center mx-auto text-[#a09f99]">
                    1
                  </div>
                  <h3 className="text-sm font-semibold text-[#f4f3ef]">No Job Currently Executing</h3>
                  <p className="text-xs text-[#a09f99] max-w-sm mx-auto leading-relaxed">
                    Submit the survey form to begin async ingestion. The deterministic cadastral engine will construct the 3D topology and evaluate all cadastral validation rules.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 3. DIGITAL TWIN VIEW */}
      {activeTab === 'digital-twin' && (
        <div className="space-y-4 animate-fadeIn">
          {selectedParcel ? (
            <>
              {/* Top Context Bar: Parcel Identity + 3D ULPIN Context */}
              <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase font-mono tracking-wider text-[#a09f99]">
                    Cadastral Survey Parcel
                  </div>
                  <div className="text-sm font-semibold text-[#f4f3ef]">
                    Survey No. {selectedParcel.survey_number} — {selectedParcel.village || selectedParcel.village_code || 'Village'}, {selectedParcel.district || selectedParcel.district_code} ({selectedParcel.state || selectedParcel.state_code})
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <div className="bg-[#222428] px-2.5 py-1 rounded border border-[#34373d] text-xs">
                    <span className="text-[10px] uppercase text-[#a09f99] block font-medium">Base ULPIN</span>
                    <span className="font-mono font-semibold text-[#f4f3ef]">{selectedParcel.ulpin}</span>
                  </div>
                  <div className="bg-[#222428] px-2.5 py-1 rounded border border-[#34373d] text-xs">
                    <span className="text-[10px] uppercase text-[#a09f99] block font-medium">Height Datum</span>
                    <span className="font-mono font-semibold text-[#6b8e72]">{selectedParcel.ground_elevation_amsl ?? selectedParcel.base_elevation_m ?? 0}m AMSL</span>
                  </div>
                </div>
              </div>

              {/* Main 3D Viewport + Right Inspector Layout */}
              {digitalTwin ? (
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 min-h-[580px]">
                  {/* Left 8 Cols: Large Interactive 3D Viewer with Overlay Layer Controls */}
                  <div className="lg:col-span-8 relative flex flex-col">
                    <DigitalTwinViewer
                      digitalTwin={digitalTwin}
                      layers={layers}
                      wireframe={wireframe}
                      selectedItem={selectedItem}
                      onSelectItem={setSelectedItem}
                      resetViewTrigger={resetViewTrigger}
                    />

                    {/* Overlay Layer Control on Top-Right of Viewport */}
                    <div className="absolute top-3 right-3 z-10 w-48 max-w-[calc(100%-24px)]">
                      <LayerControl
                        layers={layers}
                        onToggleLayer={handleToggleLayer}
                        onResetView={() => setResetViewTrigger((n) => n + 1)}
                        wireframe={wireframe}
                        onToggleWireframe={() => setWireframe((v) => !v)}
                      />
                    </div>
                  </div>

                  {/* Right 4 Cols: Property / Volume Inspector Panel */}
                  <div className="lg:col-span-4">
                    <PropertyInspector
                      selectedItem={selectedItem}
                      digitalTwin={digitalTwin}
                      anomalies={digitalTwin?.anomalies}
                      onClose={() => setSelectedItem(null)}
                    />
                  </div>
                </div>
              ) : (
                <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-12 text-center text-[#a09f99] space-y-3">
                  <Box className="w-10 h-10 text-[#5c7080] mx-auto animate-pulse" />
                  <div className="font-medium text-[#f4f3ef] text-sm">Loading 3D Digital Twin…</div>
                  <p className="text-xs max-w-sm mx-auto leading-relaxed">
                    Retrieving building envelope, vertical strata, and 3D units from FastAPI cadastre service.
                  </p>
                </div>
              )}
            </>
          ) : (
            <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-12 text-center text-[#a09f99] space-y-4">
              <Box className="w-10 h-10 text-[#5c7080] mx-auto" />
              <div className="font-medium text-[#f4f3ef] text-base">No Parcel Loaded</div>
              <p className="text-xs max-w-sm mx-auto leading-relaxed">
                Connect to the FastAPI backend to load cadastral parcels, or submit a survey ingestion job.
              </p>
              <button
                onClick={initSystem}
                className="px-4 py-2 rounded bg-[#c86446] hover:bg-[#d97757] text-[#f4f3ef] text-xs font-medium transition-colors"
              >
                Fetch Parcels from Backend
              </button>
            </div>
          )}
        </div>
      )}

      {/* 4. VALIDATION VIEW */}
      {activeTab === 'validation' && (
        <div className="space-y-6 animate-fadeIn">
          {validationReport ? (
            <>
              <ValidationSummary
                report={validationReport}
                onRerunValidation={async () => {
                  if (selectedParcel) {
                    try {
                      const res = await validationApi.validateParcel(selectedParcel.id);
                      if (res.data) setValidationReport(res.data);
                    } catch (e: any) {
                      console.error('Error re-running validation:', e);
                    }
                  }
                }}
              />

              <ValidationIssues
                clashFindings={validationReport.clash_findings || []}
                rules={validationReport.evaluated_rules || []}
                issues={validationReport.issues || []}
                deductions={validationReport.quality_score?.deductions || []}
              />
            </>
          ) : (
            <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-12 text-center text-[#a09f99] space-y-4">
              <ShieldCheck className="w-10 h-10 text-[#5c7080] mx-auto" />
              <div className="font-medium text-[#f4f3ef] text-base">No Validation Report Loaded</div>
              <p className="text-xs max-w-sm mx-auto leading-relaxed">
                Select a cadastral parcel and execute deterministic rule validation.
              </p>
              {selectedParcel && (
                <button
                  onClick={async () => {
                    try {
                      const res = await validationApi.validateParcel(selectedParcel.id);
                      if (res.data) setValidationReport(res.data);
                    } catch (e) {
                      console.error(e);
                    }
                  }}
                  className="px-4 py-2 rounded bg-[#c86446] hover:bg-[#d97757] text-[#f4f3ef] text-xs font-medium transition-colors"
                >
                  Run Validation for Survey #{selectedParcel.survey_number}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* 5. 3D ULPIN / PROPERTY DETAILS VIEW */}
      {activeTab === 'properties' && (
        <div className="space-y-6 animate-fadeIn">
          <div>
            <h1 className="text-xl font-semibold text-[#f4f3ef]">
              Vertical Properties & 3D ULPIN Registry
            </h1>
            <p className="text-xs text-[#a09f99] mt-0.5">
              Stratified vertical units registered under Survey #{selectedParcel?.survey_number || 'N/A'} with prototype 3D ULPIN identifiers.
            </p>
          </div>

          {selectedParcel && digitalTwin ? (
            <PropertyList
              units={digitalTwin.units || []}
              parcel={selectedParcel}
              onSelectUnit={handleSelectUnitFromList}
            />
          ) : (
            <div className="bg-[#1c1d20] border border-[#2d3034] rounded-lg p-12 text-center text-[#a09f99] space-y-3">
              <Layers className="w-10 h-10 text-[#5c7080] mx-auto" />
              <div className="font-medium text-[#f4f3ef] text-sm">No Property Units Available</div>
              <p className="text-xs max-w-sm mx-auto leading-relaxed">
                Select a valid cadastral parcel to inspect its registered 3D vertical units.
              </p>
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
