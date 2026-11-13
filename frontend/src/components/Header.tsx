import type { ConnectionStatus } from '@/lib/types';
import { usd } from '@/lib/format';

const dot: Record<ConnectionStatus, string> = {
  connected: 'bg-up',
  reconnecting: 'bg-accent',
  disconnected: 'bg-down',
};

export function Header({ totalValue, cash, status }: { totalValue: number | null; cash: number | null; status: ConnectionStatus }) {
  return (
    <header className="flex items-center justify-between border-b border-ink-600/70 bg-ink-950 px-4 py-2">
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-bold tracking-tight text-accent">FinAlly</span>
        <span className="hidden text-xs text-mute sm:inline">AI trading workstation</span>
      </div>
      <div className="flex items-center gap-6">
        <div className="text-right">
          <div className="text-[11px] text-mute">Portfolio value</div>
          <div data-testid="header-total" className="num text-base font-semibold text-white">
            {usd(totalValue)}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[11px] text-mute">Cash</div>
          <div data-testid="header-cash" className="num text-base font-semibold text-brand">
            {usd(cash)}
          </div>
        </div>
        <div className="flex items-center gap-1.5" title={`Price stream: ${status}`}>
          <span data-testid="connection-status" data-status={status} role="status" aria-label={`Connection ${status}`} className={`h-2.5 w-2.5 rounded-full ${dot[status]}`} />
          <span className="hidden text-xs text-mute md:inline">{status}</span>
        </div>
      </div>
    </header>
  );
}
