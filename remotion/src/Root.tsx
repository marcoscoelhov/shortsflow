import React from 'react';
import {type CalculateMetadataFunction, Composition} from 'remotion';
import {FinishPlanSchema, type FinishPlan} from './FinishPlan.schema';
import {PremiumShort} from './PremiumShort';

const calculateFinishPlanMetadata: CalculateMetadataFunction<FinishPlan> = ({props}) => ({
  durationInFrames: Math.max(1, Math.ceil((props.canvas.duration_ms / 1000) * props.canvas.fps))
});

export const Root: React.FC = () => {
  return (
    <Composition
      id="ShortsFlowPremiumShort"
      component={PremiumShort}
      schema={FinishPlanSchema}
      defaultProps={{
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
          font_family: 'Inter',
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
      }}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={1350}
      calculateMetadata={calculateFinishPlanMetadata}
    />
  );
};
