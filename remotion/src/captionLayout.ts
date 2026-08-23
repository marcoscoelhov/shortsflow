export const captionLineClampStyle = (maxLines: 1 | 2, fontSize: number) => {
  if (maxLines === 1) {
    return {
      display: 'block' as const,
      whiteSpace: 'pre' as const,
      overflow: 'visible' as const
    };
  }
  return {
    display: '-webkit-box' as const,
    WebkitBoxOrient: 'vertical' as const,
    WebkitLineClamp: maxLines,
    whiteSpace: 'normal' as const,
    overflow: 'hidden' as const,
    boxSizing: 'border-box' as const,
    maxHeight: Math.ceil(fontSize * 1.14 * maxLines) + 18
  };
};
