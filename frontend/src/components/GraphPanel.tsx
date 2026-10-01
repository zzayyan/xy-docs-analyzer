import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force';
import { SourcePanel } from './SourcePanel';
import { api, type Citation, type EntityDetail, type GraphEdge, type GraphNode } from '../lib/api';
import { useLang } from '../lib/i18n';

type SimNode = GraphNode & SimulationNodeDatum;
type SimLink = SimulationLinkDatum<SimNode> & { type: string };

// The eight node types app/ingest/kg.py extracts, each on a palette token
const TYPE_COLOR: Record<string, string> = {
  Person: 'var(--xy-blue-600)',
  Organization: 'var(--brand-primary)',
  Location: 'var(--xy-green-500)',
  Concept: 'var(--xy-navy-700)',
  Event: 'var(--xy-teal-500)',
  Product: 'var(--brand-accent)',
  Regulation: 'var(--xy-ink-600)',
  Date: 'var(--xy-grey-500)',
};
const OTHER_COLOR = 'var(--xy-grey-400)';
// Labels for this many of the most mentioned entities; the rest show theirs on hover or selection
const LABELLED = 25;
const MIN_ZOOM = 0.2;
const MAX_ZOOM = 4;
const PRESETTLE_TICKS = 200;

const colorOf = (type: string | null) => (type && TYPE_COLOR[type]) || OTHER_COLOR;
const radiusOf = (n: GraphNode) => 4 + 3 * Math.sqrt(n.mentions);
const labelText = (name: string) => (name.length > 32 ? `${name.slice(0, 30)}…` : name);

/** The zoom and offset that fit these nodes into a w x h viewport, with a margin, never zooming past 1.5x */
function fitTransform(nodes: SimNode[], w: number, h: number) {
  if (nodes.length === 0 || w === 0 || h === 0) return { x: 0, y: 0, k: 1 };
  const xs = nodes.map((n) => n.x ?? 0);
  const ys = nodes.map((n) => n.y ?? 0);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const k = Math.min(1.5, Math.max(MIN_ZOOM, Math.min(w / (maxX - minX + 120), h / (maxY - minY + 120))));
  return { k, x: -((minX + maxX) / 2) * k, y: -((minY + maxY) / 2) * k };
}

const endKey = (end: SimLink['source']) => (typeof end === 'object' ? (end as SimNode).key : String(end));

/** The document's knowledge graph, drawn as a force layout: its most mentioned entities first, and any
 * entity's neighbours pulled in when it is selected, so the graph can be explored past the first cut.
 * Selecting an entity lists its relations and the passages that mention it; a passage opens in the same
 * SourcePanel a chat citation does, page highlight included. */
