const icons = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  folder: '<path d="M3 6.5A2.5 2.5 0 0 1 5.5 4h4l2 2H18.5A2.5 2.5 0 0 1 21 8.5v7A2.5 2.5 0 0 1 18.5 18h-13A2.5 2.5 0 0 1 3 15.5Z"/>',
  clipboard: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4.5V3h6v1.5M8 9h8M8 13h8M8 17h5"/>',
  waypoints: '<circle cx="5" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><circle cx="19" cy="5" r="2"/><path d="M7 5h7a5 5 0 0 1 5 5v7M5 7v4a5 5 0 0 0 5 5h7"/>',
  sliders: '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2" fill="currentColor" stroke="none"/><circle cx="15" cy="12" r="2" fill="currentColor" stroke="none"/><circle cx="11" cy="18" r="2" fill="currentColor" stroke="none"/>',
  database: '<ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7"/>',
  bell: '<path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  calendar: '<rect x="3" y="4.5" width="18" height="17" rx="2"/><path d="M16 3v3M8 3v3M3 9h18M8 13h.01M12 13h.01M16 13h.01M8 17h.01M12 17h.01"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  'check-circle': '<circle cx="12" cy="12" r="9"/><path d="m8 12 2.7 2.7L16.5 9"/>',
  triangle: '<path d="m12 4 9 16H3Z"/><path d="M12 10v4M12 17h.01"/>',
  pause: '<rect x="5" y="4" width="14" height="16" rx="3"/><path d="M10 9v6M14 9v6"/>',
  message: '<path d="M20 11.5a7 7 0 0 1-7.2 7H8l-4 2 1.6-4A7.4 7.4 0 0 1 5 12c0-4.2 3.4-7.5 7.7-7.5S20 7.2 20 11.5Z"/><path d="M8 12h.01M12 12h.01M16 12h.01"/>',
  activity: '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
  pull: '<path d="M6 3v18M6 7h8a3 3 0 0 1 3 3v1M18 8l2 3-2 3M6 17h8a3 3 0 0 0 3-3v-1"/>',
  users: '<path d="M16 20v-1.5a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4V20M9.5 10.5A3.5 3.5 0 1 0 9.5 3a3.5 3.5 0 0 0 0 7.5ZM17 11a3 3 0 1 0-1-5.8M21 20v-1.4a4 4 0 0 0-3-3.8"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  sparkle: '<path d="m12 3 1.3 5.7L19 10l-5.7 1.3L12 17l-1.3-5.7L5 10l5.7-1.3ZM19 17l.5 2.5L22 20l-2.5.5L19 23l-.5-2.5L16 20l2.5-.5Z"/>',
  trend: '<path d="M4 17 10 11l4 4 6-7M15 8h5v5"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 15v2"/>',
};

function icon(name, className = '') {
  return `<svg class="icon-svg ${className}" viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.sparkle}</svg>`;
}

document.querySelectorAll('[data-icon]').forEach((element) => {
  element.innerHTML = icon(element.dataset.icon);
});

