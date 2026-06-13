import React from 'react';
import {AbsoluteFill, Audio, Img, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

type SceneMotion = {
  kind: string;
  start_scale: number;
  end_scale: number;
  x_delta: number;
  y_delta: number;
};

type SceneOverlay = {
  kind: string;
  text: string;
  start_ms: number;
  duration_ms: number;
};

type ScenePlan = {
  scene_id: string;
  order: number;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  asset_uri: string;
  asset_src?: string;
  asset_path: string;
  retention_role: string;
  visual_intent: string;
  primary_subject: string;
  narration_text: string;
  motion: SceneMotion;
  transition: {kind: string; duration_ms: number};
  overlays: SceneOverlay[];
};

type CaptionItem = {
  idx: string;
  start_ms: number;
  end_ms: number;
  text: string;
  emphasis: string[];
};

export type FinishPlan = {
  schema_version: string;
  finish_plan_version: string;
  plan_name: string;
  finishing_package: string;
  job_id: string;
  content_hash: string;
  canvas: {width: number; height: number; fps: number; duration_ms: number};
  audio: {uri: string; src?: string; path: string; duration_ms: number; source: string};
  source_final_video_uri: string | null;
  visual_contract_summary: {visual_thesis: string; visual_domain: string; visual_world: string};
  style: {
    component_policy: string;
    caption_style: string;
    font_family: string;
    palette: Record<string, string>;
    safe_area: {x: number; top: number; bottom: number};
  };
  caption_track: {mode: string; max_lines: number; items: CaptionItem[]};
  scenes: ScenePlan[];
  summary: {scene_count: number; caption_count: number; premium_features: string[]};
};

export const PremiumShort: React.FC<FinishPlan> = (plan) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const activeCaption = plan.caption_track.items.find((item) => {
    const start = msToFrame(item.start_ms, fps);
    const end = msToFrame(item.end_ms, fps);
    return frame >= start && frame < end;
  });

  return (
    <AbsoluteFill style={{background: plan.style.palette.background, fontFamily: plan.style.font_family}}>
      {plan.scenes.map((scene) => (
        <SceneLayer key={scene.scene_id} scene={scene} fps={fps} accent={plan.style.palette.accent} />
      ))}
      <Vignette />
      {activeCaption ? <Caption caption={activeCaption} plan={plan} fps={fps} /> : null}
      {plan.audio.src || plan.audio.uri ? <Audio src={plan.audio.src || plan.audio.uri} /> : null}
    </AbsoluteFill>
  );
};

