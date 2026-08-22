const icons = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  folder: '<path d="M3 6.5A2.5 2.5 0 0 1 5.5 4h4l2 2H18.5A2.5 2.5 0 0 1 21 8.5v7A2.5 2.5 0 0 1 18.5 18h-13A2.5 2.5 0 0 1 3 15.5Z"/>',
  database: '<ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7"/>',
  calendar: '<rect x="3" y="4.5" width="18" height="17" rx="2"/><path d="M16 3v3M8 3v3M3 9h18M8 13h.01M12 13h.01M16 13h.01M8 17h.01M12 17h.01"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  'check-circle': '<circle cx="12" cy="12" r="9"/><path d="m8 12 2.7 2.7L16.5 9"/>',
  triangle: '<path d="m12 4 9 16H3Z"/><path d="M12 10v4M12 17h.01"/>',
  pause: '<rect x="5" y="4" width="14" height="16" rx="3"/><path d="M10 9v6M14 9v6"/>',
  message: '<path d="M20 11.5a7 7 0 0 1-7.2 7H8l-4 2 1.6-4A7.4 7.4 0 0 1 5 12c0-4.2 3.4-7.5 7.7-7.5S20 7.2 20 11.5Z"/><path d="M8 12h.01M12 12h.01M16 12h.01"/>',
  activity: '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
  pull: '<path d="M6 3v18M6 7h8a3 3 0 0 1 3 3v1M18 8l2 3-2 3M6 17h8a3 3 0 0 0 3-3v-1"/>',
  users: '<path d="M16 20v-1.5a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4V20M9.5 10.5A3.5 3.5 0 1 0 9.5 3a3.5 3.5 0 0 0 0 7.5ZM17 11a3 3 0 1 0-1-5.8M21 20v-1.4a4 4 0 0 0-3-3.8"/>',
  sparkle: '<path d="m12 3 1.3 5.7L19 10l-5.7 1.3L12 17l-1.3-5.7L5 10l5.7-1.3ZM19 17l.5 2.5L22 20l-2.5.5L19 23l-.5-2.5L16 20l2.5-.5Z"/>',
  trend: '<path d="M4 17 10 11l4 4 6-7M15 8h5v5"/>',
};

function icon(name) {
  return `<svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.sparkle}</svg>`;
}

document.querySelectorAll('[data-icon]').forEach((element) => {
  element.innerHTML = icon(element.dataset.icon);
});

const API_BASE = window.PHI_API_BASE || 'http://127.0.0.1:8000';
const METRIC_DEFINITIONS = [
  { label: 'Activity', key: 'activity', metricKey: 'active_days', unit: 'd' },
  { label: 'Open PRs', key: 'openPRs', metricKey: 'open_prs', unit: '' },
  { label: 'Review latency', key: 'reviewLatency', metricKey: 'review_latency_days', unit: 'd' },
  { label: 'Active contributors', key: 'contributors', metricKey: 'active_contributors', unit: '' },
];
const AGGREGATE_METRIC_KEYS = [
  'active_days',
  'days_since_activity',
  'open_prs',
  'oldest_open_pr_days',
  'review_latency_days',
  'merged_count',
  'active_contributors',
];
const viewLabels = { overview: 'Overview', projects: 'Projects', insights: 'Insights' };
// The inventory filter chips, hoisted out of renderProjects so the router can
// validate a `?filter=` value against the same list the UI offers.
const PROJECT_FILTERS = ['All projects', 'Active projects', 'Needs attention', 'At risk', 'Watch', 'Clear', 'Insufficient data', 'Planned pause'];
const statusMeta = {
  risk: { copy: 'Needs a conversation with the team.', cta: 'Review warning' },
  watch: { copy: 'Emerging signal, worth a look.', cta: 'Review warning' },
  clear: { copy: 'No concern in current signals.', cta: 'Confirm reviewed' },
  data: { copy: 'Not enough trusted data to assess.', cta: 'Flag for mapping' },
  pause: { copy: 'Pause recorded; signals are suppressed.', cta: 'Acknowledge pause' },
};

const state = {
  loading: true,
  error: null,
  snapshot: null,
  projects: [],
  projectSnapshots: {},
  projectSnapshotMeta: {},
  // Point-in-time project profiles, keyed `${projectId}@${YYYY-MM-DD}`, kept
  // apart from projectSnapshots above so a historical view never overwrites
  // (or gets served from) the live cache. Each entry is
  // { hasData: boolean, project: normalizedProject|null }.
  projectAsOf: {},
  calendarDate: null,
  delivery: null,
  calendarLoading: false,
  calendarError: null,
  calendarResult: null,
  // The date calendarResult was actually fetched for. The router compares it
  // against calendarDate so returning to a route via Back/Forward re-renders
  // from cache instead of refetching a snapshot it already holds.
  calendarLoadedDate: null,
  calendarComputing: new Set(),
  calendarComputeErrors: {},
  // Projects-page cumulative-progress-as-of-date calendar. Separate from
  // the calendar* state above by design: the two answer different
  // questions (one week vs. cumulative-to-date) and stay independent.
  progressDate: null,
  progressLoading: false,
  progressError: null,
  progressComputable: false,
  progressResult: {}, // project_id -> { state: 'pending'|'done'|'error', data?, error? }
  // The date a *portfolio-wide* progress fan-out was last run for. Matters
  // more than calendarLoadedDate above: re-running it costs one LLM request
  // per project, so Back/Forward must never trigger it for a date already
  // loaded. Deliberately left null by the single-project loader below, whose
  // result covers only one row of the list.
  progressLoadedDate: null,
  progressRunId: 0,
  // Viewport-gated lazy compute for the *live* dashboard (the Projects and
  // Insights tables), distinct from the calendar* state above: that one
  // answers "as of a date I picked", this one fills in the current view for
  // projects GET /snapshots/latest had no snapshot for at all. Each id is
  // computed only once its row scrolls into view, so a cold database costs
  // one LLM request per project actually looked at rather than one per
  // project in the portfolio.
  lazyWeekStart: null,
  lazyComputable: false,
  lazyMissing: new Set(),
  lazyComputing: new Set(),
  lazyErrors: {},
};

let currentView = 'overview';
let selectedProjectId = null;
// The date the open profile is being viewed "as of", captured at click time
// from state.calendarDate rather than read live -- the portfolio calendar can
// be cleared or re-pointed while the profile is open, and this view must keep
// showing the week the user actually drilled into. null means live data.
let selectedProjectAsOfDate = null;
// Which project's cumulative-progress checkpoint the 'progress' view is
// showing. Deliberately separate from selectedProjectId: that one drives the
// weekly-snapshot profile, and the two views answer different questions.
let selectedProgressProjectId = null;
let currentFilter = 'All projects';
let modalFeedback = '';
let feedbackWarningId = null;

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function finiteNumber(value) {
  if (value === null || value === undefined || (typeof value === 'string' && !value.trim())) return null;
  const number = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(number) ? number : null;
}

function firstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null);
}

function hasOwn(object, key) {
  return Boolean(object && Object.prototype.hasOwnProperty.call(object, key));
}

function isAttentionProject(project) {
  return (project.statusClass === 'risk' || project.statusClass === 'watch') && project.evidence.length > 0;
}

function isActiveProject(project) {
  return project.statusClass !== 'pause';
}

function normalizeSeries(value) {
  const source = asArray(value).slice(0, 8);
  return Array.from({ length: 8 }, (_, index) => finiteNumber(source[index]));
}

function normalizeMetricObject(value) {
  const source = value && typeof value === 'object' ? value : {};
  return AGGREGATE_METRIC_KEYS.reduce((metrics, key) => {
    if (hasOwn(source, key)) {
      const normalized = finiteNumber(source[key]);
      if (normalized !== null) metrics[key] = normalized;
    }
    return metrics;
  }, {});
}

function normalizeBoundary(value) {
  if (!value || typeof value !== 'object') return null;
  return {
    rootTeam: firstDefined(value.rootTeam, value.root_team, value.root, '—'),
    subteams: asArray(firstDefined(value.subteams, value.sub_teams)).filter((item) => typeof item === 'string'),
    repos: asArray(value.repos || value.repositories).filter((item) => typeof item === 'string'),
    dataOwner: firstDefined(value.dataOwner, value.data_owner, value.owner, 'Unassigned'),
    effectiveSince: firstDefined(value.effectiveSince, value.effective_since, value.effective_from, value.effective, '—'),
    effectiveUntil: firstDefined(value.effectiveUntil, value.effective_until, value.effective_to, null),
    lifecycle: firstDefined(value.lifecycle, 'Active'),
    version: firstDefined(value.version, value.boundary_version, null),
  };
}

function evidenceReference(value, index) {
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (!value || typeof value !== 'object') return '';
  const reference = firstDefined(value.reference_id, value.referenceId, value.source_id, value.sourceId, value.id, value.ref, value.uri, value.url, value.source);
  return reference ? String(reference) : `evidence row ${index + 1}`;
}

function normalizeEvidence(value) {
  return asArray(value).map((item, index) => {
    if (!item || typeof item !== 'object') return null;
    const sources = asArray(firstDefined(item.source_evidence, item.sourceEvidence, item.source_refs, item.source_evidence_refs, item.evidence_refs, item.evidenceReferences, item.sources))
      .map((reference, referenceIndex) => evidenceReference(reference, referenceIndex))
      .filter(Boolean);
    if (!sources.length) return null;
    return {
      id: firstDefined(item.warning_id, item.warningId, item.id, null),
      type: firstDefined(item.type, item.severity, 'blue'),
      icon: firstDefined(item.icon, item.metric === 'openPRs' || item.metric === 'open_prs' ? 'pull' : item.metric === 'contributors' || item.metric === 'active_contributors' ? 'users' : 'activity'),
      title: firstDefined(item.title, item.signal_name, item.signalName, 'Signal evidence'),
      metric: firstDefined(item.metric, item.metric_key, null),
      unit: firstDefined(item.unit, ''),
      current: firstDefined(item.current, item.current_value, null),
      baseline: firstDefined(item.baseline, item.baseline_value, null),
      window: firstDefined(item.window, item.time_window, null),
      threshold: firstDefined(item.threshold, item.trigger_threshold, null),
      sources,
    };
  }).filter(Boolean).map((item) => ({ ...item, type: ['red', 'amber', 'blue', 'teal'].includes(item.type) ? item.type : 'blue' }));
}

function normalizeHistory(value) {
  return asArray(value).map((item) => {
    if (!item || typeof item !== 'object') return null;
    return {
      date: firstDefined(item.date, item.at, item.created_at, '—'),
      action: firstDefined(item.action, item.category, 'Review note'),
      note: firstDefined(item.note, item.explanation, item.detail, ''),
    };
  }).filter(Boolean);
}

const assessmentStatusMeta = {
  risk: { label: 'At risk', className: 'risk' },
  at_risk: { label: 'At risk', className: 'risk' },
  watch: { label: 'Watch', className: 'watch' },
  okay: { label: 'Okay', className: 'clear' },
  ok: { label: 'Okay', className: 'clear' },
  clear: { label: 'Okay', className: 'clear' },
  healthy: { label: 'Okay', className: 'clear' },
  on_track: { label: 'Okay', className: 'clear' },
  blocked: { label: 'Blocked', className: 'risk' },
  insufficient_data: { label: 'Insufficient data', className: 'neutral' },
  planned_pause: { label: 'Planned pause', className: 'neutral' },
};

function assessmentSource(rawProject) {
  const raw = rawProject && typeof rawProject === 'object' ? rawProject : {};
  const candidates = [
    raw.healthAssessment,
    raw.health_assessment,
    raw.projectHealthAssessment,
    raw.project_health_assessment,
    raw.profile?.healthAssessment,
    raw.profile?.health_assessment,
    raw.projectProfile?.healthAssessment,
    raw.project_profile?.health_assessment,
    raw.projectAgent?.healthAssessment,
    raw.project_agent?.health_assessment,
    raw.agent?.healthAssessment,
    raw.agent?.health_assessment,
    raw.projectAgent,
    raw.project_agent,
    raw.agent,
  ];
  return candidates.find((candidate) => candidate && typeof candidate === 'object' && !Array.isArray(candidate) && Object.keys(candidate).some((key) => /status|score|confidence|expected.?week|explanation|summary|blocker|task|recommend|citation|evidence/i.test(key))) || null;
}

function normalizeAssessmentStatus(value) {
  const raw = String(value ?? '').trim();
  if (!raw) return { label: null, className: 'neutral' };
  const key = raw.toLowerCase().replaceAll('-', '_').replaceAll(' ', '_');
  return assessmentStatusMeta[key] || { label: raw, className: 'neutral' };
}

function normalizeAssessmentItems(value, kind) {
  return asArray(value).map((item) => {
    if (typeof item === 'string' && item.trim()) return { title: item.trim(), detail: null, week: null };
    if (!item || typeof item !== 'object') return null;
    const title = firstDefined(item.title, item.task, item.name, item.label, item.blocker, item.recommendation, item.text, null);
    if (!title || !String(title).trim()) return null;
    return {
      title: String(title).trim(),
      detail: firstDefined(item.detail, item.description, item.reason, item.explanation, null),
      week: firstDefined(item.week, item.expected_week, item.expectedWeek, null),
      kind,
    };
  }).filter(Boolean);
}

function normalizeAssessmentCitations(value) {
  return asArray(value).map((item) => {
    if (typeof item === 'string' && item.trim()) return { label: item.trim(), reference: item.trim(), url: null };
    if (!item || typeof item !== 'object') return null;
    const sourceReference = [item.source_type, item.sourceType, item.source_id, item.sourceId, item.source_field, item.sourceField].filter((part) => part !== undefined && part !== null && String(part).trim()).join(':');
    const reference = firstDefined(item.reference, item.reference_id, item.referenceId, sourceReference, item.source_id, item.sourceId, item.uri, item.url, item.ref, item.id, null);
    if (!reference || !String(reference).trim()) return null;
    return {
      label: firstDefined(item.label, item.title, item.source, item.name, null),
      reference: String(reference).trim(),
      url: firstDefined(item.url, item.uri, null),
    };
  }).filter(Boolean);
}

