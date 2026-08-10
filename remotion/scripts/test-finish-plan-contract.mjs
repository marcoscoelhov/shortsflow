import assert from 'node:assert/strict';
import {FinishPlanSchema} from '../src/FinishPlan.schema.ts';

const validScene = {
  scene_id: 'scene-1',
  order: 1,
  start_ms: 0,
  end_ms: 35000,
  duration_ms: 35000,
  asset_uri: '',
  asset_path: '',
  retention_role: 'visual_hook',
  visual_intent: 'deceptive_establishing',
  primary_subject: 'polvo',
  narration_text: 'Um polvo parece simples.',
  motion: {kind: 'subtle_push', start_scale: 1.04, end_scale: 1.18, x_delta: 18, y_delta: -48},
  transition: {kind: 'cold_open', duration_ms: 0},
  overlays: []
};

const validPlan = {
  schema_version: '1.0.0',
  finish_plan_version: 'finish-plan-v1',
  plan_name: 'Plano de Acabamento Editorial',
  finishing_package: 'Pacote de Acabamento Premium Inicial',
  job_id: 'contract-test',
  content_hash: 'contract-test',
  canvas: {width: 1080, height: 1920, fps: 30, duration_ms: 35000},
  audio: {uri: '', path: '', duration_ms: 35000, source: 'narration'},
  source_final_video_uri: null,
  visual_contract_summary: {visual_thesis: '', visual_domain: '', visual_world: ''},
  style: {
    component_policy: 'free_only',
    caption_style: 'one_line_kinetic',
    font_family: 'Inter',
    palette: {background: '#000', text: '#fff', accent: '#f00'},
    safe_area: {x: 108, top: 132, bottom: 250}
  },
  caption_track: {mode: 'one_line_kinetic', max_lines: 1, items: []},
  scenes: [validScene],
  summary: {scene_count: 1, caption_count: 0, premium_features: []}
};

assert.equal(FinishPlanSchema.safeParse(validPlan).success, true);
assert.equal(FinishPlanSchema.safeParse({...validPlan, canvas: {...validPlan.canvas, width: 720}}).success, false);
assert.equal(FinishPlanSchema.safeParse({...validPlan, finish_plan_version: 'unknown'}).success, false);
assert.equal(FinishPlanSchema.safeParse({...validPlan, scenes: [{...validScene, scene_id: '../escape'}]}).success, false);
assert.equal(FinishPlanSchema.safeParse({...validPlan, scenes: [validScene, validScene]}).success, false);
assert.equal(FinishPlanSchema.safeParse({...validPlan, scenes: [{...validScene, duration_ms: 34000}]}).success, false);
assert.equal(FinishPlanSchema.safeParse({...validPlan, summary: {...validPlan.summary, scene_count: 2}}).success, false);

const producerCompatiblePlan = {
  ...validPlan,
  scenes: [
    {...validScene, end_ms: 250, duration_ms: 500},
    {
      ...validScene,
      scene_id: 'scene-2',
      order: 2,
      start_ms: 300,
      duration_ms: 34700,
      transition: {kind: 'soft_cut', duration_ms: 160}
    }
  ],
  summary: {...validPlan.summary, scene_count: 2}
};
assert.equal(FinishPlanSchema.safeParse(producerCompatiblePlan).success, true);

const captionPlan = {
  ...validPlan,
  caption_track: {
    ...validPlan.caption_track,
    items: [{
      idx: '1',
      text: 'Um polvo',
      startMs: 0,
      endMs: 1000,
      timestampMs: 0,
      confidence: null,
      emphasis: []
    }]
  },
  summary: {...validPlan.summary, caption_count: 1}
};
FinishPlanSchema.parse(captionPlan);
assert.equal(
  FinishPlanSchema.safeParse({
    ...captionPlan,
    caption_track: {
      ...captionPlan.caption_track,
      items: [{...captionPlan.caption_track.items[0], endMs: 0}]
    }
  }).success,
  false
);
