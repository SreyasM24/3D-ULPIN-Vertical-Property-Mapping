import React from 'react';
import { Layers } from 'lucide-react';

export interface LayerVisibilityState {
  parcel: boolean;
  building: boolean;
  floors: boolean;
  units: boolean;
  underground: boolean;
  sharedCommon: boolean;
}

interface LayerControlProps {
  layers: LayerVisibilityState;
  onToggleLayer: (layerKey: keyof LayerVisibilityState) => void;
  onResetView?: () => void;
  wireframe?: boolean;
  onToggleWireframe?: () => void;
}

export const LayerControl: React.FC<LayerControlProps> = ({
  layers,
  onToggleLayer,
  onResetView,
  wireframe,
  onToggleWireframe,
}) => {
  const layerItems: { key: keyof LayerVisibilityState; label: string; colorDot: string }[] = [
    { key: 'parcel', label: 'Parcel Boundary', colorDot: 'bg-[#6b8e72]' },
    { key: 'building', label: 'Building Mass', colorDot: 'bg-[#5c7080]' },
    { key: 'floors', label: 'Floor Slabs', colorDot: 'bg-[#a09f99]' },
    { key: 'units', label: 'Vertical Units', colorDot: 'bg-[#c86446]' },
    { key: 'underground', label: 'Underground', colorDot: 'bg-[#3e4249]' },
    { key: 'sharedCommon', label: 'Shared / Common', colorDot: 'bg-[#7c9d83]' },
  ];

  return (
    <div className="bg-[#1c1d20]/95 backdrop-blur-sm border border-[#2d3034] rounded-lg p-3 text-xs shadow-xl space-y-2.5">
      <div className="flex items-center justify-between pb-1.5 border-b border-[#2d3034]">
        <div className="flex items-center gap-1.5 font-semibold text-[#f4f3ef]">
          <Layers className="w-3.5 h-3.5 text-[#d97757]" />
          <span>Cadastral Layers</span>
        </div>
        {onResetView && (
          <button
            onClick={onResetView}
            className="text-[11px] text-[#a09f99] hover:text-[#f4f3ef] hover:underline transition-colors"
          >
            Reset View
          </button>
        )}
      </div>

      <div className="space-y-1.5">
        {layerItems.map(item => (
          <label
            key={item.key}
            className="flex items-center justify-between gap-2.5 px-2 py-1 rounded hover:bg-[#25282c] cursor-pointer transition-colors"
          >
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={layers[item.key]}
                onChange={() => onToggleLayer(item.key)}
                className="w-3.5 h-3.5 rounded border-[#3e4249] bg-[#18191b] text-[#c86446] focus:ring-0 focus:ring-offset-0 cursor-pointer accent-[#c86446]"
              />
              <span className={`w-2 h-2 rounded-full ${item.colorDot}`} />
              <span className={`font-medium ${layers[item.key] ? 'text-[#f4f3ef]' : 'text-[#a09f99]'}`}>
                {item.label}
              </span>
            </div>
          </label>
        ))}
      </div>

      {onToggleWireframe && (
        <div className="pt-2 border-t border-[#2d3034]">
          <button
            onClick={onToggleWireframe}
            className={`w-full text-center py-1 rounded text-[11px] font-medium border transition-colors ${
              wireframe
                ? 'bg-[#c86446]/20 border-[#c86446] text-[#d97757]'
                : 'bg-[#222428] border-[#34373d] text-[#a09f99] hover:text-[#f4f3ef]'
            }`}
          >
            {wireframe ? 'Wireframe Enabled' : 'Toggle Wireframe'}
          </button>
        </div>
      )}
    </div>
  );
};