function normalizeHealthAssessment(rawProject) {
  const source = assessmentSource(rawProject);
  if (!source) return null;
  const status = normalizeAssessmentStatus(firstDefined(source.status, source.rag_status, source.ragStatus, source.assessment_status, source.assessmentStatus, source.health_status, source.healthStatus));
  const score = finiteNumber(firstDefined(source.score, source.health_score, source.healthScore, source.rag_score, source.ragScore));
  const confidence = finiteNumber(firstDefined(source.confidence, source.confidence_score, source.confidenceScore));
  const expectedWeek = firstDefined(source.expected_week, source.expectedWeek, source.expected_week_number, source.expectedWeekNumber, source.target_week, source.targetWeek, null);
  const explanation = firstDefined(source.explanation, source.summary, source.rationale, source.reason, null);
  const blockers = normalizeAssessmentItems(firstDefined(source.blockers, source.blocking_items, source.blockingItems, source.risks, []), 'blocker');
  const weeklyTasks = normalizeAssessmentItems(firstDefined(source.recommended_weekly_tasks, source.recommendedWeeklyTasks, source.weekly_tasks, source.weeklyTasks, source.recommended_tasks, source.recommendedTasks, source.tasks, []), 'task');
  const citationInputs = [source.citations, source.evidence_references, source.evidenceReferences, source.evidence_refs, source.evidenceRefs, source.evidence_citations, source.spec_citations, source.sources].flatMap((value) => asArray(value));
  const citations = normalizeAssessmentCitations(citationInputs);
  const hasInspectableFields = Boolean(status.label || score !== null || confidence !== null || expectedWeek !== null || explanation || blockers.length || weeklyTasks.length || citations.length);
  if (!hasInspectableFields) return null;
  return {
    status: status.label,
    statusClass: status.className,
    score,
    confidence,
    expectedWeek,
    explanation,
    blockers,
    weeklyTasks,
    citations,
  };
}

function normalizeStatus(value) {
  const status = String(value || '').toLowerCase().replaceAll('-', '_').replaceAll(' ', '_');
  if (status === 'at_risk' || status === 'risk') return ['At risk', 'risk'];
  if (status === 'watch') return ['Watch', 'watch'];
  if (status === 'clear') return ['Clear', 'clear'];
  if (status === 'planned_pause' || status === 'pause' || status === 'paused') return ['Planned pause', 'pause'];
  return ['Insufficient data', 'data'];
}

function looksPaused(rawProject, boundary) {
  const lifecycle = String(firstDefined(rawProject.lifecycle, boundary?.lifecycle, '')).toLowerCase();
  return rawProject.planned_pause === true || rawProject.plannedPause === true || lifecycle === 'paused' || lifecycle === 'planned pause' || lifecycle === 'planned_pause';
}

function metricValue(metrics, key, fallback = null) {
  return hasOwn(metrics, key) ? metrics[key] : fallback;
}

function normalizeProject(rawProject, snapshotMeta = {}) {
  const raw = rawProject && typeof rawProject === 'object' ? rawProject : {};
  const healthAssessment = normalizeHealthAssessment(raw);
  const metrics = normalizeMetricObject(firstDefined(raw.metrics, raw.metric_values, {}));
  const baselines = normalizeMetricObject(firstDefined(raw.baselines, raw.baseline_metrics, {}));
  const rawSeries = raw.series && typeof raw.series === 'object' ? raw.series : {};
  const sourceWeeks = asArray(raw.weeks);
  const series = {
    activity: normalizeSeries(firstDefined(rawSeries.activity, rawSeries.active_days, raw.active_days_series)),
    openPRs: normalizeSeries(firstDefined(rawSeries.openPRs, rawSeries.open_prs)),
    reviewLatency: normalizeSeries(firstDefined(rawSeries.reviewLatency, rawSeries.review_latency_days, rawSeries.review_latency)),
    contributors: normalizeSeries(firstDefined(rawSeries.contributors, rawSeries.active_contributors)),
  };
  const contributorAggregateAvailable = hasOwn(metrics, 'active_contributors');
  if (!contributorAggregateAvailable) series.contributors = normalizeSeries(null);
  if (!series.activity.some((value) => value !== null) && sourceWeeks.length) {
    series.activity = normalizeSeries(sourceWeeks.map((value) => {
      const number = finiteNumber(value);
      return number === null ? null : number * 7;
    }));
  }
  const activitySource = series.activity.some((value) => value !== null) ? series.activity : sourceWeeks;
  const weeks = normalizeSeries(activitySource.map((value) => {
    const number = finiteNumber(value);
    return number === null ? null : Math.min(1, number > 1 ? number / 7 : number);
  }));
  const boundary = normalizeBoundary(raw.boundary);
  const sourceEvidence = firstDefined(raw.evidence, raw.warnings, []);
  const evidence = normalizeEvidence(sourceEvidence);
  const visibleEvidence = evidence.filter((item) => {
    const metric = String(item.metric || '').toLowerCase();
    return contributorAggregateAvailable || !['contributors', 'active_contributors'].includes(metric);
  });
  let [status, statusClass] = normalizeStatus(firstDefined(raw.status, raw.attention_status, raw.statusClass, raw.status_class));
  if (looksPaused(raw, boundary)) {
    status = 'Planned pause';
    statusClass = 'pause';
  }
  if ((statusClass === 'risk' || statusClass === 'watch') && !visibleEvidence.length) {
    status = 'Insufficient data';
    statusClass = 'data';
  }
  const aggregateMetrics = { ...metrics };
  const contributorCount = metricValue(metrics, 'active_contributors');
  if (contributorCount === null) delete aggregateMetrics.active_contributors;
  const hasTrustedMetricData = Object.keys(aggregateMetrics).length > 0 || series.activity.some((value) => value !== null) || series.openPRs.some((value) => value !== null) || series.reviewLatency.some((value) => value !== null);
  if (statusClass === 'clear' && !hasTrustedMetricData) {
    status = 'Insufficient data';
    statusClass = 'data';
  }
  const currentValues = {
    activity: metricValue(metrics, 'active_days', lastValue(series.activity)),
    openPRs: metricValue(metrics, 'open_prs', lastValue(series.openPRs)),
    reviewLatency: metricValue(metrics, 'review_latency_days', lastValue(series.reviewLatency)),
    contributors: metricValue(metrics, 'active_contributors', lastValue(series.contributors)),
  };
  const explicitBaselines = firstDefined(raw.seriesBaselines, raw.series_baselines, {});
  const seriesBaselines = Object.fromEntries(METRIC_DEFINITIONS.map(({ key, metricKey }) => {
    if (key === 'contributors' && !contributorAggregateAvailable) return [key, [null, null]];
    const explicit = asArray(firstDefined(explicitBaselines?.[key], explicitBaselines?.[metricKey]));
    const baseline = metricValue(baselines, metricKey, finiteNumber(explicit[0]));
    const current = currentValues[key] ?? finiteNumber(explicit[1]);
    return [key, [baseline, current]];
  }));
  if (!contributorAggregateAvailable) {
    delete series.contributors;
    delete seriesBaselines.contributors;
  }
  const completeness = finiteNumber(firstDefined(raw.data_completeness_pct, snapshotMeta.dataCompletenessPct));
  const signal = statusClass === 'data' ? 'Trusted evidence is incomplete' : statusClass === 'pause' ? 'Inactivity is expected' : firstDefined(raw.signal, raw.signal_name, visibleEvidence[0]?.title, status === 'Clear' ? 'No current concern detected' : 'Review current project signals');
  const signalDetail = statusClass === 'data' ? 'The project remains out of the attention queue until data and evidence are available.' : statusClass === 'pause' ? 'Planned pause is excluded from scoring.' : firstDefined(raw.signalDetail, raw.signal_detail, formatActivityDetail(aggregateMetrics));
  return {
    id: String(firstDefined(raw.project_id, raw.id, 'unknown-project')),
    name: firstDefined(raw.name, raw.project_name, raw.id, 'Unnamed project'),
    short: firstDefined(raw.short, String(firstDefined(raw.name, raw.id, 'P')).split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()),
    team: firstDefined(raw.team, raw.root_team, boundary?.rootTeam, 'Unassigned'),
    repo: firstDefined(raw.repo, boundary?.repos?.[0], '—'),
    status,
    statusClass,
    signal,
    signalDetail,
    lastActivity: firstDefined(raw.lastActivity, raw.last_activity, formatLastActivity(aggregateMetrics.days_since_activity)),
    trend: firstDefined(raw.trend, 'flat'),
    weeks,
    flagFrom: Number.isInteger(raw.flagFrom) ? raw.flagFrom : (statusClass === 'risk' || statusClass === 'watch' ? Math.max(0, weeks.length - 2) : 99),
    seriesBaselines,
    series,
    metrics: aggregateMetrics,
    description: firstDefined(raw.description, ''),
    boundary,
    evidence: statusClass === 'pause' || statusClass === 'data' ? [] : visibleEvidence,
    history: normalizeHistory(raw.history),
    dataCompletenessPct: completeness,
    lastSyncAt: firstDefined(raw.last_sync_at, snapshotMeta.lastSyncAt, null),
    snapshotId: firstDefined(raw.snapshot_id, snapshotMeta.snapshotId, null),
    healthAssessment,
  };
}

function lastValue(series = []) {
  for (let index = series.length - 1; index >= 0; index -= 1) {
    if (series[index] !== null && series[index] !== undefined) return series[index];
  }
  return null;
}

function formatLastActivity(days) {
  const number = finiteNumber(days);
  if (number === null) return '—';
  if (number <= 0) return 'Today';
  if (number === 1) return 'Yesterday';
  return `${number} days ago`;
}

function formatActivityDetail(metrics) {
  const activeDays = metrics.active_days;
  const openPrs = metrics.open_prs;
  if (activeDays !== undefined && openPrs !== undefined) return `${activeDays} active days · ${openPrs} open PRs`;
  if (activeDays !== undefined) return `${activeDays} active days in the snapshot window`;
  return 'Snapshot metrics are available for review.';
}

function snapshotEnvelope(raw) {
  if (raw && raw.snapshot && typeof raw.snapshot === 'object') return raw.snapshot;
  if (raw && raw.data && typeof raw.data === 'object' && !Array.isArray(raw.data)) return raw.data;
  return raw || {};
}

function normalizeSnapshot(raw) {
  const envelope = snapshotEnvelope(raw);
  const meta = {
    snapshotId: firstDefined(envelope.snapshot_id, envelope.snapshotId, envelope.id, raw?.snapshot_id, null),
    snapshotWeekStart: firstDefined(envelope.snapshot_week_start, envelope.week_start, null),
    snapshotWeekEnd: firstDefined(envelope.snapshot_week_end, envelope.week_end, null),
    generatedAt: firstDefined(envelope.generated_at, null),
    ruleSetVersion: firstDefined(envelope.rule_set_version, null),
    dataCompletenessPct: finiteNumber(envelope.data_completeness_pct),
    lastSyncAt: firstDefined(envelope.last_sync_at, null),
  };
  const rawProjects = asArray(envelope.projects);
  return { ...meta, projects: rawProjects.map((project) => normalizeProject(project, meta)) };
}

// The API authenticates with an Authentik OIDC bearer token and reads no cookies.
// A deployment supplies the token through window.PHI_API_TOKEN, either as a string
// or as a (possibly async) function so the host page can refresh an expiring token
// per request. Local dev with PHI_DEV_AUTH=true needs no token and leaves it unset.
async function authToken() {
  const source = window.PHI_API_TOKEN;
  const value = typeof source === 'function' ? await source() : source;
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

async function authHeaders() {
  let token = null;
  try {
    token = await authToken();
  } catch (error) {
    throw new Error(error?.message || 'The API session token could not be obtained.');
  }
  if (!token) return {};
  return { Authorization: /^bearer\s/i.test(token) ? token : `Bearer ${token}` };
}

async function requestJson(path, options = {}) {
  const headers = {
    Accept: 'application/json',
    ...(await authHeaders()),
    ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    ...(options.headers || {}),
  };
  const response = await fetch(`${API_BASE}${path}`, { credentials: 'omit', ...options, headers });
  let payload = null;
  try { payload = await response.json(); } catch (error) { payload = null; }
  if (!response.ok) {
    const detail = payload && typeof payload === 'object' ? firstDefined(payload.detail, payload.message, payload.error) : null;
    const message = formatErrorDetail(detail);
    if (response.status === 401) {
      const reason = message || 'Authentication is required';
      throw new Error(`${/[.!?]$/.test(reason) ? reason : `${reason}.`} Set window.PHI_API_TOKEN, or run the API with PHI_DEV_AUTH=true for local development.`);
    }
    if (response.status === 403) throw new Error(message || 'Your account does not have access to this data.');
    throw new Error(message || `Request failed (${response.status})`);
  }
  return payload;
}

// FastAPI returns a list of validation objects in `detail`; a plain string otherwise.
function formatErrorDetail(detail) {
  if (typeof detail === 'string') return detail.trim() || null;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      if (typeof item === 'string') return item;
      if (!item || typeof item !== 'object') return '';
      const field = asArray(item.loc).filter((part) => part !== 'body').join('.');
      const message = String(firstDefined(item.msg, item.message, '') || '');
      return field && message ? `${field}: ${message}` : message;
    }).filter(Boolean);
    return messages.length ? messages.join('; ') : null;
  }
  if (detail && typeof detail === 'object') return formatErrorDetail(firstDefined(detail.msg, detail.message, detail.error));
  return null;
}

function formatDate(value, includeTime = false) {
  if (!value) return 'Unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat('en-US', includeTime ? { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' } : { month: 'short', day: 'numeric', year: 'numeric' }).format(date);
}

function formatPercent(value) {
  const number = finiteNumber(value);
  return number === null ? '—' : `${Math.round(number)}%`;
}

// Cache key for one project's snapshot metadata: the plain project id for the
// live profile, id@date while that project is being viewed as of a past week.
function profileCacheKey(projectId) {
  return selectedProjectAsOfDate && projectId === selectedProjectId ? `${projectId}@${selectedProjectAsOfDate}` : projectId;
}

