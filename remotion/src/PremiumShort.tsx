import React, {useMemo} from 'react';
import {AbsoluteFill, Audio, Img, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

type RemotionCaption = {
  text: string;
  startMs: number;
  endMs: number;
};

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
  variant?: 'choice_label' | 'sand_progress' | 'hazard_progress' | 'choice_state' | 'outcome_comparison' | 'comment_prompt';
  side?: 'left' | 'right';
  progress?: number;
  secondary_text?: string;
};

type SceneVisualEvent = {
  kind: 'reframe' | 'punch_in' | 'accent' | 'reveal';
  start_ms: number;
  duration_ms: number;
  scale_delta?: number;
  x_delta?: number;
  y_delta?: number;
  intensity?: number;
};

type VisualStyleProfile = {
  id: string;
  version: string;
  finishing?: {
    contrast: number;
    saturation: number;
    accent_treatment: string;
  };
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
  visual_events?: SceneVisualEvent[];
  visual_style_profile?: Pick<VisualStyleProfile, 'id' | 'version'>;
};

type CaptionItem = RemotionCaption & {
  idx: string;
  emphasis: string[];
  start_ms?: number;
  end_ms?: number;
};

type CaptionFrame = {
  caption: CaptionItem;
  startFrame: number;
  endFrame: number;
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
    visual_style_profile?: VisualStyleProfile;
  };
  caption_track: {mode: string; max_lines: number; items: CaptionItem[]};
  scenes: ScenePlan[];
  summary: {scene_count: number; caption_count: number; premium_features: string[]};
};

export const PremiumShort: React.FC<FinishPlan> = (plan) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const audioSource = mediaSource(plan.audio.src || plan.audio.uri || '');
  const captionFrames: CaptionFrame[] = useMemo(
    () => plan.caption_track.items.map((caption) => ({
      caption,
      startFrame: msToFrame(captionStartMs(caption), fps),
      endFrame: msToFrame(captionEndMs(caption), fps)
    })),
    [fps, plan.caption_track.items]
  );
  const activeCaption = captionFrames.find((item) => frame >= item.startFrame && frame < item.endFrame)?.caption;

  return (
    <AbsoluteFill style={{background: plan.style.palette.background, fontFamily: plan.style.font_family}}>
      {plan.scenes.map((scene) => (
        <SceneLayer
          key={scene.scene_id}
          scene={scene}
          fps={fps}
          accent={plan.style.palette.accent}
          safeArea={plan.style.safe_area}
          styleProfile={plan.style.visual_style_profile}
        />
      ))}
      <Vignette />
      {activeCaption ? <Caption caption={activeCaption} plan={plan} fps={fps} /> : null}
      {audioSource ? <Audio src={audioSource} /> : null}
    </AbsoluteFill>
  );
};