const projects = [
  {
    id: 'member-portal', name: 'Member Portal', short: 'MP', team: 'Product Experience', repo: 'member-portal', status: 'At risk', statusClass: 'risk', signal: 'PR review queue is aging', signalDetail: '4 PRs · oldest 18 days', lastActivity: 'Yesterday', trend: 'down',
    weeks: [0.8, 0.7, 0.75, 0.6, 0.5, 0.3, 0.2, 0.15], flagFrom: 4,
    seriesBaselines: { openPRs: [1, 4], reviewLatency: [2.1, 5.4], contributors: [5, 2] },
    description: 'Self-service member onboarding and account management.',
    boundary: { rootTeam: 'Product Experience', subteams: ['Member Portal Core', 'Growth'], repos: ['member-portal', 'member-portal-api'], dataOwner: 'Priya N.', effectiveSince: 'Feb 12, 2026', lifecycle: 'Active' },
    contributors: [
      { name: 'Priya N.', commits: 22, additions: 1840, deletions: 410 },
      { name: 'Theo B.', commits: 9, additions: 520, deletions: 180 },
      { name: 'Jordan Kim', commits: 4, additions: 160, deletions: 40 },
      { name: 'Alex R.', commits: 2, additions: 65, deletions: 20 },
    ],
    history: [
      { date: 'Jul 27, 2026', actor: 'Jordan Kim', action: 'Risk confirmed', note: 'Talked to the team — a reviewer left the club mid-cycle. Backfill in progress.' },
      { date: 'Jul 20, 2026', actor: 'Jordan Kim', action: 'Helpful warning', note: 'Caught the review bottleneck a week before it would have blocked the release.' },
    ],
    evidence: [
      { type: 'red', icon: 'pull', title: 'Pull requests aging', metric: 'openPRs', unit: '' },
      { type: 'amber', icon: 'activity', title: 'Activity below baseline', metric: 'activity', unit: 'd' },
      { type: 'blue', icon: 'users', title: 'Concentrated contributors', metric: 'contributors', unit: '' },
    ],
  },
  {
    id: 'campus-events', name: 'Campus Events', short: 'CE', team: 'Community Programs', repo: 'campus-events', status: 'Watch', statusClass: 'watch', signal: 'Review latency is rising', signalDetail: '6.2 days · +2.1 vs baseline', lastActivity: 'Today', trend: 'flat',
    weeks: [0.55, 0.6, 0.5, 0.65, 0.5, 0.45, 0.4, 0.35], flagFrom: 6,
    seriesBaselines: { openPRs: [2, 3], reviewLatency: [4.1, 6.2], contributors: [4, 4] },
    description: 'Event discovery, registration, and volunteer coordination.',
    boundary: { rootTeam: 'Community Programs', subteams: ['Events Ops'], repos: ['campus-events'], dataOwner: 'Marcus T.', effectiveSince: 'Nov 3, 2025', lifecycle: 'Active' },
    contributors: [
      { name: 'Marcus T.', commits: 14, additions: 980, deletions: 310 },
      { name: 'Sam D.', commits: 12, additions: 860, deletions: 275 },
      { name: 'Riya S.', commits: 11, additions: 790, deletions: 240 },
      { name: 'Devon K.', commits: 9, additions: 610, deletions: 190 },
    ],
    history: [
      { date: 'Jul 20, 2026', actor: 'Jordan Kim', action: 'Expected project cycle', note: 'Reviewer bandwidth dips every semester kickoff — consistent with last fall.' },
    ],
    evidence: [
      { type: 'amber', icon: 'pull', title: 'Review latency rising', metric: 'reviewLatency', unit: 'd' },
      { type: 'blue', icon: 'activity', title: 'Activity steady', metric: 'activity', unit: 'd' },
    ],
  },
  {
    id: 'design-system', name: 'Design System', short: 'DS', team: 'Platform Experience', repo: 'design-system', status: 'Watch', statusClass: 'watch', signal: 'Contributor count dipped', signalDetail: '3 → 1 active contributors', lastActivity: '2 days ago', trend: 'down',
    weeks: [0.65, 0.7, 0.68, 0.55, 0.5, 0.4, 0.3, 0.2], flagFrom: 5,
    seriesBaselines: { openPRs: [1, 1], reviewLatency: [1.8, 1.8], contributors: [3, 1] },
    description: 'Shared interface foundations for App Dev products.',
    boundary: { rootTeam: 'Platform Experience', subteams: ['Design Systems Guild'], repos: ['design-system', 'design-tokens'], dataOwner: 'Alex R.', effectiveSince: 'Jan 8, 2026', lifecycle: 'Active' },
    contributors: [
      { name: 'Alex R.', commits: 26, additions: 2100, deletions: 640 },
      { name: 'Priya N.', commits: 3, additions: 140, deletions: 35 },
      { name: 'Theo B.', commits: 2, additions: 90, deletions: 15 },
    ],
    history: [
      { date: 'Jul 13, 2026', actor: 'Jordan Kim', action: 'Not useful', note: 'Contributor dip was a single maintainer on vacation, not a resourcing gap.' },
    ],
    evidence: [
      { type: 'amber', icon: 'users', title: 'Contributor count dipped', metric: 'contributors', unit: '' },
      { type: 'blue', icon: 'pull', title: 'PR flow healthy', metric: 'openPRs', unit: '' },
    ],
  },
  {
    id: 'alumni-network', name: 'Alumni Network', short: 'AN', team: 'Community Programs', repo: 'alumni-network', status: 'Clear', statusClass: 'clear', signal: 'No current concern detected', signalDetail: '12 active days · steady flow', lastActivity: 'Today', trend: 'up', weeks: [0.5, 0.55, 0.6, 0.58, 0.65, 0.7, 0.72, 0.75], flagFrom: 99,
    seriesBaselines: { openPRs: [1, 2], reviewLatency: [1.5, 1.2], contributors: [4, 5] },
    description: 'A lightweight connection hub for alumni and mentors.',
    boundary: { rootTeam: 'Community Programs', subteams: ['Alumni Relations'], repos: ['alumni-network'], dataOwner: 'Marcus T.', effectiveSince: 'Sep 1, 2025', lifecycle: 'Active' },
    contributors: [
      { name: 'Marcus T.', commits: 10, additions: 640, deletions: 180 },
      { name: 'Ana G.', commits: 9, additions: 590, deletions: 160 },
      { name: 'Jamie L.', commits: 8, additions: 510, deletions: 140 },
      { name: 'Riya S.', commits: 7, additions: 450, deletions: 120 },
      { name: 'Devon K.', commits: 6, additions: 380, deletions: 95 },
    ],
    history: [{ date: 'Jul 13, 2026', actor: 'Jordan Kim', action: 'Risk resolved', note: 'Contributor rotation from last month fully backfilled.' }],
    evidence: [],
  },
  {
    id: 'onboarding', name: 'Onboarding Refresh', short: 'OR', team: 'People Operations', repo: 'onboarding-refresh', status: 'Clear', statusClass: 'clear', signal: 'No current concern detected', signalDetail: '9 active days · 3 PRs merged', lastActivity: 'Today', trend: 'up', weeks: [0.4, 0.45, 0.5, 0.55, 0.6, 0.62, 0.68, 0.7], flagFrom: 99,
    seriesBaselines: { openPRs: [1, 1], reviewLatency: [1.1, 0.9], contributors: [2, 3] },
    description: 'The first-week experience for new App Dev members.',
    boundary: { rootTeam: 'People Operations', subteams: ['Member Experience'], repos: ['onboarding-refresh'], dataOwner: 'Priya N.', effectiveSince: 'Mar 4, 2026', lifecycle: 'Active' },
    contributors: [
      { name: 'Priya N.', commits: 13, additions: 720, deletions: 190 },
      { name: 'Jamie L.', commits: 10, additions: 560, deletions: 150 },
      { name: 'Ana G.', commits: 7, additions: 410, deletions: 100 },
    ],
    history: [],
    evidence: [],
  },
  {
    id: 'mobile-lab', name: 'Mobile Lab', short: 'ML', team: 'Innovation Studio', repo: 'mobile-lab', status: 'Insufficient data', statusClass: 'data', signal: 'Repository mapping incomplete', signalDetail: 'Ownership review required', lastActivity: '11 days ago', trend: 'flat', weeks: [0.3, 0.2, null, null, 0.25, null, null, 0.1], flagFrom: 99,
    seriesBaselines: { openPRs: [null, null], reviewLatency: [null, null], contributors: [null, null] },
    description: 'Experimental mobile prototypes and technical spikes.',
    boundary: { rootTeam: 'Innovation Studio', subteams: ['Mobile Spikes'], repos: ['mobile-lab', 'mobile-lab-experiments (unmapped)'], dataOwner: 'Unassigned', effectiveSince: '—', lifecycle: 'New' },
    contributors: [],
    history: [{ date: 'Jul 6, 2026', actor: 'System', action: 'Data quality problem', note: 'mobile-lab-experiments repository has no confirmed owning project.' }],
    evidence: [{ type: 'blue', icon: 'lock', title: 'Boundary needs mapping', metric: null, current: '1 unmapped repo', baseline: '0 unmapped repos' }],
  },
  {
    id: 'winter-campaign', name: 'Winter Campaign', short: 'WC', team: 'Marketing', repo: 'winter-campaign', status: 'Planned pause', statusClass: 'pause', signal: 'Inactivity is expected', signalDetail: 'Pause recorded through Aug 20', lastActivity: '16 days ago', trend: 'flat', weeks: [0.5, 0.4, 0.2, 0.05, 0.05, 0.05, 0.05, 0.05], flagFrom: 99,
    seriesBaselines: { openPRs: [1, 0], reviewLatency: [null, null], contributors: [2, 1] },
    description: 'Seasonal campaign planning and creative coordination.',
    boundary: { rootTeam: 'Marketing', subteams: [], repos: ['winter-campaign'], dataOwner: 'Sam D.', effectiveSince: 'Oct 2, 2025', lifecycle: 'Paused' },
    contributors: [{ name: 'Sam D.', commits: 3, additions: 140, deletions: 30 }],
    history: [{ date: 'Jul 6, 2026', actor: 'Sam D.', action: 'Planned pause', note: 'Campaign work resumes after the August 20 seasonal kickoff.' }],
    evidence: [{ type: 'blue', icon: 'calendar', title: 'Planned pause recorded', metric: null, current: 'Through Aug 20', baseline: 'Excluded from scoring' }],
  },
];

