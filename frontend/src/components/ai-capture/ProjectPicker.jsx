// frontend/src/components/ai-capture/ProjectPicker.jsx — Chat 19C §R3.3
//
// Project select with an AI-suggested-tag annotation on the row matching
// `job.suggested_project_id`. Uses the lucide `Sparkles` icon rather than
// the UTF-8 star char so glyphs render consistently across fonts (PASS-2 M2).
import { useQuery } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { api } from '@/lib/api';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';

function useProjects() {
  return useQuery({
    queryKey: ['projects-for-capture'],
    queryFn: async () =>
      // PASS-2 C3: /v1/ prefix per lib/api.js baseURL convention
      (await api.get('/v1/projects', { params: { page_size: 200 } })).data?.items ?? [],
    staleTime: 60_000,
  });
}

export function ProjectPicker({ value, onChange, suggested }) {
  const { data: projects = [], isLoading } = useProjects();

  if (isLoading) {
    return (
      <div className="text-sm text-slate-500" data-testid="project-picker-loading">
        Loading projects…
      </div>
    );
  }

  return (
    <Select value={value || ''} onValueChange={onChange}>
      <SelectTrigger data-testid="project-picker">
        <SelectValue placeholder="Select project…" />
      </SelectTrigger>
      <SelectContent>
        {projects.map((p) => {
          const isSuggested = suggested && p.id === suggested;
          return (
            <SelectItem
              key={p.id}
              value={p.id}
              data-testid={`project-picker-option-${p.id}`}
            >
              <span className="inline-flex items-center gap-1.5">
                {p.name}
                {isSuggested && (
                  <span
                    className="inline-flex items-center gap-0.5 text-xs text-amber-700"
                    data-testid={`project-picker-suggested-${p.id}`}
                  >
                    <Sparkles size={11} strokeWidth={2.25} /> AI suggestion
                  </span>
                )}
              </span>
            </SelectItem>
          );
        })}
      </SelectContent>
    </Select>
  );
}
