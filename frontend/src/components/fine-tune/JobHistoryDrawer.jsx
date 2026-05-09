import React, { useState } from 'react';
import { X } from 'lucide-react';

export const JobHistoryDrawer = ({ job, onClose, log = null }) => {
  const [selectedRun, setSelectedRun] = useState(log ? { log } : null);

  // Mock history list (would typically come from a /api/fine-tune/jobs/{id}/history endpoint)
  const history = [
    { id: `${job.id}-run-1`, started_at: '2026-05-09 10:00', status: 'completed', log: 'Training completed successfully...' },
    { id: `${job.id}-run-2`, started_at: '2026-05-08 10:00', status: 'failed', log: 'Error: Out of memory...' }
  ];

  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-center mb-6">
        <h3 className="font-semibold text-lg">{selectedRun ? 'Run Log' : `History: ${job.name}`}</h3>
        <button type="button" onClick={selectedRun && !log ? () => setSelectedRun(null) : onClose} className="text-[#a8b8c8] hover:text-[#f0f4f8]">
          <X size={20}/>
        </button>
      </div>

      {selectedRun ? (
        <pre className="bg-[#050810] p-4 rounded text-xs text-[#00d4ff] overflow-auto h-full font-mono">
          {selectedRun.log}
        </pre>
      ) : (
        <div className="space-y-2">
          {history.map(run => (
            <button key={run.id} onClick={() => setSelectedRun(run)} className="w-full text-left nav-glass p-3 rounded border border-[rgba(100,180,255,0.08)] hover:border-[#00d4ff]">
              <div className="text-sm font-medium">{run.started_at}</div>
              <div className={`text-xs ${run.status === 'completed' ? 'text-[#10b981]' : 'text-[#f04d4d]'}`}>{run.status}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
