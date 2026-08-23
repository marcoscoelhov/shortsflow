import React, {useMemo} from 'react';
import {fitText} from '@remotion/layout-utils';
import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import type {CaptionItem, FinishPlan} from './FinishPlan.schema';
import {fontFamily} from './fonts';

type CaptionFrame = {
  caption: CaptionItem;
  startFrame: number;
  endFrame: number;
};

export const PremiumCaptionTrack: React.FC<{
  items: CaptionItem[];
  plan: FinishPlan;
}> = ({items, plan}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const captionFrames: CaptionFrame[] = useMemo(
    () => items.map((caption) => ({
      caption,
      startFrame: msToFrame(captionStartMs(caption), fps),
      endFrame: msToFrame(captionEndMs(caption), fps)
    })),
    [fps, items]
  );
  const activeCaption = captionFrames.find((item) => frame >= item.startFrame && frame < item.endFrame)?.caption;

  return activeCaption ? <PremiumCaption caption={activeCaption} plan={plan} fps={fps} /> : null;
};

const PremiumCaption: React.FC<{
  caption: CaptionItem;
  plan: FinishPlan;
  fps: number;
}> = ({caption, plan, fps}) => {
  const frame = useCurrentFrame();
  const start = msToFrame(captionStartMs(caption), fps);
  const end = msToFrame(captionEndMs(caption), fps);
  const textParts = caption.text.split(' ');
  const localProgress = Math.min(0.999, Math.max(0, (frame - start) / Math.max(1, end - start)));
  const activeWordIndex = weightedActiveWordIndex(textParts, localProgress);
  const fontSize = captionFontSize(caption.text);
  const safeAreaX = Math.max(108, Number(plan.style.safe_area?.x || 0));
  const sideInset = safeAreaX;
  const bottomInset = plan.style.safe_area?.bottom ? Math.max(292, Number(plan.style.safe_area.bottom)) : 292;
  const maxLines = plan.caption_track?.max_lines ?? 1;

  return (
    <div
      style={{
        position: 'absolute',
        left: sideInset,
        right: sideInset,
        bottom: bottomInset,
        display: 'flex',
        justifyContent: 'center',
        translate: `0 ${interpolate(frame, [start, start + Math.round(fps * 0.12)], [20, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp'
        })}px`,
        scale: interpolate(frame, [start, start + Math.round(fps * 0.12)], [0.96, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp'
        }),
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
          lineHeight: 1.14,
          letterSpacing: 0,
          textAlign: 'center',
          whiteSpace: maxLines > 1 ? 'normal' : 'pre',
          overflowWrap: maxLines > 1 ? 'anywhere' : 'normal',
          wordBreak: maxLines > 1 ? 'break-word' : 'normal',
          textTransform: 'uppercase',
          WebkitTextStroke: '8px rgba(5, 5, 7, 0.92)',
          paintOrder: 'stroke fill',
          filter: 'drop-shadow(0 16px 22px rgba(0,0,0,0.58))'
        }}
      >
        {textParts.map((text, index) => {
          const highlight = wordHighlightProgress(frame, start, end, index, textParts.length);
          return (
            <React.Fragment key={`${text}-${index}`}>
              <span
                style={{
                  display: 'inline-block',
                  color: index === activeWordIndex ? 'oklch(0.86 0.17 88)' : plan.style.palette.text,
                  translate: `0 ${-2 * highlight}px`,
                  scale: 1 + 0.04 * highlight
                }}
              >
                {text}
              </span>
              {index < textParts.length - 1 ? ' ' : ''}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

const captionStartMs = (caption: CaptionItem) => caption.startMs ?? caption.start_ms ?? 0;

const captionEndMs = (caption: CaptionItem) => caption.endMs ?? caption.end_ms ?? Math.max(1, captionStartMs(caption) + 1);

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

const captionFontSize = (text: string) => {
  const {fontSize} = fitText({
    text,
    withinWidth: 730,
    fontFamily,
    fontWeight: 900
  });
  return Math.max(30, Math.min(64, Math.floor(fontSize)));
};

const msToFrame = (ms: number, fps: number) => Math.round((ms / 1000) * fps);