const weekDates = ['Jun 15', 'Jun 22', 'Jun 29', 'Jul 06', 'Jul 13', 'Jul 20', 'Jul 27', 'Aug 03'];

const CONTRIB_WEEKS = 26;
const CONTRIB_DAYS = CONTRIB_WEEKS * 7;
const contribEnd = new Date(2026, 7, 3);
const contribStart = new Date(contribEnd);
contribStart.setDate(contribStart.getDate() - (CONTRIB_DAYS - 1));
const dailyDates = Array.from({ length: CONTRIB_DAYS }, (_, i) => {
  const d = new Date(contribStart);
  d.setDate(d.getDate() + i);
  return d;
});
const dailyRowLabels = Array.from({ length: 7 }, (_, r) => ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][dailyDates[r].getDay()]);
const dailyIsWeekend = dailyRowLabels.map((label) => label === 'Sun' || label === 'Sat');

function lerp8(baseline, current) {
  if (baseline === null || current === null) return [null, null, null, null, null, null, null, null];
  return Array.from({ length: 8 }, (_, i) => {
    if (i === 0) return baseline;
    if (i === 7) return current;
    const t = i / 7;
    const taper = Math.sin(t * Math.PI);
    const wobble = Math.sin(i * 1.9) * Math.abs(current - baseline) * 0.06 * taper;
    return Math.max(0, Math.round((baseline + (current - baseline) * t + wobble) * 10) / 10);
  });
}

function seededRandom(seedStr) {
  let h = 0;
  for (let i = 0; i < seedStr.length; i += 1) h = (h * 31 + seedStr.charCodeAt(i)) | 0;
  let s = Math.abs(h) || 1;
  return () => { s = (s * 16807) % 2147483647; return (s % 1000) / 1000; };
}

projects.forEach((project) => {
  const b = project.seriesBaselines;
  project.series = {
    activity: project.weeks.map((w) => (w === null ? null : Math.round(w * 7))),
    openPRs: lerp8(...b.openPRs),
    reviewLatency: lerp8(...b.reviewLatency),
    contributors: lerp8(...b.contributors),
  };

  const rngCommits = seededRandom(`${project.id}-commits`);
  project.commits = project.weeks.map((w) => (w === null ? null : Math.round(w * 13 + rngCommits() * 5)));

  const rngCode = seededRandom(`${project.id}-code`);
  project.codeFrequency = {
    additions: project.commits.map((c) => (c === null ? null : Math.round(c * (10 + rngCode() * 18)))),
    deletions: project.commits.map((c) => (c === null ? null : Math.round(c * (4 + rngCode() * 9)))),
  };

  const rngPunch = seededRandom(`${project.id}-punch`);
  const validWeeks = project.weeks.filter((w) => w !== null);
  const activityLevel = validWeeks.length ? validWeeks.reduce((a, v) => a + v, 0) / validWeeks.length : 0;
  project.punchCard = Array.from({ length: 7 }, (_, day) => {
    const dayWeight = day === 0 || day === 6 ? 0.4 : 1;
    return Array.from({ length: 24 }, (_, hour) => {
      const hourCurve = Math.max(0, Math.sin(((hour - 8) / 16) * Math.PI));
      const noise = 0.55 + rngPunch() * 0.9;
      return Math.max(0, Math.min(1, activityLevel * dayWeight * hourCurve * noise));
    });
  });

  const rngDaily = seededRandom(`${project.id}-daily`);
  const knownWeekLevels = project.weeks.filter((w) => w !== null);
  const avgLevel = knownWeekLevels.length ? knownWeekLevels.reduce((a, v) => a + v, 0) / knownWeekLevels.length : 0;
  const priorWeeks = CONTRIB_WEEKS - 8;
  let walkLevel = avgLevel;
  const priorWeekLevels = Array.from({ length: priorWeeks }, () => {
    walkLevel = Math.max(0.04, Math.min(0.95, walkLevel + (rngDaily() - 0.5) * 0.4));
    return walkLevel;
  });
  project.dailyActivity = Array.from({ length: CONTRIB_DAYS }, (_, i) => {
    const col = Math.floor(i / 7);
    const row = i % 7;
    const weekLevel = col >= priorWeeks ? project.weeks[col - priorWeeks] : priorWeekLevels[col];
    if (weekLevel === null) return null;
    if (weekLevel < 0.12 && rngDaily() < 0.55) return null;
    const dayWeight = dailyIsWeekend[row] ? 0.4 : 1;
    const noise = 0.35 + rngDaily() * 1.15;
    const raw = weekLevel * dayWeight * noise;
    if (raw < 0.06) return 0;
    return Math.round(Math.min(1, raw) * 100) / 100;
  });
});

function statusColor(statusClass) {
  return { risk: 'var(--clay)', watch: 'var(--amber)', clear: 'var(--moss)', data: 'var(--plum)', pause: 'var(--slate)' }[statusClass];
}

function lastValue(series) {
  for (let i = series.length - 1; i >= 0; i -= 1) if (series[i] !== null) return series[i];
  return null;
}

function sparkChart(points, { color = 'var(--ink)', baseline = null, width = 220, height = 56, suffix = '', area = true } = {}) {
  const vals = points.filter((v) => v !== null);
  if (!vals.length) return `<div class="chart-empty" style="width:${width}px;height:${height}px">No data</div>`;
  const allVals = baseline !== null ? vals.concat([baseline]) : vals;
  const min = Math.min(...allVals);
  const max = Math.max(...allVals);
  const span = max - min || Math.max(1, max * 0.2);
  const pad = span * 0.2;
  const domainMin = min - pad;
  const domainMax = max + pad;
  const stepX = width / (points.length - 1);
  const y = (v) => height - 6 - ((v - domainMin) / (domainMax - domainMin)) * (height - 12);
  const segments = [];
  let current = [];
  points.forEach((v, i) => {
    if (v === null) { if (current.length) segments.push(current); current = []; }
    else current.push([i * stepX, y(v)]);
  });
  if (current.length) segments.push(current);
  const fmt = (seg) => seg.map(([x, yy]) => `${x.toFixed(1)} ${yy.toFixed(1)}`).join(' L ');
  const pathD = segments.map((seg) => `M${fmt(seg)}`).join(' ');
  const areaD = segments.map((seg) => `M${fmt(seg)} L${seg[seg.length - 1][0].toFixed(1)} ${height} L${seg[0][0].toFixed(1)} ${height} Z`).join(' ');
  const last = segments.length ? segments[segments.length - 1].at(-1) : null;
  const dots = points.map((v, i) => (v === null ? '' : `<circle class="chart-hit" cx="${(i * stepX).toFixed(1)}" cy="${y(v).toFixed(1)}" r="7" fill="transparent"><title>${weekDates[i]}: ${v}${suffix}</title></circle>`)).join('');
  const baselineLine = baseline !== null ? `<line class="chart-baseline" x1="0" y1="${y(baseline).toFixed(1)}" x2="${width}" y2="${y(baseline).toFixed(1)}"/>` : '';
  return `<svg class="spark-chart" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" preserveAspectRatio="none" role="img" aria-label="8-week trend">${baselineLine}${area ? `<path class="spark-area" d="${areaD}" fill="${color}" opacity="0.12"/>` : ''}<path class="spark-line" d="${pathD}" stroke="${color}" fill="none"/>${last ? `<circle class="spark-end" cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="3" fill="${color}"/>` : ''}${dots}</svg>`;
}