const SceneLayer: React.FC<{
  scene: ScenePlan;
  fps: number;
  accent: string;
  safeArea: FinishPlan['style']['safe_area'];
  styleProfile?: VisualStyleProfile;
}> = ({scene, fps, accent, safeArea, styleProfile}) => {
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
  const eventCamera = eventCameraOffset(scene.visual_events, localFrame, fps);
  const pulse = scene.motion.kind === 'payoff_pulse'
    ? Math.sin(Math.PI * motionProgress) * 0.018
    : Math.sin(Math.PI * motionProgress * 2) * 0.006;
  const scale = scene.motion.start_scale + (scene.motion.end_scale - scene.motion.start_scale) * easedMotion + pulse + eventCamera.scale;
  const x = scene.motion.x_delta * easedMotion + eventCamera.x;
  const y = scene.motion.y_delta * easedMotion + eventCamera.y;
  const opacityIn = scene.order === 1 ? 1 : interpolate(localFrame, [0, transitionFrames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  // The outgoing Sequence extends through the incoming transition and stays
  // opaque underneath it. Fading both layers exposes the composition's black
  // background for one or two frames at scene boundaries.
  const opacity = opacityIn;
  const enter = spring({
    frame: Math.max(0, localFrame),
    fps,
    config: {damping: 24, stiffness: 140, mass: 0.75}
  });
  const transitionLift = transitionOffset(scene.transition.kind, enter);
  const clipPath = transitionClipPath(scene.transition.kind, enter);
  const roleContrast = scene.retention_role === 'visual_hook'
    ? 1.12
    : scene.retention_role === 'turn_or_payoff' || scene.retention_role === 'loop_close'
      ? 1.1
      : 1.04;
  const roleSaturation = scene.retention_role === 'visual_hook'
    ? 1.12
    : scene.retention_role === 'turn_or_payoff' || scene.retention_role === 'loop_close'
      ? 1.08
      : 1.04;
  const profileFinishing = styleProfile?.finishing;
  const imageFilter = `contrast(${roleContrast * ((profileFinishing?.contrast ?? 1.07) / 1.07)}) saturate(${roleSaturation * ((profileFinishing?.saturation ?? 0.96) / 0.96)})`;
  const assetSource = mediaSource(scene.asset_src || scene.asset_uri || scene.asset_path);

  return (
    <Sequence from={startFrame} durationInFrames={durationFrames + transitionFrames}>
      <AbsoluteFill style={{opacity, clipPath}}>
        <Img
          src={assetSource}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            transform: `translate3d(${x + transitionLift.x}px, ${y + transitionLift.y}px, 0) scale(${scale * transitionLift.scale})`,
            filter: imageFilter
          }}
        />
        <SceneTone scene={scene} accent={accent} localFrame={localFrame} fps={fps} />
        <EventAccent
          events={scene.visual_events}
          localFrame={localFrame}
          fps={fps}
          accent={accent}
          treatment={profileFinishing?.accent_treatment}
        />
        <TransitionAccent kind={scene.transition.kind} accent={accent} progress={enter} />
        <SceneOverlays overlays={scene.overlays} fps={fps} accent={accent} safeArea={safeArea} />
      </AbsoluteFill>
    </Sequence>
  );
};

