import { describe, it, expect } from 'vitest';
import { icon, type IconName } from './icons';

const ALL_NAMES: IconName[] = [
  'sleep', 'training', 'tasks', 'calendar', 'habit', 'nutrition', 'system', 'brain', 'skills',
  'weather-sun', 'weather-rain', 'weather-cloud', 'weather-snow', 'chat', 'warning', 'error',
];

describe('icon', () => {
  it.each(ALL_NAMES)('rendert für "%s" ein gültiges SVG mit currentColor-Stroke', (name) => {
    const markup = icon(name);
    expect(markup).toContain('<svg');
    expect(markup).toContain('stroke="currentColor"');
    expect(markup).toContain('</svg>');
  });

  it('rendert für unterschiedliche Namen unterschiedliches Markup', () => {
    expect(icon('sleep')).not.toBe(icon('training'));
  });
});