function snapshotMetaFor(project = null) {
  const cached = project ? state.projectSnapshotMeta[profileCacheKey(project.id)] : null;
  const snapshot = cached || (project && selectedProjectAsOfDate && project.id === selectedProjectId ? {} : state.snapshot || {});
  return {
    snapshotId: firstDefined(project?.snapshotId, snapshot.snapshotId, null),
    snapshotWeekStart: snapshot.snapshotWeekStart,
    snapshotWeekEnd: snapshot.snapshotWeekEnd,
    generatedAt: snapshot.generatedAt,
    ruleSetVersion: snapshot.ruleSetVersion,
    dataCompletenessPct: firstDefined(project?.dataCompletenessPct, snapshot.dataCompletenessPct, null),
    lastSyncAt: firstDefined(project?.lastSyncAt, snapshot.lastSyncAt, null),
  };
}

function snapshotMetaMarkup(project = null, compact = false) {
  const meta = snapshotMetaFor(project);
  const week = meta.snapshotWeekStart || meta.snapshotWeekEnd ? `${formatDate(meta.snapshotWeekStart)}${meta.snapshotWeekEnd ? ` – ${formatDate(meta.snapshotWeekEnd)}` : ''}` : 'Current snapshot';
  return `<div class="snapshot-meta ${compact ? 'compact' : ''}"><span>${escapeHtml(week)}</span><span>Data completeness ${escapeHtml(formatPercent(meta.dataCompletenessPct))}</span><span>Last sync ${escapeHtml(formatDate(meta.lastSyncAt, true))}</span></div>`;
}

function weekLabels(project = null) {
  const start = snapshotMetaFor(project).snapshotWeekStart;
  if (!start) return Array.from({ length: 8 }, (_, index) => `Week ${index + 1}`);
  const end = new Date(start);
  if (Number.isNaN(end.getTime())) return Array.from({ length: 8 }, (_, index) => `Week ${index + 1}`);
  return Array.from({ length: 8 }, (_, index) => {
    const date = new Date(end);
    date.setUTCDate(date.getUTCDate() - (7 * (7 - index)));
    return date.toLocaleDateString('en-US', { month: 'short', day: '2-digit', timeZone: 'UTC' });
  });
}

function statusColor(statusClass) {
  return { risk: 'var(--clay)', watch: 'var(--amber)', clear: 'var(--moss)', data: 'var(--plum)', pause: 'var(--slate)' }[statusClass] || 'var(--ink)';
}

function statusPill(project) {
  return `<span class="status-pill status-${escapeHtml(project.statusClass)}">${escapeHtml(project.status)}</span>`;
}

function monogram(project, className = '') {
  return `<div class="id-tag ${escapeHtml(project.statusClass)} ${className}">${escapeHtml(project.short)}</div>`;
}

function chartDomain(points, baseline = null) {
  const values = points.filter((value) => value !== null);
  if (!values.length) return null;
  const allValues = baseline !== null ? values.concat([baseline]) : values;
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const span = max - min || Math.max(1, max * 0.2);
  return { domainMin: min - span * 0.2, domainMax: max + span * 0.2 };
}

function formatChartTick(value, suffix = '', step = 1) {
  const precision = step >= 10 ? 0 : step >= 1 ? 1 : step >= 0.1 ? 2 : 3;
  const formatted = Number(value.toFixed(precision));
  return `${formatted}${suffix}`;
}

function chartYAxis(points, baseline, suffix = '', label = 'chart') {
  const domain = chartDomain(points, baseline);
  if (!domain) return '<div class="chart-y-axis chart-y-axis-empty" aria-hidden="true"></div>';
  const step = (domain.domainMax - domain.domainMin) / 4;
  const ticks = Array.from({ length: 5 }, (_, index) => domain.domainMax - (step * index));
  return `<div class="chart-y-axis" aria-label="${escapeHtml(label)} y-axis">${ticks.map((tick) => `<span>${escapeHtml(formatChartTick(tick, suffix, step))}</span>`).join('')}</div>`;
}

function sparkChart(points, { color = 'var(--ink)', baseline = null, width = 220, height = 56, suffix = '', area = true, labels = null, grid = false } = {}) {
  const domain = chartDomain(points, baseline);
  if (!domain) return `<div class="chart-empty" style="width:100%;height:${height}px">Insufficient data</div>`;
  const { domainMin, domainMax } = domain;
  const stepX = points.length > 1 ? width / (points.length - 1) : width;
  const y = (value) => height - 6 - ((value - domainMin) / (domainMax - domainMin)) * (height - 12);
  const segments = [];
  let current = [];
  points.forEach((value, index) => {
    if (value === null) { if (current.length) segments.push(current); current = []; }
    else current.push([index * stepX, y(value)]);
  });
  if (current.length) segments.push(current);
  const formatSegment = (segment) => segment.map(([x, yy]) => `${x.toFixed(1)} ${yy.toFixed(1)}`).join(' L ');
  const path = segments.map((segment) => `M${formatSegment(segment)}`).join(' ');
  const areaPath = segments.map((segment) => `M${formatSegment(segment)} L${segment.at(-1)[0].toFixed(1)} ${height} L${segment[0][0].toFixed(1)} ${height} Z`).join(' ');
  const last = segments.at(-1)?.at(-1);
  const chartLabels = labels || weekLabels();
  const gridLines = grid ? [0.25, 0.5, 0.75].map((fraction) => `<line class="chart-grid" x1="0" y1="${(height * fraction).toFixed(1)}" x2="${width}" y2="${(height * fraction).toFixed(1)}"/>`).join('') : '';
  const pointsMarkup = points.map((value, index) => {
    if (value === null) return '';
    const x = (index * stepX).toFixed(1);
    const yy = y(value).toFixed(1);
    const label = chartLabels[index] || `Week ${index + 1}`;
    return `<circle class="chart-point" cx="${x}" cy="${yy}" r="2.7" fill="${color}"/><circle class="chart-hit" cx="${x}" cy="${yy}" r="9" fill="transparent"><title>${escapeHtml(label)}: ${escapeHtml(value)}${escapeHtml(suffix)}</title></circle>`;
  }).join('');
  const baselineLine = baseline !== null ? `<line class="chart-baseline" x1="0" y1="${y(baseline).toFixed(1)}" x2="${width}" y2="${y(baseline).toFixed(1)}"/>` : '';
  return `<svg class="spark-chart" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" preserveAspectRatio="none" role="img" aria-label="8-week trend">${gridLines}${baselineLine}${area ? `<path class="spark-area" d="${areaPath}" fill="${color}" opacity="0.12"/>` : ''}<path class="spark-line" d="${path}" stroke="${color}" fill="none"/>${last ? `<circle class="spark-end" cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="3.5" fill="${color}"/>` : ''}${pointsMarkup}</svg>`;
}

function chartTimestampAxis(labels) {
  return `<div class="chart-axis-wrap"><div class="chart-axis" aria-label="Weekly chart timestamps">${labels.map((label, index) => `<span title="Week ${index + 1}: ${escapeHtml(label)}">${escapeHtml(label)}</span>`).join('')}</div><div class="chart-axis-note">Weekly timestamp · hover a point for its value</div></div>`;
}

function chartCaption(label, current, baseline, unit = '') {
  if (current === null || current === undefined) return `<div class="chart-caption"><span class="chart-caption-label">${escapeHtml(label)}</span><span class="chart-caption-value">—</span></div>`;
  const numericCurrent = finiteNumber(current);
  const numericBaseline = finiteNumber(baseline);
  if (numericCurrent === null) return `<div class="chart-caption"><span class="chart-caption-label">${escapeHtml(label)}</span><span class="chart-caption-value">—</span></div>`;
  const delta = numericBaseline === null ? null : numericCurrent - numericBaseline;
  const arrow = delta === null || Math.abs(delta) < 0.05 ? '' : delta > 0 ? '▲' : '▼';
  return `<div class="chart-caption"><span class="chart-caption-label">${escapeHtml(label)}</span><span class="chart-caption-value">${escapeHtml(numericCurrent)}${escapeHtml(unit)}${numericBaseline !== null ? ` <em>${arrow} vs ${escapeHtml(numericBaseline)}${escapeHtml(unit)} baseline</em>` : ''}</span></div>`;
}

function metricCharts(project) {
  const color = statusColor(project.statusClass);
  const definitions = METRIC_DEFINITIONS.filter(({ metricKey }) => metricKey !== 'active_contributors' || hasOwn(project.metrics, 'active_contributors'));
  return `<div class="metric-charts metric-count-${definitions.length}">${definitions.map(({ label, key, metricKey, unit }) => {
    const series = project.series[key];
    const baseline = project.seriesBaselines[key]?.[0] ?? null;
    const current = metricValue(project.metrics, metricKey, lastValue(series));
    const labels = weekLabels(project).slice(0, series.length);
    return `<article class="metric-chart-tile">${chartCaption(label, current, baseline, unit)}<div class="metric-chart-body"><div class="chart-plot-row">${chartYAxis(series, baseline, unit, label)}${sparkChart(series, { color, baseline, width: 520, height: 154, suffix: unit, labels, grid: true })}</div><div class="chart-axis-row"><span class="chart-axis-gutter" aria-hidden="true"></span>${chartTimestampAxis(labels)}</div></div></article>`;
  }).join('')}</div>`;
}

function aggregateMetricsSection(project) {
  const definitions = [
    ['Active days', 'active_days', 'd'],
    ['Days since activity', 'days_since_activity', 'd'],
    ['Open PRs', 'open_prs', ''],
    ['Oldest open PR', 'oldest_open_pr_days', 'd'],
    ['Review latency', 'review_latency_days', 'd'],
    ['Merged PRs', 'merged_count', ''],
  ];
  if (hasOwn(project.metrics, 'active_contributors')) definitions.push(['Active contributors (aggregate)', 'active_contributors', '']);
  return `<section class="panel code-insights"><div class="panel-header"><div><h2 class="panel-title">Project aggregates</h2><p class="panel-subtitle">Repository-level signals only; individual-level data is never shown.</p></div><span class="eyebrow">${escapeHtml(snapshotMetaFor(project).ruleSetVersion || 'Current rules')}</span></div><div class="aggregate-metrics">${definitions.map(([label, key, unit]) => `<div class="aggregate-metric"><span class="chart-caption-label">${escapeHtml(label)}</span><strong>${project.metrics[key] === undefined ? '—' : `${escapeHtml(project.metrics[key])}${escapeHtml(unit)}`}</strong></div>`).join('')}</div></section>`;
}

function evidenceRow(project, item, size = '') {
  const metricDefinition = METRIC_DEFINITIONS.find(({ key, metricKey }) => key === item.metric || metricKey === item.metric);
  const metricKey = metricDefinition?.key || item.metric;
  const series = metricKey && project.series[metricKey] ? project.series[metricKey] : [];
  const metricName = metricDefinition?.metricKey;
  const baseline = finiteNumber(item.baseline) ?? (metricDefinition ? project.seriesBaselines[metricDefinition.key]?.[0] ?? null : null);
  const current = finiteNumber(item.current) ?? (metricDefinition ? metricValue(project.metrics, metricName, lastValue(series)) : null);
  const detail = [item.window ? `Window ${item.window}` : '', item.threshold ? `Trigger ${item.threshold}` : ''].filter(Boolean).join(' · ');
  if (metricDefinition && series.some((value) => value !== null)) {
    return `<div class="evidence-item ${size}"><span class="evidence-marker ${escapeHtml(item.type)}">${icon(item.icon)}</span><div class="evidence-copy"><div class="evidence-top"><strong>${escapeHtml(item.title)}</strong>${chartCaption('', current, baseline, metricDefinition.unit)}</div>${sparkChart(series, { color: statusColor(project.statusClass), baseline, width: size === 'lg' ? 420 : 220, height: size === 'lg' ? 56 : 36, suffix: metricDefinition.unit, labels: weekLabels(project), area: size === 'lg' })}${detail ? `<div class="evidence-note">${escapeHtml(detail)}</div>` : ''}</div></div>`;
  }
  return `<div class="evidence-item ${size}"><span class="evidence-marker ${escapeHtml(item.type)}">${icon(item.icon)}</span><div class="evidence-copy"><div class="evidence-top"><strong>${escapeHtml(item.title)}</strong>${metricDefinition ? chartCaption('', current, baseline, metricDefinition.unit) : `<span class="chart-caption-value">${current === null ? '—' : escapeHtml(current)}</span>`}</div>${detail ? `<div class="evidence-note">${escapeHtml(detail)}</div>` : ''}</div></div>`;
}

function evidenceList(project, size = '') {
  if (project.statusClass === 'data') return `<div class="evidence-item"><span class="evidence-marker blue">${icon('database')}</span><div class="evidence-copy"><strong>Insufficient data</strong><p>Warnings stay suppressed until the project has complete, inspectable evidence.</p></div></div>`;
  if (project.statusClass === 'pause') return `<div class="evidence-item"><span class="evidence-marker blue">${icon('pause')}</span><div class="evidence-copy"><strong>Signals suppressed during planned pause</strong><p>Recorded lifecycle pauses are excluded before rule evaluation.</p></div></div>`;
  if (!project.evidence.length) return `<div class="evidence-item"><span class="evidence-marker teal">${icon('check-circle')}</span><div class="evidence-copy"><strong>No current concern detected from available signals.</strong></div></div>`;
  return project.evidence.map((item) => evidenceRow(project, item, size)).join('');
}

function assessmentNumber(value, asPercent = false) {
  const number = finiteNumber(value);
  if (number === null) return '—';
  if (asPercent && number >= 0 && number <= 1) return `${Math.round(number * 100)}%`;
  return `${Number(number.toFixed(2))}${asPercent ? '%' : ''}`;
}

function assessmentCitation(item) {
  const label = item.label && item.label !== item.reference ? `${item.label} · ` : '';
  const reference = `${label}${item.reference}`;
  const safeUrl = typeof item.url === 'string' && /^https?:\/\//i.test(item.url) ? item.url : null;
  return safeUrl
    ? `<li><a href="${escapeHtml(safeUrl)}" target="_blank" rel="noreferrer">${escapeHtml(reference)}</a></li>`
    : `<li>${escapeHtml(reference)}</li>`;
}