export function GraphPanel({ docId }: { docId: string }) {
  const { t } = useLang();
  const graphQuery = useQuery({ queryKey: ['graph', docId], queryFn: () => api.graph(docId) });
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  // Entities and relations pulled in from selected entities' neighbourhoods, on top of the first cut;
  // anchor is the entity they came from, so they appear next to it rather than at the origin
  const [extra, setExtra] = useState<{ nodes: GraphNode[]; edges: GraphEdge[]; anchor: string | null }>({
    nodes: [],
    edges: [],
    anchor: null,
  });
  const detailQuery = useQuery({
    queryKey: ['entity', docId, selectedKey],
    queryFn: async () => {
      const detail = await api.entity(docId, selectedKey as string);
      setExtra((current) => ({
        nodes: [...current.nodes, detail.entity, ...detail.nodes],
        edges: [...current.edges, ...detail.edges],
        anchor: detail.entity.key,
      }));
      return detail;
    },
    enabled: selectedKey !== null,
  });
  const [citation, setCitation] = useState<Citation | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');
  // Viewport, declared ahead of the layout effect that frames the first layout in it
  const svgRef = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });

  // ---- Layout ----
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null);
  // The simulation mutates its node objects in place; each tick copies them into state, which is what
  // render reads. nodesRef is the same nodes by key, for effects and event handlers.
  const nodesRef = useRef(new Map<string, SimNode>());
  const linksRef = useRef<SimLink[]>([]);
  const [frame, setFrame] = useState<{ nodes: SimNode[]; links: SimLink[] }>({ nodes: [], links: [] });

  useEffect(() => {
    const base = graphQuery.data;
    if (!base) return;
    const known = nodesRef.current;
    const anchor = extra.anchor ? known.get(extra.anchor) : undefined;
    const nodes = new Map<string, SimNode>();
    for (const n of [...base.nodes, ...extra.nodes]) {
      if (nodes.has(n.key)) continue;
      // New entities appear next to the one whose neighbourhood brought them in, not at the origin
      nodes.set(n.key, known.get(n.key) ?? { ...n, x: (anchor?.x ?? 0) + Math.random() * 40 - 20, y: (anchor?.y ?? 0) + Math.random() * 40 - 20 });
    }
    const seen = new Set<string>();
    const nextLinks: SimLink[] = [];
    for (const e of [...base.edges, ...extra.edges]) {
      const id = `${e.source}|${e.type}|${e.target}`;
      if (seen.has(id) || e.source === e.target || !nodes.has(e.source) || !nodes.has(e.target)) continue;
      seen.add(id);
      nextLinks.push({ source: e.source, target: e.target, type: e.type });
    }
    nodesRef.current = nodes;
    linksRef.current = nextLinks;

    const first = simRef.current === null;
    const sim =
      simRef.current ??
      forceSimulation<SimNode, SimLink>().on('tick', () => setFrame({ nodes: sim.nodes().slice(), links: linksRef.current.slice() }));
    sim
      .nodes([...nodes.values()])
      .force('link', forceLink<SimNode, SimLink>(nextLinks).id((d) => d.key).distance(70).strength(0.25))
      .force('charge', forceManyBody().strength(-140))
      .force('center', forceCenter(0, 0))
      .force('collide', forceCollide<SimNode>().radius((d) => radiusOf(d) + 3))
      // A gentle pull to the middle: without it, entities with no relation drift far out and the view
      // fitted around them leaves the connected graph tiny
      .force('x', forceX(0).strength(0.08))
      .force('y', forceY(0).strength(0.08));
    if (first) {
      // Most of the first layout runs here, off-screen: rendering every tick of it redraws a few hundred
      // SVG elements per frame for seconds. What is left still animates, so the graph visibly settles.
      sim.stop().alpha(1).tick(PRESETTLE_TICKS);
      sim.alpha(0.3).restart();
      // Opens framed on the whole graph rather than at 1x, where much of it sat off-screen
      requestAnimationFrame(() => {
        const el = svgRef.current;
        if (el) setView(fitTransform(sim.nodes(), el.clientWidth, el.clientHeight));
      });
    } else {
      sim.alpha(0.5).restart();
    }
    simRef.current = sim;
  }, [graphQuery.data, extra]);

  useEffect(() => () => void simRef.current?.stop(), []);

  // ---- Viewport: pan, zoom, drag ----
  const [panning, setPanning] = useState(false);
  const drag = useRef<{ kind: 'pan' | 'node'; key?: string; startX: number; startY: number; moved: boolean; vx: number; vy: number } | null>(null);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setSize({ w: entry.contentRect.width, h: entry.contentRect.height }));
    observer.observe(el);
    return () => observer.disconnect();
  }, [graphQuery.data]);

  const toGraph = (clientX: number, clientY: number) => {
    const rect = svgRef.current!.getBoundingClientRect();
    return { x: (clientX - rect.left - size.w / 2 - view.x) / view.k, y: (clientY - rect.top - size.h / 2 - view.y) / view.k };
  };

  const onPointerDown = (e: ReactPointerEvent, key?: string) => {
    e.stopPropagation();
    (e.target as Element).setPointerCapture?.(e.pointerId);
    drag.current = { kind: key ? 'node' : 'pan', key, startX: e.clientX, startY: e.clientY, moved: false, vx: view.x, vy: view.y };
    setPanning(!key);
  };

  const onPointerMove = (e: ReactPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    if (Math.abs(e.clientX - d.startX) + Math.abs(e.clientY - d.startY) > 3) d.moved = true;
    if (d.kind === 'pan') {
      setView((v) => ({ ...v, x: d.vx + e.clientX - d.startX, y: d.vy + e.clientY - d.startY }));
    } else if (d.moved && d.key) {
      const node = nodesRef.current.get(d.key);
      if (!node) return;
      const p = toGraph(e.clientX, e.clientY);
      node.fx = p.x;
      node.fy = p.y;
      simRef.current?.alphaTarget(0.3).restart();
    }
  };

  const onPointerUp = () => {
    const d = drag.current;
    drag.current = null;
    setPanning(false);
    if (!d) return;
    if (d.kind === 'node' && d.key) {
      const node = nodesRef.current.get(d.key);
      if (node) {
        node.fx = null;
        node.fy = null;
      }
      simRef.current?.alphaTarget(0);
      if (!d.moved) select(d.key);
    } else if (!d.moved) {
      select(null);
    }
  };

  const onWheel = (e: React.WheelEvent) => {
    const rect = svgRef.current!.getBoundingClientRect();
    const k = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, view.k * Math.exp(-e.deltaY * 0.0015)));
    // Zoom around the cursor: the graph point under it stays under it
    const cx = e.clientX - rect.left - size.w / 2;
    const cy = e.clientY - rect.top - size.h / 2;
    setView({ k, x: cx - ((cx - view.x) * k) / view.k, y: cy - ((cy - view.y) * k) / view.k });
  };

  const select = (key: string | null) => {
    setSelectedKey(key);
    setCitation(null);
  };

  const centerOn = (key: string) => {
    const node = nodesRef.current.get(key);
    if (node) setView((v) => ({ ...v, x: -(node.x ?? 0) * v.k, y: -(node.y ?? 0) * v.k }));
    select(key);
  };

  // ---- What is drawn ----
  const nodes = frame.nodes.filter((n) => !hiddenTypes.has(n.type ?? ''));
  const visible = new Set(nodes.map((n) => n.key));
  const shownLinks = frame.links.filter((l) => visible.has(endKey(l.source)) && visible.has(endKey(l.target)));
  // A few hundred nodes at most, so these are recomputed every frame rather than memoised
  const neighbours = new Set<string>();
  for (const l of selectedKey ? frame.links : []) {
    if (endKey(l.source) === selectedKey) neighbours.add(endKey(l.target));
    if (endKey(l.target) === selectedKey) neighbours.add(endKey(l.source));
  }
  const all = frame.nodes;
  const labelled = new Set([...all].sort((a, b) => b.mentions - a.mentions).slice(0, LABELLED).map((n) => n.key));
  // Labels are placed most important first and skipped where they would overlap one already placed;
  // the selected and hovered entities always get theirs. Boxes are in graph units, as the labels are.
  const rank = (n: SimNode) =>
    n.key === selectedKey || n.key === hovered ? 3 : neighbours.has(n.key) ? 2 : labelled.has(n.key) ? 1 : 0;
  const placed: [number, number, number, number][] = [];
  const shownLabels = new Set<string>();
  for (const n of nodes.filter((n) => rank(n) > 0).sort((a, b) => rank(b) - rank(a) || b.mentions - a.mentions)) {
    const w = (labelText(n.name).length * 6.2) / view.k;
    const top = (n.y ?? 0) + radiusOf(n);
    const box: [number, number, number, number] = [(n.x ?? 0) - w / 2, top, (n.x ?? 0) + w / 2, top + 14 / view.k];
    const clear = placed.every(([l, t2, r, b]) => box[2] < l || box[0] > r || box[3] < t2 || box[1] > b);
    if (clear || rank(n) === 3) {
      placed.push(box);
      shownLabels.add(n.key);
    }
  }
  const counts = new Map<string, number>();
  for (const n of all) counts.set(n.type ?? '', (counts.get(n.type ?? '') ?? 0) + 1);
  const typeCounts = [...counts.entries()].sort((a, b) => b[1] - a[1]);

  const dim = (key: string) => selectedKey !== null && key !== selectedKey && !neighbours.has(key);

  if (graphQuery.isPending) return null;
  if (!graphQuery.data || graphQuery.data.nodes.length === 0) {
    return <p style={{ margin: 0, padding: 'var(--space-6)', color: 'var(--text-muted)' }}>{t.graphEmpty}</p>;
  }

  const findFirst = () => {
    const q = search.trim().toLowerCase();
    if (!q) return;
    const hit = nodes.filter((n) => n.name.toLowerCase().includes(q)).sort((a, b) => b.mentions - a.mentions)[0];
    if (hit) centerOn(hit.key);
  };

  return (
    <div className="chat-layout" data-sources={selectedKey !== null}>
      <div style={{ position: 'relative', minHeight: 0, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, padding: '10px 16px', borderBottom: 'var(--stroke-hairline) solid var(--border-subtle)' }}>
          <input
            className="field"
            style={{ width: 200 }}
            value={search}
            placeholder={t.graphSearch}
            aria-label={t.graphSearch}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && findFirst()}
          />
          {typeCounts.map(([type, count]) => (
            <button
              key={type}
              className="chip"
              aria-pressed={!hiddenTypes.has(type)}
              onClick={() =>
                setHiddenTypes((current) => {
                  const next = new Set(current);
                  if (next.has(type)) next.delete(type);
                  else next.add(type);
                  return next;
                })
              }
              style={{ opacity: hiddenTypes.has(type) ? 0.5 : 1 }}
            >
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: colorOf(type || null), flex: '0 0 auto' }} />
              {t.graphTypes[type] ?? (type || '?')} <span style={{ color: 'var(--text-muted)' }}>{count}</span>
            </button>
          ))}
          <span style={{ marginLeft: 'auto', fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>
            {t.graphShowing(frame.nodes.length, Math.max(graphQuery.data.total, frame.nodes.length))}
          </span>
          <button className="quiet-button" onClick={() => setView(fitTransform(nodes, size.w, size.h))}>
            {t.graphFit}
          </button>
        </div>

        <svg
          ref={svgRef}
          style={{ flex: 1, minHeight: 0, width: '100%', cursor: panning ? 'grabbing' : 'grab', touchAction: 'none', background: 'var(--surface-page)' }}
          onPointerDown={(e) => onPointerDown(e)}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
          onWheel={onWheel}
        >
          <g transform={`translate(${size.w / 2 + view.x},${size.h / 2 + view.y}) scale(${view.k})`}>
            {shownLinks.map((l) => {
              const s = l.source as SimNode;
              const d = l.target as SimNode;
              const lit = selectedKey !== null && (s.key === selectedKey || d.key === selectedKey);
              return (
                <line
                  key={`${s.key}|${l.type}|${d.key}`}
                  x1={s.x}
                  y1={s.y}
                  x2={d.x}
                  y2={d.y}
                  stroke={lit ? 'var(--brand-primary)' : 'var(--border-strong)'}
                  strokeOpacity={selectedKey === null ? 0.5 : lit ? 0.9 : 0.12}
                  strokeWidth={(lit ? 1.6 : 1) / Math.sqrt(view.k)}
                />
              );
            })}
            {nodes.map((n) => {
              const r = radiusOf(n);
              return (
                <g
                  key={n.key}
                  transform={`translate(${n.x ?? 0},${n.y ?? 0})`}
                  style={{ cursor: 'pointer', opacity: dim(n.key) ? 0.15 : 1, transition: 'opacity var(--dur-fast) var(--ease-standard)' }}
                  onPointerDown={(e) => onPointerDown(e, n.key)}
                  onPointerEnter={() => setHovered(n.key)}
                  onPointerLeave={() => setHovered((h) => (h === n.key ? null : h))}
                >
                  <circle
                    r={r}
                    fill={colorOf(n.type)}
                    stroke={n.key === selectedKey ? 'var(--text-title)' : 'var(--surface-card)'}
                    strokeWidth={n.key === selectedKey ? 2.5 : 1.5}
                  />
                </g>
              );
            })}
            {/* Labels in their own layer over every node, so a node drawn later never covers one */}
            {nodes
              .filter((n) => shownLabels.has(n.key))
              .map((n) => (
                <text
                  key={n.key}
                  x={n.x ?? 0}
                  y={(n.y ?? 0) + radiusOf(n) + 11 / view.k}
                  textAnchor="middle"
                  style={{
                    fontSize: 11 / view.k,
                    fill: 'var(--text-title)',
                    opacity: dim(n.key) ? 0.15 : 1,
                    paintOrder: 'stroke',
                    stroke: 'var(--surface-page)',
                    strokeWidth: 3 / view.k,
                    pointerEvents: 'none',
                  }}
                >
                  {labelText(n.name)}
                </text>
              ))}
          </g>
        </svg>

        <span style={{ position: 'absolute', left: 16, bottom: 10, fontSize: 11, color: 'var(--text-muted)', pointerEvents: 'none' }}>
          {t.graphHint}
        </span>
      </div>

      {selectedKey !== null &&
        (citation ? (
          <SourcePanel docId={docId} citation={citation} citations={detailQuery.data?.citations} onClose={() => setCitation(null)} />
        ) : (
          <EntityPanel
            entityKey={selectedKey}
            detail={detailQuery.data ?? null}
            loading={detailQuery.isPending}
            onSelect={centerOn}
            onCitation={setCitation}
            onClose={() => select(null)}
          />
        ))}
    </div>
  );
}

