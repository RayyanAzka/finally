'use client';
import { useEffect, useRef, useState } from 'react';
import { num } from '@/lib/format';

/** Shows a price; flashes green/red briefly when it changes. */
export function PriceCell({ price, testId, className = '' }: { price?: number | null; testId?: string; className?: string }) {
  const prev = useRef<number | null | undefined>(price);
  const [flash, setFlash] = useState<'up' | 'down' | null>(null);

  useEffect(() => {
    if (price == null || prev.current == null || price === prev.current) {
      prev.current = price;
      return;
    }
    setFlash(price > prev.current ? 'up' : 'down');
    prev.current = price;
    const t = setTimeout(() => setFlash(null), 80);
    return () => clearTimeout(t);
  }, [price]);

  const cls = flash === 'up' ? 'flash-up' : flash === 'down' ? 'flash-down' : 'flash-idle';
  return (
    <span data-testid={testId} data-flash={flash ?? ''} className={`num inline-block rounded px-1.5 py-0.5 ${cls} ${className}`}>
      {num(price)}
    </span>
  );
}