const SceneLayer: React.FC<{scene: ScenePlan; fps: number; accent: string}> = ({scene, fps, accent}) => {
  const frame = useCurrentFrame();
  const startFrame = msToFrame(scene.start_ms, fps);
  const durationFrames = Math.max(1, msToFrame(scene.duration_ms, fps));
  const localFrame = frame - startFrame;
  const transitionFrames = Math.max(1, msToFrame(scene.transition.duration_ms || 160, fps));
  const motionProgress = interpolate(localFrame, [0, durationFrames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const easedMotion = easeInOutCubic(motionProgress);
  const pulse = scene.motion.kind === 'payoff_pulse'
    ? Math.sin(Math.PI * motionProgress) * 0.018
    : Math.sin(Math.PI * motionProgress * 2) * 0.006;
  const scale = scene.motion.start_scale + (scene.motion.end_scale - scene.motion.start_scale) * easedMotion + pulse;
  const x = scene.motion.x_delta * easedMotion;
  const y = scene.motion.y_delta * easedMotion;
  const opacityIn = scene.order === 1 ? 1 : interpolate(localFrame, [0, transitionFrames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const opacityOut = interpolate(localFrame, [durationFrames - transitionFrames, durationFrames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const opacity = Math.min(opacityIn, opacityOut);
  const enter = spring({
    frame: Math.max(0, localFrame),
    fps,
    config: {damping: 24, stiffness: 140, mass: 0.75}
  });
  const transitionLift = transitionOffset(scene.transition.kind, enter);
  const clipPath = transitionClipPath(scene.transition.kind, enter);
  const imageFilter = scene.retention_role === 'visual_hook'
    ? 'contrast(1.12) saturate(1.12)'
    : scene.retention_role === 'turn_or_payoff' || scene.retention_role === 'loop_close'
      ? 'contrast(1.1) saturate(1.08)'
      : 'contrast(1.04) saturate(1.04)';

  return (
    <Sequence from={startFrame} durationInFrames={durationFrames + transitionFrames}>
      <AbsoluteFill style={{opacity, clipPath}}>
        <Img
          src={scene.asset_src || scene.asset_uri}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            transform: `translate3d(${x + transitionLift.x}px, ${y + transitionLift.y}px, 0) scale(${scale * transitionLift.scale})`,
            filter: imageFilter
          }}
        />
        <SceneTone scene={scene} accent={accent} localFrame={localFrame} fps={fps} />
        <TransitionAccent kind={scene.transition.kind} accent={accent} progress={enter} />
      </AbsoluteFill>
    </Sequence>
  );
};

const SceneTone: React.FC<{scene: ScenePlan; accent: string; localFrame: number; fps: number}> = ({scene, accent, localFrame, fps}) => {
  const reveal = interpolate(localFrame, [0, Math.round(fps * 0.35)], [0.65, 0.2], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const payoff = scene.retention_role === 'turn_or_payoff' || scene.retention_role === 'loop_close';
  return (
    <AbsoluteFill
      style={{
        background: payoff
          ? `linear-gradient(180deg, rgba(0,0,0,${reveal}), rgba(0,0,0,0.12) 42%, color-mix(in oklch, ${accent} 24%, transparent))`
          : `linear-gradient(180deg, rgba(0,0,0,${reveal}), rgba(0,0,0,0.08) 48%, rgba(0,0,0,0.42))`
      }}
    />
  );
};

const Overlay: React.FC<{overlay: SceneOverlay; fps: number; localFrame: number; accent: string}> = ({overlay, fps, localFrame, accent}) => {
  const start = msToFrame(overlay.start_ms, fps);
  const end = start + msToFrame(overlay.duration_ms, fps);
  const visible = localFrame >= start && localFrame <= end;
  const enter = interpolate(localFrame, [start, start + Math.round(fps * 0.18)], [18, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  if (!visible || !overlay.text) {
    return null;
  }
  return (
    <div
      style={{
        position: 'absolute',
        top: 126,
        left: 72,
        maxWidth: 760,
        padding: '18px 24px',
        borderRadius: 8,
        background: 'rgba(9, 9, 11, 0.74)',
        border: `2px solid ${accent}`,
        color: 'oklch(0.96 0.012 35)',
        fontSize: 34,
        fontWeight: 800,
        letterSpacing: 0,
        lineHeight: 1.05,
        textTransform: 'uppercase',
        transform: `translateY(${enter}px)`
      }}
    >
      {overlay.text}
    </div>
  );
};

const Caption: React.FC<{caption: CaptionItem; plan: FinishPlan; fps: number}> = ({caption, plan, fps}) => {
  const frame = useCurrentFrame();
  const start = msToFrame(caption.start_ms, fps);
  const end = msToFrame(caption.end_ms, fps);
  const words = caption.text.split(' ');
  const localProgress = Math.min(0.999, Math.max(0, (frame - start) / Math.max(1, end - start)));
  const activeWordIndex = weightedActiveWordIndex(words, localProgress);
  const fontSize = captionFontSize(caption.text);
  const enter = interpolate(frame, [start, start + Math.round(fps * 0.12)], [20, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const scale = interpolate(frame, [start, start + Math.round(fps * 0.12)], [0.96, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  return (
    <div
      style={{
        position: 'absolute',
        left: plan.style.safe_area.x,
        right: plan.style.safe_area.x,
        bottom: 292,
        display: 'flex',
        justifyContent: 'center',
        transform: `translateY(${enter}px) scale(${scale})`
      }}
    >
      <div
        style={{
          maxWidth: 980,
          padding: '8px 14px 10px',
          color: plan.style.palette.text,
          fontSize,
          fontWeight: 900,
          lineHeight: 1,
          letterSpacing: 0,
          textAlign: 'center',
          whiteSpace: 'nowrap',
          textTransform: 'uppercase',
          WebkitTextStroke: '10px rgba(5, 5, 7, 0.92)',
          paintOrder: 'stroke fill',
          filter: 'drop-shadow(0 16px 22px rgba(0,0,0,0.58))'
        }}
      >
        {words.map((word, index) => {
          const emphasized = index === activeWordIndex;
          return (
            <React.Fragment key={`${word}-${index}`}>
              <span
                style={{
                  display: 'inline-block',
                  color: emphasized ? 'oklch(0.86 0.17 88)' : plan.style.palette.text,
                  transform: index === activeWordIndex ? 'translateY(-2px) scale(1.06)' : 'translateY(0) scale(1)',
                  transition: 'transform 35ms linear, color 35ms linear'
                }}
              >
                {word}
              </span>
              {index < words.length - 1 ? ' ' : ''}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

const TransitionAccent: React.FC<{kind: string; accent: string; progress: number}> = ({kind, accent, progress}) => {
  if (kind === 'cold_open') {
    return null;
  }
  const alpha = interpolate(progress, [0, 0.45, 1], [0.34, 0.12, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const borderWidth = interpolate(progress, [0, 1], [18, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const payoff = kind === 'payoff_reveal';
  return (
    <AbsoluteFill
      style={{
        background: payoff
          ? `linear-gradient(90deg, color-mix(in oklch, ${accent} ${Math.round(alpha * 100)}%, transparent), transparent 52%)`
          : `linear-gradient(180deg, rgba(255,255,255,${alpha}), transparent 40%)`,
        boxShadow: payoff ? `inset 0 0 0 ${borderWidth}px color-mix(in oklch, ${accent} 48%, transparent)` : 'none',
        pointerEvents: 'none'
      }}
    />
  );
};

const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{
      background: 'radial-gradient(circle at 50% 42%, transparent 0%, transparent 55%, rgba(0,0,0,0.56) 100%)',
      pointerEvents: 'none'
    }}
  />
);

const msToFrame = (ms: number, fps: number) => Math.round((ms / 1000) * fps);

const easeInOutCubic = (value: number) => {
  const t = Math.min(1, Math.max(0, value));
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
};

const weightedActiveWordIndex = (words: string[], progress: number) => {
  if (words.length <= 1) {
    return 0;
  }
  const weights = words.map((word) => {
    const cleanLength = word.replace(/[^\p{L}\p{N}-]/gu, '').length;
    const pauseWeight = /[.,:;!?]$/.test(word) ? 1.4 : 0;
    return Math.max(1.6, cleanLength + pauseWeight);
  });
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  const cursor = Math.min(total - 0.001, Math.max(0, progress * total));
  let accumulated = 0;
  for (let index = 0; index < weights.length; index += 1) {
    accumulated += weights[index];
    if (cursor < accumulated) {
      return index;
    }
  }
  return words.length - 1;
};

const transitionOffset = (kind: string, progress: number) => {
  const eased = 1 - Math.pow(1 - progress, 4);
  if (kind === 'payoff_reveal') {
    return {x: interpolate(eased, [0, 1], [34, 0]), y: 0, scale: interpolate(eased, [0, 1], [1.035, 1])};
  }
  if (kind === 'evidence_cut') {
    return {x: 0, y: interpolate(eased, [0, 1], [18, 0]), scale: interpolate(eased, [0, 1], [1.025, 1])};
  }
  return {x: 0, y: 0, scale: interpolate(eased, [0, 1], [1.012, 1])};
};

const transitionClipPath = (kind: string, progress: number) => {
  if (kind !== 'payoff_reveal') {
    return 'inset(0 0 0 0)';
  }
  const right = interpolate(progress, [0, 1], [20, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  return `inset(0 ${right}% 0 0)`;
};

const captionFontSize = (text: string) => {
  const length = Math.max(12, text.length);
  return Math.max(32, Math.min(68, Math.floor(900 / (length * 0.66))));
};
