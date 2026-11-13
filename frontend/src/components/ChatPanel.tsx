'use client';
import { useEffect, useRef, useState } from 'react';
import type { ChatAction, ChatMessage } from '@/lib/types';
import { usd } from '@/lib/format';

export function describeTrade(t: ChatAction): string {
  const verb = t.side === 'sell' ? 'Sold' : 'Bought';
  const price = typeof t.price === 'number' ? ` @ ${usd(t.price)}` : '';
  return `${verb} ${t.quantity} ${t.ticker}${price}`;
}

export function describeWatch(w: ChatAction): string {
  return `${w.action === 'remove' ? 'Removed' : 'Added'} ${w.ticker} ${w.action === 'remove' ? 'from' : 'to'} watchlist`;
}

export function MessageBubble({ m }: { m: ChatMessage }) {
  const isUser = m.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        data-testid={isUser ? 'chat-message-user' : 'chat-message-assistant'}
        className={`max-w-[92%] rounded-md px-3 py-2 text-sm ${isUser ? 'bg-brand/20 text-white' : 'border border-ink-600 bg-ink-800 text-[#d6dde8]'}`}
      >
        <p className="whitespace-pre-wrap">{m.content}</p>
        {(m.trades?.length || m.watchlist_changes?.length || m.errors?.length) ? (
          <ul className="mt-2 space-y-1 border-t border-ink-600 pt-2 text-xs">
            {m.trades?.map((t, i) =>
              t.error ? (
                <li key={`t${i}`} data-testid="chat-action-error" className="text-down">
                  Trade failed: {t.side} {t.quantity} {t.ticker} - {t.error}
                </li>
              ) : (
                <li key={`t${i}`} data-testid="chat-action-trade" className="text-up">
                  {describeTrade(t)}
                </li>
              ),
            )}
            {m.watchlist_changes?.map((w, i) => (
              <li key={`w${i}`} data-testid="chat-action-watchlist" className={w.error ? 'text-down' : 'text-brand'}>
                {w.error ? `Watchlist change failed: ${w.ticker} - ${w.error}` : describeWatch(w)}
              </li>
            ))}
            {m.errors?.map((e, i) => (
              <li key={`e${i}`} data-testid="chat-action-error" className="text-down">
                {e}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

interface Props {
  messages: ChatMessage[];
  loading: boolean;
  onSend: (text: string) => void | Promise<void>;
  open: boolean;
  onToggle: () => void;
}

export function ChatPanel({ messages, loading, onSend, open, onToggle }: Props) {
  const [text, setText] = useState('');
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' });
  }, [messages, loading, open]);

  if (!open) {
    return (
      <button onClick={onToggle} aria-label="Open AI chat" className="panel flex h-full w-10 flex-col items-center justify-start gap-2 rounded-md py-3 text-accent hover:bg-ink-700">
        <span className="text-lg leading-none">&lsaquo;</span>
        <span className="text-xs font-semibold [writing-mode:vertical-rl]">AI assistant</span>
      </button>
    );
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t || loading) return;
    setText('');
    void onSend(t);
  };

  return (
    <aside className="panel flex h-full min-h-0 flex-col rounded-md" aria-label="AI chat">
      <div className="flex items-center justify-between border-b border-ink-600/60 px-3 py-2">
        <h2 className="panel-title text-accent">FinAlly assistant</h2>
        <button onClick={onToggle} aria-label="Collapse AI chat" className="rounded px-2 text-mute hover:text-white">
          &rsaquo;
        </button>
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3" data-testid="chat-messages">
        {messages.length === 0 && !loading && (
          <p className="text-xs text-mute">Ask about your portfolio, or tell me to trade. Try: &quot;Buy 5 shares of AAPL&quot; or &quot;How concentrated am I?&quot;</p>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} m={m} />
        ))}
        {loading && (
          <div data-testid="chat-loading" role="status" aria-label="Assistant is thinking" className="flex gap-1 px-1 py-2">
            <span className="h-2 w-2 animate-bounce rounded-full bg-accent [animation-delay:-0.3s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-accent [animation-delay:-0.15s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-accent" />
          </div>
        )}
        <div ref={end} />
      </div>
      <form onSubmit={submit} className="flex gap-2 border-t border-ink-600/60 p-2">
        <input
          data-testid="chat-input"
          aria-label="Message"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Message FinAlly"
          className="min-w-0 flex-1 rounded border border-ink-600 bg-ink-900 px-2 py-1.5 text-sm text-white placeholder:text-mute"
        />
        <button data-testid="chat-send" type="submit" disabled={loading} className="rounded bg-violet px-3 py-1.5 text-sm font-semibold text-white hover:brightness-125 disabled:opacity-50">
          Send
        </button>
      </form>
    </aside>
  );
}
