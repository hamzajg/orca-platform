import React, { useState, useEffect } from 'react';
import { X, ChevronRight, ChevronLeft } from 'lucide-react';
import { api, getNodes, getModelList } from '../../lib/api';

export const NewJobForm = ({ onClose, onCreated, toast, initialData = null }) => {
  const [nodes, setNodes] = useState([]);
  const [models, setModels] = useState([]);
  const [step, setStep] = useState(1);
  const [preview, setPreview] = useState(false);
  const [formData, setFormData] = useState(() => {
    if (initialData) return initialData;
    const now = new Date();
    const offset = now.getTimezoneOffset() * 60000;
    const local = new Date(now - offset).toISOString().slice(0, 16);
    return {
      name: '', description: '', base_model: '', method: 'lora', dataset_source: '', 
      dataset_format: 'alpaca', output_model_name: '', hyperparameters: '{"epochs": 3}', 
      schedule_at: local, schedule_time: '00:00', target_node_id: '', schedule_type: 'once', recurring_days: []
    };
  });

  useEffect(() => { 
    getNodes().then(d => setNodes(d.nodes || [])).catch(() => toast('Failed to load nodes', 'err'));
    getModelList().then(d => setModels(d.models || [])).catch(() => toast('Failed to load models', 'err'));
  }, []);

  useEffect(() => {
    if (initialData) {
      setFormData(initialData);
    }
  }, [initialData]);

  const toggleDay = (day) => {
    setFormData(prev => ({
      ...prev,
      recurring_days: prev.recurring_days.includes(day)
        ? prev.recurring_days.filter(d => d !== day)
        : [...prev.recurring_days, day]
    }));
  };

  const uploadHyperparameters = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const text = await file.text();
    setFormData({...formData, hyperparameters: text});
    toast('Hyperparameters loaded');
  };

  const createJob = async () => {
    try {
      const resp = await fetch('/api/fine-tune/jobs', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'X-API-Key': sessionStorage.getItem('ollama_api_key') 
        },
        body: JSON.stringify({ 
          ...formData, 
          hyperparameters: JSON.parse(formData.hyperparameters),
          schedule_at: formData.schedule_type === 'once' ? formData.schedule_at : null
        })
      });
      if (resp.ok) {
        toast('Job scheduled');
        onCreated();
        onClose();
      } else { toast('Failed to create job', 'err'); }
    } catch (e) { toast('Error creating job', 'err'); }
  };

  const getAvailableModels = () => {
    if (!formData.target_node_id) return [];
    return models.filter(m => m.available_on.includes(formData.target_node_id));
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-center mb-6">
        <h3 className="font-semibold text-lg">New Training Job - Step {step} of 2</h3>
        <button type="button" onClick={onClose} className="text-[#a8b8c8] hover:text-[#f0f4f8]"><X size={20}/></button>
      </div>
      
      {step === 1 ? (
        <div className="flex flex-col gap-4">
          <input type="text" placeholder="Job Name" className="inp-base w-full" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} required/>
          <textarea placeholder="Description" className="inp-base w-full h-20" value={formData.description} onChange={e => setFormData({...formData, description: e.target.value})} />
          <select className="inp-base w-full" value={formData.target_node_id} onChange={e => setFormData({...formData, target_node_id: e.target.value})} required>
            <option value="">Select Target Node</option>
            {Array.isArray(nodes) && nodes.map(n => <option key={n.id} value={n.id}>{n.label}</option>)}
          </select>
          <select className="inp-base w-full" value={formData.base_model} onChange={e => setFormData({...formData, base_model: e.target.value})} required>
            <option value="">Select Base Model</option>
            {getAvailableModels().map(m => <option key={m.name} value={m.name}>{m.name}</option>)}
          </select>
          <div className="flex flex-col gap-2">
            <label className="text-xs text-[#7a8a9a]">Schedule Type</label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-sm"><input type="radio" name="stype" checked={formData.schedule_type === 'once'} onChange={() => setFormData({...formData, schedule_type: 'once'})}/> Once</label>
              <label className="flex items-center gap-2 text-sm"><input type="radio" name="stype" checked={formData.schedule_type === 'recurring'} onChange={() => setFormData({...formData, schedule_type: 'recurring'})}/> Recurring</label>
            </div>
          </div>
          {formData.schedule_type === 'once' && (
            <input type="datetime-local" className="inp-base w-full" value={formData.schedule_at} onChange={e => setFormData({...formData, schedule_at: e.target.value})} />
          )}
          {formData.schedule_type === 'recurring' && (
            <div className="flex flex-col gap-2">
              <input type="time" className="inp-base w-full" value={formData.schedule_time} onChange={e => setFormData({...formData, schedule_time: e.target.value})} />
              <div className="flex flex-wrap gap-2">
                {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(day => (
                  <button key={day} type="button" onClick={() => toggleDay(day)} className={`text-xs px-2 py-1 rounded border ${formData.recurring_days.includes(day) ? 'bg-[#00d4ff] text-[#0c1220]' : 'border-[#5a6a7a]'}`}>{day}</button>
                ))}
              </div>
            </div>
          )}
          <button type="button" onClick={() => setStep(2)} className="btn-primary w-full mt-4 flex justify-center items-center gap-2">
            Next <ChevronRight size={16} />
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <input type="text" placeholder="Dataset Path" className="inp-base w-full" value={formData.dataset_source} onChange={e => setFormData({...formData, dataset_source: e.target.value})} required />
          <div className="flex flex-col gap-2">
            <div className="flex justify-between items-center">
              <label className="text-xs text-[#7a8a9a]">Hyperparameters (JSON)</label>
              <button type="button" onClick={() => setPreview(!preview)} className="text-xs btn-ghost text-[#00d4ff]">
                {preview ? 'Hide Preview' : 'Preview'}
              </button>
            </div>
            {preview ? (
              <pre className="bg-[#050810] p-4 rounded text-xs text-[#00d4ff] overflow-auto h-48">{formData.hyperparameters}</pre>
            ) : (
              <>
                <input type="file" onChange={uploadHyperparameters} className="inp-base w-full p-1 text-xs" />
                <textarea className="inp-base w-full h-32" value={formData.hyperparameters} onChange={e => setFormData({...formData, hyperparameters: e.target.value})} />
              </>
            )}
          </div>
          <div className="flex gap-2 mt-4">
            <button type="button" onClick={() => setStep(1)} className="btn-ghost flex-1 flex justify-center items-center gap-2">
              <ChevronLeft size={16} /> Back
            </button>
            <button type="button" onClick={createJob} className="btn-primary flex-[2]">Schedule Job</button>
          </div>
        </div>
      )}
    </div>
  );
};