function chartCaption(label, current, baseline, unit = '') {
  if (current === null) return `<div class="chart-caption"><span class="chart-caption-label">${label}</span><span class="chart-caption-value">—</span></div>`;
  const delta = baseline !== null ? current - baseline : null;
  const arrow = delta === null || Math.abs(delta) < 0.05 ? '' : delta > 0 ? '▲' : '▼';
  return `<div class="chart-caption"><span class="chart-caption-label">${label}</span><span class="chart-caption-value">${current}${unit}${baseline !== null ? ` <em>${arrow} vs ${baseline}${unit} baseline</em>` : ''}</span></div>`;
}

function barChart(points, { color = 'var(--ink)', width = 520, height = 110, suffix = '' } = {}) {
  const vals = points.filter((v) => v !== null);
  if (!vals.length) return `<div class="chart-empty" style="width:100%;height:${height}px">No data</div>`;
  const max = Math.max(...vals, 1);
  const stepX = width / points.length;
  const barW = Math.max(4, stepX * 0.5);
  const bars = points.map((v, i) => {
    if (v === null) return '';
    const h = Math.max(1, (v / max) * (height - 14));
    const x = i * stepX + (stepX - barW) / 2;
    const y = height - h;
    return `<rect class="bar-mark" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="${color}"><title>${weekDates[i]}: ${v}${suffix}</title></rect>`;
  }).join('');
  return `<svg class="bar-chart" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" preserveAspectRatio="none" role="img" aria-label="Weekly commit activity">${bars}</svg>`;
}

function codeFrequencyChart(project, { width = 520, height = 140 } = {}) {
  const { additions, deletions } = project.codeFrequency;
  const vals = additions.concat(deletions).filter((v) => v !== null);
  if (!vals.length) return `<div class="chart-empty" style="width:100%;height:${height}px">No data</div>`;
  const max = Math.max(...vals, 1);
  const mid = height / 2;
  const stepX = width / additions.length;
  const barW = Math.max(4, stepX * 0.46);
  const bars = additions.map((a, i) => {
    const d = deletions[i];
    if (a === null) return '';
    const hA = Math.max(1, (a / max) * (mid - 8));
    const hD = Math.max(1, (d / max) * (mid - 8));
    const x = i * stepX + (stepX - barW) / 2;
    return `<rect class="bar-mark" x="${x.toFixed(1)}" y="${(mid - hA).toFixed(1)}" width="${barW.toFixed(1)}" height="${hA.toFixed(1)}" rx="2" fill="var(--moss)"><title>${weekDates[i]}: +${a} lines</title></rect><rect class="bar-mark" x="${x.toFixed(1)}" y="${mid.toFixed(1)}" width="${barW.toFixed(1)}" height="${hD.toFixed(1)}" rx="2" fill="var(--clay)"><title>${weekDates[i]}: −${d} lines</title></rect>`;
  }).join('');
  return `<svg class="bar-chart" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" preserveAspectRatio="none" role="img" aria-label="Weekly lines added and removed"><line class="chart-zero" x1="0" y1="${mid}" x2="${width}" y2="${mid}"/>${bars}</svg>`;
}

const punchDays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function punchCardChart(project, { cell = 15 } = {}) {
  const grid = project.punchCard;
  const maxV = Math.max(...grid.flat(), 0.05);
  const width = 24 * cell + 34;
  const height = 7 * cell + 16;
  let dots = '';
  grid.forEach((row, day) => {
    row.forEach((v, hour) => {
      const r = (v / maxV) * (cell * 0.42);
      if (r < 0.6) return;
      const cx = 34 + hour * cell + cell / 2;
      const cy = 4 + day * cell + cell / 2;
      dots += `<circle cx="${cx}" cy="${cy}" r="${r.toFixed(1)}" fill="var(--brand)" opacity="${(0.3 + v * 0.55).toFixed(2)}"><title>${punchDays[day]} ${hour}:00 — ${Math.round((v / maxV) * 100)}% of peak</title></circle>`;
    });
  });
  const dayLabels = punchDays.map((d, i) => `<text x="26" y="${4 + i * cell + cell / 2 + 3}" class="punch-label" text-anchor="end">${d}</text>`).join('');
  const hourLabels = [0, 6, 12, 18].map((h) => `<text x="${34 + h * cell + cell / 2}" y="${height + 11}" class="punch-label" text-anchor="middle">${h === 0 ? '12a' : h === 12 ? '12p' : h < 12 ? `${h}a` : `${h - 12}p`}</text>`).join('');
  return `<svg class="punch-chart" viewBox="0 0 ${width} ${height + 14}" width="100%" height="${height + 14}" role="img" aria-label="Commit activity by day and hour">${dayLabels}${dots}${hourLabels}</svg>`;
}

function contributorsCard(project) {
  const list = project.contributors || [];
  if (!list.length) return `<section class="panel"><div class="panel-header"><div><h2 class="panel-title">Contributors</h2><p class="panel-subtitle">Trailing 8 weeks</p></div></div><div class="history-empty" style="padding:4px 20px 18px;">No contributor data available yet.</div></section>`;
  const max = Math.max(...list.map((c) => c.commits));
  const total = list.reduce((sum, c) => sum + c.commits, 0);
  const color = statusColor(project.statusClass);
  const rows = list.map((c) => `<div class="contributor-row"><div class="contributor-line"><span class="contributor-name">${c.name}</span><span class="contributor-commits">${c.commits} commits</span></div><div class="contributor-bar-track"><div class="contributor-bar" style="width:${Math.max(4, (c.commits / max) * 100)}%; background:${color}"></div></div><div class="contributor-lines"><span class="add">+${c.additions}</span><span class="del">−${c.deletions}</span><span class="share">${Math.round((c.commits / total) * 100)}% of commits</span></div></div>`).join('');
  return `<section class="panel"><div class="panel-header"><div><h2 class="panel-title">Contributors</h2><p class="panel-subtitle">Trailing 8 weeks · ${total} commits total</p></div></div><div class="contributor-list">${rows}</div></section>`;
}

