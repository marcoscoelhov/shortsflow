import React from 'react';
import {Audio} from '@remotion/media';
import {AbsoluteFill, Easing, Img, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import type {FinishPlan, SceneOverlay, ScenePlan, SceneVisualEvent, VisualStyleProfile} from './FinishPlan.schema';
import {fontFamily} from './fonts';
import {PremiumCaptionTrack} from './PremiumCaption';

export type {FinishPlan} from './FinishPlan.schema';

export const PremiumShort: React.FC<FinishPlan> = (plan) => {
  const {fps} = useVideoConfig();
  const audioSource = mediaSource(plan.audio.src || plan.audio.uri || '');

  return (
    <AbsoluteFill style={{background: plan.style.palette.background, fontFamily}}>
      {plan.scenes.map((scene, index) => {
        const nextScene = plan.scenes[index + 1];
        const exitOverlapFrames = msToFrame(nextScene?.transition.duration_ms ?? 0, fps);
        return (
          <SceneLayer
            key={scene.scene_id}
            scene={scene}
            fps={fps}
            accent={plan.style.palette.accent}
            safeArea={plan.style.safe_area}
            styleProfile={plan.style.visual_style_profile}
            exitOverlapFrames={exitOverlapFrames}
          />
        );
      })}
      <Vignette />
      <PremiumCaptionTrack items={plan.caption_track.items} plan={plan} />
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
  exitOverlapFrames: number;
}> = ({scene, fps, accent, safeArea, styleProfile, exitOverlapFrames}) => {
  const frame = useCurrentFrame();
  const startFrame = msToFrame(scene.start_ms, fps);
  const durationFrames = Math.max(1, msToFrame(scene.duration_ms, fps));
  const localFrame = frame - startFrame;
  const transitionFrames = scene.order === 1 ? 0 : Math.max(1, msToFrame(scene.transition.duration_ms || 180, fps));
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
  const transitionStartOpacity = scene.transition.kind === 'evidence_cut'
    ? 0.58
    : scene.transition.kind === 'payoff_reveal'
      ? 0.16
      : 0;
  const opacity = scene.order === 1 ? 1 : interpolate(localFrame, [0, transitionFrames], [transitionStartOpacity, 1], {
    easing: Easing.bezier(0.22, 1, 0.36, 1),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const enter = transitionFrames === 0 ? 1 : interpolate(localFrame, [0, transitionFrames], [0, 1], {
    easing: Easing.bezier(0.22, 1, 0.36, 1),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const transitionLift = transitionOffset(scene.transition.kind, enter);
  const clipPath = transitionClipPath(scene.transition.kind, enter);
  const transitionExposure = 1 + Math.sin(Math.PI * enter) * (scene.transition.kind === 'payoff_reveal' ? 0.035 : 0.018);
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
    <Sequence from={startFrame} durationInFrames={durationFrames + exitOverlapFrames}>
      <AbsoluteFill style={{opacity, clipPath}}>
        <Img
          src={assetSource}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            translate: `${x + transitionLift.x}px ${y + transitionLift.y}px`,
            scale: scale * transitionLift.scale,
            filter: `${imageFilter} brightness(${transitionExposure})`,
            willChange: 'opacity, translate, scale, clip-path'
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
        const enterFrames = Math.min(Math.max(2, Math.round(fps * 0.18)), Math.max(1, Math.floor(durationFrames / 3)));
        const exitFrames = Math.min(Math.max(3, Math.round(fps * 0.24)), Math.max(1, Math.floor(durationFrames / 3)));
        const enter = spring({
          frame: activeFrame,
          fps,
          config: {damping: 22, stiffness: 145, mass: 0.78}
        });
        const opacity = durationFrames < 4
          ? 1
          : interpolate(
              activeFrame,
              [0, enterFrames, durationFrames - exitFrames, durationFrames - 1],
              [0, 1, 1, 0],
              {
                easing: [Easing.bezier(0.22, 1, 0.36, 1), Easing.linear, Easing.bezier(0.4, 0, 1, 1)],
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp'
              }
            );
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
  const reveal = interpolate(localFrame, [0, Math.round(fps * 0.55)], [0.38, 0.16], {
    easing: Easing.bezier(0.22, 1, 0.36, 1),
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

const TransitionAccent: React.FC<{kind: string; accent: string; progress: number}> = ({kind, accent, progress}) => {
  if (kind === 'cold_open') {
    return null;
  }
  const atmosphereOpacity = interpolate(progress, [0, 0.42, 1], [0, kind === 'payoff_reveal' ? 0.2 : 0.11, 0], {
    easing: [Easing.bezier(0.22, 1, 0.36, 1), Easing.bezier(0.4, 0, 1, 1)],
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const sheenPosition = interpolate(progress, [0, 1], [-32, 132], {
    easing: Easing.bezier(0.22, 1, 0.36, 1),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  const payoff = kind === 'payoff_reveal';
  return (
    <AbsoluteFill
      style={{
        background: payoff
          ? `radial-gradient(ellipse at ${sheenPosition}% 46%, color-mix(in oklch, ${accent} 74%, transparent), transparent 42%)`
          : `linear-gradient(108deg, transparent ${sheenPosition - 24}%, color-mix(in oklch, ${accent} 56%, transparent) ${sheenPosition}%, transparent ${sheenPosition + 20}%)`,
        mixBlendMode: 'screen',
        opacity: atmosphereOpacity,
        pointerEvents: 'none'
      }}
    />
  );
};

const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{
      background: 'radial-gradient(circle at 50% 42%, transparent 0%, transparent 58%, rgba(0,0,0,0.46) 100%)',
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
  const progress = interpolate(localFrame, [startFrame, startFrame + durationFrames], [0, 1], {
    easing: Easing.bezier(0.22, 1, 0.36, 1),
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });
  return Math.sin(Math.PI * progress);
};

const easeInOutCubic = (value: number) => {
  const t = Math.min(1, Math.max(0, value));
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
};

const transitionOffset = (kind: string, progress: number) => {
  if (kind === 'payoff_reveal') {
    return {x: interpolate(progress, [0, 1], [28, 0]), y: 0, scale: interpolate(progress, [0, 1], [1.028, 1])};
  }
  if (kind === 'evidence_cut') {
    return {x: 0, y: interpolate(progress, [0, 1], [12, 0]), scale: interpolate(progress, [0, 1], [1.018, 1])};
  }
  return {x: 0, y: interpolate(progress, [0, 1], [6, 0]), scale: interpolate(progress, [0, 1], [1.012, 1])};
};

const transitionClipPath = (kind: string, progress: number) => {
  if (kind === 'payoff_reveal') {
    const right = interpolate(progress, [0, 1], [12, 0], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp'
    });
    return `inset(0 ${right}% 0 0 round ${Math.round((1 - progress) * 18)}px)`;
  }
  if (kind === 'evidence_cut') {
    const bottom = interpolate(progress, [0, 1], [5, 0], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp'
    });
    return `inset(0 0 ${bottom}% 0)`;
  }
  return 'inset(0 0 0 0)';
};
