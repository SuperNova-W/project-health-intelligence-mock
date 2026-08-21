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
  calendarDate: null,
  calendarLoading: false,
  calendarError: null,
  calendarResult: null,
  calendarComputing: new Set(),
  calendarComputeErrors: {},
};

let currentView = 'overview';
let selectedProjectId = null;
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

function snapshotMetaFor(project = null) {
  const snapshot = project && state.projectSnapshotMeta[project.id] ? state.projectSnapshotMeta[project.id] : state.snapshot || {};
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

function boundaryCard(project) {
  const boundary = project.boundary;
  if (!boundary) return `<section class="panel"><div class="panel-header"><div><h2 class="panel-title">Project boundary</h2><p class="panel-subtitle">Canonical ownership record</p></div></div><div class="history-empty">No boundary record returned for this project.</div></section>`;
  const effective = boundary.effectiveUntil ? `${boundary.effectiveSince} – ${boundary.effectiveUntil}` : boundary.effectiveSince;
  return `<section class="panel"><div class="panel-header"><div><h2 class="panel-title">Project boundary</h2><p class="panel-subtitle">Versioned ownership record</p></div><span class="eyebrow">${escapeHtml(boundary.lifecycle)}</span></div><dl class="boundary-list"><div><dt>Root team</dt><dd>${escapeHtml(boundary.rootTeam)}</dd></div><div><dt>Included subteams</dt><dd>${escapeHtml(boundary.subteams.length ? boundary.subteams.join(', ') : '—')}</dd></div><div><dt>Repositories</dt><dd>${escapeHtml(boundary.repos.length ? boundary.repos.join(', ') : '—')}</dd></div><div><dt>Data owner</dt><dd>${escapeHtml(boundary.dataOwner)}</dd></div><div><dt>Effective dates</dt><dd>${escapeHtml(effective)}</dd></div>${boundary.version ? `<div><dt>Boundary version</dt><dd>${escapeHtml(boundary.version)}</dd></div>` : ''}</dl></section>`;
}

function historyCard(project) {
  const items = project.history || [];
  return `<section class="panel"><div class="panel-header"><div><h2 class="panel-title">Review history</h2><p class="panel-subtitle">Recorded decisions for this project</p></div></div><div class="history-list">${items.length ? items.map((item) => `<div class="history-item"><div class="history-top"><span class="history-action">${escapeHtml(item.action)}</span><span class="history-date">${escapeHtml(formatDate(item.date, true))}</span></div>${item.note ? `<p>${escapeHtml(item.note)}</p>` : ''}</div>`).join('') : '<div class="history-empty">No review notes recorded for this project.</div>'}</div></section>`;
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

function healthAssessmentCard(project) {
  const assessment = project.healthAssessment;
  if (!assessment) {
    return `<section class="panel ci-assessment ci-assessment-unavailable"><div class="panel-header"><div><span class="eyebrow">CI project health</span><h2 class="panel-title">Assessment not available</h2><p class="panel-subtitle">The CI agent has not returned an inspectable assessment for this project.</p></div><span class="assessment-badge neutral">Unavailable</span></div><div class="assessment-empty-body">Project health stays separate from the repository signals until the server provides status, evidence, or recommendations.</div></section>`;
  }
  const statusClass = ['risk', 'watch', 'clear'].includes(assessment.statusClass) ? assessment.statusClass : 'neutral';
  const statusLabel = assessment.status || 'Assessment returned';
  const metrics = `<div class="assessment-metrics"><div><span>Score</span><strong>${escapeHtml(assessmentNumber(assessment.score))}</strong></div><div><span>Confidence</span><strong>${escapeHtml(assessmentNumber(assessment.confidence, true))}</strong></div><div><span>Expected week</span><strong>${assessment.expectedWeek === null || assessment.expectedWeek === undefined ? '—' : `Week ${escapeHtml(assessment.expectedWeek)}`}</strong></div></div>`;
  const citations = assessment.citations.length ? `<div class="assessment-block"><h3>Evidence references</h3><ul class="assessment-citations">${assessment.citations.map(assessmentCitation).join('')}</ul></div>` : '';
  return `<section class="panel ci-assessment"><div class="panel-header"><div><span class="eyebrow">CI project health</span><h2 class="panel-title">${escapeHtml(statusLabel)}</h2><p class="panel-subtitle">Server-provided assessment against the project specification and weekly plan.</p></div><span class="assessment-badge ${statusClass}">${escapeHtml(statusLabel)}</span></div>${metrics}${assessment.explanation ? `<div class="assessment-explanation">${escapeHtml(assessment.explanation)}</div>` : ''}<div class="assessment-columns"><div class="assessment-block"><h3>Blockers</h3>${assessmentItems(assessment.blockers, 'No blockers returned.')}</div><div class="assessment-block"><h3>Recommended weekly tasks</h3>${assessmentItems(assessment.weeklyTasks, 'No weekly tasks returned.')}</div></div>${citations}</section>`;
}

function overviewAssessmentSummary(projects) {
  const assessed = projects.filter((project) => project.healthAssessment);
  const attention = assessed.filter((project) => ['risk', 'watch'].includes(project.healthAssessment.statusClass));
  return `<section class="panel ci-overview-summary"><div class="ci-summary-copy"><span class="eyebrow">CI project health</span><h2 class="panel-title">Early project-spec coverage</h2><p class="panel-subtitle">Coverage is counted only when the server returns an inspectable assessment.</p></div><div class="ci-summary-stats"><div><strong>${assessed.length}/${projects.length}</strong><span>projects assessed</span></div><div><strong>${attention.length}</strong><span>need attention</span></div></div><button class="panel-link ci-attention-link" data-dashboard-filter="Needs attention" type="button">Open attention table →</button></section>`;
}

function calendarControlMarkup() {
  const today = new Date().toISOString().slice(0, 10);
  return `<div class="calendar-control"><label for="calendar-date-input">${icon('calendar')}<span>View portfolio as of</span></label><input type="date" id="calendar-date-input" max="${today}" value="${escapeHtml(state.calendarDate || '')}" />${state.calendarDate ? '<button class="text-button" id="calendar-clear">Back to live ×</button>' : ''}</div>`;
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
      const action = isComputing
        ? '<span class="queue-action compute-pending"><span class="spinner"></span> Computing…</span>'
        : computeError
          ? `<button class="queue-action compute-week-retry" data-project-id="${escapeHtml(project.id)}">Could not compute — Retry</button>`
          : computable
            ? `<button class="queue-action compute-week" data-project-id="${escapeHtml(project.id)}">Compute this week</button>`
            : '<span class="queue-action compute-disabled">LLM signal not configured</span>';
      return `<div class="queue-item">${monogram(project)}<div class="queue-main"><div class="queue-name-line"><span class="queue-name">${escapeHtml(project.name)}</span></div><div class="queue-meta">${escapeHtml(project.team)} · ${escapeHtml(project.repo)}</div></div><div class="queue-signal"><span class="mono">No snapshot computed for this week yet.</span></div>${action}</div>`;
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
  const signalMetricAliases = {
    openPRs: ['openPRs', 'open_prs', 'oldest_open_pr_days'],
    activity: ['activity', 'active_days', 'days_since_activity'],
    contributors: ['contributors', 'active_contributors'],
  };
  const signalCounts = ['openPRs', 'activity', 'contributors'].map((metric, index) => ({
    metric,
    count: projects.filter((project) => project.evidence.some((item) => signalMetricAliases[metric].includes(item.metric))).length,
    icon: ['pull', 'activity', 'users'][index],
    title: ['Pull request aging', 'Activity trend', 'Contributor resilience'][index],
    copy: ['Review or decision bottlenecks', 'Below project baseline', 'Aggregate count only'][index],
  }));
  return `<div class="page-heading"><div><span class="eyebrow">Weekly portfolio review</span><h1>Good morning</h1><p>Here’s the current read on the projects that matter this week.</p>${snapshotMetaMarkup()}</div><div class="heading-actions"><div class="date-chip">${icon('calendar')} ${escapeHtml(snapshotMetaFor().snapshotWeekStart ? `${formatDate(snapshotMetaFor().snapshotWeekStart)}${snapshotMetaFor().snapshotWeekEnd ? ` – ${formatDate(snapshotMetaFor().snapshotWeekEnd)}` : ''}` : 'Current snapshot')}</div>${calendarControlMarkup()}</div></div>
    ${calendarPanelMarkup()}
    <div class="stat-grid"><button class="stat-card total dashboard-filter" data-dashboard-filter="Active projects" type="button"><span class="stat-label"><span>Active projects</span><span class="stat-icon">${icon('folder')}</span></span><span class="stat-value">${active.length}</span><span class="stat-foot">Current snapshot</span></button><button class="stat-card attention dashboard-filter" data-dashboard-filter="Needs attention" type="button"><span class="stat-label"><span>Need attention</span><span class="stat-icon">${icon('triangle')}</span></span><span class="stat-value">${attention.length}</span><span class="stat-foot">Warnings with evidence</span></button><button class="stat-card clear dashboard-filter" data-dashboard-filter="Clear" type="button"><span class="stat-label"><span>Clear</span><span class="stat-icon">${icon('check-circle')}</span></span><span class="stat-value">${clear.length}</span><span class="stat-foot">Explicit server status only</span></button><button class="stat-card data dashboard-filter" data-dashboard-filter="Insufficient data" type="button"><span class="stat-label"><span>Insufficient data</span><span class="stat-icon">${icon('database')}</span></span><span class="stat-value">${insufficient.length}</span><span class="stat-foot">Signals remain suppressed</span></button></div>
    ${overviewAssessmentSummary(projects)}
    <div class="insight-banner"><div class="insight-banner-icon">${icon(attention.length ? 'sparkle' : 'database')}</div><div class="insight-copy"><strong>${attention.length ? `${attention.length} projects may need leadership attention this week.` : 'No inspectable warnings are in the current queue.'}</strong><span>${attention.length ? 'Review the evidence, add context, and decide what to verify with each team.' : 'Insufficient data and planned pauses stay out of the attention queue.'}</span></div><button class="insight-link" id="banner-review">Review attention queue →</button></div>
    <div class="dashboard-grid"><section class="panel queue-panel"><div class="panel-header"><div><h2 class="panel-title">Attention queue</h2><p class="panel-subtitle">Only server-issued warnings with evidence references appear here.</p></div><button class="panel-link" id="queue-filter">View all projects</button></div><div class="queue-list">${attention.length ? attention.map((project) => `<div class="queue-item">${monogram(project)}<div class="queue-main"><div class="queue-name-line"><span class="queue-name">${escapeHtml(project.name)}</span>${statusPill(project)}</div><div class="queue-meta">${escapeHtml(project.team)} · ${escapeHtml(project.repo)}</div></div><div class="queue-signal"><strong>${escapeHtml(project.signal)}</strong><span class="mono">${escapeHtml(project.signalDetail)}</span></div><button class="queue-action view-project" data-project-id="${escapeHtml(project.id)}">View project</button></div>`).join('') : '<div class="history-empty" style="padding:20px;">No projects require attention from this snapshot.</div>'}</div></section><div><section class="panel pulse-panel"><div class="panel-header"><div><h2 class="panel-title">Portfolio pulse</h2><p class="panel-subtitle">Historical queue series is shown only when returned by the API.</p></div><span class="eyebrow">Snapshot</span></div><div class="pulse-chart"><div class="chart-empty" style="width:100%;height:128px;">Historical queue data unavailable</div></div><div class="pulse-footer"><div class="chart-legend"><span class="legend-line"></span> Evidence-backed status</div><span class="chart-note">No inferred history</span></div></section><section class="panel signal-panel"><div class="panel-header"><div><h2 class="panel-title">Signal mix</h2><p class="panel-subtitle">What is driving this week’s queue</p></div></div><div class="signal-list">${signalCounts.map((signal) => `<div class="signal-row"><span class="signal-icon ${signal.metric === 'openPRs' ? 'red' : signal.metric === 'activity' ? 'amber' : 'blue'}">${icon(signal.icon)}</span><div class="signal-copy"><strong>${signal.title}</strong><span>${signal.copy}</span></div><span class="signal-count">${signal.count}</span></div>`).join('')}</div></section></div></div>`;
}

function renderProjects() {
  const filters = ['All projects', 'Active projects', 'Needs attention', 'At risk', 'Watch', 'Clear', 'Insufficient data', 'Planned pause'];
  const filtered = currentFilter === 'All projects'
    ? state.projects
    : currentFilter === 'Active projects'
      ? state.projects.filter(isActiveProject)
      : currentFilter === 'Needs attention'
        ? state.projects.filter(isAttentionProject)
        : state.projects.filter((project) => project.status === currentFilter);
  return `<div class="page-heading"><div><span class="eyebrow">Portfolio inventory</span><h1>All projects</h1><p>Every project boundary, current attention status, and data freshness in one place.</p>${snapshotMetaMarkup()}</div><div class="heading-actions"></div></div><section class="panel"><div class="panel-header"><div><h2 class="panel-title">Project inventory</h2><p class="panel-subtitle">${filtered.length} of ${state.projects.length} projects shown</p></div><div class="filter-row">${filters.map((filter) => `<button class="filter-button ${currentFilter === filter ? 'active' : ''}" data-filter="${escapeHtml(filter)}">${escapeHtml(filter)}</button>`).join('')}</div></div><div class="table-scroll"><table class="projects-table"><thead><tr><th>Project</th><th>Status</th><th>Signal</th><th>Active</th><th>Coverage</th></tr></thead><tbody>${filtered.length ? filtered.map((project) => `<tr class="project-row" data-project-id="${escapeHtml(project.id)}"><td><div class="table-project">${monogram(project, 'sm')}<div><strong>${escapeHtml(project.name)}</strong><span>${escapeHtml(project.team)} · ${escapeHtml(project.repo)}</span></div></div></td><td>${statusPill(project)}</td><td>${escapeHtml(project.signal)}</td><td><span class="freshness">${escapeHtml(project.lastActivity)}</span></td><td><span class="freshness">${escapeHtml(formatPercent(project.dataCompletenessPct))}</span></td></tr>`).join('') : '<tr><td colspan="5"><div class="history-empty">No projects returned for this view.</div></td></tr>'}</tbody></table></div><div class="table-footer"><span>Ownership metadata is included in each project profile.</span></div></section>`;
}

function insightsProjectCell(project) {
  return `<div class="insights-project-cell">${monogram(project, 'sm')}<div class="insights-project-copy"><div><strong>${escapeHtml(project.name)}</strong><span>${escapeHtml(project.team)}</span></div>${statusPill(project)}</div></div>`;
}

function renderInsights() {
  const showContributorColumn = state.projects.some((project) => hasOwn(project.metrics, 'active_contributors'));
  const contributorHeader = showContributorColumn ? '<th>Active contributors <span>aggregate only</span></th>' : '';
  const contributorCell = (project) => showContributorColumn ? `<td>${hasOwn(project.metrics, 'active_contributors') ? chartCaption('', project.metrics.active_contributors, project.seriesBaselines.contributors?.[0]) : '<div class="chart-caption"><span class="chart-caption-label"></span><span class="chart-caption-value">—</span></div>'}</td>` : '';
  return `<div class="page-heading"><div><span class="eyebrow">Combined view · last 8 weeks</span><h1>Insights</h1><p>Aggregate activity, review flow, and contributor counts where the server aggregation floor permits.</p>${snapshotMetaMarkup()}</div></div><section class="panel"><div class="table-scroll"><table class="insights-table"><thead><tr><th>Project</th><th>Activity <span>days/wk</span></th><th>Open PRs</th><th>Review latency</th>${contributorHeader}</tr></thead><tbody>${state.projects.length ? state.projects.map((project) => `<tr class="insights-row" data-project-id="${escapeHtml(project.id)}"><td>${insightsProjectCell(project)}</td><td>${chartCaption('', metricValue(project.metrics, 'active_days', lastValue(project.series.activity)), project.seriesBaselines.activity?.[0])}</td><td>${chartCaption('', metricValue(project.metrics, 'open_prs', lastValue(project.series.openPRs)), project.seriesBaselines.openPRs?.[0])}</td><td>${chartCaption('', metricValue(project.metrics, 'review_latency_days', lastValue(project.series.reviewLatency)), project.seriesBaselines.reviewLatency?.[0], 'd')}</td>${contributorCell(project)}</tr>`).join('') : `<tr><td colspan="${showContributorColumn ? 5 : 4}"><div class="history-empty">No project metrics returned.</div></td></tr>`}</tbody></table></div></section>`;
}

function renderProjectProfile(project) {
  const meta = statusMeta[project.statusClass] || statusMeta.data;
  return `<div class="page-heading"><div><button class="text-button back-link" id="profile-back"><span>←</span> Back to inventory</button><div class="profile-title-row">${monogram(project, 'lg')}<div><h1>${escapeHtml(project.name)}</h1><p>${escapeHtml(project.team)} · ${escapeHtml(project.repo)}</p>${snapshotMetaMarkup(project, true)}</div>${statusPill(project)}</div></div></div><div class="detail-status wide ${escapeHtml(project.statusClass)}"><strong>${escapeHtml(project.status)}</strong><span>${escapeHtml(meta.copy)}</span></div>${healthAssessmentCard(project)}${metricCharts(project)}${aggregateMetricsSection(project)}<div class="profile-grid"><section class="panel"><div class="panel-header"><div><h2 class="panel-title">Evidence</h2><p class="panel-subtitle">Warnings require inspectable source evidence.</p></div><span class="eyebrow">${escapeHtml(formatPercent(project.dataCompletenessPct))} complete</span></div><div class="evidence-section wide">${evidenceList(project, 'lg')}</div><div class="detail-actions"><button class="secondary-button" id="add-context">Add context</button><button class="primary-button" id="confirm-review">${escapeHtml(meta.cta)} <span>→</span></button></div></section><div class="profile-side">${boundaryCard(project)}${historyCard(project)}</div></div>`;
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

function render() {
  const appView = document.getElementById('app-view');
  if (state.loading) appView.innerHTML = renderLoading();
  else if (state.error) appView.innerHTML = renderGlobalError();
  else if (currentView === 'overview') appView.innerHTML = renderOverview();
  else if (currentView === 'projects') appView.innerHTML = renderProjects();
  else if (currentView === 'insights') appView.innerHTML = renderInsights();
  else if (currentView === 'profile') {
    const project = selectedProject();
    appView.innerHTML = !project ? errorPanel('This project is outside the current access scope.') : state.profileLoading ? loadingPanel('Loading project snapshots…') : state.profileError ? errorPanel(state.profileError, 'retry-profile') : renderProjectProfile(project);
  }
  document.getElementById('breadcrumb-current').textContent = currentView === 'profile' ? (selectedProject()?.name || 'Project') : viewLabels[currentView];
  const navActiveView = currentView === 'profile' ? 'projects' : currentView;
  document.querySelectorAll('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.view === navActiveView));
  updateChrome();
  bindViewEvents();
  window.scrollTo(0, 0);
}

function selectedProject() {
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
    state.loading = false;
    if (!selectedProjectId && state.projects[0]) selectedProjectId = state.projects[0].id;
    render();
  } catch (error) {
    state.loading = false;
    state.error = error;
    render();
  }
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
    state.calendarLoading = false;
    render();
  } catch (error) {
    state.calendarLoading = false;
    state.calendarError = error;
    render();
  }
}

async function computeCalendarProjectSnapshot(projectId) {
  if (!state.calendarDate || state.calendarComputing.has(projectId)) return;
  state.calendarComputing.add(projectId);
  delete state.calendarComputeErrors[projectId];
  render();
  try {
    const raw = await requestJson(`/projects/${encodeURIComponent(projectId)}/snapshots/at?date=${encodeURIComponent(state.calendarDate)}`, { method: 'POST' });
    const updated = normalizeProject(raw?.project, state.calendarResult || {});
    const projects = state.calendarResult.projects.map((project) => (project.id === projectId ? updated : project));
    state.calendarResult = { ...state.calendarResult, projects, missingProjectIds: state.calendarResult.missingProjectIds.filter((id) => id !== projectId) };
  } catch (error) {
    state.calendarComputeErrors[projectId] = error;
  } finally {
    state.calendarComputing.delete(projectId);
    render();
  }
}

function clearCalendarSnapshot() {
  state.calendarDate = null;
  state.calendarResult = null;
  state.calendarError = null;
  state.calendarComputing = new Set();
  state.calendarComputeErrors = {};
  render();
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

function navigate(view) {
  currentView = view;
  render();
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
    await loadProjectSnapshots(project.id);
  } catch (error) {
    showToast(error.message || 'Review context could not be recorded.', true);
  } finally {
    saveButton.disabled = false;
  }
}

function bindViewEvents() {
  document.getElementById('calendar-date-input')?.addEventListener('change', (event) => {
    if (event.target.value) loadCalendarSnapshot(event.target.value);
  });
  document.getElementById('calendar-clear')?.addEventListener('click', clearCalendarSnapshot);
  document.getElementById('retry-calendar')?.addEventListener('click', () => { if (state.calendarDate) loadCalendarSnapshot(state.calendarDate); });
  document.querySelectorAll('.compute-week, .compute-week-retry').forEach((button) => button.addEventListener('click', (event) => {
    event.stopPropagation();
    computeCalendarProjectSnapshot(button.dataset.projectId);
  }));
  document.querySelectorAll('.view-project').forEach((button) => button.addEventListener('click', (event) => {
    event.stopPropagation();
    selectedProjectId = button.dataset.projectId;
    currentView = 'profile';
    state.profileLoading = true;
    render();
    loadProjectSnapshots(selectedProjectId);
  }));
  document.querySelectorAll('.insights-row, .project-row').forEach((row) => row.addEventListener('click', () => {
    selectedProjectId = row.dataset.projectId;
    currentView = 'profile';
    state.profileLoading = true;
    render();
    loadProjectSnapshots(selectedProjectId);
  }));
  document.getElementById('profile-back')?.addEventListener('click', () => navigate('projects'));
  document.querySelectorAll('[data-dashboard-filter]').forEach((button) => button.addEventListener('click', () => {
    currentFilter = button.dataset.dashboardFilter;
    navigate('projects');
  }));
  document.querySelectorAll('[data-filter]').forEach((button) => button.addEventListener('click', (event) => { event.stopPropagation(); currentFilter = button.dataset.filter; render(); }));
  document.getElementById('banner-review')?.addEventListener('click', () => { currentFilter = 'All projects'; navigate('projects'); });
  document.getElementById('queue-filter')?.addEventListener('click', () => { currentFilter = 'All projects'; navigate('projects'); });
  document.getElementById('add-context')?.addEventListener('click', () => openFeedback());
  document.getElementById('confirm-review')?.addEventListener('click', () => openFeedback());
  document.getElementById('retry-latest')?.addEventListener('click', loadLatestSnapshot);
  document.getElementById('retry-profile')?.addEventListener('click', () => loadProjectSnapshots(selectedProjectId));
}

document.querySelectorAll('.nav-item').forEach((item) => item.addEventListener('click', () => navigate(item.dataset.view)));
document.querySelectorAll('.feedback-options button').forEach((button) => button.addEventListener('click', () => {
  modalFeedback = button.dataset.feedback;
  document.querySelectorAll('.feedback-options button').forEach((option) => option.classList.toggle('selected', option === button));
}));
document.getElementById('modal-close').addEventListener('click', closeFeedback);
document.getElementById('modal-cancel').addEventListener('click', closeFeedback);
document.getElementById('modal-backdrop').addEventListener('click', (event) => { if (event.target.id === 'modal-backdrop') closeFeedback(); });
document.getElementById('modal-save').addEventListener('click', saveFeedback);
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeFeedback(); });

if (location.hash) {
  const params = new URLSearchParams(location.hash.slice(1));
  if (viewLabels[params.get('view')]) currentView = params.get('view');
  if (params.get('project')) selectedProjectId = params.get('project');
}

loadLatestSnapshot().then(() => {
  if (state.error) return;
  if (currentView === 'profile' && selectedProjectId) loadProjectSnapshots(selectedProjectId);
});