const SceneOverlays: React.FC<{
  overlays: SceneOverlay[];
  fps: number;
  accent: string;
  safeArea: FinishPlan['style']['safe_area'];
}> = ({overlays, fps, accent, safeArea}) => {
  const frame = useCurrentFrame();
  const choiceCardTop = Math.max(212, safeArea.top + 80);
  const sandProgressTop = choiceCardTop + 148;
  return (
    <>
      {overlays.map((overlay, index) => {
        const startFrame = msToFrame(overlay.start_ms, fps);
        const durationFrames = Math.max(1, msToFrame(overlay.duration_ms, fps));
        const activeFrame = frame - startFrame;
        if (activeFrame < 0 || activeFrame >= durationFrames) {
          return null;
        }
        const enter = spring({
          frame: activeFrame,
          fps,
          config: {damping: 18, stiffness: 170, mass: 0.7}
        });
        const opacity = interpolate(activeFrame, [0, Math.max(2, fps * 0.16)], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp'
        });
        const key = `${overlay.variant || overlay.kind}-${overlay.side || index}`;

        if (overlay.variant === 'choice_label') {
          const pulseFrames = Math.max(12, Math.round(fps * 0.8));
          const pulse = interpolate(activeFrame % pulseFrames, [0, pulseFrames / 2, pulseFrames], [1, 1.045, 1]);
          return (
            <div
              key={key}
              style={{
                position: 'absolute',
                top: choiceCardTop,
                [overlay.side === 'right' ? 'right' : 'left']: Math.max(96, safeArea.x),
                width: 350,
                padding: '24px 30px',
                boxSizing: 'border-box',
                border: `3px solid ${accent}`,
                borderRadius: 24,
                background: 'rgba(7, 8, 10, 0.84)',
                color: 'white',
                fontSize: 48,
                fontWeight: 900,
                letterSpacing: 2,
                textAlign: 'center',
                opacity,
                scale: enter * pulse,
                translate: `${(overlay.side === 'right' ? 1 : -1) * (1 - enter) * 42}px 0`,
                boxShadow: `0 18px 48px rgba(0,0,0,0.42), inset 0 0 28px color-mix(in oklch, ${accent} 18%, transparent)`
              }}
            >
              {overlay.text}
            </div>
          );
        }

        if (overlay.variant === 'sand_progress' || overlay.variant === 'hazard_progress') {
          const target = Math.min(1, Math.max(0, Number(overlay.progress ?? 0)));
          const progress = interpolate(activeFrame, [0, durationFrames], [0, target], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp'
          });
          return (
            <div
              key={key}
              style={{
                position: 'absolute',
                top: sandProgressTop,
                left: Math.max(108, safeArea.x),
                right: Math.max(108, safeArea.x),
                opacity,
                translate: `0 ${(1 - enter) * -24}px`
              }}
            >
              <div style={{display: 'flex', justifyContent: 'space-between', color: 'white', fontSize: 32, fontWeight: 850}}>
                <span>{overlay.text}</span>
                <span>{Math.round(progress * 100)}%</span>
              </div>
              <div style={{height: 22, marginTop: 12, borderRadius: 20, background: 'rgba(255,255,255,0.2)', overflow: 'hidden'}}>
                <div
                  style={{
                    width: `${progress * 100}%`,
                    height: '100%',
                    borderRadius: 20,
                    background: `linear-gradient(90deg, oklch(0.82 0.11 78), ${accent})`,
                    boxShadow: `0 0 26px color-mix(in oklch, ${accent} 68%, transparent)`
                  }}
                />
              </div>
            </div>
          );
        }

        if (overlay.variant === 'choice_state') {
          const lock = interpolate(activeFrame, [0, Math.max(3, fps * 0.42)], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp'
          });
          return (
            <div
              key={key}
              style={{
                position: 'absolute',
                left: Math.max(150, safeArea.x),
                right: Math.max(150, safeArea.x),
                bottom: safeArea.bottom + 470,
                height: 180,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderTop: `6px solid ${accent}`,
                borderBottom: `6px solid ${accent}`,
                background: 'rgba(7, 8, 10, 0.82)',
                color: 'white',
                fontSize: 50,
                fontWeight: 950,
                letterSpacing: 3,
                opacity,
                scale: 0.92 + enter * 0.08,
                clipPath: `inset(0 ${Math.round((1 - lock) * 48)}% 0 ${Math.round((1 - lock) * 48)}%)`
              }}
            >
              {overlay.text}
            </div>
          );
        }

        if (overlay.variant === 'outcome_comparison') {
          const delayedEnter = spring({
            frame: Math.max(0, activeFrame - (overlay.side === 'right' ? Math.round(fps * 0.12) : 0)),
            fps,
            config: {damping: 20, stiffness: 150, mass: 0.78}
          });
          const wrong = overlay.side !== 'right';
          const outcomeIndicatorProgress = interpolate(activeFrame, [0, Math.max(3, fps * 0.28)], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp'
          });
          return (
            <div
              key={key}
              style={{
                position: 'absolute',
                [overlay.side === 'right' ? 'right' : 'left']: Math.max(76, safeArea.x - 30),
                bottom: safeArea.bottom + 470,
                width: 420,
                minHeight: 260,
                padding: '34px 28px',
                boxSizing: 'border-box',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 18,
                borderRadius: 28,
                border: `4px solid ${wrong ? 'oklch(0.65 0.2 28)' : 'oklch(0.78 0.18 145)'}`,
                background: wrong ? 'rgba(36, 8, 10, 0.88)' : 'rgba(5, 31, 18, 0.9)',
                color: 'white',
                textAlign: 'center',
                opacity,
                scale: 0.88 + delayedEnter * 0.12,
                translate: `0 ${(1 - delayedEnter) * 46}px`,
                boxShadow: '0 24px 54px rgba(0,0,0,0.48)'
              }}
            >
              <div
                style={{
                  color: wrong ? 'oklch(0.72 0.22 28)' : 'oklch(0.82 0.2 145)',
                  fontSize: 72,
                  fontWeight: 950,
                  lineHeight: 0.8,
                  opacity: outcomeIndicatorProgress,
                  scale: 0.55 + outcomeIndicatorProgress * 0.45
                }}
              >
                {wrong ? '×' : '✓'}
              </div>
              <div style={{fontSize: 38, fontWeight: 950, lineHeight: 1.05}}>{overlay.text}</div>
              {overlay.secondary_text ? (
                <div style={{fontSize: 46, fontWeight: 850, color: wrong ? 'oklch(0.82 0.12 28)' : 'oklch(0.86 0.15 145)'}}>
                  {overlay.secondary_text}
                </div>
              ) : null}
            </div>
          );
        }

        if (overlay.variant === 'comment_prompt') {
          const commentEnter = spring({
            frame: activeFrame,
            fps,
            config: {damping: 16, stiffness: 180, mass: 0.72}
          });
          const commentLift = interpolate(activeFrame, [0, Math.max(3, fps * 0.28)], [54, 0], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp'
          });
          const choices = (overlay.secondary_text || '').replace(/\?$/, '').split(/\s+OU\s+/);
          const emphasisFrames = Math.max(8, Math.round(fps * 0.42));
          const emphasizedChoiceIndex = Math.floor(activeFrame / emphasisFrames) % Math.max(1, choices.length);
          const emphasisPulse = interpolate(activeFrame % emphasisFrames, [0, emphasisFrames / 2, emphasisFrames], [0.65, 1, 0.65]);
          return (
            <div
              key={key}
              style={{
                position: 'absolute',
                left: Math.max(108, safeArea.x),
                right: Math.max(108, safeArea.x),
                bottom: safeArea.bottom + 240,
                maxWidth: 820,
                minHeight: 300,
                margin: '0 auto',
                padding: '42px 48px',
                boxSizing: 'border-box',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 26,
                border: `5px solid ${accent}`,
                borderRadius: 34,
                background: 'rgba(7, 8, 10, 0.92)',
                color: 'white',
                textAlign: 'center',
                opacity,
                scale: 0.88 + commentEnter * 0.12,
                translate: `0 ${commentLift}px`,
                boxShadow: `0 30px 72px rgba(0,0,0,0.58), inset 0 0 42px color-mix(in oklch, ${accent} 18%, transparent)`
              }}
            >
              <div style={{fontSize: 66, fontWeight: 950, lineHeight: 1.02, letterSpacing: 1}}>{overlay.text}</div>
              <div style={{display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 20, fontSize: 58, fontWeight: 950}}>
                {choices.map((choice, choiceIndex) => (
                  <React.Fragment key={`${choice}-${choiceIndex}`}>
                    <span
                      style={{
                        display: 'inline-block',
                        color: choiceIndex === emphasizedChoiceIndex ? accent : 'white',
                        scale: choiceIndex === emphasizedChoiceIndex ? 1 + emphasisPulse * 0.06 : 1,
                        opacity: choiceIndex === emphasizedChoiceIndex ? 1 : 0.82
                      }}
                    >
                      {choice}
                    </span>
                    {choiceIndex < choices.length - 1 ? <span style={{fontSize: 36, opacity: 0.68}}>OU</span> : null}
                  </React.Fragment>
                ))}
                <span>?</span>
              </div>
            </div>
          );
        }
        return null;
      })}
    </>
  );
};

