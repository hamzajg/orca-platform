import React, { useState } from 'react';
import { Plus } from 'lucide-react';
import { useFineTuneJobs } from '../hooks/useFineTuneJobs';
import { FineTuneTable } from '../components/fine-tune/FineTuneTable';
import { NewJobForm } from '../components/fine-tune/NewJobForm';
import { JobHistoryDrawer } from '../components/fine-tune/JobHistoryDrawer';

export default function FineTune({ toast }) {
  const { jobs, refetch } = useFineTuneJobs();
  const [drawer, setDrawer] = useState({ open: false, component: null });

  const openNewJobDrawer = () => {
    setDrawer({
      open: true,
      component: <NewJobForm onClose={() => setDrawer({ open: false, component: null })} onCreated={refetch} toast={toast} />
    });
  };

  const runJob = async (id) => {
    try {
      const resp = await fetch(`/api/fine-tune/jobs/${id}/run`, {
        method: 'POST',
        headers: { 'X-API-Key': sessionStorage.getItem('ollama_api_key') }
      });
      if (resp.ok) {
        toast('Job triggered');
        refetch();
      } else { toast('Failed to trigger job', 'err'); }
    } catch (e) { toast('Error triggering job', 'err'); }
  };

  const deleteJob = async (id) => {
    try {
      const resp = await fetch(`/api/fine-tune/jobs/${id}`, {
        method: 'DELETE',
        headers: { 'X-API-Key': sessionStorage.getItem('ollama_api_key') }
      });
      if (resp.ok) {
        toast('Job deleted');
        refetch();
      } else { toast('Failed to delete job', 'err'); }
    } catch (e) { toast('Error deleting job', 'err'); }
  };

  const openDrawerForEdit = (job) => {
    setDrawer({
      open: true,
      component: <NewJobForm initialData={job} onClose={() => setDrawer({ open: false, component: null })} onCreated={refetch} toast={toast} />
    });
  };

  const showHistory = (job) => {
    setDrawer({
      open: true,
      component: <JobHistoryDrawer job={job} onClose={() => setDrawer({ open: false, component: null })} />
    });
  };

  const viewLog = (run) => {
    setDrawer({
      open: true,
      component: <JobHistoryDrawer job={{ name: run.id }} onClose={() => setDrawer({ open: false, component: null })} log={run.log} />
    });
  };

  return (
    <div className="flex flex-col gap-6 relative h-full">
      {drawer.open && (
        <div className="fixed inset-0 z-[100] flex">
          <div className="absolute inset-0 bg-[#0c1220]/60" onClick={() => setDrawer({ open: false, component: null })} />
          <div className="fixed right-0 top-0 bottom-0 h-screen w-full max-w-md nav-glass border-l border-[rgba(100,180,255,0.12)] p-6 shadow-2xl overflow-y-auto">
             {drawer.component}
          </div>
        </div>
      )}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-[#f0f4f8]">Fine-Tuning Jobs</h2>
        <button onClick={openNewJobDrawer} className="btn-primary flex items-center gap-2">
          <Plus size={16} /> New Job
        </button>
      </div>
      <FineTuneTable jobs={jobs} onDelete={deleteJob} onEdit={openDrawerForEdit} onRun={runJob} onViewLog={viewLog} />
    </div>
  );
  }

