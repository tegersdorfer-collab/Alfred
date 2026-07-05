import { describe, it, expect } from 'vitest';
import { latLonToTile, tileGrid } from './map-tiles';

describe('latLonToTile', () => {
  it('berechnet die bekannte Kachel für Nürnberg bei Zoom 8', () => {
    // Referenzwert: https://tools.geofabrik.de/calc/ für lat=49.4521, lon=11.0767, zoom=8
    const tile = latLonToTile(49.4521, 11.0767, 8);
    expect(tile.x).toBe(135);
    expect(tile.y).toBe(87);
  });

  it('berechnet die Kachel (0,0) für die Nordwest-Ecke der Karte', () => {
    const tile = latLonToTile(85.0, -180, 2);
    expect(tile.x).toBe(0);
    expect(tile.y).toBe(0);
  });

  it('skaliert korrekt mit dem Zoom-Level (mehr Kacheln bei höherem Zoom)', () => {
    const low = latLonToTile(49.4521, 11.0767, 4);
    const high = latLonToTile(49.4521, 11.0767, 8);
    expect(high.x).toBeGreaterThan(low.x);
  });
});

describe('tileGrid', () => {
  it('erzeugt ein 3x3-Raster bei radius=1', () => {
    const grid = tileGrid(10, 10, 1);
    expect(grid.length).toBe(9);
    expect(grid).toContainEqual({ x: 9, y: 9 });
    expect(grid).toContainEqual({ x: 10, y: 10 });
    expect(grid).toContainEqual({ x: 11, y: 11 });
  });

  it('erzeugt genau eine Kachel bei radius=0', () => {
    const grid = tileGrid(5, 5, 0);
    expect(grid).toEqual([{ x: 5, y: 5 }]);
  });

  it('ist in row-major Reihenfolge (y äußere, x innere Schleife)', () => {
    const grid = tileGrid(0, 0, 1);
    expect(grid[0]).toEqual({ x: -1, y: -1 });
    expect(grid[1]).toEqual({ x: 0, y: -1 });
    expect(grid[2]).toEqual({ x: 1, y: -1 });
    expect(grid[3]).toEqual({ x: -1, y: 0 });
  });
});
