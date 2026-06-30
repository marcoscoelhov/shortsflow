import React from 'react';
import {Composition} from 'remotion';
import {PremiumShort, type FinishPlan} from './PremiumShort';

const defaultPlan: FinishPlan = {
  schema_version: '1.0.0',
  finish_plan_version: 'finish-plan-v1',
  plan_name: 'Plano de Acabamento Editorial',
  finishing_package: 'Pacote de Acabamento Premium Inicial',
  job_id: 'preview',
  content_hash: 'preview',
  canvas: {width: 1080, height: 1920, fps: 30, duration_ms: 45000},
  audio: {uri: '', path: '', duration_ms: 45000, source: 'narration'},
  source_final_video_uri: null,
  visual_contract_summary: {visual_thesis: '', visual_domain: '', visual_world: ''},
  style: {
    component_policy: 'free_only',
    caption_style: 'one_line_kinetic',
    font_family: 'Inter, system-ui, sans-serif',
    palette: {
      background: 'oklch(0.13 0.012 25)',
      text: 'oklch(0.96 0.012 35)',
      muted: 'oklch(0.72 0.028 35)',
      accent: 'oklch(0.69 0.19 31)',
      accent_soft: 'oklch(0.84 0.08 31)'
    },
    safe_area: {x: 108, top: 132, bottom: 250}
  },
  caption_track: {mode: 'one_line_kinetic', max_lines: 1, items: []},
  scenes: [],
  summary: {scene_count: 0, caption_count: 0, premium_features: []}
};

export const Root: React.FC = () => {
  return (
    <Composition
      id="ShortsFlowPremiumShort"
      component={PremiumShort}
      defaultProps={defaultPlan}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={1350}
      calculateMetadata={({props}) => {
        const plan = props as FinishPlan;
        const fps = Number(plan.canvas?.fps || 30);
        return {
          width: Number(plan.canvas?.width || 1080),
          height: Number(plan.canvas?.height || 1920),
          fps,
          durationInFrames: Math.max(1, Math.ceil((Number(plan.canvas?.duration_ms || 45000) / 1000) * fps))
        };
      }}
    />
  );
};
