import {z} from 'zod';
import type {Caption as RemotionCaption} from '@remotion/captions';

const finiteNumber = z.number().finite();
const nonNegativeInteger = z.number().int().nonnegative();
const positiveInteger = z.number().int().positive();
const safeIdentifier = z.string().min(1).max(128).regex(/^[A-Za-z0-9_-]+$/);

export const CaptionTokenSchema = z.object({
  text: z.string(),
  fromMs: nonNegativeInteger,
  toMs: positiveInteger
}).refine((token) => token.toMs > token.fromMs, {message: 'caption token must end after it starts'});

export const CaptionItemSchema = z.object({
  idx: z.string(),
  text: z.string().min(1),
  startMs: nonNegativeInteger,
  endMs: positiveInteger,
  timestampMs: nonNegativeInteger.nullable(),
  confidence: finiteNumber.nullable(),
  emphasis: z.array(z.string()),
  start_ms: nonNegativeInteger.optional(),
  end_ms: positiveInteger.optional(),
  tokens: z.array(CaptionTokenSchema).optional()
}).superRefine((caption, context) => {
  if (caption.endMs <= caption.startMs) {
    context.addIssue({code: 'custom', message: 'caption must end after it starts'});
  }
  let previousTokenEnd = caption.startMs;
  for (const token of caption.tokens ?? []) {
    if (token.fromMs < caption.startMs || token.toMs > caption.endMs) {
      context.addIssue({code: 'custom', message: 'caption token exceeds caption timing', path: ['tokens']});
    }
    if (token.fromMs < previousTokenEnd) {
      context.addIssue({code: 'custom', message: 'caption tokens overlap or are out of order', path: ['tokens']});
    }
    previousTokenEnd = token.toMs;
  }
});

export const SceneMotionSchema = z.object({
  kind: z.enum(['stable_hold', 'subtle_push', 'slow_drift', 'payoff_pulse']),
  start_scale: finiteNumber.positive(),
  end_scale: finiteNumber.positive(),
  x_delta: finiteNumber,
  y_delta: finiteNumber
});

export const SceneOverlaySchema = z.object({
  kind: z.enum(['hook_tag', 'payoff_tag', 'evidence_marker']),
  text: z.string(),
  start_ms: nonNegativeInteger,
  duration_ms: positiveInteger,
  variant: z.enum(['choice_label', 'sand_progress', 'hazard_progress', 'choice_state', 'outcome_comparison', 'comment_prompt']).optional(),
  side: z.enum(['left', 'right']).optional(),
  progress: finiteNumber.min(0).max(1).optional(),
  secondary_text: z.string().optional()
});

export const SceneVisualEventSchema = z.object({
  kind: z.enum(['reframe', 'punch_in', 'accent', 'reveal']),
  start_ms: nonNegativeInteger,
  duration_ms: positiveInteger,
  scale_delta: finiteNumber.optional(),
  x_delta: finiteNumber.optional(),
  y_delta: finiteNumber.optional(),
  intensity: finiteNumber.nonnegative().optional()
});

export const VisualStyleProfileSchema = z.object({
  id: safeIdentifier,
  version: safeIdentifier,
  finishing: z.object({
    contrast: finiteNumber.positive(),
    saturation: finiteNumber.nonnegative(),
    accent_treatment: z.string()
  }).optional()
});

export const ScenePlanSchema = z.object({
  scene_id: safeIdentifier,
  order: positiveInteger,
  start_ms: nonNegativeInteger,
  end_ms: positiveInteger,
  duration_ms: positiveInteger,
  asset_uri: z.string().optional().default(''),
  asset_src: z.string().optional(),
  asset_path: z.string().optional().default(''),
  retention_role: z.string(),
  visual_intent: z.string(),
  primary_subject: z.string(),
  narration_text: z.string(),
  motion: SceneMotionSchema,
  transition: z.object({
    kind: z.enum(['cold_open', 'evidence_cut', 'payoff_reveal', 'soft_cut']),
    duration_ms: nonNegativeInteger
  }),
  overlays: z.array(SceneOverlaySchema),
  visual_events: z.array(SceneVisualEventSchema).optional(),
  visual_style_profile: VisualStyleProfileSchema.pick({id: true, version: true}).optional()
}).refine((scene) => scene.end_ms > scene.start_ms, {message: 'scene must end after it starts'});

