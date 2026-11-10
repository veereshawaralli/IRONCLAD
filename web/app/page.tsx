'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import {
  Shield, Activity, GitPullRequest, Layers, Settings, Search,
  ArrowUpRight, Play, ChevronRight, Terminal, Check, AlertTriangle,
  Radio, Command, LogOut, RefreshCw, Database, Workflow, Clock,
  ArrowLeft, X, Zap, Eye, Lock, Cpu
} from 'lucide-react';

/* ─── Types ─── */
type Event = {
  seq: number;
  agent: string;
  kind: string;
  timestamp: string;
  duration_ms: number;
  payload: Record<string, unknown>;
};
type Run = {
  id: string;
  summary: string;
  status: string;
  steps: number;
  mode: string;
  reserved_usd: number;
  created_at: string;
};
type Citation = { path: string; start_line: number; end_line: number; text: string };

/* ─── Constants ─── */
const tabs = ['Overview', 'Incidents', 'Replay', 'PR review', 'Knowledge', 'Settings'];
const roles = ['watcher', 'diagnostician', 'surgeon', 'verifier', 'reporter'] as const;

const roleDescriptions: Record<string, string> = {
  watcher: 'Failure ingestion & clustering',
  diagnostician: 'Evidence & root-cause analysis',
  surgeon: 'Scoped patch generation',
  verifier: 'Isolated sandbox validation',
  reporter: 'Review-ready reports & PRs',
};

const tabIcons = [Activity, Layers, Clock, GitPullRequest, Database, Settings];

/* ─── API Helper ─── */
async function api(path: string, method = 'GET', body?: unknown) {
  const response = await fetch('/api' + path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Ironclad-Intent': 'dashboard' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: response.statusText }));
    throw Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  }
  return response.json();
}

/* ─── Badge Component ─── */
function Badge({ value }: { value: string }) {
  return <span className={'badge ' + value}>{value.replaceAll('_', ' ')}</span>;
}