function codeInsightsSection(project) {
  return `<section class="panel code-insights">
    <div class="panel-header"><div><h2 class="panel-title">Code insights</h2><p class="panel-subtitle">Repository-level activity — commits, lines changed, and when work happens</p></div><span class="eyebrow">Aug 03</span></div>
    <div class="code-charts-row">
      <div class="code-chart-col"><span class="chart-caption-label">Commits per week</span>${barChart(project.commits, { color: statusColor(project.statusClass) })}</div>
      <div class="code-chart-col"><span class="chart-caption-label">Lines added / removed</span>${codeFrequencyChart(project)}</div>
    </div>
    <div class="punch-wrap"><span class="chart-caption-label">When commits happen</span>${punchCardChart(project)}</div>
  </section>`;
}

function contributionCalendar(project, { cell = 10, gap = 2 } = {}) {
  const colW = cell + gap;
  const rowH = cell + gap;
  const leftPad = 26;
  const topPad = 14;
  const width = leftPad + CONTRIB_WEEKS * colW - gap;
  const height = topPad + 7 * rowH - gap;
  const color = statusColor(project.statusClass);
  const flat = project.dailyActivity.filter((v) => v !== null);
  const maxV = Math.max(...flat, 0.05);
  let cells = '';
  let months = '';
  let lastMonth = null;
  for (let col = 0; col < CONTRIB_WEEKS; col += 1) {
    const firstDate = dailyDates[col * 7];
    const m = firstDate.getMonth();
    if (m !== lastMonth) {
      months += `<text x="${leftPad + col * colW}" y="9" class="punch-label">${firstDate.toLocaleString('en-US', { month: 'short' })}</text>`;
      lastMonth = m;
    }
    for (let row = 0; row < 7; row += 1) {
      const idx = col * 7 + row;
      const v = project.dailyActivity[idx];
      const date = dailyDates[idx];
      const x = leftPad + col * colW;
      const y = topPad + row * rowH;
      const dateLabel = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
      if (v === null) {
        cells += `<rect x="${x}" y="${y}" width="${cell}" height="${cell}" rx="2" class="contrib-cell contrib-cell-empty"><title>${dateLabel}: no data</title></rect>`;
      } else {
        const t = Math.min(1, v / maxV);
        const isLow = t <= 0.04;
        cells += isLow
          ? `<rect x="${x}" y="${y}" width="${cell}" height="${cell}" rx="2" class="contrib-cell contrib-cell-empty"><title>${dateLabel}: ${Math.round(t * 100)}% of peak</title></rect>`
          : `<rect x="${x}" y="${y}" width="${cell}" height="${cell}" rx="2" class="contrib-cell" fill="${color}" opacity="${(0.18 + t * 0.82).toFixed(2)}"><title>${dateLabel}: ${Math.round(t * 100)}% of peak</title></rect>`;
      }
    }
  }
  const rowLabels = [1, 3, 5].map((r) => `<text x="${leftPad - 6}" y="${topPad + r * rowH + cell * 0.8}" class="punch-label" text-anchor="end">${dailyRowLabels[r]}</text>`).join('');
  return `<svg class="contrib-chart" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Daily contribution activity, last 26 weeks">${months}${rowLabels}${cells}</svg>`;
}

function contributionStats(project) {
  const data = project.dailyActivity;
  const isActive = (v) => v !== null && v > 0.05;
  let current = 0;
  for (let i = data.length - 1; i >= 0; i -= 1) {
    if (isActive(data[i])) current += 1; else break;
  }
  let longest = 0;
  let run = 0;
  data.forEach((v) => { if (isActive(v)) { run += 1; longest = Math.max(longest, run); } else run = 0; });
  const weekdaySums = Array.from({ length: 7 }, () => 0);
  data.forEach((v, i) => { if (v !== null) weekdaySums[i % 7] += v; });
  const topWeekday = Math.max(...weekdaySums) > 0 ? dailyRowLabels[weekdaySums.indexOf(Math.max(...weekdaySums))] : '—';
  const weekSums = Array.from({ length: CONTRIB_WEEKS }, (_, col) => {
    let sum = 0;
    let any = false;
    for (let r = 0; r < 7; r += 1) {
      const v = data[col * 7 + r];
      if (v !== null) { sum += v; any = true; }
    }
    return any ? sum : -1;
  });
  const maxWeekSum = Math.max(...weekSums);
  const busiestLabel = maxWeekSum > 0 ? dailyDates[weekSums.indexOf(maxWeekSum) * 7].toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—';
  return [
    { label: 'Current streak', value: `${current}d` },
    { label: 'Longest streak', value: `${longest}d` },
    { label: 'Most active day', value: topWeekday },
    { label: 'Busiest week of', value: busiestLabel },
  ];
}

function contributionCalendarSection(project) {
  const stats = contributionStats(project);
  return `<section class="panel contrib-panel">
    <div class="panel-header"><div><h2 class="panel-title">Contribution calendar</h2><p class="panel-subtitle">Daily commit activity — last 26 weeks</p></div><span class="eyebrow">Through Aug 03</span></div>
    <div class="contrib-stats">${stats.map((s) => `<div class="contrib-stat"><span class="chart-caption-label">${s.label}</span><span class="chart-caption-value">${s.value}</span></div>`).join('')}</div>
    <div class="contrib-wrap">${contributionCalendar(project)}</div>
  </section>`;
}

const viewLabels = { overview: 'Overview', projects: 'Projects', insights: 'Insights', 'review-log': 'Review log', boundaries: 'Project boundaries', rules: 'Signal rules' };
let currentView = 'overview';
let selectedProject = projects[0];
let currentFilter = 'All projects';
let modalFeedback = '';

function statusPill(project) {
  return `<span class="status-pill status-${project.statusClass}">${project.status}</span>`;
}

function monogram(project, className = '') {
  return `<div class="id-tag ${project.statusClass} ${className}">${project.short}</div>`;
}

function signalStrip(project, size = '') {
  const ticks = project.weeks.map((value, index) => {
    if (value === null) return '<span class="tick" style="height:100%;background:transparent;border-right:1px dashed var(--line-strong)"></span>';
    const flagged = index >= project.flagFrom;
    const cls = flagged ? (project.statusClass === 'risk' ? 'flag-red' : project.statusClass === 'watch' ? 'flag-amber' : 'flag-moss') : (value < 0.3 ? 'low' : '');
    return `<span class="tick ${cls}" style="height:${Math.max(value, 0.06) * 100}%"></span>`;
  }).join('');
  return `<div class="signal-strip ${size}" title="8-week activity trace">${ticks}</div>`;
}

