import React from 'react';
import { ArrowRight, Box } from 'lucide-react';
import { AerialVideoBackground } from './AerialVideoBackground.tsx';

interface OverviewHeroProps {
  onStartSurvey?: () => void;
  onViewDemoDigitalTwin?: () => void;
}

export const OverviewHero: React.FC<OverviewHeroProps> = ({
  onStartSurvey,
  onViewDemoDigitalTwin,
}) => {
  return (
    <div className="space-y-6">
      {/* 1. 3-IMAGE SLIDESHOW ONLY */}
      <div className="relative rounded-xl overflow-hidden border border-[#2d3034] bg-[#18191b] shadow-xl w-full h-64 sm:h-72 md:h-80 lg:h-96">
        <AerialVideoBackground />
      </div>

      {/* 2. COMPACT HERO CONTENT (HEADING + DESCRIPTION + TWO BUTTONS) */}
      <div className="space-y-3 max-w-3xl">
        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-[#f4f3ef]">
          3D ULPIN & Vertical Property Mapping
        </h1>
        <p className="text-sm sm:text-base text-[#a09f99] leading-relaxed max-w-2xl font-normal">
          Transforming parcel, building and vertical property data into a validated 3D cadastral digital twin.
        </p>

        {/* Buttons on one row */}
        <div className="flex flex-wrap items-center gap-3 pt-2">
          {onStartSurvey && (
            <button
              onClick={onStartSurvey}
              className="flex items-center gap-2 px-5 py-2.5 rounded bg-[#c86446] hover:bg-[#d97757] text-[#f4f3ef] text-sm font-medium shadow-md transition-all duration-200"
            >
              <span>Start Survey Processing</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          )}

          {onViewDemoDigitalTwin && (
            <button
              onClick={onViewDemoDigitalTwin}
              className="flex items-center gap-2 px-5 py-2.5 rounded bg-[#222428] hover:bg-[#2b2d32] border border-[#3e4249] text-[#f4f3ef] text-sm font-medium transition-all duration-200"
            >
              <Box className="w-4 h-4 text-[#6b8e72]" />
              <span>View Demo Digital Twin</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};



