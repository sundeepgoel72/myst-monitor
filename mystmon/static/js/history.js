function pickMetric(source, keys) {
    if (!source) return null;
    for (const key of keys) {
        if (typeof source[key] === 'number' && Number.isFinite(source[key])) {
            return source[key];
        }
    }
    return null;
}

function loadHistorySummary(current, prior) {
    const currentOnline = pickMetric(current, ['online', 'running']);
    const priorOnline = pickMetric(prior, ['online', 'running']);
    if (currentOnline === null || priorOnline === null) {
        return 'No prior data';
    }
    return `${currentOnline} / ${priorOnline}`;
}
