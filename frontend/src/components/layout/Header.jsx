import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Shield, RefreshCw, Upload, BarChart3, LogOut } from 'lucide-react';
import { getHealth } from '../../api/client';
import { ThemeToggle } from '../ui/ThemeToggle';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { useDataset } from '../../context/DatasetContext';
import { useAuth } from '../../context/AuthContext';

export const Header = ({ onRefreshAll, isRefreshing, activeTab, setActiveTab }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { hasDataset } = useDataset();
  const { user, logout } = useAuth();
  const isInsightsPage = location.pathname === '/insights';

  const [backendOnline, setBackendOnline] = useState(null);

  const checkHealth = async () => {
    try {
      const res = await getHealth();
      setBackendOnline(res?.status === 'ok');
    } catch {
      setBackendOnline(false);
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="sticky top-0 z-40 w-full border-b border-th-border bg-th-surface/95 backdrop-blur-md">
      <div className="px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">

          {/* Logo */}
          <button
            type="button"
            onClick={() => navigate('/')}
            className="flex items-center space-x-3 cursor-pointer group"
          >
            <div className="w-8 h-8 rounded-lg bg-th-brand flex items-center justify-center text-white shadow-soft group-hover:bg-th-brand-hover transition-colors">
              <Shield className="w-4 h-4" />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-semibold text-th-text-primary font-serif tracking-tight">
                CyberRisk
              </span>
              {hasDataset && isInsightsPage && (
                <Badge variant="brand" className="hidden sm:inline-flex text-[10px] py-0 px-1.5 font-normal">
                  Active Run
                </Badge>
              )}
            </div>
          </button>

          {/* Right actions: Theme toggle + Upload New + Refresh Report */}
          <div className="flex items-center space-x-2.5">
            <ThemeToggle />

            {user && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => { logout(); navigate('/login', { replace: true }); }}
                title={`Signed in as ${user.username} — sign out`}
                className="text-xs font-medium gap-1.5"
              >
                <span className="hidden sm:inline max-w-[8rem] truncate">{user.username}</span>
                <LogOut className="w-3.5 h-3.5" />
              </Button>
            )}

            {isInsightsPage ? (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate('/')}
                  title="Upload another dataset"
                  className="hidden sm:inline-flex text-xs font-medium gap-1.5"
                >
                  <Upload className="w-3.5 h-3.5" />
                  <span>Upload New</span>
                </Button>

                {onRefreshAll && (
                  <Button
                    onClick={onRefreshAll}
                    isLoading={isRefreshing}
                    size="sm"
                    title="Refresh Portfolio Risk Data"
                  >
                    {!isRefreshing && <RefreshCw className="w-3.5 h-3.5 mr-1.5" />}
                    Refresh Report
                  </Button>
                )}
              </>
            ) : (
              hasDataset && (
                <Button
                  size="sm"
                  onClick={() => navigate('/insights')}
                  className="font-medium gap-1.5"
                >
                  <BarChart3 className="w-3.5 h-3.5" />
                  <span>View Insights</span>
                </Button>
              )
            )}
          </div>

        </div>
      </div>
    </header>
  );
};