function assessmentItems(items, emptyCopy) {
  if (!items.length) return `<p class="assessment-empty">${escapeHtml(emptyCopy)}</p>`;
  return `<ul class="assessment-list">${items.map((item) => `<li><strong>${escapeHtml(item.title)}</strong>${item.week !== null && item.week !== undefined ? `<span class="assessment-week">Week ${escapeHtml(item.week)}</span>` : ''}${item.detail ? `<span>${escapeHtml(item.detail)}</span>` : ''}</li>`).join('')}</ul>`;
}

function weeklyProgressCard(project) {
  const statusClass = ['risk', 'watch', 'clear'].includes(project.statusClass) ? project.statusClass : 'neutral';
  return `<section class="panel ci-assessment"><div class="panel-header"><div><span class="eyebrow">This week's progress</span><h2 class="panel-title">${escapeHtml(project.signal)}</h2><p class="panel-subtitle">${escapeHtml(project.signalDetail)}</p></div><span class="assessment-badge ${statusClass}">${escapeHtml(project.status)}</span></div></section>`;
}

function healthAssessmentCard(project) {
  const assessment = project.healthAssessment;
  if (!assessment) {
    return weeklyProgressCard(project);
  }
  const statusClass = ['risk', 'watch', 'clear'].includes(assessment.statusClass) ? assessment.statusClass : 'neutral';
  const statusLabel = assessment.status || 'Assessment returned';
  const metrics = `<div class="assessment-metrics"><div><span>Score</span><strong>${escapeHtml(assessmentNumber(assessment.score))}</strong></div><div><span>Confidence</span><strong>${escapeHtml(assessmentNumber(assessment.confidence, true))}</strong></div><div><span>Expected week</span><strong>${assessment.expectedWeek === null || assessment.expectedWeek === undefined ? '—' : `Week ${escapeHtml(assessment.expectedWeek)}`}</strong></div></div>`;
  const citations = assessment.citations.length ? `<div class="assessment-block"><h3>Evidence references</h3><ul class="assessment-citations">${assessment.citations.map(assessmentCitation).join('')}</ul></div>` : '';
  return `<section class="panel ci-assessment"><div class="panel-header"><div><span class="eyebrow">CI project health</span><h2 class="panel-title">${escapeHtml(statusLabel)}</h2><p class="panel-subtitle">Server-provided assessment against the project specification and weekly plan.</p></div><span class="assessment-badge ${statusClass}">${escapeHtml(statusLabel)}</span></div>${metrics}${assessment.explanation ? `<div class="assessment-explanation">${escapeHtml(assessment.explanation)}</div>` : ''}<div class="assessment-columns"><div class="assessment-block"><h3>Blockers</h3>${assessmentItems(assessment.blockers, 'No blockers returned.')}</div><div class="assessment-block"><h3>Recommended weekly tasks</h3>${assessmentItems(assessment.weeklyTasks, 'No weekly tasks returned.')}</div></div>${citations}</section>`;
}

// Overview's date picker is a jump-off, not a mode: choosing a date navigates
// to the inventory page's as-of view. So it deliberately shows no current value
// and no "Back to live" affordance -- Overview is never itself in an as-of
// state, and echoing state.calendarDate here would surface a date left over
// from a project profile's historical drill-down.
function calendarControlMarkup() {
  const today = new Date().toISOString().slice(0, 10);
  return `<div class="calendar-control"><label for="calendar-date-input">${icon('calendar')}<span>View portfolio as of</span></label><input type="date" id="calendar-date-input" max="${today}" value="" /></div>`;
}

function calendarPanelMarkup() {
  if (!state.calendarDate) return '';
  if (state.calendarLoading) return `<section class="panel calendar-panel">${loadingPanel('Loading portfolio snapshot…')}</section>`;
  if (state.calendarError) return `<section class="panel calendar-panel">${errorPanel(state.calendarError.message || 'That date could not be loaded.', 'retry-calendar')}</section>`;
  const result = state.calendarResult;
  const items = result?.projects || [];
  const missing = new Set(result?.missingProjectIds || []);
  const computable = Boolean(result?.computable);
  const weekLabel = result?.snapshotWeekStart ? `${formatDate(result.snapshotWeekStart)} – ${formatDate(result.snapshotWeekEnd)}` : null;
  const rowMarkup = (project) => {
    const isMissing = missing.has(project.id);
    if (isMissing) {
      const isComputing = state.calendarComputing.has(project.id);
      const computeError = state.calendarComputeErrors[project.id];
      // No "Compute this week" button any more: a missing row that is on
      // screen computes itself. Only the error case still needs a click,
      // so a failed project cannot re-spend a request every time it
      // scrolls back into view.
      const action = isComputing
        ? '<span class="queue-action compute-pending"><span class="spinner"></span> Computing…</span>'
        : computeError
          ? `<button class="queue-action compute-week-retry lazy-retry" data-project-id="${escapeHtml(project.id)}" data-lazy-kind="calendar">Could not compute — Retry</button>`
          : computable
            ? '<span class="queue-action compute-pending"><span class="spinner"></span> Computing…</span>'
            : '<span class="queue-action compute-disabled">LLM signal not configured</span>';
      const lazyAttrs = (!isComputing && !computeError && computable)
        ? ` data-lazy-project="${escapeHtml(project.id)}" data-lazy-kind="calendar"`
        : '';
      return `<div class="queue-item"${lazyAttrs}>${monogram(project)}<div class="queue-main"><div class="queue-name-line"><span class="queue-name">${escapeHtml(project.name)}</span></div><div class="queue-meta">${escapeHtml(project.team)} · ${escapeHtml(project.repo)}</div></div><div class="queue-signal"><span class="mono">No snapshot computed for this week yet.</span></div>${action}</div>`;
    }
    return `<div class="queue-item">${monogram(project)}<div class="queue-main"><div class="queue-name-line"><span class="queue-name">${escapeHtml(project.name)}</span>${statusPill(project)}</div><div class="queue-meta">${escapeHtml(project.team)} · ${escapeHtml(project.repo)}</div></div><div class="queue-signal"><strong>${escapeHtml(project.signal)}</strong><span class="mono">${escapeHtml(project.signalDetail)}</span></div><button class="queue-action view-project" data-project-id="${escapeHtml(project.id)}">View project</button></div>`;
  };
  return `<section class="panel calendar-panel"><div class="panel-header"><div><h2 class="panel-title">Portfolio as of ${escapeHtml(formatDate(state.calendarDate))}</h2><p class="panel-subtitle">${weekLabel ? `Week of ${escapeHtml(weekLabel)} · the verdict as it was judged that week, not re-scored against today's rules.` : 'No snapshot has been computed for this week.'}</p></div></div><div class="queue-list">${items.length ? items.map(rowMarkup).join('') : '<div class="history-empty" style="padding:20px;">No projects to show.</div>'}</div></section>`;
}

function renderOverview() {
  const projects = state.projects;
  const attention = projects.filter(isAttentionProject);
  const clear = projects.filter((project) => project.statusClass === 'clear');
  const insufficient = projects.filter((project) => project.statusClass === 'data');
  const active = projects.filter(isActiveProject);
  return `<div class="page-heading"><div><span class="eyebrow">Weekly portfolio review</span><h1>Good morning</h1></div><div class="heading-actions"><div class="date-chip">${icon('calendar')} ${escapeHtml(snapshotMetaFor().snapshotWeekStart ? `${formatDate(snapshotMetaFor().snapshotWeekStart)}${snapshotMetaFor().snapshotWeekEnd ? ` – ${formatDate(snapshotMetaFor().snapshotWeekEnd)}` : ''}` : 'Current snapshot')}</div>${calendarControlMarkup()}</div></div>
    ${statGridMarkup(active, attention, clear, insufficient)}`;
}

// A stat card that is not a filter: the delivery figures describe the whole
// portfolio and have no corresponding project filter to switch to, so they
// render as plain tiles rather than buttons.
function deliveryCardMarkup(accent, label, iconName, value, foot) {
  const shown = value === null || value === undefined ? '—' : value;
  return `<div class="stat-card ${accent}"><span class="stat-label"><span>${escapeHtml(label)}</span><span class="stat-icon">${icon(iconName)}</span></span><span class="stat-value">${escapeHtml(String(shown))}</span><span class="stat-foot">${escapeHtml(foot)}</span></div>`;
}

// Second row of the stat grid: what the portfolio has in flight, as opposed to
// the status counts above. Contributor count is deliberately NOT shown: the
// identity_map table is empty, so /portfolio/delivery can only count distinct
// author strings -- display names and usernames for the same person both
// count -- and a headline figure of 'people' built from that would be wrong. Everything here comes from the Gitea sync via
// /portfolio/delivery; a null renders as "--" so "not synced yet" never
// masquerades as a real zero.
function deliveryGridMarkup() {
  const d = state.delivery;
  const oldest = d && typeof d.oldest_open_pr_days === 'number' ? `${Math.round(d.oldest_open_pr_days)}d` : null;
  return [
    deliveryCardMarkup('total', 'Open PRs', 'pull', d ? d.open_prs : null, 'Awaiting review or merge'),
    deliveryCardMarkup('attention', 'Oldest open PR', 'calendar', oldest, 'Longest wait in the portfolio'),
    deliveryCardMarkup('data', 'Branches ahead', 'activity', d ? d.branches_ahead : null, 'Work not yet on the default branch'),
    deliveryCardMarkup('clear', 'Open issues', 'message', d ? d.open_issues : null, 'Tracked across all repositories'),
  ].join('');
}

// The stat cards are Overview's whole body now that the per-project week-signal
// list has moved to the inventory page, so they always render. They used to be
// suppressed whenever that list was open.
function statGridMarkup(active, attention, clear, insufficient) {
  return `<div class="stat-grid"><button class="stat-card total dashboard-filter" data-dashboard-filter="Active projects" type="button"><span class="stat-label"><span>Active projects</span><span class="stat-icon">${icon('folder')}</span></span><span class="stat-value">${active.length}</span><span class="stat-foot">Current snapshot</span></button><button class="stat-card attention dashboard-filter" data-dashboard-filter="Needs attention" type="button"><span class="stat-label"><span>Need attention</span><span class="stat-icon">${icon('triangle')}</span></span><span class="stat-value">${attention.length}</span><span class="stat-foot">Warnings with evidence</span></button><button class="stat-card clear dashboard-filter" data-dashboard-filter="Clear" type="button"><span class="stat-label"><span>Clear</span><span class="stat-icon">${icon('check-circle')}</span></span><span class="stat-value">${clear.length}</span><span class="stat-foot">Explicit server status only</span></button><button class="stat-card data dashboard-filter" data-dashboard-filter="Insufficient data" type="button"><span class="stat-label"><span>Insufficient data</span><span class="stat-icon">${icon('database')}</span></span><span class="stat-value">${insufficient.length}</span><span class="stat-foot">Signals remain suppressed</span></button>${deliveryGridMarkup()}</div>`;
}

function renderProjects() {
  const filters = PROJECT_FILTERS;
  const filtered = currentFilter === 'All projects'
    ? state.projects
    : currentFilter === 'Active projects'
      ? state.projects.filter(isActiveProject)
      : currentFilter === 'Needs attention'
        ? state.projects.filter(isAttentionProject)
        : state.projects.filter((project) => project.status === currentFilter);
  return `<div class="page-heading"><div><span class="eyebrow">Portfolio inventory</span><h1>All projects</h1></div><div class="heading-actions">${progressControlMarkup()}</div></div>
    ${progressPanelMarkup()}
    <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Project inventory</h2><p class="panel-subtitle">${filtered.length} of ${state.projects.length} projects shown</p></div><div class="filter-row">${filters.map((filter) => `<button class="filter-button ${currentFilter === filter ? 'active' : ''}" data-filter="${escapeHtml(filter)}">${escapeHtml(filter)}</button>`).join('')}</div></div><div class="table-scroll"><table class="projects-table"><thead><tr><th>Project</th><th>Status</th><th>Signal</th><th>Active</th><th>Coverage</th></tr></thead><tbody>${filtered.length ? filtered.map((project) => {
      const identityCell = `<td><div class="table-project">${monogram(project, 'sm')}<div><strong>${escapeHtml(project.name)}</strong><span>${escapeHtml(project.team)} · ${escapeHtml(project.repo)}</span></div></div></td>`;
      // A project with no snapshot keeps its identity cell and replaces the
      // four data columns with the lazy placeholder, so the table's shape
      // holds steady as rows fill in.
      if (lazyRowState(project.id)) return `<tr class="project-row lazy-row" data-project-id="${escapeHtml(project.id)}"${lazyRowAttrs(project.id)}>${identityCell}${lazyCellMarkup(project.id, 4)}</tr>`;
      return `<tr class="project-row" data-project-id="${escapeHtml(project.id)}">${identityCell}<td>${statusPill(project)}</td><td>${escapeHtml(project.signal)}</td><td><span class="freshness">${escapeHtml(project.lastActivity)}</span></td><td><span class="freshness">${escapeHtml(formatPercent(project.dataCompletenessPct))}</span></td></tr>`;
    }).join('') : '<tr><td colspan="5"><div class="history-empty">No projects returned for this view.</div></td></tr>'}</tbody></table></div><div class="table-footer"><span>Ownership metadata is included in each project profile.</span></div></section>`;
}

function insightsProjectCell(project) {
  return `<div class="insights-project-cell">${monogram(project, 'sm')}<div class="insights-project-copy"><div><strong>${escapeHtml(project.name)}</strong><span>${escapeHtml(project.team)}</span></div>${statusPill(project)}</div></div>`;
}

