export type IconName =
  | 'sleep'
  | 'training'
  | 'tasks'
  | 'calendar'
  | 'habit'
  | 'nutrition'
  | 'system'
  | 'brain'
  | 'skills'
  | 'weather-sun'
  | 'weather-rain'
  | 'weather-cloud'
  | 'weather-snow'
  | 'chat'
  | 'warning'
  | 'error';

const PATHS: Record<IconName, string> = {
  sleep: '<path d="M10 2a6 6 0 1 0 4 10.5A6.5 6.5 0 0 1 10 2z" />',
  training: '<path d="M2 8h2M12 8h2M4 5v6M12 5v6M4 8h8" />',
  tasks: '<path d="M3 4h10M3 8h10M3 12h6" /><circle cx="13" cy="12" r="1.4" />',
  calendar: '<rect x="2.5" y="3.5" width="11" height="10" rx="1" /><path d="M2.5 6.5h11M5.5 2v3M10.5 2v3" />',
  habit: '<circle cx="8" cy="8" r="5.5" /><path d="M8 5v3l2 2" />',
  nutrition: '<path d="M8 2v3M5 5c0 4-2 4-2 8a5 5 0 0 0 10 0c0-4-2-4-2-8" />',
  system: '<rect x="3" y="3" width="10" height="10" rx="1" /><path d="M6 6h4v4H6z" /><path d="M8 1v2M8 13v2M1 8h2M13 8h2" />',
  brain: '<path d="M6 3a2.5 2.5 0 0 0-2.5 2.5v.2A2.3 2.3 0 0 0 3 9.8a2.4 2.4 0 0 0 2 2.4A2.4 2.4 0 0 0 7.5 14V5.5A2.5 2.5 0 0 0 6 3z" /><path d="M10 3a2.5 2.5 0 0 1 2.5 2.5v.2A2.3 2.3 0 0 1 13 9.8a2.4 2.4 0 0 1-2 2.4 2.4 2.4 0 0 1-2.5 1.8V5.5A2.5 2.5 0 0 1 10 3z" />',
  skills: '<path d="M9.5 2.5 11 4l-5.5 5.5-2-2z" /><path d="M4 10l-1.5 3.5L6 12" />',
  'weather-sun': '<circle cx="8" cy="8" r="3" /><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.5 3.5l1.4 1.4M11.1 11.1l1.4 1.4M3.5 12.5l1.4-1.4M11.1 4.9l1.4-1.4" />',
  'weather-rain': '<path d="M4.5 8.5a3 3 0 0 1 .5-6 3.8 3.8 0 0 1 7 1.3A2.7 2.7 0 0 1 11.5 9H5z" /><path d="M5 11.5l-1 2M8 11.5l-1 2M11 11.5l-1 2" />',
  'weather-cloud': '<path d="M4.5 11a3 3 0 0 1 .5-6 3.8 3.8 0 0 1 7 1.3A2.7 2.7 0 0 1 11.5 11.5H4.5z" />',
  'weather-snow': '<path d="M4.5 8.5a3 3 0 0 1 .5-6 3.8 3.8 0 0 1 7 1.3A2.7 2.7 0 0 1 11.5 9H5z" /><path d="M5.5 12v2M8 12v2M10.5 12v2" />',
  chat: '<path d="M2.5 3.5h11v7h-6l-2.5 2.5v-2.5h-2.5z" />',
  warning: '<path d="M8 2 14.5 13.5h-13z" /><path d="M8 6.5v3M8 11.2v.1" />',
  error: '<circle cx="8" cy="8" r="5.5" /><path d="M6 6l4 4M10 6l-4 4" />',
};

export function icon(name: IconName): string {
  return `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">${PATHS[name]}</svg>`;
}