export const FinishPlanSchema = z.object({
  schema_version: z.string().min(1),
  finish_plan_version: z.literal('finish-plan-v1'),
  plan_name: z.string().min(1),
  finishing_package: z.string().min(1),
  job_id: z.string().min(1),
  content_hash: z.string().min(1),
  canvas: z.object({width: z.literal(1080), height: z.literal(1920), fps: z.literal(30), duration_ms: positiveInteger}),
  audio: z.object({
    uri: z.string().optional().default(''),
    src: z.string().optional(),
    path: z.string().optional().default(''),
    duration_ms: positiveInteger,
    source: z.string()
  }),
  source_final_video_uri: z.string().nullable(),
  visual_contract_summary: z.object({visual_thesis: z.string(), visual_domain: z.string(), visual_world: z.string()}),
  style: z.object({
    component_policy: z.literal('free_only'),
    caption_style: z.literal('one_line_kinetic'),
    font_family: z.string(),
    palette: z.record(z.string(), z.string()),
    safe_area: z.object({x: nonNegativeInteger, top: nonNegativeInteger, bottom: nonNegativeInteger}),
    visual_style_profile: VisualStyleProfileSchema.optional()
  }),
  caption_track: z.object({mode: z.literal('one_line_kinetic'), max_lines: z.literal(1), items: z.array(CaptionItemSchema)}),
  scenes: z.array(ScenePlanSchema),
  summary: z.object({scene_count: nonNegativeInteger, caption_count: nonNegativeInteger, premium_features: z.array(z.string())})
}).superRefine((plan, context) => {
  const sceneIds = new Set<string>();
  let previousSceneEnd = 0;
  for (const [index, scene] of plan.scenes.entries()) {
    if (sceneIds.has(scene.scene_id)) {
      context.addIssue({code: 'custom', message: `duplicate scene_id: ${scene.scene_id}`, path: ['scenes']});
    }
    sceneIds.add(scene.scene_id);
    if (scene.end_ms > plan.canvas.duration_ms) {
      context.addIssue({code: 'custom', message: 'scene exceeds composition duration', path: ['scenes']});
    }
    if (scene.order !== index + 1 || scene.start_ms !== previousSceneEnd) {
      context.addIssue({code: 'custom', message: 'scenes must be ordered and contiguous', path: ['scenes']});
    }
    if (scene.duration_ms !== scene.end_ms - scene.start_ms) {
      context.addIssue({code: 'custom', message: 'scene duration is inconsistent', path: ['scenes']});
    }
    previousSceneEnd = scene.end_ms;
  }
  for (const caption of plan.caption_track.items) {
    if (caption.endMs > plan.canvas.duration_ms) {
      context.addIssue({code: 'custom', message: 'caption exceeds composition duration', path: ['caption_track', 'items']});
    }
  }
  if (plan.scenes.length > 0 && previousSceneEnd !== plan.canvas.duration_ms) {
    context.addIssue({code: 'custom', message: 'scenes must cover the composition duration', path: ['scenes']});
  }
  if (plan.audio.duration_ms !== plan.canvas.duration_ms) {
    context.addIssue({code: 'custom', message: 'audio duration must match composition duration', path: ['audio', 'duration_ms']});
  }
  if (plan.summary.scene_count !== plan.scenes.length || plan.summary.caption_count !== plan.caption_track.items.length) {
    context.addIssue({code: 'custom', message: 'summary counts do not match the plan', path: ['summary']});
  }
});

export type CaptionItem = z.infer<typeof CaptionItemSchema> & RemotionCaption;
export type FinishPlan = z.infer<typeof FinishPlanSchema>;
export type SceneOverlay = z.infer<typeof SceneOverlaySchema>;
export type ScenePlan = z.infer<typeof ScenePlanSchema>;
export type SceneVisualEvent = z.infer<typeof SceneVisualEventSchema>;
export type VisualStyleProfile = z.infer<typeof VisualStyleProfileSchema>;