function renderInsights() {
  const showContributorColumn = state.projects.some((project) => hasOwn(project.metrics, 'active_contributors'));
  const contributorHeader = showContributorColumn ? '<th>Active contributors <span>aggregate only</span></th>' : '';
  const contributorCell = (project) => showContributorColumn ? `<td>${hasOwn(project.metrics, 'active_contributors') ? chartCaption('', project.metrics.active_contributors, project.seriesBaselines.contributors?.[0]) : '<div class="chart-caption"><span class="chart-caption-label"></span><span class="chart-caption-value">—</span></div>'}</td>` : '';
  return `<div class="page-heading"><div><span class="eyebrow">Combined view · last 8 weeks</span><h1>Insights</h1><p>Aggregate activity, review flow, and contributor counts where the server aggregation floor permits.</p>${snapshotMetaMarkup()}</div></div><section class="panel"><div class="table-scroll"><table class="insights-table"><thead><tr><th>Project</th><th>Activity <span>days/wk</span></th><th>Open PRs</th><th>Review latency</th>${contributorHeader}</tr></thead><tbody>${state.projects.length ? state.projects.map((project) => {
      if (lazyRowState(project.id)) return `<tr class="insights-row lazy-row" data-project-id="${escapeHtml(project.id)}"${lazyRowAttrs(project.id)}><td>${insightsProjectCell(project)}</td>${lazyCellMarkup(project.id, showContributorColumn ? 4 : 3)}</tr>`;
      return `<tr class="insights-row" data-project-id="${escapeHtml(project.id)}"><td>${insightsProjectCell(project)}</td><td>${chartCaption('', metricValue(project.metrics, 'active_days', lastValue(project.series.activity)), project.seriesBaselines.activity?.[0])}</td><td>${chartCaption('', metricValue(project.metrics, 'open_prs', lastValue(project.series.openPRs)), project.seriesBaselines.openPRs?.[0])}</td><td>${chartCaption('', metricValue(project.metrics, 'review_latency_days', lastValue(project.series.reviewLatency)), project.seriesBaselines.reviewLatency?.[0], 'd')}</td>${contributorCell(project)}</tr>`;
    }).join('') : `<tr><td colspan="${showContributorColumn ? 5 : 4}"><div class="history-empty">No project metrics returned.</div></td></tr>`}</tbody></table></div></section>`;
}

// Banner shown on a profile opened from the portfolio-as-of-date calendar, so
// a historical week can never be mistaken for live data. Reuses the date-chip
// and "Back to live ×" affordances the calendar controls already use.
function asOfBannerMarkup() {
  if (!selectedProjectAsOfDate) return '';
  return `<div class="as-of-banner"><div class="date-chip">${icon('calendar')} As of ${escapeHtml(formatDate(selectedProjectAsOfDate))}</div><span>Historical snapshot · the verdict as it was judged that week, not today's signals.</span><button class="text-button" id="profile-live">Back to live ×</button></div>`;
}

function profileBackLinkMarkup() {
  const label = selectedProjectAsOfDate ? `Back to portfolio as of ${formatDate(selectedProjectAsOfDate)}` : 'Back to inventory';
  return `<button class="text-button back-link" id="profile-back"><span>←</span> ${escapeHtml(label)}</button>`;
}

// A project can have no persisted snapshot for the selected week. Say so
// plainly -- falling back to the live profile here would silently reintroduce
// exactly the present-data-under-a-past-date confusion this view fixes.
function renderAsOfEmptyProfile() {
  const listed = state.projects.find((project) => project.id === selectedProjectId);
  const name = listed ? listed.name : 'This project';
  return `<div class="page-heading"><div>${profileBackLinkMarkup()}<div class="profile-title-row">${listed ? monogram({ ...listed, statusClass: '' }, 'lg') : ''}<div><h1>${escapeHtml(name)}</h1><p>${escapeHtml(listed ? `${listed.team} · ${listed.repo}` : 'No snapshot for this week')}</p></div></div></div></div>${asOfBannerMarkup()}<section class="panel"><div class="empty-view"><div class="empty-view-inner"><div class="empty-view-icon">${icon('database')}</div><h2>No snapshot for this week</h2><p>No snapshot was computed for ${escapeHtml(name)} for the week of ${escapeHtml(formatDate(selectedProjectAsOfDate))}, so there is nothing to show as of that date. Return to live to see the current profile.</p></div></div></section>`;
}

function renderProjectProfile(project) {
  const meta = statusMeta[project.statusClass] || statusMeta.data;
  return `<div class="page-heading"><div>${profileBackLinkMarkup()}<div class="profile-title-row">${monogram(project, 'lg')}<div><h1>${escapeHtml(project.name)}</h1><p>${escapeHtml(project.team)} · ${escapeHtml(project.repo)}</p>${snapshotMetaMarkup(project, true)}</div>${statusPill(project)}</div></div></div>${asOfBannerMarkup()}<div class="detail-status wide ${escapeHtml(project.statusClass)}"><strong>${escapeHtml(project.status)}</strong><span>${escapeHtml(meta.copy)}</span></div>${healthAssessmentCard(project)}${metricCharts(project)}${aggregateMetricsSection(project)}<div class="profile-grid"><section class="panel"><div class="panel-header"><div><h2 class="panel-title">Evidence</h2><p class="panel-subtitle">Warnings require inspectable source evidence.</p></div><span class="eyebrow">${escapeHtml(formatPercent(project.dataCompletenessPct))} complete</span></div><div class="evidence-section wide">${evidenceList(project, 'lg')}</div><div class="detail-actions"><button class="secondary-button" id="add-context">Add context</button><button class="primary-button" id="confirm-review">${escapeHtml(meta.cta)} <span>→</span></button></div></section></div>`;
}

function loadingPanel(message) {
  return `<div class="empty-view"><div class="empty-view-inner"><div class="empty-view-icon">${icon('database')}</div><h2>Loading</h2><p>${escapeHtml(message)}</p></div></div>`;
}

function errorPanel(message, retryId = 'retry-latest') {
  return `<div class="empty-view"><div class="empty-view-inner"><div class="empty-view-icon">${icon('triangle')}</div><h2>Couldn’t load this view</h2><p>${escapeHtml(message)}</p><button class="primary-button" id="${retryId}" style="margin-top:18px;">Try again</button></div></div>`;
}

function renderLoading() {
  return `<div class="page-heading"><div><span class="eyebrow">Connected data</span><h1>Loading App Dev Horizon</h1><p>Requesting the latest immutable snapshot.</p></div></div>${loadingPanel('Fetching /snapshots/latest…')}`;
}

function renderGlobalError() {
  return `<div class="page-heading"><div><span class="eyebrow">Connected data</span><h1>App Dev Horizon is unavailable</h1><p>The latest snapshot could not be loaded.</p></div></div>${errorPanel(state.error?.message || 'The latest snapshot request failed.')}`;
}

// `preserveScroll` is for renders that are a data update rather than a
// navigation -- a lazy row filling in must not yank the page back to the top,
// which would also change which rows are on screen and so which ones the
// observer decides to compute next.
function render(preserveScroll = false) {
  const scrollY = preserveScroll ? window.scrollY : 0;
  const appView = document.getElementById('app-view');
  if (state.loading) appView.innerHTML = renderLoading();
  else if (state.error) appView.innerHTML = renderGlobalError();
  else if (currentView === 'overview') appView.innerHTML = renderOverview();
  else if (currentView === 'projects') appView.innerHTML = renderProjects();
  else if (currentView === 'insights') appView.innerHTML = renderInsights();
  else if (currentView === 'progress') appView.innerHTML = renderProgressDetail();
  else if (currentView === 'profile') {
    const project = selectedProject();
    const asOfEntry = selectedProjectAsOfDate ? state.projectAsOf[`${selectedProjectId}@${selectedProjectAsOfDate}`] : null;
    appView.innerHTML = state.profileLoading
      ? loadingPanel(selectedProjectAsOfDate ? `Loading the snapshot as of ${formatDate(selectedProjectAsOfDate)}…` : 'Loading project snapshots…')
      : state.profileError ? errorPanel(state.profileError, 'retry-profile')
        : asOfEntry && !asOfEntry.hasData ? renderAsOfEmptyProfile()
          : !project ? errorPanel('This project is outside the current access scope.')
            : renderProjectProfile(project);
  }
  // Lets CSS target a single view without inspecting its contents. Overview
  // uses it to fill the viewport and centre its stat row vertically, which
  // must not happen on the content-driven views.
  appView.dataset.view = (state.loading || state.error) ? 'loading' : currentView;
  const navActiveView = (currentView === 'profile' || currentView === 'progress') ? 'projects' : currentView;
  document.querySelectorAll('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.view === navActiveView));
  updateChrome();
  bindViewEvents();
  bindLazyCompute();
  window.scrollTo(0, scrollY);
}

function selectedProject() {
  // A profile opened as of a past date resolves only from the point-in-time
  // cache; it must never fall back to the live snapshot or the live list.
  if (selectedProjectAsOfDate) return state.projectAsOf[`${selectedProjectId}@${selectedProjectAsOfDate}`]?.project || null;
  return state.projectSnapshots[selectedProjectId] || state.projects.find((project) => project.id === selectedProjectId) || null;
}

function updateChrome() {
  const count = document.querySelector('.nav-count');
  if (count) count.textContent = String(state.projects.filter((project) => project.statusClass === 'risk' || project.statusClass === 'watch').length);
}

function showToast(message, isError = false) {
  const toast = document.getElementById('toast');
  document.getElementById('toast-message').textContent = message;
  toast.classList.toggle('error', isError);
  toast.classList.add('show');
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => toast.classList.remove('show'), 3000);
}

async function loadLatestSnapshot() {
  state.loading = true;
  state.error = null;
  render();
  try {
    const raw = await requestJson('/snapshots/latest');
    state.snapshot = normalizeSnapshot(raw);
    state.projects = state.snapshot.projects;
    state.lazyWeekStart = firstDefined(raw?.lazy_week_start, null);
    state.lazyComputable = Boolean(raw?.computable);
    state.lazyMissing = new Set(asArray(raw?.missing_project_ids));
    state.lazyComputing = new Set();
    state.lazyErrors = {};
    state.loading = false;
    if (!selectedProjectId && state.projects[0]) selectedProjectId = state.projects[0].id;
    render();
  } catch (error) {
    state.loading = false;
    state.error = error;
    render();
  }
}

// Portfolio-wide delivery facts for the Overview stat row. Cache-only on the
// server, so it is cheap and never blocks the page: a failure leaves the extra
// cards showing "--" rather than surfacing an error over the status counts.
async function loadPortfolioDelivery() {
  try {
    state.delivery = await requestJson('/portfolio/delivery');
  } catch {
    state.delivery = null;
  }
  render();
}

// ---------------------------------------------------------------------
// Viewport-gated lazy compute. Both lazy surfaces -- the live dashboard
// tables and the as-of-date calendar -- mark a row with data-lazy-project
// when it has no snapshot yet; bindLazyCompute() observes those rows and
// fires the POST only once one is on screen. Nothing here is ever driven by
// a button: a row that is visible is a row that gets computed.
// ---------------------------------------------------------------------

// Start the request slightly before the row is actually visible, so the
// result usually lands by the time the reviewer has scrolled to it.
const LAZY_ROOT_MARGIN = '200px';
let lazyObserver = null;

// Which of the two lazy surfaces a row belongs to. They write to different
// state (state.projects vs. state.calendarResult.projects) and post to a
// different week, so the row carries its channel rather than the observer
// guessing from the current view.
function lazyComputeFor(kind, projectId) {
  if (!projectId) return;
  if (kind === 'calendar') computeCalendarProjectSnapshot(projectId);
  else computeLatestProjectSnapshot(projectId);
}

function bindLazyCompute() {
  const rows = document.querySelectorAll('[data-lazy-project]');
  if (!('IntersectionObserver' in window)) {
    // Without observer support, compute every pending row immediately. That
    // costs more requests than the lazy path, but a browser that cannot
    // observe would otherwise sit on placeholder rows forever.
    rows.forEach((node) => lazyComputeFor(node.dataset.lazyKind, node.dataset.lazyProject));
    return;
  }
  // render() replaces the view's whole innerHTML, so every observed node is
  // destroyed on each paint; the observer is rebuilt here rather than once
  // at boot. The observed set only ever shrinks -- a row that starts
  // computing loses its data-lazy-project attribute -- so this cannot loop.
  if (lazyObserver) lazyObserver.disconnect();
  lazyObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      observer.unobserve(entry.target);
      lazyComputeFor(entry.target.dataset.lazyKind, entry.target.dataset.lazyProject);
    });
  }, { rootMargin: LAZY_ROOT_MARGIN });
  rows.forEach((node) => lazyObserver.observe(node));
}

async function computeLatestProjectSnapshot(projectId) {
  if (!state.lazyComputable || !state.lazyWeekStart) return;
  if (!state.lazyMissing.has(projectId) || state.lazyComputing.has(projectId)) return;
  state.lazyComputing.add(projectId);
  delete state.lazyErrors[projectId];
  render(true);
  try {
    const raw = await requestJson(`/projects/${encodeURIComponent(projectId)}/snapshots/at?date=${encodeURIComponent(state.lazyWeekStart)}`, { method: 'POST' });
    const updated = normalizeProject(raw?.project, state.snapshot || {});
    state.projects = state.projects.map((project) => (project.id === projectId ? updated : project));
    // state.snapshot.projects is what selectedProject() falls back to, so it
    // has to track the list rather than keep serving the pre-compute row.
    if (state.snapshot) state.snapshot.projects = state.projects;
    state.lazyMissing.delete(projectId);
  } catch (error) {
    // Left in lazyMissing so the row keeps its placeholder and offers a
    // retry -- but it is no longer observed, so scrolling past it again
    // cannot silently re-spend an LLM request on a project that just failed.
    state.lazyErrors[projectId] = error;
  } finally {
    state.lazyComputing.delete(projectId);
    render(true);
  }
}

// Row state for a project the live dashboard has no snapshot for. null means
// the project has real data and renders normally.
function lazyRowState(projectId) {
  if (state.lazyComputing.has(projectId)) return 'computing';
  if (state.lazyErrors[projectId]) return 'error';
  if (!state.lazyMissing.has(projectId)) return null;
  return state.lazyComputable ? 'pending' : 'unavailable';
}

// Only a 'pending' row is observed. A computing row has a request in flight,
// an errored one waits for an explicit retry, and an unavailable one has no
// LLM configured to compute it with.
function lazyRowAttrs(projectId, kind = 'latest') {
  return lazyRowState(projectId) === 'pending'
    ? ` data-lazy-project="${escapeHtml(projectId)}" data-lazy-kind="${escapeHtml(kind)}"`
    : '';
}