function renderOverview() {
  const attention = projects.filter((project) => project.status === 'At risk' || project.status === 'Watch');
  return `
    <div class="page-heading">
      <div>
        <span class="eyebrow">Monday · Week 32</span>
        <h1>Good morning, Jordan</h1>
        <p>Here’s the current read on the projects that matter this week.</p>
      </div>
      <div class="heading-actions">
        <div class="date-chip">${icon('calendar')} Aug 03 – Aug 09, 2026</div>
        <button class="primary-button" id="review-button">Start weekly review <span>→</span></button>
      </div>
    </div>

    <div class="stat-grid">
      <article class="stat-card total"><div class="stat-label"><span>Active projects</span><span class="stat-icon">${icon('folder')}</span></div><div class="stat-value">6</div><div class="stat-foot"><span class="positive">+1</span> since last week</div></article>
      <article class="stat-card attention"><div class="stat-label"><span>Need attention</span><span class="stat-icon">${icon('triangle')}</span></div><div class="stat-value">3</div><div class="stat-foot"><span class="negative">2 new</span> since last week</div></article>
      <article class="stat-card clear"><div class="stat-label"><span>Clear</span><span class="stat-icon">${icon('check-circle')}</span></div><div class="stat-value">2</div><div class="stat-foot"><span class="positive">33%</span> of active projects</div></article>
      <article class="stat-card data"><div class="stat-label"><span>Insufficient data</span><span class="stat-icon">${icon('database')}</span></div><div class="stat-value">1</div><div class="stat-foot">Coverage is being resolved</div></article>
    </div>

    <div class="insight-banner">
      <div class="insight-banner-icon">${icon('sparkle')}</div>
      <div class="insight-copy"><strong>${attention.length} projects may need leadership attention this week.</strong><span>Review the evidence, add context, and decide what to verify with each team.</span></div>
      <button class="insight-link" id="banner-review">Review attention queue →</button>
    </div>

    <div class="dashboard-grid">
      <section class="panel queue-panel">
        <div class="panel-header"><div><h2 class="panel-title">Attention queue</h2><p class="panel-subtitle">Prioritized by signal strength and change since last review</p></div><button class="panel-link" id="queue-filter">View all projects</button></div>
        <div class="queue-list">${attention.map((project) => `
          <div class="queue-item">
            ${monogram(project)}
            ${signalStrip(project)}
            <div class="queue-main"><div class="queue-name-line"><span class="queue-name">${project.name}</span>${statusPill(project)}</div><div class="queue-meta">${project.team} · ${project.repo}</div></div>
            <div class="queue-signal"><strong>${project.signal}</strong><span class="mono">${project.signalDetail}</span></div>
            <button class="queue-action view-project" data-project-id="${project.id}">View project</button>
          </div>`).join('')}</div>
      </section>

      <div>
        <section class="panel pulse-panel"><div class="panel-header"><div><h2 class="panel-title">Portfolio pulse</h2><p class="panel-subtitle">Attention status across the last 8 weeks</p></div><span class="eyebrow">Projects</span></div><div class="pulse-chart"><svg class="chart-svg" viewBox="0 0 500 130" preserveAspectRatio="none" aria-label="Portfolio pulse trend"><defs><linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0083ff" stop-opacity=".17"/><stop offset="1" stop-color="#0083ff" stop-opacity="0"/></linearGradient></defs><line class="chart-grid-line" x1="0" y1="16" x2="500" y2="16"/><line class="chart-grid-line" x1="0" y1="48" x2="500" y2="48"/><line class="chart-grid-line" x1="0" y1="80" x2="500" y2="80"/><line class="chart-grid-line" x1="0" y1="112" x2="500" y2="112"/><line class="chart-baseline" x1="0" y1="70" x2="500" y2="70"/><path class="chart-area" d="M0 88 L70 78 L140 84 L210 57 L280 66 L350 45 L420 54 L500 32 L500 116 L0 116 Z"/><path class="chart-line" d="M0 88 L70 78 L140 84 L210 57 L280 66 L350 45 L420 54 L500 32"/><circle class="chart-dot" cx="0" cy="88" r="3"/><circle class="chart-dot" cx="70" cy="78" r="3"/><circle class="chart-dot" cx="140" cy="84" r="3"/><circle class="chart-dot" cx="210" cy="57" r="3"/><circle class="chart-dot" cx="280" cy="66" r="3"/><circle class="chart-dot" cx="350" cy="45" r="3"/><circle class="chart-dot" cx="420" cy="54" r="3"/><circle class="chart-dot" cx="500" cy="32" r="3"/><text class="chart-label" x="0" y="129">Jun 15</text><text class="chart-label" x="215" y="129">Jul 13</text><text class="chart-label" x="450" y="129">Aug 03</text></svg></div><div class="pulse-footer"><div class="chart-legend"><span class="legend-line"></span> Projects with attention status</div><span class="chart-note">Dashed line: 8-week baseline</span></div></section>
        <section class="panel signal-panel"><div class="panel-header"><div><h2 class="panel-title">Signal mix</h2><p class="panel-subtitle">What is driving this week’s queue</p></div></div><div class="signal-list"><div class="signal-row"><span class="signal-icon red">${icon('pull')}</span><div class="signal-copy"><strong>Pull request aging</strong><span>Review or decision bottlenecks</span></div><span class="signal-count">2</span></div><div class="signal-row"><span class="signal-icon amber">${icon('activity')}</span><div class="signal-copy"><strong>Activity trend</strong><span>Below project baseline</span></div><span class="signal-count">2</span></div><div class="signal-row"><span class="signal-icon blue">${icon('users')}</span><div class="signal-copy"><strong>Contributor resilience</strong><span>Project dependency signal</span></div><span class="signal-count">1</span></div></div></section>
        <div class="review-card"><div class="review-card-icon">${icon('clipboard')}</div><div class="review-copy"><strong>Weekly review ritual</strong><span>Last review was Jul 27 · 8 decisions recorded</span></div><button class="panel-link" id="review-log-button">Open log</button></div>
      </div>
    </div>`;
}