const eventCameraOffset = (events: SceneVisualEvent[] | undefined, localFrame: number, fps: number) => {
  return (events ?? []).reduce(
    (total, event) => {
      if (event.kind === 'accent') {
        return total;
      }
      const progress = visualEventProgress(event, localFrame, fps);
      return {
        scale: total.scale + Number(event.scale_delta || 0) * progress,
        x: total.x + Number(event.x_delta || 0) * progress,
        y: total.y + Number(event.y_delta || 0) * progress
      };
    },
    {scale: 0, x: 0, y: 0}
  );
};

const EventAccent: React.FC<{
  events?: SceneVisualEvent[];
  localFrame: number;
  fps: number;
  accent: string;
  treatment?: string;
}> = ({events, localFrame, fps, accent, treatment}) => {
  const intensity = (events ?? [])
    .filter((event) => event.kind === 'accent')
    .reduce((maximum, event) => {
      const progress = visualEventPulse(event, localFrame, fps);
      return Math.max(maximum, Number(event.intensity || 0.22) * progress);
    }, 0);
  if (intensity <= 0) {
    return null;
  }
  const background = treatment === 'paper_wash'
    ? `radial-gradient(circle at 50% 34%, color-mix(in oklch, ${accent} ${Math.round(intensity * 70)}%, transparent), transparent 58%)`
    : treatment === 'ink_strike'
      ? `linear-gradient(112deg, transparent 18%, color-mix(in oklch, ${accent} ${Math.round(intensity * 100)}%, transparent) 49%, transparent 52%)`
      : treatment === 'miniature_spotlight'
        ? `radial-gradient(ellipse at 50% 44%, color-mix(in oklch, ${accent} ${Math.round(intensity * 64)}%, transparent), transparent 48%)`
        : `linear-gradient(90deg, color-mix(in oklch, ${accent} ${Math.round(intensity * 78)}%, transparent), transparent 46%)`;
  return <AbsoluteFill style={{background, pointerEvents: 'none'}} />;
};

