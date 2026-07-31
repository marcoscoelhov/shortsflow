import type {FinishPlan} from './PremiumShort';

type SceneContract = FinishPlan['scenes'][number];

export const legacySceneContract: SceneContract = {
  scene_id: 'legacy-scene',
  order: 1,
  start_ms: 0,
  end_ms: 4000,
  duration_ms: 4000,
  asset_uri: 'legacy.png',
  asset_path: '',
  retention_role: 'visual_hook',
  visual_intent: 'deceptive_establishing',
  primary_subject: 'octopus',
  narration_text: 'Legacy plans remain renderable.',
  motion: {kind: 'subtle_push', start_scale: 1.04, end_scale: 1.18, x_delta: 18, y_delta: -48},
  transition: {kind: 'cold_open', duration_ms: 0},
  overlays: []
};

export const enhancedSceneContract: SceneContract = {
  ...legacySceneContract,
  visual_style_profile: {id: 'high_contrast_comic', version: 'visual-style-v1'},
  visual_events: [
    {
      kind: 'punch_in',
      start_ms: 900,
      duration_ms: 700,
      scale_delta: 0.04,
      x_delta: 0,
      y_delta: -10
    },
    {
      kind: 'accent',
      start_ms: 2600,
      duration_ms: 600,
      intensity: 0.24
    }
  ]
};