function renderProjects() {
  const filtered = currentFilter === 'All projects' ? projects : projects.filter((project) => project.status === currentFilter);
  return `
    <div class="page-heading"><div><span class="eyebrow">Portfolio inventory</span><h1>All projects</h1><p>Every project boundary, current attention status, and data freshness in one place.</p></div><div class="heading-actions"><button class="secondary-button" id="export-projects">Export inventory</button><button class="primary-button" id="add-project">Add project boundary <span>+</span></button></div></div>
    <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Project inventory</h2><p class="panel-subtitle">${filtered.length} of ${projects.length} projects shown · evidence snapshots from Aug 03, 2026</p></div><div class="filter-row">${['All projects', 'At risk', 'Watch', 'Clear'].map((filter) => `<button class="filter-button ${currentFilter === filter ? 'active' : ''}" data-filter="${filter}">${filter}</button>`).join('')}</div></div><div class="table-scroll"><table class="projects-table"><thead><tr><th>Project</th><th>Status</th><th>Trace</th><th>Signal</th><th>Active</th><th>Coverage</th></tr></thead><tbody>${filtered.map((project) => `<tr class="project-row" data-project-id="${project.id}"><td><div class="table-project">${monogram(project, 'sm')}<div><strong>${project.name}</strong><span>${project.team} · ${project.repo}</span></div></div></td><td>${statusPill(project)}</td><td>${signalStrip(project)}</td><td>${project.signal}</td><td><span class="freshness">${project.lastActivity}</span></td><td><span class="freshness">${project.status === 'Insufficient data' ? 'Needs mapping' : 'Complete · 97%'}</span></td></tr>`).join('')}</tbody></table></div><div class="table-footer"><span>Boundaries are versioned and reviewed by project owners.</span><button class="panel-link" id="boundary-link">Manage boundaries →</button></div></section>`;
}

function renderInsights() {
  return `
    <div class="page-heading"><div><span class="eyebrow">Combined view · last 8 weeks</span><h1>Insights</h1><p>Every project's activity, review flow, and contributor trend, side by side.</p></div></div>
    <section class="panel">
      <div class="table-scroll">
      <table class="insights-table">
        <thead><tr><th>Project</th><th>Activity <span>days/wk</span></th><th>Open PRs</th><th>Review latency</th><th>Contributors</th></tr></thead>
        <tbody>${projects.map((project) => {
          return `<tr class="insights-row" data-project-id="${project.id}">
            <td><div class="table-project">${monogram(project, 'sm')}<div><strong>${project.name}</strong><span>${project.team}</span></div></div>${statusPill(project)}</td>
            <td>${chartCaption('', lastValue(project.series.activity), null)}</td>
            <td>${chartCaption('', lastValue(project.series.openPRs), project.seriesBaselines.openPRs[0])}</td>
            <td>${chartCaption('', lastValue(project.series.reviewLatency), project.seriesBaselines.reviewLatency[0], 'd')}</td>
            <td>${chartCaption('', lastValue(project.series.contributors), project.seriesBaselines.contributors[0])}</td>
          </tr>`;
        }).join('')}</tbody>
      </table>
      </div>
    </section>`;
}

const statusMeta = {
  risk: { copy: 'Needs a conversation with the team.', cta: 'Review warning' },
  watch: { copy: 'Emerging signal, worth a look.', cta: 'Review warning' },
  clear: { copy: 'No concern in current signals.', cta: 'Confirm reviewed' },
  data: { copy: 'Boundary needs mapping.', cta: 'Flag for mapping' },
  pause: { copy: 'Pause recorded, excluded from risk.', cta: 'Acknowledge pause' },
};

function evidenceRow(project, item, size = '') {
  if (item.metric) {
    const series = project.series[item.metric];
    const baseline = project.seriesBaselines[item.metric] ? project.seriesBaselines[item.metric][0] : null;
    const current = lastValue(series);
    return `<div class="evidence-item ${size}"><span class="evidence-marker ${item.type}">${icon(item.icon)}</span><div class="evidence-copy"><div class="evidence-top"><strong>${item.title}</strong>${chartCaption('', current, baseline, item.unit)}</div>${sparkChart(series, { color: statusColor(project.statusClass), baseline, width: size === 'lg' ? 420 : 220, height: size === 'lg' ? 56 : 36, suffix: item.unit, area: size === 'lg' })}</div></div>`;
  }
  return `<div class="evidence-item ${size}"><span class="evidence-marker ${item.type}">${icon(item.icon)}</span><div class="evidence-copy"><div class="evidence-top"><strong>${item.title}</strong><span class="chart-caption-value">${item.current}</span></div><span class="evidence-note">${item.baseline}</span></div></div>`;
}

function evidenceList(project, size = '') {
  if (!project.evidence.length) return `<div class="evidence-item"><span class="evidence-marker teal">${icon('check-circle')}</span><div class="evidence-copy"><strong>No current concern</strong></div></div>`;
  return project.evidence.map((item) => evidenceRow(project, item, size)).join('');
}

const chartMetrics = [
  ['Activity', 'activity', ''],
  ['Open PRs', 'openPRs', ''],
  ['Review latency', 'reviewLatency', 'd'],
  ['Contributors', 'contributors', ''],
];

function metricCharts(project, size = '') {
  const color = statusColor(project.statusClass);
  return `<div class="metric-charts">${chartMetrics.map(([label, key, unit]) => {
    const series = project.series[key];
    const baseline = key === 'activity' ? null : project.seriesBaselines[key][0];
    const current = lastValue(series);
    return `<div class="metric-chart-tile">${chartCaption(label, current, baseline, unit)}${sparkChart(series, { color, baseline, width: size === 'sm' ? 130 : 260, height: size === 'sm' ? 40 : 64 })}</div>`;
  }).join('')}</div>`;
}

function boundaryCard(project) {
  const b = project.boundary;
  if (!b) return '';
  return `<section class="panel"><div class="panel-header"><div><h2 class="panel-title">Project boundary</h2><p class="panel-subtitle">Canonical ownership record</p></div><span class="eyebrow">${b.lifecycle}</span></div><dl class="boundary-list"><div><dt>Root team</dt><dd>${b.rootTeam}</dd></div><div><dt>Included subteams</dt><dd>${b.subteams.length ? b.subteams.join(', ') : '—'}</dd></div><div><dt>Repositories</dt><dd>${b.repos.join(', ')}</dd></div><div><dt>Data owner</dt><dd>${b.dataOwner}</dd></div><div><dt>Effective since</dt><dd>${b.effectiveSince}</dd></div></dl></section>`;
}

function historyCard(project) {
  const items = project.history || [];
  return `<section class="panel"><div class="panel-header"><div><h2 class="panel-title">Review history</h2><p class="panel-subtitle">Decisions leadership has recorded</p></div></div><div class="history-list">${items.length ? items.map((h) => `<div class="history-item"><div class="history-top"><span class="history-action">${h.action}</span><span class="history-date">${h.date}</span></div><p>${h.note}</p><span class="history-actor">${h.actor}</span></div>`).join('') : `<div class="history-empty">No review notes recorded yet for this project.</div>`}</div></section>`;
}

