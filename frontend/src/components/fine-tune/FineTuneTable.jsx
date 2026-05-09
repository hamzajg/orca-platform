import React, { useState } from 'react';
import { Loader2, CheckCircle2, AlertCircle, Clock, Trash2, Edit2, Play, ChevronDown, ChevronUp } from 'lucide-react';

export const FineTuneTable = ({ jobs, onDelete, onEdit, onRun, onViewLog }) => {
  const [deleteId, setDeleteId] = useState(null);
  const [expandedId, setExpandedId] = useState(null);

  const getStatusIcon = (status) => {
    if (status === 'running') return <Loader2 className="animate-spin text-[#00d4ff]" size={16} />;
    if (status === 'completed') return <CheckCircle2 className="text-[#10b981]" size={16} />;
    if (status === 'failed') return <AlertCircle className="text-[#f04d4d]" size={16} />;
    return <Clock className="text-[#a8b8c8]" size={16} />;
  };

  const getJobHistory = (jobId) => [
    { id: `${jobId}-run-1`, started_at: '2026-05-09 10:00', status: 'completed', log: 'Training completed successfully...' },
    { id: `${jobId}-run-2`, started_at: '2026-05-08 10:00', status: 'failed', log: 'Error: Out of memory...' }
  ];

  return (
    <>
      <div className="overflow-x-auto nav-glass rounded-lg border border-[rgba(100,180,255,0.08)]">
        <table className="w-full text-sm text-left">
          <thead className="text-[#7a8a9a] uppercase border-b border-[rgba(100,180,255,0.08)]">
            <tr>
              <th className="px-4 py-3">Job Name</th>
              <th className="px-4 py-3">Schedule</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map(job => (
              <React.Fragment key={job.id}>
                <tr className="border-b border-[rgba(100,180,255,0.04)] hover:bg-[rgba(100,180,255,0.02)]">
                  <td className="px-4 py-3">
                    <div className="font-medium text-[#f0f4f8]">{job.name}</div>
                    <div className="text-xs text-[#5a6a7a]">{job.base_model} ({job.method})</div>
                  </td>
                  <td className="px-4 py-3 text-xs text-[#a8b8c8]">
                    {job.schedule_type === 'once' 
                      ? job.schedule_at ? new Date(job.schedule_at).toLocaleString() : 'Immediate'
                      : `${job.recurring_days?.join(', ') || 'None'} at ${job.schedule_time || '00:00'}`
                    }
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {getStatusIcon(job.status)}
                      <span className="capitalize text-sm">{job.status}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 flex gap-2">
                    <button onClick={() => onEdit(job)} className="btn-ghost text-[#a8b8c8]"><Edit2 size={16} /></button>
                    <button onClick={() => setDeleteId(job.id)} className="btn-ghost text-[#f04d4d]"><Trash2 size={16} /></button>
                    <div className="flex items-center bg-[rgba(100,180,255,0.05)] border border-[rgba(100,180,255,0.12)] rounded-lg overflow-hidden">
                      <button onClick={() => onRun(job.id)} className="px-3 py-1 text-xs text-[#10b981] border-r border-[rgba(100,180,255,0.12)] hover:bg-[rgba(16,185,129,0.1)]">
                        <Play size={14} />
                      </button>
                      <button 
                        onClick={() => setExpandedId(expandedId === job.id ? null : job.id)} 
                        className={`px-3 py-1 text-xs font-bold ${expandedId === job.id ? 'text-[#00d4ff]' : 'text-[#7a8a9a]'}`}
                      >
                        {expandedId === job.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                    </div>
                  </td>
                </tr>
                {expandedId === job.id && (
                  <tr className="bg-[rgba(0,212,255,0.03)]">
                    <td colSpan="4" className="px-6 py-4">
                      <div className="text-xs font-medium text-[#7a8a9a] mb-2 uppercase">Execution History</div>
                      <div className="space-y-1">
                        {getJobHistory(job.id).map(run => (
                          <div key={run.id} className="flex justify-between items-center p-2 rounded bg-[rgba(100,180,255,0.05)] border border-[rgba(100,180,255,0.05)]">
                            <span className="font-mono text-[#a8b8c8]">{run.started_at} - {run.status}</span>
                            <button onClick={() => onViewLog(run)} className="text-[#00d4ff] hover:underline">View Log</button>
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {deleteId && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-[#0c1220]/80">
          <div className="nav-glass p-6 rounded-lg border border-[rgba(100,180,255,0.12)] max-w-sm w-full">
            <h3 className="font-semibold mb-4">Confirm Deletion</h3>
            <p className="text-sm text-[#a8b8c8] mb-6">Are you sure you want to delete this job? This action cannot be undone.</p>
            <div className="flex gap-3">
              <button onClick={() => setDeleteId(null)} className="btn-ghost flex-1">Cancel</button>
              <button onClick={() => { onDelete(deleteId); setDeleteId(null); }} className="btn-primary bg-[#f04d4d] border-[#f04d4d] flex-1">Delete</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
