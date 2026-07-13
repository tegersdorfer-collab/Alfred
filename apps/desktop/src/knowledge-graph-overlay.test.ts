import { describe, it, expect } from 'vitest';
import { filterGraph, neighborsOf } from './knowledge-graph-overlay';

const G = {
  nodes: [
    { id: 'note:1', kind: 'note', label: 'Auto', group: 'inbox', color: '#aaa', size: 12 },
    { id: 'entity:5', kind: 'entity', label: 'Timo', group: 'person', color: '#26c6da', size: 14 },
    { id: 'fact:9', kind: 'fact', label: 'Kaffee', group: 'preference', color: '#ffb74d', size: 10 },
  ],
  edges: [
    { from: 'note:1', to: 'entity:5', kind: 'mention' },
    { from: 'fact:9', to: 'entity:5', kind: 'mention' },
  ],
};

describe('filterGraph', () => {
  it('behält nur gewählte Knotenarten und wirft verwaiste Kanten weg', () => {
    const f = filterGraph(G, ['note', 'entity']);
    expect(f.nodes.map((n) => n.id).sort()).toEqual(['entity:5', 'note:1']);
    // fact:9→entity:5-Kante fällt weg (fact gefiltert), mention note:1→entity:5 bleibt.
    expect(f.edges).toEqual([{ from: 'note:1', to: 'entity:5', kind: 'mention' }]);
  });

  it('leere Auswahl = alles', () => {
    expect(filterGraph(G, []).nodes.length).toBe(3);
  });
});

describe('neighborsOf', () => {
  it('liefert ein- und ausgehende Nachbarn', () => {
    const n = neighborsOf('entity:5', G);
    expect(n).toContainEqual({ id: 'note:1', kind: 'mention', dir: 'in' });
    expect(n).toContainEqual({ id: 'fact:9', kind: 'mention', dir: 'in' });
    expect(neighborsOf('note:1', G)).toContainEqual({ id: 'entity:5', kind: 'mention', dir: 'out' });
  });
});