function renderProjectProfile(project) {
  const meta = statusMeta[project.statusClass];
  return `
    <div class="page-heading">
      <div>
        <button class="text-button back-link" id="profile-back"><span>←</span> Back to inventory</button>
        <div class="profile-title-row">${monogram(project, 'lg')}<div><h1>${project.name}</h1><p>${project.team} · ${project.repo} · Snapshot Aug 03, 2026</p></div>${statusPill(project)}</div>
      </div>
      <div class="heading-actions">${signalStrip(project, 'lg')}</div>
    </div>
    <div class="detail-status wide ${project.statusClass}"><strong>${project.status}</strong><span>${meta.copy}</span></div>
    ${metricCharts(project)}
    ${codeInsightsSection(project)}
    ${contributionCalendarSection(project)}
    <div class="profile-grid">
      <section class="panel">
        <div class="panel-header"><div><h2 class="panel-title">Evidence</h2><p class="panel-subtitle">Signal vs. this project's own baseline</p></div><span class="eyebrow">Snapshot · Aug 03</span></div>
        <div class="evidence-section wide">${evidenceList(project, 'lg')}</div>
        <div class="detail-actions"><button class="secondary-button" id="add-context">Add context</button><button class="primary-button" id="confirm-review">${meta.cta} <span>→</span></button></div>
      </section>
      <div class="profile-side">${contributorsCard(project)}${boundaryCard(project)}${historyCard(project)}</div>
    </div>`;
}

function renderUtilityView(view) {
  const content = {
    'review-log': { icon: 'clipboard', title: 'Review log', copy: 'A shared record of weekly decisions, context, and follow-up actions will live here.' },
    boundaries: { icon: 'waypoints', title: 'Project boundaries', copy: 'Map canonical projects to Authentik teams and Gitea repositories. Every boundary will have an owner and an effective date.' },
    rules: { icon: 'sliders', title: 'Signal rules', copy: 'Review explainable rule hypotheses, thresholds, baselines, and the evidence required before a project enters the attention queue.' },
  }[view];
  return `<div class="page-heading"><div><span class="eyebrow">Product surface preview</span><h1>${content.title}</h1><p>${content.copy}</p></div><div class="heading-actions"><button class="secondary-button" id="back-overview">← Back to overview</button></div></div><section class="panel empty-view"><div class="empty-view-inner"><div class="empty-view-icon">${icon(content.icon)}</div><h2>${content.title} is part of the next slice</h2><p>This mock keeps the concept visible without pretending these workflows are connected yet. The overview and project evidence experience are ready for the product conversation.</p></div></section>`;
}

function render() {
  const appView = document.getElementById('app-view');
  if (currentView === 'overview') appView.innerHTML = renderOverview();
  if (currentView === 'projects') appView.innerHTML = renderProjects();
  if (currentView === 'insights') appView.innerHTML = renderInsights();
  if (currentView === 'profile') appView.innerHTML = renderProjectProfile(selectedProject);
  if (currentView === 'review-log' || currentView === 'boundaries' || currentView === 'rules') appView.innerHTML = renderUtilityView(currentView);
  document.getElementById('breadcrumb-current').textContent = currentView === 'profile' ? selectedProject.name : viewLabels[currentView];
  const navActiveView = currentView === 'profile' ? 'projects' : currentView;
  document.querySelectorAll('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.view === navActiveView));
  bindViewEvents();
  window.scrollTo(0, 0);
}

function showToast(message) {
  const toast = document.getElementById('toast');
  document.getElementById('toast-message').textContent = message;
  toast.classList.add('show');
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => toast.classList.remove('show'), 2800);
}

function openFeedback(project = selectedProject) {
  selectedProject = project;
  modalFeedback = '';
  document.getElementById('feedback-project-name').textContent = `Add context to the ${project.name} warning. Your note will be attached to this weekly snapshot.`;
  document.getElementById('feedback-note').value = '';
  document.querySelectorAll('.feedback-options button').forEach((button) => button.classList.remove('selected'));
  document.getElementById('modal-backdrop').hidden = false;
}

function closeFeedback() { document.getElementById('modal-backdrop').hidden = true; }

function bindViewEvents() {
  document.querySelectorAll('.view-project').forEach((button) => button.addEventListener('click', () => {
    selectedProject = projects.find((project) => project.id === button.dataset.projectId) || selectedProject;
    currentView = 'profile';
    render();
  }));
  document.querySelectorAll('.insights-row, .project-row').forEach((row) => row.addEventListener('click', () => {
    selectedProject = projects.find((project) => project.id === row.dataset.projectId) || selectedProject;
    currentView = 'profile';
    render();
  }));
  document.getElementById('profile-back')?.addEventListener('click', () => { currentView = 'projects'; render(); });
  document.querySelectorAll('[data-filter]').forEach((button) => button.addEventListener('click', () => { currentFilter = button.dataset.filter; render(); }));
  document.querySelectorAll('#review-button, #banner-review').forEach((button) => button.addEventListener('click', () => { currentView = 'projects'; currentFilter = 'All projects'; render(); }));
  document.getElementById('queue-filter')?.addEventListener('click', () => { currentView = 'projects'; currentFilter = 'All projects'; render(); });
  document.getElementById('review-log-button')?.addEventListener('click', () => { currentView = 'review-log'; render(); });
  document.getElementById('back-overview')?.addEventListener('click', () => { currentView = 'overview'; render(); });
  document.getElementById('boundary-link')?.addEventListener('click', () => { currentView = 'boundaries'; render(); });
  document.getElementById('coverage-details')?.addEventListener('click', () => { currentView = 'boundaries'; render(); showToast('Data quality view opened'); });
  document.getElementById('add-project')?.addEventListener('click', () => showToast('Boundary creation is mocked for this demo'));
  document.getElementById('export-projects')?.addEventListener('click', () => showToast('Project inventory exported (mock)'));
  document.getElementById('add-context')?.addEventListener('click', () => openFeedback(selectedProject));
  document.getElementById('confirm-review')?.addEventListener('click', () => openFeedback(selectedProject));
}

document.querySelectorAll('.nav-item').forEach((item) => item.addEventListener('click', () => { currentView = item.dataset.view; render(); }));
document.querySelectorAll('.feedback-options button').forEach((button) => button.addEventListener('click', () => { modalFeedback = button.dataset.feedback; document.querySelectorAll('.feedback-options button').forEach((option) => option.classList.toggle('selected', option === button)); }));
document.getElementById('modal-close').addEventListener('click', closeFeedback);
document.getElementById('modal-cancel').addEventListener('click', closeFeedback);
document.getElementById('modal-backdrop').addEventListener('click', (event) => { if (event.target.id === 'modal-backdrop') closeFeedback(); });
document.getElementById('modal-save').addEventListener('click', () => { closeFeedback(); showToast(modalFeedback ? `${modalFeedback} recorded for ${selectedProject.name}` : `Review note saved for ${selectedProject.name}`); });
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeFeedback(); });
if (location.hash) { const p = new URLSearchParams(location.hash.slice(1)); if (p.get('view')) currentView = p.get('view'); if (p.get('project')) selectedProject = projects.find((x) => x.id === p.get('project')) || selectedProject; }

render();