interface EntityPanelProps {
  entityKey: string;
  detail: EntityDetail | null;
  loading: boolean;
  onSelect: (key: string) => void;
  onCitation: (citation: Citation) => void;
  onClose: () => void;
}

function EntityPanel({ entityKey, detail, loading, onSelect, onCitation, onClose }: EntityPanelProps) {
  const { t } = useLang();
  const entity = detail?.entity;
  const names = new Map((detail?.nodes ?? []).map((n) => [n.key, n]));
  // One line per neighbour, with every relation to it: two models compared eight ways are one neighbour
  const relations = new Map<string, string[]>();
  for (const e of detail?.edges ?? []) {
    const outgoing = e.source === entityKey;
    const other = outgoing ? e.target : e.source;
    relations.set(other, [...(relations.get(other) ?? []), outgoing ? `→ ${e.type}` : `← ${e.type}`]);
  }

  return (
    <aside className="source-panel" key={entityKey}>
      <div style={{ flex: '0 0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: 44, padding: '0 12px 0 20px', borderBottom: 'var(--stroke-hairline) solid var(--border-subtle)' }}>
        <span className="truncate" style={{ fontWeight: 'var(--fw-semibold)', color: 'var(--text-title)' }}>
          {entity?.name ?? entityKey}
        </span>
        <button className="quiet-button" onClick={onClose}>
          {t.citationClose}
        </button>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 20px 24px', display: 'flex', flexDirection: 'column', gap: 18 }}>
        {loading && [80, 60, 70].map((w) => <div key={w} className="skeleton-block" style={{ height: 12, width: `${w}%` }} />)}

        {entity && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: colorOf(entity.type) }} />
            <span>{t.graphTypes[entity.type ?? ''] ?? entity.type}</span>
            <span>·</span>
            <span>{t.graphMentions(entity.mentions)}</span>
          </div>
        )}

        {detail && (
          <section style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <h3 style={{ margin: 0, fontSize: 'var(--fs-ui-xs)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-muted)' }}>{t.graphRelations}</h3>
            {detail.edges.length === 0 && <span style={{ fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>{t.graphNoRelations}</span>}
            {[...relations.entries()].map(([key, types]) => {
              const other = names.get(key);
              if (!other) return null;
              return (
                <button
                  key={key}
                  className="outline-node"
                  style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}
                  onClick={() => onSelect(other.key)}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, maxWidth: '100%' }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: colorOf(other.type), flex: '0 0 auto' }} />
                    <span className="truncate">{other.name}</span>
                  </span>
                  <span style={{ fontSize: 10.5, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', whiteSpace: 'normal', textAlign: 'left' }}>
                    {types.join(' · ')}
                  </span>
                </button>
              );
            })}
          </section>
        )}

        {detail && detail.citations.length > 0 && (
          <section style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <h3 style={{ margin: 0, fontSize: 'var(--fs-ui-xs)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-muted)' }}>{t.graphEvidence}</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {detail.citations.map((c) => (
                <button key={c.chunk_id} className="chip" onClick={() => onCitation(c)} title={c.headings.join(' / ')}>
                  <span style={{ color: 'var(--brand-primary)', fontWeight: 'var(--fw-semibold)' }}>
                    {c.pages.length > 0 ? `p. ${c.pages[0]}` : c.n}
                  </span>
                  {c.headings.length > 0 && <span className="truncate">{c.headings[c.headings.length - 1]}</span>}
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </aside>
  );
}