/* ─── Virtualized Incident Table ─── */
function IncidentTable({ rows, open }: { rows: Run[]; open: (id: string) => void }) {
  const parent = useRef<HTMLDivElement>(null);
  const virtual = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parent.current,
    estimateSize: () => 48,
    overscan: 8,
  });
  const items = virtual.getVirtualItems();

  return (
    <div className="table-wrap" ref={parent} style={{ maxHeight: 440, overflow: 'auto' }}>
      <table>
        <thead style={{ position: 'sticky', top: 0, zIndex: 1 }}>
          <tr>
            <th>INCIDENT</th>
            <th>STATUS</th>
            <th>MODE</th>
            <th>STEPS</th>
            <th>CREATED</th>
            <th scope="col"><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          {items.length > 0 && (
            <tr aria-hidden="true">
              <td colSpan={6} style={{ height: items[0].start, padding: 0, border: 0 }} />
            </tr>
          )}
          {items.map(item => {
            const r = rows[item.index];
            return (
              <tr key={r.id} style={{ height: 48 }}>
                <td>
                  <button className="row-link" onClick={() => open(r.id)}>
                    <span className="incident-id mono">IC-{r.id.slice(0, 6).toUpperCase()}</span>
                    <span>{r.summary}</span>
                  </button>
                </td>
                <td><Badge value={r.status} /></td>
                <td className="mono muted">{r.mode}</td>
                <td className="mono">{r.steps.toString().padStart(2, '0')}</td>
                <td className="mono muted">
                  {r.created_at ? new Date(r.created_at).toLocaleTimeString() : 'Queued'}
                </td>
                <td>
                  <button aria-label={'Open incident ' + r.id} onClick={() => open(r.id)}>
                    <ArrowUpRight size={14} />
                  </button>
                </td>
              </tr>
            );
          })}
          {items.length > 0 && (
            <tr aria-hidden="true">
              <td
                colSpan={6}
                style={{
                  height: virtual.getTotalSize() - items[items.length - 1].end,
                  padding: 0,
                  border: 0,
                }}
              />
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/* ─── Agent Graph (SVG) ─── */
function AgentGraph({ active, visible }: { active: string; visible: Event[] }) {
  return (
    <div className="graph">
      <div className="graph-caption">
        <span className="eyebrow">AGENT TOPOLOGY</span>
        <span className="mono muted" style={{ fontSize: 9 }}>06 NODES / TYPED HANDOFFS</span>
      </div>
      <svg viewBox="0 0 760 280" role="img" aria-label="Agent topology graph">
        <defs>
          <pattern id="dots" width="20" height="20" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.5" fill="#1a1e22" />
          </pattern>
          <linearGradient id="edge-active" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#e9a23b" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#e9a23b" stopOpacity="0.2" />
          </linearGradient>
          <linearGradient id="edge-idle" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#2a2e34" />
            <stop offset="100%" stopColor="#1e2126" />
          </linearGradient>
        </defs>
        <rect width="760" height="280" fill="url(#dots)" />

        {roles.map((r, i) => {
          const x = 80 + i * 150;
          const isActive = active === r;
          return (
            <g key={r}>
              <path
                d={`M380 105 Q${x} 105 ${x} 190`}
                fill="none"
                stroke={isActive ? 'url(#edge-active)' : 'url(#edge-idle)'}
                strokeWidth={isActive ? '1.5' : '1'}
                strokeDasharray={isActive ? 'none' : '4 4'}
              />
              <rect
                x={x - 60} y="188" width="120" height="56" rx="10"
                fill={isActive ? '#181610' : '#12151a'}
                stroke={isActive ? '#e9a23b' : '#2a2e34'}
                strokeWidth={isActive ? '1.5' : '1'}
              />
              {isActive && (
                <rect
                  x={x - 60} y="188" width="120" height="1" rx="0.5"
                  fill="#e9a23b" opacity="0.3"
                />
              )}
              <circle
                cx={x - 42} cy="210" r="3.5"
                fill={isActive ? '#e9a23b' : '#4a5158'}
              />
              {isActive && (
                <circle cx={x - 42} cy="210" r="6" fill="none" stroke="#e9a23b" strokeWidth="0.5" opacity="0.4">
                  <animate attributeName="r" values="4;8;4" dur="2s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.4;0;0.4" dur="2s" repeatCount="indefinite" />
                </circle>
              )}
              <text
                x={x - 30} y="214" fill={isActive ? '#edeef0' : '#8a939d'}
                fontSize="10" fontFamily="'JetBrains Mono', monospace" fontWeight="500"
              >
                {r.toUpperCase()}
              </text>
              <text
                x={x - 42} y="232" fill="#666d75"
                fontSize="9" fontFamily="'JetBrains Mono', monospace"
              >
                {visible.filter(e => e.agent === r).length} events
              </text>
            </g>
          );
        })}

        {/* Supervisor node */}
        <rect x="298" y="46" width="164" height="62" rx="12" fill="#1a1812" stroke="#5a4a28" strokeWidth="1.2" />
        <rect x="298" y="46" width="164" height="1" rx="0.5" fill="#e9a23b" opacity="0.2" />
        <text x="380" y="73" textAnchor="middle" fill="#e9a23b" fontSize="11" fontFamily="'JetBrains Mono', monospace" fontWeight="600">
          SUPERVISOR
        </text>
        <text x="380" y="92" textAnchor="middle" fill="#8a8474" fontSize="9.5" fontFamily="'JetBrains Mono', monospace">
          scope · budget · recovery
        </text>
      </svg>
      <div className="graph-footer">
        <span><i className="dot amber" /> Event-driven orchestration</span>
        <span>MAX 3 REPAIR ATTEMPTS</span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Dashboard — Main Component
   ═══════════════════════════════════════════════════════════════ */
export default function Dashboard() {
  const [playing, setPlaying] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const [token, setToken] = useState('');
  const [tab, setTab] = useState('Overview');
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState('');
  const [events, setEvents] = useState<Event[]>([]);
  const [mode, setMode] = useState('demo');
  const [health, setHealth] = useState<Record<string, unknown>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState('');
  const [query, setQuery] = useState('average');
  const [citations, setCitations] = useState<Citation[]>([]);
  const [settings, setSettings] = useState<Record<string, number>>({});
  const [replay, setReplay] = useState(999);
  const [palette, setPalette] = useState(false);
  const [compose, setCompose] = useState(false);
  const [log, setLog] = useState('ZeroDivisionError: division by zero in average');
  const [confirmed, setConfirmed] = useState(false);

  /* ─── Replay timer ─── */
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      setReplay(n => {
        if (n >= events.length) { setPlaying(false); return n; }
        return n + 1;
      });
    }, 700);
    return () => clearInterval(timer);
  }, [playing, events.length]);

  /* ─── Focus trap for dialogs ─── */
  useEffect(() => {
    if (!palette && !compose) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector('[role="dialog"]');
    const focusable = () =>
      Array.from(dialog?.querySelectorAll<HTMLElement>('button:not(:disabled),input,textarea,[tabindex="0"]') || []);
    focusable()[0]?.focus();

    const trap = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const nodes = focusable();
      const first = nodes[0], last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', trap);
    return () => { document.removeEventListener('keydown', trap); previous?.focus(); };
  }, [palette, compose]);

  const notify = (e: unknown) => setError(e instanceof Error ? e.message : String(e));

  /* ─── Polling ─── */
  const refresh = useCallback(async () => {
    try {
      const [r, h] = await Promise.all([api('/runs'), api('/health')]);
      setRuns(old => [...r, ...old.filter(item => !r.some((n: Run) => n.id === item.id))]);
      setHealth(h);
      setAuthorized(true);
    } catch (e) {
      if ((e as Error).message === 'Sign in required') setAuthorized(false);
      else notify(e);
    }
  }, []);

  useEffect(() => { refresh(); const id = setInterval(refresh, 3000); return () => clearInterval(id); }, [refresh]);

  /* ─── Keyboard shortcuts ─── */
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); setPalette(p => !p); }
      if (e.key === 'Escape') { setPalette(false); setCompose(false); }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, []);

  /* ─── WebSocket for live events ─── */
  useEffect(() => {
    if (!selected || !authorized) return;
    let stopped = false;
    let socket: WebSocket;
    let timer: ReturnType<typeof setTimeout>;
    let cursor = 0;
    setEvents([]);
    setReplay(999);
    setConfirmed(false);

    const connect = () => {
      socket = new WebSocket(
        `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/runs/${selected}/stream?after=${cursor}`
      );
      socket.onmessage = e => {
        const data = JSON.parse(e.data);
        if (data.heartbeat) return;
        cursor = Math.max(cursor, data.seq);
        setEvents(old => old.some(v => v.seq === data.seq) ? old : [...old, data].sort((a, b) => a.seq - b.seq));
      };
      socket.onclose = () => { if (!stopped) timer = setTimeout(connect, 1500); };
    };
    api('/runs/' + selected).then(d => setMode(d.mode)).catch(notify);
    connect();
    return () => { stopped = true; clearTimeout(timer); socket?.close(); };
  }, [selected, authorized]);

  /* ─── Tab data loading ─── */
  useEffect(() => {
    if (tab === 'Settings') api('/settings').then(setSettings).catch(notify);
    if (tab === 'Knowledge') api('/knowledge?q=' + encodeURIComponent(query)).then(d => setCitations(d.results)).catch(notify);
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError('');
    try { await fn(); } catch (e) { notify(e); } finally { setBusy(false); }
  }

  const open = (id: string, destination = 'Incident') => { setSelected(id); setTab(destination); };

  async function demo() {
    await action(async () => {
      const r = await api('/demo', 'POST');
      await refresh();
      open(r.id);
    });
  }

  /* ─── Derived state ─── */
  const visible = events.filter(e => e.seq <= replay);
  const last = visible.at(-1);
  const proposal = [...visible].reverse().find(e => e.kind === 'proposal');
  const diagnosis = [...visible].reverse().find(e => e.kind === 'diagnosis');
  const active = last?.agent || 'supervisor';
  const count = (status: string) => runs.filter(r => r.status === status).length;
  const completed = count('report') + count('pull_request');
  const escalations = count('escalated');

  /* ═══════════════════════════════════════════════════════════
     LOGIN SCREEN
     ═══════════════════════════════════════════════════════════ */
  if (!authorized) {
    return (
      <main className="login">
        <div className="login-card">
          <Shield size={28} color="#e9a23b" />
          <p className="eyebrow">AUTONOMOUS CODE GUARDIAN</p>
          <h1>IRONCLAD<span className="amber-text">.</span></h1>
          <p className="muted">Your codebase. Under watch.</p>
          <form onSubmit={e => {
            e.preventDefault();
            action(async () => { await api('/login', 'POST', { token }); setToken(''); await refresh(); });
          }}>
            <label htmlFor="access">Installation access token</label>
            <input
              id="access"
              type="password"
              autoComplete="current-password"
              value={token}
              onChange={e => setToken(e.target.value)}
              placeholder="Enter your IRONCLAD_ADMIN_TOKEN"
              required
            />
            <button className="primary" disabled={busy}>
              Enter mission control <ArrowUpRight size={15} />
            </button>
          </form>
          {error && <p role="alert" className="error">{error}</p>}
          <small className="muted">Use IRONCLAD_ADMIN_TOKEN from your installation.</small>
        </div>
      </main>
    );
  }

  /* ═══════════════════════════════════════════════════════════
     MAIN DASHBOARD
     ═══════════════════════════════════════════════════════════ */
  return (
    <div className="shell">
      {/* ─── Sidebar ─── */}
      <aside>
        <div className="brand">
          <Shield size={22} />
          <div>
            IRONCLAD
            <span>CODE GUARDIAN / V1</span>
          </div>
        </div>

        <div className="workspace">
          <span className="repo-icon">IC</span>
          <div>
            {String(health.repository || 'repository')}
            <small>Single-repository workspace</small>
          </div>
          <ChevronRight size={14} />
        </div>

        <p className="nav-label">WORKSPACE</p>

        <nav>
          {tabs.map((name, i) => {
            const Icon = tabIcons[i];
            return (
              <button
                key={name}
                className={tab === name || (name === 'Incidents' && tab === 'Incident') ? 'selected' : ''}
                onClick={() => {
                  setTab(name);
                  if (name === 'Replay' && !selected && runs[0]) setSelected(runs[0].id);
                }}
              >
                <Icon size={17} />
                {name}
                {name === 'Incidents' && <span className="nav-count">{runs.length}</span>}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-bottom">
          <div className="mini-health">
            <i className="dot green" /> API operational
            <span className="mono">{String(health.version || '')}</span>
          </div>
          <button onClick={() => setPalette(true)}>
            <Command size={15} /> Quick navigation <kbd>⌘K</kbd>
          </button>
          <button onClick={() => action(async () => { await api('/logout', 'POST'); setAuthorized(false); })}>
            <LogOut size={15} /> Sign out
          </button>
        </div>
      </aside>

      {/* ─── Content ─── */}
      <div className="content">
        <header>
          <span className="crumb">
            Workspace <ChevronRight size={12} /> <strong>{tab}</strong>
          </span>
          <div className="header-right">
            <span className="mono muted">
              {health.docker ? 'SANDBOX READY' : 'DOCKER REQUIRED'}
            </span>
            <span className="live"><i className="dot green" /> LIVE</span>
          </div>
        </header>

        <main>
          {/* Page heading */}
          <div className="page-heading">
            <div>
              <p className="eyebrow">IRONCLAD / MISSION CONTROL</p>
              <h1>
                {tab === 'Overview' ? 'Your code. Under watch.' :
                 tab === 'Incident' ? 'Incident workspace' : tab}
              </h1>
              <p className="muted">
                {tab === 'Overview'
                  ? 'A clear view of every failure, decision, and repair.'
                  : tab === 'Knowledge'
                  ? 'Inspect the evidence behind every diagnosis.'
                  : 'Every action recorded. Every decision reviewable.'}
              </p>
            </div>
            <div className="actions">
              <button onClick={demo} disabled={busy}>
                <Play size={14} /> Explore demo
              </button>
              <button className="primary" onClick={() => setCompose(true)}>
                <Zap size={14} /> New incident
              </button>
            </div>
          </div>

          {error && (
            <div className="alert" role="alert">
              <AlertTriangle size={15} />
              {error}
              <button aria-label="Dismiss error" onClick={() => setError('')}><X size={14} /></button>
            </div>
          )}

          {/* ═══ OVERVIEW TAB ═══ */}
          {tab === 'Overview' && (
            <>
              <div className="metrics">
                {([
                  ['INCIDENTS', runs.length, 'Recorded across this installation', Activity],
                  ['REPAIRS READY', completed, 'Reports available for review', Check],
                  ['ESCALATED', escalations, 'Human investigation needed', AlertTriangle],
                  ['RESERVED COST', '$' + runs.reduce((n, r) => n + r.reserved_usd, 0).toFixed(3), 'Conservative model reservations', Cpu],
                ] as const).map(([label, value, note, Icon]) => (
                  <section key={label} className="metric">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span className="eyebrow">{label}</span>
                      <Icon size={14} color="#4a5158" />
                    </div>
                    <strong className="mono">{value}</strong>
                    <small>{note}</small>
                  </section>
                ))}
              </div>

              <div className="overview-grid">
                <AgentGraph active={active} visible={visible} />
                <section className="panel fleet-health">
                  <div className="panel-title">
                    Fleet health <Badge value={Number(health.workers) > 0 ? 'operational' : 'idle'} />
                  </div>
                  {roles.map(role => (
                    <div className="agent-row" key={role}>
                      <span className="node-icon"><Workflow size={15} /></span>
                      <div>
                        {role}
                        <small>{roleDescriptions[role]}</small>
                      </div>
                      <i className={'dot ' + (Number(health.workers) > 0 && active === role ? 'amber' : 'grey')} />
                    </div>
                  ))}
                </section>
              </div>
            </>
          )}

          {/* ═══ INCIDENTS TAB ═══ */}
          {(tab === 'Overview' || tab === 'Incidents') && (
            <section className="panel incidents">
              <div className="panel-title">
                <span>
                  Incident feed <span className="muted mono" style={{ marginLeft: 6 }}>/ {runs.length}</span>
                </span>
                <div className="search">
                  <Search size={14} />
                  <input
                    aria-label="Filter incidents"
                    placeholder="Filter incidents…"
                    value={filter}
                    onChange={e => setFilter(e.target.value)}
                  />
                </div>
              </div>
              <IncidentTable
                rows={runs.filter(r =>
                  (r.summary + r.id + r.status).toLowerCase().includes(filter.toLowerCase())
                )}
                open={open}
              />
              {!runs.length && (
                <div className="empty">
                  <Radio size={28} />
                  <h3>Standing by for the first signal.</h3>
                  <p>Submit a failure log, or explore a clearly labelled simulation.</p>
                  <button onClick={demo}><Play size={14} /> Explore demo</button>
                </div>
              )}
              <div className="padded" style={{ textAlign: 'center' }}>
                <button
                  disabled={busy}
                  onClick={() => action(async () => {
                    const older: Run[] = await api('/runs?limit=200&offset=' + runs.length);
                    setRuns(old => [...old, ...older.filter(row => !old.some(item => item.id === row.id))]);
                    if (!older.length) setError('All recorded incidents are loaded.');
                  })}
                >
                  Load older incidents
                </button>
              </div>
            </section>
          )}

          {/* ═══ INCIDENT / REPLAY / PR REVIEW ═══ */}
          {(tab === 'Incident' || tab === 'Replay' || tab === 'PR review') && (
            <>
              {!selected ? (
                <div className="empty">
                  <Eye size={28} />
                  <h3>No incident selected</h3>
                  <p>Select an incident from the feed to inspect its run.</p>
                  <button onClick={() => setTab('Incidents')}>View incidents</button>
                </div>
              ) : (
                <>
                  <div className="detail-meta">
                    <button onClick={() => setTab('Incidents')}>
                      <ArrowLeft size={14} /> Incidents
                    </button>
                    <span className="mono" style={{ fontSize: 11 }}>
                      IC-{selected.slice(0, 8).toUpperCase()}
                    </span>
                    <Badge value={last?.kind || 'queued'} />
                    {mode === 'simulation' && <Badge value="simulation" />}
                  </div>

                  {/* Replay controls */}
                  {tab === 'Replay' && (
                    <section className="panel replay">
                      <div className="panel-title">
                        <span>Event replay</span>
                        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                          <button onClick={() => { setReplay(0); setPlaying(true); }}>
                            <Play size={12} /> Play
                          </button>
                          <span className="mono muted" style={{ fontSize: 10 }}>
                            {Math.min(replay, events.length)} / {events.length}
                          </span>
                        </div>
                      </div>
                      <input
                        aria-label="Replay event position"
                        type="range"
                        min="0"
                        max={events.length}
                        value={Math.min(replay, events.length)}
                        onChange={e => setReplay(+e.target.value)}
                      />
                      <p className="muted" style={{ fontSize: 11 }}>
                        Scrub through persisted events. Replay performs no model calls or code execution.
                      </p>
                    </section>
                  )}

                  {tab === 'Replay' && <AgentGraph active={active} visible={visible} />}

                  <div className="detail-grid">
                    {/* Execution trace */}
                    <section className="panel">
                      <div className="panel-title">
                        Execution trace
                        <span className="mono muted" style={{ fontSize: 10 }}>{visible.length} EVENTS</span>
                      </div>
                      <div className="trace">
                        {visible.map(e => (
                          <details key={e.seq} open={e.seq === last?.seq}>
                            <summary>
                              <span className="sequence mono">{String(e.seq).padStart(2, '0')}</span>
                              <span className={'trace-dot ' + e.kind} />
                              <span>
                                <strong>{e.agent}</strong>
                                <small>{e.kind}</small>
                              </span>
                              <span
                                className="waterfall"
                                style={{
                                  width: Math.max(12, Math.min(140,
                                    e.duration_ms / Math.max(1, ...visible.map(s => s.duration_ms)) * 140
                                  )),
                                }}
                              />
                              <span className="mono muted">{e.duration_ms}ms</span>
                            </summary>
                            <pre>{JSON.stringify(e.payload, null, 2)}</pre>
                          </details>
                        ))}
                      </div>
                      {!visible.length && (
                        <div className="empty">
                          <Cpu size={20} />
                          <p>Waiting for the worker to process this incident.</p>
                        </div>
                      )}
                    </section>

                    {/* Right column: Diagnosis + Patch + PR */}
                    <div>
                      {/* Diagnosis */}
                      <section className="panel" style={{ marginBottom: 18 }}>
                        <div className="panel-title">
                          Diagnosis
                          <span className="mono amber-text">
                            {diagnosis ? Math.round(Number(diagnosis.payload.confidence) * 100) + '%' : '—'}
                          </span>
                        </div>
                        <div className="padded">
                          <p style={{ fontSize: 12.5, lineHeight: 1.6 }}>
                            {String(diagnosis?.payload.hypothesis || 'Evidence will appear as the diagnostician completes its step.')}
                          </p>
                          {((diagnosis?.payload.evidence || []) as Citation[]).map((e, i) => (
                            <details key={i}>
                              <summary className="citation mono">{e.path}:{e.start_line}–{e.end_line}</summary>
                              <pre>{e.text}</pre>
                            </details>
                          ))}
                        </div>
                      </section>

                      {/* Proposed patch */}
                      <section className="panel diff" style={{ marginBottom: 18 }}>
                        <div className="panel-title">
                          Proposed patch
                          <span className="mono muted" style={{ fontSize: 9 }}>UNMERGED</span>
                        </div>
                        <div className="diff-lines">
                          {String(proposal?.payload.diff || 'No patch proposed yet.')
                            .split('\n')
                            .map((line, i) => (
                              <div key={i} className={line.startsWith('+') ? 'added' : line.startsWith('-') ? 'removed' : ''}>
                                <span>{i + 1}</span>
                                <code>{line || ' '}</code>
                              </div>
                            ))}
                        </div>
                        <div className="padded">
                          {((proposal?.payload.edits || []) as { path: string; rationale: string }[]).map((edit, i) => (
                            <p className="rationale" key={i}>
                              <span className="mono amber-text">{edit.path}</span><br />
                              {edit.rationale}
                            </p>
                          ))}
                        </div>
                        <p className="diff-note">
                          {String(proposal?.payload.summary || 'Edits remain scoped to cited repository evidence.')}
                        </p>
                      </section>

                      {/* PR approval */}
                      <section className="panel">
                        <div className="panel-title">
                          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Lock size={14} /> Review & draft PR
                          </span>
                        </div>
                        <div className="padded">
                          <p className="muted" style={{ fontSize: 12 }}>
                            Review the diff and verification results before approving. Simulation runs cannot create pull requests.
                          </p>
                          <label className="checkbox">
                            <input
                              type="checkbox"
                              checked={confirmed}
                              disabled={mode === 'simulation'}
                              onChange={e => setConfirmed(e.target.checked)}
                            />
                            I reviewed this patch and its checks.
                          </label>
                          <button
                            className="primary"
                            disabled={!confirmed || busy || mode === 'simulation'}
                            onClick={() => action(async () => {
                              await api('/runs/' + selected + '/approve', 'POST', { confirmed: true });
                              await api('/runs/' + selected + '/publish', 'POST');
                              await refresh();
                            })}
                          >
                            <GitPullRequest size={14} /> Approve & create draft PR
                          </button>
                        </div>
                      </section>
                    </div>
                  </div>
                </>
              )}
            </>
          )}

          {/* ═══ KNOWLEDGE TAB ═══ */}
          {tab === 'Knowledge' && (
            <>
              <section className="panel padded">
                <form
                  className="knowledge-search"
                  onSubmit={e => {
                    e.preventDefault();
                    action(async () => {
                      const d = await api('/knowledge?q=' + encodeURIComponent(query));
                      setCitations(d.results);
                    });
                  }}
                >
                  <Search size={20} />
                  <input
                    aria-label="Search repository knowledge"
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    placeholder="Search by function, class, or concept…"
                  />
                  <button className="primary" disabled={busy}>
                    Retrieve evidence <ArrowUpRight size={14} />
                  </button>
                </form>
                <p className="muted" style={{ marginTop: 12, fontSize: 10 }}>
                  AST-aware Python retrieval · BM25 + optional pgvector · live repository evidence
                </p>
              </section>
              <div className="knowledge-grid">
                {citations.map((c, i) => (
                  <section className="panel" key={i}>
                    <div className="panel-title">
                      <span className="mono" style={{ fontSize: 11 }}>{c.path}:{c.start_line}–{c.end_line}</span>
                      <Badge value="citation" />
                    </div>
                    <pre>{c.text}</pre>
                  </section>
                ))}
              </div>
              {!citations.length && (
                <div className="empty">
                  <Database size={24} />
                  <h3>No eligible evidence</h3>
                  <p>Check the configured repository or refine your query.</p>
                </div>
              )}
            </>
          )}

          {/* ═══ SETTINGS TAB ═══ */}
          {tab === 'Settings' && (
            <div className="settings-grid">
              <section className="panel">
                <div className="panel-title">
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Shield size={14} /> Execution guardrails
                  </span>
                </div>
                <form
                  className="padded settings-form"
                  onSubmit={e => {
                    e.preventDefault();
                    action(async () => {
                      setSettings(await api('/settings', 'PUT', settings));
                      setError('Guardrails saved for new runs.');
                    });
                  }}
                >
                  {Object.entries(settings).map(([key, value]) => (
                    <label key={key}>
                      {key.replaceAll('_', ' ')}
                      <input
                        type="number"
                        min="0"
                        step={key === 'dollar_budget' ? '.01' : '1'}
                        value={value}
                        onChange={e => setSettings({ ...settings, [key]: Number(e.target.value) })}
                      />
                    </label>
                  ))}
                  <button className="primary" disabled={busy}>Save guardrails</button>
                </form>
              </section>

              <section className="panel">
                <div className="panel-title">Installation</div>
                <div className="padded">
                  <p className="eyebrow">REPOSITORY</p>
                  <p className="mono" style={{ fontSize: 12 }}>{String(health.repository)}</p>
                  <hr />
                  <p className="eyebrow">SANDBOX</p>
                  <p style={{ fontSize: 12 }}>
                    {health.docker
                      ? 'Docker executable detected; image still required'
                      : 'Docker required before actual verification'}
                  </p>
                  <hr />
                  <p className="eyebrow">MODEL</p>
                  <p style={{ fontSize: 12 }}>
                    {health.model_configured
                      ? 'Hosted credentials configured'
                      : 'Demo mode available; hosted API key not set'}
                  </p>
                  <hr />
                  <p className="muted" style={{ fontSize: 11, lineHeight: 1.6 }}>
                    Repository, credentials, provider prices, and GitHub scope are configured through environment
                    variables. Denied paths and no-auto-merge policy are enforced server-side.
                  </p>
                </div>
              </section>
            </div>
          )}

          <footer>
            <span><Shield size={12} /> IRONCLAD — AUTONOMOUS CODE GUARDIAN</span>
            <span className="mono">HUMAN REVIEW. ALWAYS.</span>
          </footer>
        </main>
      </div>

      {/* ─── Command Palette ─── */}
      {palette && (
        <div className="overlay" onClick={() => setPalette(false)}>
          <div
            className="dialog"
            role="dialog"
            aria-modal="true"
            aria-label="Quick navigation"
            onClick={e => e.stopPropagation()}
          >
            <div className="panel-title">Jump to workspace <kbd>ESC</kbd></div>
            {tabs.map(t => (
              <button key={t} onClick={() => { setTab(t); setPalette(false); }}>
                <ChevronRight size={14} /> {t}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ─── New Incident Dialog ─── */}
      {compose && (
        <div className="overlay">
          <div className="dialog compose" role="dialog" aria-modal="true" aria-labelledby="new-title">
            <form onSubmit={e => {
              e.preventDefault();
              action(async () => {
                const r = await api('/runs', 'POST', {
                  log,
                  mode: health.model_configured ? 'hosted' : 'demo',
                });
                setCompose(false);
                await refresh();
                open(r.id);
              });
            }}>
              <div className="panel-title">
                <span id="new-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Zap size={14} /> Submit an incident
                </span>
                <button type="button" aria-label="Close" onClick={() => setCompose(false)}>
                  <X size={16} />
                </button>
              </div>
              <div className="padded">
                <label htmlFor="failure">Failure log / stack trace</label>
                <textarea
                  id="failure"
                  value={log}
                  onChange={e => setLog(e.target.value)}
                  maxLength={24000}
                  required
                />
                <p className="muted" style={{ fontSize: 11, lineHeight: 1.6 }}>
                  Queued for the worker. Docker verification is mandatory.
                  Credentials and secrets must be removed before submission.
                </p>
                <button className="primary" disabled={busy}>
                  Queue diagnosis <ArrowUpRight size={14} />
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