function lazyCellMarkup(projectId, colspan, kind = 'latest') {
  const status = lazyRowState(projectId);
  const body = status === 'computing'
    ? '<span class="lazy-note"><span class="spinner"></span>Computing this week’s signal…</span>'
    : status === 'error'
      ? `<button class="lazy-retry" data-project-id="${escapeHtml(projectId)}" data-lazy-kind="${escapeHtml(kind)}">Could not compute — Retry</button>`
      : status === 'unavailable'
        ? '<span class="lazy-note mono">No snapshot yet; LLM signal is not configured.</span>'
        : '<span class="lazy-note mono">Not computed yet — scroll into view to compute.</span>';
  return `<td colspan="${colspan}">${body}</td>`;
}

async function loadCalendarSnapshot(dateStr) {
  state.calendarDate = dateStr;
  state.calendarLoading = true;
  state.calendarError = null;
  state.calendarComputing = new Set();
  state.calendarComputeErrors = {};
  render();
  try {
    const raw = await requestJson(`/snapshots/at?date=${encodeURIComponent(dateStr)}`);
    state.calendarResult = normalizeSnapshot(raw);
    state.calendarResult.hasData = Boolean(raw?.has_data);
    state.calendarResult.missingProjectIds = asArray(raw?.missing_project_ids);
    state.calendarResult.computable = Boolean(raw?.computable);
    state.calendarLoadedDate = dateStr;
    state.calendarLoading = false;
    render();
  } catch (error) {
    state.calendarLoading = false;
    state.calendarLoadedDate = null; // leave it refetchable when the route is revisited
    state.calendarError = error;
    render();
  }
}

async function computeCalendarProjectSnapshot(projectId) {
  if (!state.calendarDate || state.calendarComputing.has(projectId)) return;
  state.calendarComputing.add(projectId);
  delete state.calendarComputeErrors[projectId];
  render(true);
  try {
    const raw = await requestJson(`/projects/${encodeURIComponent(projectId)}/snapshots/at?date=${encodeURIComponent(state.calendarDate)}`, { method: 'POST' });
    const updated = normalizeProject(raw?.project, state.calendarResult || {});
    const projects = state.calendarResult.projects.map((project) => (project.id === projectId ? updated : project));
    state.calendarResult = { ...state.calendarResult, projects, missingProjectIds: state.calendarResult.missingProjectIds.filter((id) => id !== projectId) };
  } catch (error) {
    state.calendarComputeErrors[projectId] = error;
  } finally {
    state.calendarComputing.delete(projectId);
    render(true);
  }
}

// Clearing the portfolio calendar *is* a navigation -- #/overview?asOf=... to
// plain #/overview -- so it goes through the router rather than mutating state
// directly, which is what keeps the URL and the screen from drifting apart.
function clearCalendarSnapshot() {
  goto({ view: 'overview', asOf: null });
}

// ---------------------------------------------------------------------
// Projects-page cumulative-progress-as-of-date calendar. Picking a date
// automatically computes every project's progress (bounded client-side
// concurrency, one request per project) -- no per-project button.
// ---------------------------------------------------------------------

const PROGRESS_FAN_OUT_CONCURRENCY = 3;

async function loadProgressAt(dateStr) {
  const runId = ++state.progressRunId;
  state.progressDate = dateStr;
  state.progressResult = {};
  state.progressLoading = true;
  state.progressError = null;
  render();

  let raw;
  try {
    raw = await requestJson(`/progress/at?date=${encodeURIComponent(dateStr)}`);
  } catch (error) {
    if (runId !== state.progressRunId) return;
    state.progressLoading = false;
    state.progressLoadedDate = null; // leave it refetchable when the route is revisited
    state.progressError = error;
    render();
    return;
  }
  if (runId !== state.progressRunId) return;

  const missing = new Set(asArray(raw?.missing_project_ids));
  const results = {};
  asArray(raw?.projects).forEach((project) => {
    if (!missing.has(project.id)) results[project.id] = { state: 'done', data: project };
  });
  missing.forEach((id) => { results[id] = { state: 'pending' }; });
  state.progressResult = results;
  state.progressLoading = false;
  state.progressLoadedDate = dateStr;
  state.progressComputable = Boolean(raw?.computable);
  render();

  const queue = Array.from(missing);
  const worker = async () => {
    while (queue.length) {
      const projectId = queue.shift();
      await computeProjectProgress(projectId, dateStr, runId);
    }
  };
  await Promise.all(Array.from({ length: PROGRESS_FAN_OUT_CONCURRENCY }, worker));
}

async function computeProjectProgress(projectId, dateStr, runId) {
  try {
    const raw = await requestJson(`/projects/${encodeURIComponent(projectId)}/progress/at?date=${encodeURIComponent(dateStr)}`, { method: 'POST' });
    if (runId !== state.progressRunId) return; // a newer date pick superseded this request
    state.progressResult[projectId] = { state: 'done', data: raw?.project };
    render(true);
  } catch (error) {
    if (runId !== state.progressRunId) return;
    state.progressResult[projectId] = { state: 'error', error };
    render(true);
  }
}

// Cold-load path for #/projects/:id/progress?asOf=... -- a deep link, a
// refresh, or Back onto a detail view whose checkpoint is no longer in memory.
// It reads the same cache-only GET the list view does, but computes at most
// the ONE project the URL names; running the portfolio fan-out here would
// spend an LLM request per project to render a single-project screen.
async function loadProgressForProject(projectId, dateStr) {
  const runId = ++state.progressRunId;
  state.progressDate = dateStr;
  state.progressResult = { [projectId]: { state: 'pending' } };
  state.progressLoading = false;
  state.progressError = null;
  render();

  let raw;
  try {
    raw = await requestJson(`/progress/at?date=${encodeURIComponent(dateStr)}`);
  } catch (error) {
    if (runId !== state.progressRunId) return;
    state.progressResult[projectId] = { state: 'error', error };
    render();
    return;
  }
  if (runId !== state.progressRunId) return;

  state.progressComputable = Boolean(raw?.computable);
  const missing = new Set(asArray(raw?.missing_project_ids));
  const cached = asArray(raw?.projects).find((project) => project.id === projectId);
  if (cached && !missing.has(projectId)) {
    state.progressResult[projectId] = { state: 'done', data: cached };
    render();
    return;
  }
  await computeProjectProgress(projectId, dateStr, runId);
}

function retryProjectProgress(projectId) {
  if (!state.progressDate) return;
  const runId = state.progressRunId;
  state.progressResult[projectId] = { state: 'pending' };
  render(true);
  computeProjectProgress(projectId, state.progressDate, runId);
}

// Like clearCalendarSnapshot: a route change (#/projects?asOf=... -> #/projects),
// so the router owns it and the in-flight fan-out is orphaned by setProgressDate.
function clearProgress() {
  goto({ view: 'projects', filter: currentFilter, asOf: null });
}

function progressControlMarkup() {
  const today = new Date().toISOString().slice(0, 10);
  return `<div class="calendar-control"><label for="progress-date-input">${icon('calendar')}<span>View progress as of</span></label><input type="date" id="progress-date-input" max="${today}" value="${escapeHtml(state.progressDate || '')}" />${state.progressDate ? '<button class="text-button" id="progress-clear">Back to live ×</button>' : ''}</div>`;
}

// 'stalled' is retired; kept here only so a checkpoint persisted before the
// change still renders a label rather than a blank chip.
const TRAJECTORY_LABELS = { accelerating: 'Accelerating', steady: 'Steady', slowing: 'Slowing', stalled: 'Slowing', unknown: '' };

function progressRowMarkup(projectId) {
  const entry = state.progressResult[projectId];
  const meta = state.projects.find((project) => project.id === projectId) || { id: projectId, name: projectId, team: '', repo: '' };
  if (!entry || entry.state === 'pending') {
    return `<div class="queue-item">${monogram(meta)}<div class="queue-main"><div class="queue-name-line"><span class="queue-name">${escapeHtml(meta.name)}</span></div><div class="queue-meta">${escapeHtml(meta.team)} · ${escapeHtml(meta.repo)}</div></div><span class="queue-action compute-pending"><span class="spinner"></span> Computing progress…</span></div>`;
  }
  if (entry.state === 'error') {
    return `<div class="queue-item">${monogram(meta)}<div class="queue-main"><div class="queue-name-line"><span class="queue-name">${escapeHtml(meta.name)}</span></div><div class="queue-meta">${escapeHtml(meta.team)} · ${escapeHtml(meta.repo)}</div></div><button class="queue-action progress-retry" data-project-id="${escapeHtml(projectId)}">Could not compute — Retry</button></div>`;
  }
  const project = entry.data || {};
  const fidelity = project.weeksTotal ? `${project.weeksDeepJudged} of ${project.weeksTotal} weeks reviewed in depth` : '';
  // One signal per row: the attention status pill alone. Trajectory used to ride
  // beside it as a second chip, which read as two competing verdicts on the same
  // project; it now shows only in the checkpoint detail, where it is labelled and
  // sits beside Work to date and Confidence.
  return `<div class="queue-item">${monogram(project)}<div class="queue-main"><div class="queue-name-line"><span class="queue-name">${escapeHtml(project.name)}</span><span class="status-pill status-${escapeHtml(project.statusClass)}">${escapeHtml(project.status)}</span></div><div class="queue-meta">${escapeHtml(project.team)} · ${escapeHtml(project.repo)}</div></div><div class="queue-signal"><strong>${escapeHtml(project.headline || '')}</strong>${fidelity ? `<span class="mono">${escapeHtml(fidelity)}</span>` : ''}</div><button class="queue-action view-progress" data-project-id="${escapeHtml(projectId)}">View progress</button></div>`;
}

function progressPanelMarkup() {
  if (!state.progressDate) return '';
  if (state.progressLoading) return `<section class="panel calendar-panel">${loadingPanel('Loading portfolio progress…')}</section>`;
  if (state.progressError) return `<section class="panel calendar-panel">${errorPanel(state.progressError.message || 'That date could not be loaded.', 'retry-progress')}</section>`;
  const ids = Object.keys(state.progressResult);
  const subtitle = state.progressComputable
    ? 'Cumulative standing as of this date, built from evidence available up to it -- computed automatically for every project.'
    : 'LLM signal is not configured, so progress cannot be computed.';
  return `<section class="panel calendar-panel"><div class="panel-header"><div><h2 class="panel-title">Portfolio progress as of ${escapeHtml(formatDate(state.progressDate))}</h2><p class="panel-subtitle">${escapeHtml(subtitle)}</p></div></div><div class="queue-list">${ids.length ? ids.map(progressRowMarkup).join('') : '<div class="history-empty" style="padding:20px;">No projects to show.</div>'}</div></section>`;
}

// ---------------------------------------------------------------------
// Cumulative-checkpoint detail view (the drill-down from a progress row).
//
// Deliberately NOT the weekly-snapshot profile: a checkpoint answers
// "where does this project stand, cumulatively, as of this date", so it
// renders the checkpoint's own fields (trajectory, work to date,
// milestones, open concerns) and never a single week's metrics/series.
// Needs no fetch -- GET /progress/at and POST /projects/{id}/progress/at
// already return the whole checkpoint, which the row cached in
// state.progressResult.
// ---------------------------------------------------------------------

const WORK_LEVEL_LABELS = { none: 'None', trivial: 'Trivial', minimal: 'Minimal', moderate: 'Moderate', substantial: 'Substantial' };
const SEVERITY_LABELS = { info: 'Info', warning: 'Warning', critical: 'Critical' };

function openProgressDetail(projectId) {
  goto({ view: 'progress', projectId, asOf: state.progressDate });
}

function progressBackLinkMarkup() {
  const label = state.progressDate ? `Back to portfolio progress as of ${formatDate(state.progressDate)}` : 'Back to inventory';
  return `<button class="text-button back-link" id="progress-back"><span>←</span> ${escapeHtml(label)}</button>`;
}

function progressBannerMarkup() {
  return `<div class="as-of-banner"><div class="date-chip">${icon('calendar')} Cumulative standing as of ${escapeHtml(formatDate(state.progressDate))}</div><span>Cumulative-to-date synthesis · everything known about this project up to this date, not a single week's snapshot.</span></div>`;
}

function checkpointRefs(refs) {
  const list = asArray(refs).filter((ref) => typeof ref === 'string' && ref.trim());
  if (!list.length) return '';
  return `<ul class="checkpoint-refs">${list.map((ref) => `<li>${escapeHtml(ref)}</li>`).join('')}</ul>`;
}

function checkpointItems(items, emptyCopy) {
  const list = asArray(items);
  if (!list.length) return `<p class="assessment-empty">${escapeHtml(emptyCopy)}</p>`;
  return `<ul class="assessment-list">${list.map((item) => {
    const severity = typeof item?.severity === 'string' ? item.severity : null;
    const chip = severity ? `<span class="severity-chip severity-${escapeHtml(severity)}">${escapeHtml(SEVERITY_LABELS[severity] || severity)}</span>` : '';
    return `<li><strong>${escapeHtml(item?.text || '')}</strong>${chip}${checkpointRefs(item?.evidence)}</li>`;
  }).join('')}</ul>`;
}

function checkpointNotes(items, emptyCopy) {
  const list = asArray(items).filter((item) => typeof item === 'string' && item.trim());
  if (!list.length) return `<p class="assessment-empty">${escapeHtml(emptyCopy)}</p>`;
  return `<ul class="assessment-list">${list.map((item) => `<li><strong>${escapeHtml(item)}</strong></li>`).join('')}</ul>`;
}

function progressDetailShell(name, body) {
  return `<div class="page-heading"><div>${progressBackLinkMarkup()}<div class="profile-title-row"><div><h1>${escapeHtml(name)}</h1><p>Cumulative progress</p></div></div></div></div>${progressBannerMarkup()}<section class="panel">${body}</section>`;
}

function renderProgressEmptyDetail(name, reason) {
  return progressDetailShell(name, `<div class="empty-view"><div class="empty-view-inner"><div class="empty-view-icon">${icon('database')}</div><h2>No cumulative progress to show</h2><p>${escapeHtml(reason)}</p></div></div>`);
}

