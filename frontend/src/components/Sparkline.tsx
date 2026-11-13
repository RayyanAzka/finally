export function Sparkline({ data, width = 84, height = 24 }: { data: number[]; width?: number; height?: number }) {
  if (data.length < 2) {
    return <svg width={width} height={height} aria-hidden="true" />;
  }
  const pts = data.slice(-80);
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const step = width / (pts.length - 1);
  const d = pts.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(height - 2 - ((v - min) / span) * (height - 4)).toFixed(1)}`).join(' ');
  const up = pts[pts.length - 1] >= pts[0];
  return (
    <svg width={width} height={height} data-testid="sparkline" aria-hidden="true">
      <path d={d} fill="none" stroke={up ? '#26c281' : '#ef4b5f'} strokeWidth={1.4} strokeLinejoin="round" />
    </svg>
  );
}
