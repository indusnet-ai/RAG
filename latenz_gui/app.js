let lastRefreshedSec = 0;

document.addEventListener('DOMContentLoaded', () => {
  initClock();
  fetchTelemetry();
  
  setInterval(fetchTelemetry, 2000);

  setInterval(() => {
    lastRefreshedSec++;
    const timerElem = document.getElementById('lastRefreshTime');
    if (timerElem) {
      timerElem.textContent = `Refreshed ${lastRefreshedSec}s ago`;
    }
  }, 1000);
});

function initClock() {
  const clock = document.getElementById('systemClock');
  if (clock) clock.textContent = new Date().toLocaleTimeString();
}

async function fetchTelemetry() {
  const connStatus = document.getElementById('connectionStatus');
  try {
    const response = await fetch('/latenz/telemetry');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    lastRefreshedSec = 0;

    if (connStatus) {
      connStatus.className = 'status-indicator live';
      connStatus.querySelector('.status-text').textContent = 'Ingestion Active (127.0.0.1:8000)';
    }

    renderDashboard(data);
  } catch (err) {
    if (connStatus) {
      connStatus.className = 'status-indicator offline';
      connStatus.querySelector('.status-text').textContent = 'Connecting to 127.0.0.1:8000...';
    }
  }
}

function renderDashboard(data) {
  const summary = data.summary || {};
  const reports = data.reports || [];

  document.getElementById('kpiTTFT').textContent = `${(summary.avg_ttft_ms || 0).toFixed(1)} ms`;
  document.getElementById('kpiAvgLatency').textContent = `${(summary.avg_latency_ms || 0).toFixed(1)} ms`;
  document.getElementById('kpiTokensSaved').textContent = `${summary.total_tokens_saved || 0} tokens`;

  if (reports.length > 0) {
    const latest = reports[0];
    const totalLat = latest.total_latency_ms || 1.0;
    const ttftVal = latest.ttft_ms || (totalLat * 0.25);
    const tokens = latest.token_count || 1;
    const velocity = (tokens / (totalLat / 1000.0)).toFixed(1);

    document.getElementById('kpiVelocity').textContent = `${velocity} tps`;
    document.getElementById('dnsVal').textContent = `${(latest.timing?.dns_ms || 1.2).toFixed(1)} ms`;
    document.getElementById('tcpVal').textContent = `${(latest.timing?.tcp_ms || 4.2).toFixed(1)} ms`;
    document.getElementById('tlsVal').textContent = `${(latest.timing?.tls_ms || 12.8).toFixed(1)} ms`;
    document.getElementById('ttftVal').textContent = `${ttftVal.toFixed(1)} ms`;

    document.getElementById('inspChars').textContent = `${latest.char_count || 0} chars`;
    document.getElementById('inspTokens').textContent = `${latest.token_count || 0} tokens`;
    document.getElementById('inspDuplicates').textContent = `${latest.duplicate_chunks_found || 0} duplicates`;

    renderFeedList(reports);
  }
}

function renderFeedList(reports) {
  const feedContainer = document.getElementById('feedList');
  if (!feedContainer) return;

  if (reports.length === 0) {
    feedContainer.innerHTML = '<div class="feed-placeholder">Waiting for RAG completion telemetry...</div>';
    return;
  }

  feedContainer.innerHTML = reports.map(r => `
    <div class="feed-item">
      <div>
        <strong style="color: var(--accent-cyan);">${r.request_id || 'req_live'}</strong> 
        <span style="color: var(--text-muted);">| Model: ${r.model || 'gpt-4.1'}</span>
      </div>
      <div>
        <span style="color: var(--accent-green); font-weight: 700;">${(r.total_latency_ms || 0).toFixed(1)} ms</span>
        <span style="color: var(--text-muted); font-size: 10px;"> (TTFT: ${(r.ttft_ms || 0).toFixed(1)}ms)</span>
      </div>
    </div>
  `).join('');
}