function renderProgressDetail() {
  const projectId = selectedProgressProjectId;
  const entry = projectId ? state.progressResult[projectId] : null;
  const listed = state.projects.find((project) => project.id === projectId);
  const fallbackName = listed ? listed.name : (projectId || 'This project');
  // Reached on a deep link or a refresh: the checkpoint isn't in memory yet
  // and loadProgressForProject is fetching (or computing) it. state.progressLoading
  // covers the frame between the route being applied and that fetch starting.
  if (state.progressLoading || (entry && entry.state === 'pending')) {
    return progressDetailShell(fallbackName, loadingPanel(`Loading cumulative progress as of ${formatDate(state.progressDate)}…`));
  }
  if (entry && entry.state === 'error') {
    return progressDetailShell(fallbackName, errorPanel(entry.error?.message || 'This project’s progress could not be loaded.', 'retry-progress-detail'));
  }
  if (!entry || entry.state !== 'done' || !entry.data) {
    return renderProgressEmptyDetail(fallbackName, 'This project’s progress is no longer loaded for the selected date. Return to the portfolio progress list and pick the date again.');
  }
  const project = entry.data;
  // A checkpoint the server had nothing to build from: say so rather than
  // dressing an empty synthesis up as a verdict.
  if (!project.checkpointId) {
    return renderProgressEmptyDetail(project.name || fallbackName, `No cumulative-progress checkpoint has been computed for ${project.name || fallbackName} as of ${formatDate(state.progressDate)}.`);
  }

  const trajectoryLabel = TRAJECTORY_LABELS[project.trajectory] || 'Unknown';
  const workLabel = WORK_LEVEL_LABELS[project.workToDate] || '—';
  const confidence = finiteNumber(project.confidence);
  const fidelityBits = [];
  if (project.weeksTotal) {
    const shallow = project.weeksTotal - project.weeksDeepJudged;
    fidelityBits.push(`${project.weeksDeepJudged} of ${project.weeksTotal} weeks reviewed in depth${shallow > 0 ? `; the other ${shallow} counted from commit metadata only` : ''}`);
  }
  if (project.historyTruncated) fidelityBits.push('history was truncated, so older activity may be missing');
  if (project.isProvisional) fidelityBits.push('provisional — this date falls in the current, in-progress week');
  if (project.generatedAt) fidelityBits.push(`synthesized ${formatDate(project.generatedAt, true)}`);
  const fidelity = fidelityBits.length ? `<p class="assessment-empty-body">${escapeHtml(fidelityBits.join(' · '))}</p>` : '';

  const header = `<div class="page-heading"><div>${progressBackLinkMarkup()}<div class="profile-title-row">${monogram(project, 'lg')}<div><h1>${escapeHtml(project.name)}</h1><p>${escapeHtml(project.team)} · ${escapeHtml(project.repo)}</p></div>${statusPill(project)}</div></div></div>`;
  // Everything here was previously said two or three times over: the status as
  // both the header pill and a full-width standing band, the trajectory as both
  // a header chip and a metric cell, and "as of <date>, cumulative not weekly"
  // in the back link, the banner AND the panel subtitle. Each now appears once,
  // in whichever spot carries it best — nothing was dropped from the page.
  // The narrative stands alone, directly under the as-of banner: it is the one
  // thing a reader wants first, so it gets its own tile rather than being
  // buried mid-panel between the metrics row and the milestone columns.
  const summaryTile = project.narrative
    ? `<section class="panel progress-summary"><span class="eyebrow">Summary</span><p>${escapeHtml(project.narrative)}</p></section>`
    : '';
  const summary = `<section class="panel ci-assessment"><div class="panel-header"><div><span class="eyebrow">Cumulative progress</span><h2 class="panel-title">${escapeHtml(project.headline || 'Cumulative progress')}</h2></div></div><div class="assessment-metrics"><div><span>Trajectory</span><strong class="trajectory-value trajectory-${escapeHtml(project.trajectory || 'unknown')}">${escapeHtml(trajectoryLabel)}</strong></div><div><span>Work to date</span><strong>${escapeHtml(workLabel)}</strong></div><div><span>Confidence</span><strong>${confidence === null ? '—' : `${Math.round(confidence * 100)}%`}</strong></div></div><div class="assessment-columns"><div class="assessment-block"><h3>Milestones to date</h3>${checkpointItems(project.milestones, 'No grounded milestones were recorded up to this date.')}</div><div class="assessment-block"><h3>Open concerns</h3>${checkpointItems(project.openConcerns, 'No open concerns were recorded up to this date.')}</div></div><div class="assessment-columns"><div class="assessment-block"><h3>Recommendations</h3>${checkpointNotes(project.recommendations, 'No recommendations were returned.')}</div><div class="assessment-block"><h3>Data gaps</h3>${checkpointNotes(project.dataGaps, 'No data gaps were reported.')}</div></div>${fidelity}</section>`;
  return `${header}${progressBannerMarkup()}${summaryTile}${summary}`;
}

function projectFromSnapshotResponse(raw, projectId) {
  const withProfileAssessment = (project, envelope) => {
    if (!project || typeof project !== 'object' || !envelope || typeof envelope !== 'object') return project;
    const assessment = firstDefined(envelope.healthAssessment, envelope.health_assessment, envelope.projectHealthAssessment, envelope.project_health_assessment, envelope.agent?.healthAssessment, envelope.agent?.health_assessment, null);
    return assessment && !project.healthAssessment && !project.health_assessment ? { ...project, healthAssessment: assessment } : project;
  };
  if (raw && raw.project) return withProfileAssessment(raw.project, raw);
  if (raw && raw.snapshot && Array.isArray(raw.snapshot.projects)) return raw.snapshot.projects.find((project) => project.id === projectId) || raw.snapshot.projects[0];
  if (raw && Array.isArray(raw.projects)) return raw.projects.find((project) => project.id === projectId) || raw.projects[0];
  if (raw && Array.isArray(raw.items)) return projectFromSnapshotResponse(raw.items, projectId);
  if (raw && Array.isArray(raw.snapshots)) {
    const sorted = raw.snapshots.slice().sort((left, right) => String(firstDefined(right.snapshot_week_end, right.week_end, right.generated_at, '')).localeCompare(String(firstDefined(left.snapshot_week_end, left.week_end, left.generated_at, ''))));
    return projectFromSnapshotResponse(sorted[0], projectId);
  }
  if (Array.isArray(raw)) {
    const sorted = raw.slice().sort((left, right) => String(firstDefined(right.snapshot_week_end, right.week_end, right.generated_at, '')).localeCompare(String(firstDefined(left.snapshot_week_end, left.week_end, left.generated_at, ''))));
    return sorted[0];
  }
  return raw;
}

function snapshotMetaFromResponse(raw) {
  const candidates = Array.isArray(raw) ? raw : asArray(raw?.snapshots || raw?.items);
  const latest = candidates.length ? candidates.slice().sort((left, right) => String(firstDefined(right.snapshot_week_end, right.week_end, right.generated_at, '')).localeCompare(String(firstDefined(left.snapshot_week_end, left.week_end, left.generated_at, ''))))[0] : raw;
  const envelope = snapshotEnvelope(latest);
  return { snapshotId: firstDefined(envelope.snapshot_id, envelope.snapshotId, envelope.id, null), snapshotWeekStart: firstDefined(envelope.snapshot_week_start, envelope.week_start, null), snapshotWeekEnd: firstDefined(envelope.snapshot_week_end, envelope.week_end, null), generatedAt: firstDefined(envelope.generated_at, null), ruleSetVersion: firstDefined(envelope.rule_set_version, null), dataCompletenessPct: finiteNumber(envelope.data_completeness_pct), lastSyncAt: firstDefined(envelope.last_sync_at, null) };
}

async function loadProjectSnapshots(projectId) {
  state.profileLoading = true;
  state.profileError = null;
  render();
  try {
    const raw = await requestJson(`/projects/${encodeURIComponent(projectId)}/snapshots`);
    const baseMeta = snapshotMetaFor();
    const responseMeta = snapshotMetaFromResponse(raw);
    const meta = Object.fromEntries(Object.keys(baseMeta).map((key) => [key, firstDefined(responseMeta[key], baseMeta[key])]));
    const rawProject = projectFromSnapshotResponse(raw, projectId);
    if (!rawProject || typeof rawProject !== 'object') throw new Error('No snapshot was returned for this project.');
    state.projectSnapshotMeta[projectId] = meta;
    const baseProject = state.projects.find((project) => project.id === projectId) || {};
    state.projectSnapshots[projectId] = normalizeProject({ ...baseProject, ...rawProject }, meta);
    state.profileLoading = false;
    render();
  } catch (error) {
    state.profileLoading = false;
    state.profileError = error.message || 'Project snapshots could not be loaded.';
    render();
  }
}

// Point-in-time sibling of loadProjectSnapshots. The cache-only endpoint
// serves the same _project_response shape the live endpoint does, so the same
// normalizeProject/renderProjectProfile path renders it unchanged.
async function loadProjectSnapshotAsOf(projectId, dateStr) {
  state.profileLoading = true;
  state.profileError = null;
  render();
  const key = `${projectId}@${dateStr}`;
  try {
    const raw = await requestJson(`/projects/${encodeURIComponent(projectId)}/snapshots/at?date=${encodeURIComponent(dateStr)}`);
    const meta = snapshotMetaFromResponse(raw);
    state.projectSnapshotMeta[key] = meta;
    // Deliberately no merge with the live project record: filling gaps from
    // today's data is what made the historical view misleading before.
    state.projectAsOf[key] = raw?.has_data
      ? { hasData: true, project: normalizeProject(raw.project, meta) }
      : { hasData: false, project: null };
    state.profileLoading = false;
    render();
  } catch (error) {
    state.profileLoading = false;
    state.profileError = error.message || `The snapshot as of ${formatDate(dateStr)} could not be loaded.`;
    render();
  }
}

// Opens a profile, live or as of a captured date, from wherever it was clicked.
function openProject(projectId, asOfDate = null) {
  goto({ view: 'profile', projectId, asOf: asOfDate });
}

function reloadProfile() {
  if (!selectedProjectId) return;
  if (selectedProjectAsOfDate) return loadProjectSnapshotAsOf(selectedProjectId, selectedProjectAsOfDate);
  return loadProjectSnapshots(selectedProjectId);
}

// =====================================================================
// Router
//
// Route table (hash routes, see buildHash/parseRoute below):
//
//   #/overview                                  overview, live portfolio
//   #/overview?asOf=YYYY-MM-DD                  overview, portfolio-as-of calendar open
//   #/insights                                  insights
//   #/projects                                  project inventory
//   #/projects?filter=At%20risk                 inventory, filter chip applied
//   #/projects?asOf=YYYY-MM-DD                  inventory, cumulative-progress calendar open
//   #/projects/:projectId                       project profile, live
//   #/projects/:projectId?asOf=YYYY-MM-DD       project profile, historical week
//   #/projects/:projectId/progress?asOf=DATE    cumulative-progress detail
//
// HASH routes, not pushState paths: the frontend is served by
// `python -m http.server` locally and as plain static files on Vercel, and
// neither rewrites unknown paths to index.html -- a path route would hard-404
// on refresh and on every deep link. history.pushState is still used to
// *write* the hash-bearing URL so Back/Forward get real history entries.
//
// A route object is the single source of truth for what is on screen:
//   { view, projectId, asOf, filter }
// applyRouteState() derives every module-level variable from it, which is what
// makes Back restore not just the view but the project, date and filter too.
// =====================================================================

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function withQuery(path, query) {
  // URLSearchParams encodes spaces as '+', which round-trips fine but reads
  // badly in a shared link; %20 is friendlier and parses identically.
  const search = query.toString().replace(/\+/g, '%20');
  return search ? `${path}?${search}` : path;
}

function buildHash(route) {
  const query = new URLSearchParams();
  if (route.asOf) query.set('asOf', route.asOf);
  if (route.view === 'insights') return '#/insights';
  if (route.view === 'projects') {
    // 'All projects' is the default, so it stays out of the URL.
    if (route.filter && route.filter !== 'All projects') query.set('filter', route.filter);
    return withQuery('#/projects', query);
  }
  if (route.view === 'profile' && route.projectId) return withQuery(`#/projects/${encodeURIComponent(route.projectId)}`, query);
  if (route.view === 'progress' && route.projectId) return withQuery(`#/projects/${encodeURIComponent(route.projectId)}/progress`, query);
  // Overview, and the fallback for any half-built route (e.g. a profile with
  // no project id) that has no addressable form of its own. Overview carries no
  // query of its own now that its as-of date redirects to the inventory.
  return '#/overview';
}

// Bookmarks predating the path-style routes used `#view=X&project=Y`. Map them
// onto the equivalent new route; parseRoute's caller replaces the URL with the
// modern form on arrival, so an old link upgrades itself on first use.
function legacyRoute(hash) {
  const params = new URLSearchParams(hash);
  const view = params.get('view');
  const projectId = params.get('project');
  if (projectId && (view === 'profile' || !viewLabels[view])) return { view: 'profile', projectId };
  if (viewLabels[view]) return { view };
  return null;
}

