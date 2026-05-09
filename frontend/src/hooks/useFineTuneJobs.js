import { useState, useEffect } from 'react';

export const useFineTuneJobs = () => {
  const [jobs, setJobs] = useState([]);

  const fetchJobs = async () => {
    try {
      const resp = await fetch('/api/fine-tune/jobs', {
        headers: { 'X-API-Key': sessionStorage.getItem('ollama_api_key') }
      });
      const data = await resp.json();
      setJobs(data);
    } catch (e) { console.error('Failed to load jobs', e); }
  };

  useEffect(() => { 
    fetchJobs(); 
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  return { jobs, refetch: fetchJobs };
};
