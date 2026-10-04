import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getDatasetStatus } from '../api/client';

const DatasetContext = createContext(null);

export const DatasetProvider = ({ children }) => {
  const [hasDataset, setHasDataset] = useState(false);
  const [datasetMeta, setDatasetMeta] = useState(null);
  const [isCheckingStatus, setIsCheckingStatus] = useState(true);

  const checkStatus = useCallback(async () => {
    try {
      const status = await getDatasetStatus();
      if (status?.outputs_ready) {
        setHasDataset(true);
        setDatasetMeta({
          assetCount: status.asset_count,
          lastUpdated: status.last_updated,
        });
      }
    } catch {
      // Backend might be offline or outputs not ready
    } finally {
      setIsCheckingStatus(false);
    }
  }, []);

  useEffect(() => {
    checkStatus();
  }, [checkStatus]);

  const setDatasetLoaded = (meta) => {
    setHasDataset(true);
    setDatasetMeta(meta || {});
  };

  const resetDataset = () => {
    setHasDataset(false);
    setDatasetMeta(null);
  };

  return (
    <DatasetContext.Provider
      value={{
        hasDataset,
        datasetMeta,
        isCheckingStatus,
        setDatasetLoaded,
        resetDataset,
        checkStatus,
      }}
    >
      {children}
    </DatasetContext.Provider>
  );
};

export const useDataset = () => {
  const context = useContext(DatasetContext);
  if (!context) {
    throw new Error('useDataset must be used within a DatasetProvider');
  }
  return context;
};