// Returns a route object, or null for anything unrecognized (the caller falls
// back to overview rather than rendering a blank view).
function parseRoute(rawHash) {
  const hash = String(rawHash || '').replace(/^#/, '');
  if (!hash || hash === '/') return { view: 'overview' };
  if (!hash.startsWith('/')) return legacyRoute(hash);

  const [pathPart, queryPart] = hash.split('?');
  const query = new URLSearchParams(queryPart || '');
  const rawAsOf = query.get('asOf');
  // A malformed date is dropped rather than honoured: every consumer of it
  // feeds it straight into an API query string.
  const asOf = rawAsOf && ISO_DATE_PATTERN.test(rawAsOf) ? rawAsOf : null;
  let segments;
  try {
    segments = pathPart.split('/').filter(Boolean).map(decodeURIComponent);
  } catch {
    return null; // malformed percent-encoding
  }

  // Overview no longer renders a per-project week-signal list, so it has no
  // dated form: an as-of date is a request to see the portfolio at a date,
  // which now lives entirely on the inventory page. Old #/overview?asOf links
  // land there instead of on a page that would ignore their date.
  if (segments.length === 1 && segments[0] === 'overview') {
    return asOf ? { view: 'projects', filter: 'All projects', asOf } : { view: 'overview' };
  }
  if (segments.length === 1 && segments[0] === 'insights') return { view: 'insights' };
  if (segments[0] !== 'projects') return null;
  if (segments.length === 1) {
    const filter = query.get('filter');
    return { view: 'projects', filter: PROJECT_FILTERS.includes(filter) ? filter : 'All projects', asOf };
  }
  if (segments.length === 2) return { view: 'profile', projectId: segments[1], asOf };
  if (segments.length === 3 && segments[2] === 'progress') {
    // A cumulative checkpoint only exists relative to a date, so a progress
    // link without a usable one isn't addressable -- send it to the inventory,
    // where the date can be picked, rather than to an undated empty view.
    return asOf ? { view: 'progress', projectId: segments[1], asOf } : { view: 'projects' };
  }
  return null;
}

// The inverse of applyRouteState: what the current module state says the URL
// should be. buildHash reads from here rather than from the route object passed
// to goto(), so the URL reflects what was actually applied (normalized filter,
// dropped as-of date, and so on).
function routeFromState() {
  if (currentView === 'profile') return { view: 'profile', projectId: selectedProjectId, asOf: selectedProjectAsOfDate };
  if (currentView === 'progress') return { view: 'progress', projectId: selectedProgressProjectId, asOf: state.progressDate };
  if (currentView === 'projects') return { view: 'projects', filter: currentFilter, asOf: state.progressDate };
  if (currentView === 'overview') return { view: 'overview' };
  return { view: currentView };
}

// Repointing either calendar invalidates its cached result. Both setters are
// no-ops when the date is unchanged, which is what lets Back/Forward land on a
// date-bearing route without discarding data already loaded for it.
function setCalendarDate(dateStr) {
  if (state.calendarDate === dateStr) return;
  state.calendarDate = dateStr;
  state.calendarResult = null;
  state.calendarLoadedDate = null;
  state.calendarError = null;
  state.calendarComputing = new Set();
  state.calendarComputeErrors = {};
  // Marked loading up front so the render that follows shows a spinner rather
  // than one frame of an empty panel before the fetch below starts.
  state.calendarLoading = Boolean(dateStr);
}

function setProgressDate(dateStr) {
  if (state.progressDate === dateStr) return;
  state.progressRunId += 1; // orphan any in-flight fan-out requests
  state.progressDate = dateStr;
  state.progressResult = {};
  state.progressLoadedDate = null;
  state.progressError = null;
  state.progressLoading = Boolean(dateStr);
}

function applyRouteState(route) {
  currentView = route.view;
  // On an inventory route the URL is authoritative: no `?filter=` means the
  // default, so a link to plain #/projects can't inherit a filter left over
  // from wherever the user was before. Other views carry the current filter
  // through untouched so it survives a round trip to a profile and back.
  if (route.view === 'projects') currentFilter = route.filter || 'All projects';
  else if (route.filter) currentFilter = route.filter;
  if (route.view === 'profile') selectedProjectId = route.projectId;
  // Leaving the profile ends the as-of drill-down; the next profile opened is
  // live unless it too is opened from a historical row.
  selectedProjectAsOfDate = route.view === 'profile' ? (route.asOf || null) : null;
  selectedProgressProjectId = route.view === 'progress' ? route.projectId : null;

  if (route.view === 'overview') setCalendarDate(route.asOf || null);
  // A profile opened as of a date came from the portfolio calendar -- or from
  // a deep link that means the same thing -- so point the calendar at that
  // week. Without this, a cold-loaded historical profile's "Back to portfolio
  // as of ..." link would land on the live overview instead.
  else if (route.view === 'profile' && route.asOf) setCalendarDate(route.asOf);
  // The other views leave the portfolio calendar alone: they are drill-downs,
  // and their back links rely on the date the user came from still being set.

  if (route.view === 'projects' || route.view === 'progress') setProgressDate(route.asOf || null);

  if (route.view === 'profile') {
    state.profileLoading = true;
    state.profileError = null;
  }
}

// Fires whatever fetches the route needs. Safe to call for a route whose data
// is already in memory -- each branch checks first -- which is what keeps
// Back/Forward from re-requesting (and, for progress, re-computing) snapshots
// the app already holds.
function startRouteLoads(route) {
  // Nothing can resolve before the portfolio snapshot lands; the bootstrap at
  // the bottom of this file re-runs this once it has.
  if (state.loading || state.error) return;
  if (route.view === 'profile') {
    if (selectedProjectId) reloadProfile();
    return;
  }
  if (route.view === 'progress') {
    const entry = selectedProgressProjectId ? state.progressResult[selectedProgressProjectId] : null;
    if (selectedProgressProjectId && state.progressDate && (!entry || entry.state !== 'done')) {
      loadProgressForProject(selectedProgressProjectId, state.progressDate);
    }
    return;
  }
  // Overview needs no fetch of its own: the stat cards count state.projects,
  // which loadLatestSnapshot already populated.
  if (route.view === 'overview') return;
  if (route.view === 'projects') {
    if (state.progressDate && state.progressLoadedDate !== state.progressDate) loadProgressAt(state.progressDate);
  }
}

// The last hash the app itself wrote or applied. pushState/replaceState do not
// fire popstate or hashchange, so a URL write can never re-enter the router on
// its own; this is the belt-and-braces guard for the one path that does fire
// events for a URL we may have just produced (a hash edited in the address bar
// of an already-loaded page).
let lastAppliedHash = null;

function writeUrl(replace) {
  const hash = buildHash(routeFromState());
  if (hash !== location.hash) {
    // Keep pathname and search intact -- only the fragment is ours.
    const url = `${location.pathname}${location.search}${hash}`;
    if (replace) history.replaceState(null, '', url);
    else history.pushState(null, '', url);
  }
  lastAppliedHash = location.hash;
}

// The one way to change what is on screen: update state from the route, write
// the URL, render, then start the route's fetches.
function goto(route, { replace = false } = {}) {
  applyRouteState(route);
  writeUrl(replace);
  render();
  startRouteLoads(route);
}

// Back/Forward, and a hash pasted into the address bar of a loaded page.
function applyLocationRoute() {
  if (location.hash === lastAppliedHash) return;
  const route = parseRoute(location.hash);
  // Unknown or malformed routes fall back to Overview, and replace the bad
  // history entry so Back doesn't walk straight back into it.
  goto(route || { view: 'overview' }, { replace: true });
}

window.addEventListener('popstate', applyLocationRoute);
window.addEventListener('hashchange', applyLocationRoute);

// Sidebar / brand navigation. Nav clicks keep the as-of date the destination
// page already had -- the stickiness the pre-router view switcher had -- while
// the route object stays the single source of truth for what gets rendered.
function navigate(view) {
  const asOf = view === 'overview' ? state.calendarDate : view === 'projects' ? state.progressDate : null;
  goto({ view, asOf, filter: currentFilter });
}

function openFeedback(project = selectedProject(), warningId = null) {
  if (!project) return;
  modalFeedback = '';
  feedbackWarningId = warningId || project.evidence[0]?.id || null;
  document.getElementById('feedback-project-name').textContent = `Add context to the ${project.name} warning. Your note will be attached to this immutable snapshot.`;
  document.getElementById('feedback-note').value = '';
  document.querySelectorAll('.feedback-options button').forEach((button) => button.classList.remove('selected'));
  document.getElementById('modal-backdrop').hidden = false;
}

function closeFeedback() {
  document.getElementById('modal-backdrop').hidden = true;
}

async function saveFeedback() {
  const project = selectedProject();
  if (!project) return;
  const saveButton = document.getElementById('modal-save');
  const note = document.getElementById('feedback-note').value.trim();
  // The API requires a category; posting without one only produces a 422.
  if (!modalFeedback) {
    showToast('Choose a review category before saving.', true);
    return;
  }
  const snapshotId = snapshotMetaFor(project).snapshotId;
  if (!snapshotId) {
    showToast('This project has no snapshot to attach review context to.', true);
    return;
  }
  const payload = { snapshot_id: snapshotId, project_id: project.id, warning_id: feedbackWarningId, category: modalFeedback, note };
  saveButton.disabled = true;
  try {
    await requestJson('/feedback', { method: 'POST', body: JSON.stringify(payload) });
    closeFeedback();
    showToast('Review context recorded');
    // The note is stored server-side; refetch so the review history reflects it.
    await reloadProfile();
  } catch (error) {
    showToast(error.message || 'Review context could not be recorded.', true);
  } finally {
    saveButton.disabled = false;
  }
}

function bindViewEvents() {
  // Picking a date on Overview navigates to the inventory page's as-of view --
  // Overview itself no longer renders a per-project list for a date, so the
  // portfolio-at-a-date question is answered in exactly one place.
  document.getElementById('calendar-date-input')?.addEventListener('change', (event) => {
    if (event.target.value) goto({ view: 'projects', filter: 'All projects', asOf: event.target.value });
  });
  document.getElementById('calendar-clear')?.addEventListener('click', clearCalendarSnapshot);
  document.getElementById('retry-calendar')?.addEventListener('click', () => { if (state.calendarDate) loadCalendarSnapshot(state.calendarDate); });
  // Retry is the one lazy action still driven by a click; everything else
  // fires from the observer. Clearing the recorded error first is what puts
  // the row back into the 'pending' state the compute functions require.
  document.querySelectorAll('.lazy-retry').forEach((button) => button.addEventListener('click', (event) => {
    event.stopPropagation();
    const projectId = button.dataset.projectId;
    if (button.dataset.lazyKind === 'calendar') {
      delete state.calendarComputeErrors[projectId];
      computeCalendarProjectSnapshot(projectId);
    } else {
      delete state.lazyErrors[projectId];
      computeLatestProjectSnapshot(projectId);
    }
  }));
  document.getElementById('progress-date-input')?.addEventListener('change', (event) => {
    if (event.target.value) goto({ view: 'projects', filter: currentFilter, asOf: event.target.value });
  });
  document.getElementById('progress-clear')?.addEventListener('click', clearProgress);
  document.getElementById('retry-progress')?.addEventListener('click', () => { if (state.progressDate) loadProgressAt(state.progressDate); });
  document.getElementById('retry-progress-detail')?.addEventListener('click', () => {
    if (selectedProgressProjectId && state.progressDate) loadProgressForProject(selectedProgressProjectId, state.progressDate);
  });
  document.querySelectorAll('.progress-retry').forEach((button) => button.addEventListener('click', (event) => {
    event.stopPropagation();
    retryProjectProgress(button.dataset.projectId);
  }));
  document.querySelectorAll('.view-progress').forEach((button) => button.addEventListener('click', (event) => {
    event.stopPropagation();
    openProgressDetail(button.dataset.projectId);
  }));
  document.getElementById('progress-back')?.addEventListener('click', () => navigate('projects'));
  document.querySelectorAll('.view-project').forEach((button) => button.addEventListener('click', (event) => {
    event.stopPropagation();
    // Carry the calendar's date into the profile so the drill-down shows the
    // week the user was looking at, not today's signals.
    openProject(button.dataset.projectId, state.calendarDate || null);
  }));
  document.querySelectorAll('.insights-row, .project-row').forEach((row) => row.addEventListener('click', () => {
    openProject(row.dataset.projectId);
  }));
  document.getElementById('profile-back')?.addEventListener('click', () => {
    // A historical profile came from the portfolio calendar, so it goes back
    // to the overview (still pointed at that week); a live one goes back to
    // the inventory. navigate() carries the calendar date across.
    navigate(selectedProjectAsOfDate ? 'overview' : 'projects');
  });
  document.getElementById('profile-live')?.addEventListener('click', () => openProject(selectedProjectId, null));
  document.querySelectorAll('[data-dashboard-filter]').forEach((button) => button.addEventListener('click', () => {
    goto({ view: 'projects', filter: button.dataset.dashboardFilter, asOf: state.progressDate });
  }));
  document.querySelectorAll('[data-filter]').forEach((button) => button.addEventListener('click', (event) => {
    event.stopPropagation();
    goto({ view: 'projects', filter: button.dataset.filter, asOf: state.progressDate });
  }));
  document.getElementById('add-context')?.addEventListener('click', () => openFeedback());
  document.getElementById('confirm-review')?.addEventListener('click', () => openFeedback());
  document.getElementById('retry-latest')?.addEventListener('click', loadLatestSnapshot);
  document.getElementById('retry-profile')?.addEventListener('click', () => reloadProfile());
}

document.querySelectorAll('.nav-item').forEach((item) => item.addEventListener('click', () => navigate(item.dataset.view)));
document.querySelector('.brand-lockup')?.addEventListener('click', () => navigate('overview'));
document.querySelectorAll('.feedback-options button').forEach((button) => button.addEventListener('click', () => {
  modalFeedback = button.dataset.feedback;
  document.querySelectorAll('.feedback-options button').forEach((option) => option.classList.toggle('selected', option === button));
}));
document.getElementById('modal-close').addEventListener('click', closeFeedback);
document.getElementById('modal-cancel').addEventListener('click', closeFeedback);
document.getElementById('modal-backdrop').addEventListener('click', (event) => { if (event.target.id === 'modal-backdrop') closeFeedback(); });
document.getElementById('modal-save').addEventListener('click', saveFeedback);
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeFeedback(); });

// Cold load. Resolve the route before the first fetch so the deep-linked view
// is what renders while the portfolio snapshot is loading, and normalize the
// URL with replaceState -- a legacy `#view=...` link, a bare '#', or garbage
// all become their canonical route without leaving a junk history entry.
const bootRoute = parseRoute(location.hash) || { view: 'overview' };
applyRouteState(bootRoute);
writeUrl(true);

loadLatestSnapshot().then(() => {
  if (state.error) return;
  // Fired after the status counts land so the page paints immediately; the
  // delivery cards fill in on the follow-up render.
  loadPortfolioDelivery();
  // startRouteLoads is a deliberate no-op while state.loading is true, so the
  // route's own fetches -- the profile, its as-of snapshot, either calendar --
  // start here, once the snapshot they layer on top of has landed.
  startRouteLoads(routeFromState());
});