const mediaSource = (value: string): string => {
  if (!value) {
    return '';
  }
  if (/^(https?:|data:|blob:|file:)/.test(value)) {
    return value;
  }
  return staticFile(value.replace(/^\/+/, ''));
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

const Caption: React.FC<{caption: CaptionItem; plan: FinishPlan; fps: number}> = ({caption, plan, fps}) => {
  const frame = useCurrentFrame();
  const start = msToFrame(captionStartMs(caption), fps);
  const end = msToFrame(captionEndMs(caption), fps);
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
  const sideInset = captionSideInset(plan);
  return (
    <div
      style={{
        position: 'absolute',
        left: sideInset,
        right: sideInset,
        bottom: 292,
        display: 'flex',
        justifyContent: 'center',
        transform: `translateY(${enter}px) scale(${scale})`,
        transformOrigin: 'center center',
        boxSizing: 'border-box',
        overflow: 'visible'
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 840,
          padding: '8px 28px 10px',
          boxSizing: 'border-box',
          color: plan.style.palette.text,
          fontSize,
          fontWeight: 900,
          lineHeight: 1,
          letterSpacing: 0,
          textAlign: 'center',
          whiteSpace: 'nowrap',
          textTransform: 'uppercase',
          WebkitTextStroke: '8px rgba(5, 5, 7, 0.92)',
          paintOrder: 'stroke fill',
          filter: 'drop-shadow(0 16px 22px rgba(0,0,0,0.58))'
        }}
      >
        {words.map((word, index) => {
          const emphasized = index === activeWordIndex;
          const highlight = wordHighlightProgress(frame, start, end, index, words.length);
          return (
            <React.Fragment key={`${word}-${index}`}>
              <span
                style={{
                  display: 'inline-block',
                  color: emphasized ? 'oklch(0.86 0.17 88)' : plan.style.palette.text,
                  transform: `translateY(${-2 * highlight}px) scale(${1 + 0.04 * highlight})`
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

const captionSideInset = (plan: FinishPlan) => {
  const configured = Number(plan.style.safe_area?.x || 0);
  return Math.max(108, configured);
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

const visualEventProgress = (event: SceneVisualEvent, localFrame: number, fps: number) => {
  const startFrame = msToFrame(event.start_ms, fps);
  const durationFrames = Math.max(1, msToFrame(event.duration_ms, fps));
  return interpolate(localFrame, [startFrame, startFrame + durationFrames], [0, 1], {
    easing: easeInOutCubic,
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
};

const visualEventPulse = (event: SceneVisualEvent, localFrame: number, fps: number) => {
  const startFrame = msToFrame(event.start_ms, fps);
  const durationFrames = Math.max(2, msToFrame(event.duration_ms, fps));
  return interpolate(
    localFrame,
    [startFrame, startFrame + durationFrames * 0.42, startFrame + durationFrames],
    [0, 1, 0],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp'
    }
  );
};

const captionStartMs = (caption: CaptionItem) => caption.startMs ?? caption.start_ms ?? 0;

const captionEndMs = (caption: CaptionItem) => caption.endMs ?? caption.end_ms ?? Math.max(1, captionStartMs(caption) + 1);

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

const wordHighlightProgress = (frame: number, start: number, end: number, index: number, wordCount: number) => {
  const duration = Math.max(1, end - start);
  const wordStart = start + (duration * index) / Math.max(1, wordCount);
  const wordEnd = start + (duration * (index + 1)) / Math.max(1, wordCount);
  const ramp = Math.max(2, Math.min(5, Math.round(duration / Math.max(1, wordCount) / 4)));
  return interpolate(frame, [wordStart - ramp, wordStart, wordEnd, wordEnd + ramp], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
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
  return Math.max(30, Math.min(64, Math.floor(760 / (length * 0.66))));
};
