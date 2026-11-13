'use client';
import { useEffect, useRef } from 'react';
import { createChart, ColorType, type IChartApi, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts';

export interface ChartPoint {
  time: number; // unix seconds
  value: number;
}

/** Strictly ascending, de-duplicated times as required by lightweight-charts. */
export function normalizePoints(points: ChartPoint[]): { time: UTCTimestamp; value: number }[] {
  const out: { time: UTCTimestamp; value: number }[] = [];
  let last = -Infinity;
  for (const p of points) {
    const t = Math.floor(p.time);
    if (t <= last) {
      if (out.length) out[out.length - 1].value = p.value;
      continue;
    }
    out.push({ time: t as UTCTimestamp, value: p.value });
    last = t;
  }
  return out;
}

export function LineChart({ points, color, testId }: { points: ChartPoint[]; color: string; testId?: string }) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<'Area'> | null>(null);

  useEffect(() => {
    if (!el.current) return;
    const c = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#7d8b9f', fontSize: 11 },
      grid: { vertLines: { color: '#182231' }, horzLines: { color: '#182231' } },
      rightPriceScale: { borderColor: '#202b3a' },
      timeScale: { borderColor: '#202b3a', timeVisible: true, secondsVisible: true },
      crosshair: { mode: 1 },
    });
    chart.current = c;
    series.current = c.addAreaSeries({ lineColor: color, topColor: color + '55', bottomColor: color + '00', lineWidth: 2 });
    return () => {
      c.remove();
      chart.current = null;
      series.current = null;
    };
  }, [color]);

  useEffect(() => {
    series.current?.setData(normalizePoints(points));
    if (points.length > 1) chart.current?.timeScale().fitContent();
  }, [points, color]);

  return <div ref={el} data-testid={testId} data-points={points.length} className="absolute inset-0" />;
}
