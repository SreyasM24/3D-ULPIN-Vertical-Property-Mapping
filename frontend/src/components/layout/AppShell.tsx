import React, { useState } from 'react';
import { NavigationTab } from '../../types/api.ts';
import { TopBar } from './TopBar.tsx';
import {
  LayoutDashboard,
  Cpu,
  Box,
  ShieldCheck,
  Building2,
  Menu,
  X,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

interface AppShellProps {
  children: React.ReactNode;
  activeTab: NavigationTab;
  onNavigate: (tab: NavigationTab) => void;
  onLoadDemo: () => void;
  isBackendConnected: boolean;
  activeCrs?: string;
  parcelNumber?: string;
  validationBadge?: string;
}

export const AppShell: React.FC<AppShellProps> = ({
  children,
  activeTab,
  onNavigate,
  onLoadDemo,
  isBackendConnected,
  activeCrs,
  parcelNumber,
  validationBadge,
}) => {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const navItems: { tab: NavigationTab; label: string; icon: React.ReactNode; badge?: string }[] = [
    {
      tab: 'overview',
      label: 'Overview',
      icon: <LayoutDashboard className="w-4 h-4" />,
    },
    {
      tab: 'survey',
      label: 'Survey / Ingestion',
      icon: <Cpu className="w-4 h-4" />,
    },
    {
      tab: 'digital-twin',
      label: '3D Digital Twin',
      icon: <Box className="w-4 h-4" />,
      badge: '3D',
    },
    {
      tab: 'validation',
      label: 'Cadastral Validation',
      icon: <ShieldCheck className="w-4 h-4" />,
      badge: validationBadge || 'Audit',
    },
    {
      tab: 'properties',
      label: '3D ULPIN Registry',
      icon: <Building2 className="w-4 h-4" />,
    },
  ];

  return (
    <div className="min-h-screen bg-[#141517] text-[#f4f3ef] flex flex-col font-sans selection:bg-[#c86446]/30 selection:text-[#f4f3ef]">
      {/* Top Bar */}
      <TopBar
        onLoadDemo={onLoadDemo}
        isBackendConnected={isBackendConnected}
        activeCrs={activeCrs}
        parcelNumber={parcelNumber}
      />

      {/* Main Workspace Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Desktop Sidebar Navigation */}
        <aside
          className={`hidden md:flex flex-col bg-[#18191b] border-r border-[#2d3034] transition-all duration-200 z-10 ${
            isSidebarCollapsed ? 'w-16' : 'w-60'
          }`}
        >
          {/* Nav Items */}
          <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
            {navItems.map((item) => {
              const isActive = activeTab === item.tab;
              return (
                <button
                  key={item.tab}
                  onClick={() => onNavigate(item.tab)}
                  title={isSidebarCollapsed ? item.label : undefined}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-[#282a2e] text-[#f4f3ef] border border-[#3e4249]'
                      : 'text-[#a09f99] hover:text-[#f4f3ef] hover:bg-[#202226]'
                  }`}
                >
                  <span className={`${isActive ? 'text-[#d97757]' : 'text-[#a09f99]'}`}>
                    {item.icon}
                  </span>
                  {!isSidebarCollapsed && (
                    <span className="truncate flex-1 text-left">{item.label}</span>
                  )}
                  {!isSidebarCollapsed && item.badge && (
                    <span
                      className={`text-[10px] font-mono px-1.5 py-0.2 rounded ${
                        isActive
                          ? 'bg-[#c86446]/20 text-[#d97757]'
                          : 'bg-[#222428] text-[#a09f99]'
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          {/* Collapse Toggle Footer */}
          <div className="p-3 border-t border-[#2d3034]">
            <button
              onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
              className="w-full flex items-center justify-center p-2 rounded hover:bg-[#202226] text-[#a09f99] hover:text-[#f4f3ef] transition-colors text-xs"
              title={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {isSidebarCollapsed ? (
                <ChevronRight className="w-4 h-4" />
              ) : (
                <div className="flex items-center gap-2">
                  <ChevronLeft className="w-4 h-4" />
                  <span className="text-[11px]">Collapse View</span>
                </div>
              )}
            </button>
          </div>
        </aside>

        {/* Mobile Navigation Header Bar */}
        <div className="md:hidden fixed bottom-0 left-0 right-0 bg-[#18191b] border-t border-[#2d3034] z-30 flex items-center justify-around p-2">
          {navItems.map((item) => {
            const isActive = activeTab === item.tab;
            return (
              <button
                key={item.tab}
                onClick={() => onNavigate(item.tab)}
                className={`flex flex-col items-center gap-1 p-2 rounded text-[10px] font-medium ${
                  isActive ? 'text-[#d97757]' : 'text-[#a09f99]'
                }`}
              >
                {item.icon}
                <span className="truncate max-w-[60px]">{item.label.split(' ')[0]}</span>
              </button>
            );
          })}
        </div>

        {/* Primary Viewport Area */}
        <main className="flex-1 overflow-y-auto p-4 md:p-6 pb-20 md:pb-6 bg-[#141517]">
          <div className="max-w-7xl mx-auto">{children}</div>
        </main>
      </div>
    </div>
  );
};
