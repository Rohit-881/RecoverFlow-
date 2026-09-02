
// ===== STATE =====
let transactions = []; // Start with an empty array

// Fetch real data from the backend
async function fetchTransactions() {
  try {
    // We assume your FastAPI backend has an endpoint at GET /transactions
    const response = await fetch('https://recoverflow-backened.onrender.com/transactions');
    if (!response.ok) throw new Error("Network response was not ok");

    transactions = await response.json();

    // Re-render the dashboard metrics, charts, and tables with the new data
    renderAll();
  } catch (error) {
    console.error("Error fetching data from backend:", error);
  }
}

let merchantConfig = { maxRetries: 3, maxCost: 50, dndStart: 22, dndEnd: 8, minScore: 20, autoRetry: 1 };
let currentFilter = 'all';
let selectedTx = null;
let showHistory = false;

function toggleHistory() {
  showHistory = !showHistory;
  renderTable();
}

async function renderMetrics() {
  try {
    const response = await fetch('https://recoverflow-backened.onrender.com/metrics');
    const metrics = await response.json();

    document.getElementById('metricRisk').textContent = '₹' + metrics.revenue_at_risk.toLocaleString('en-IN');
    document.getElementById('metricRecovered').textContent = '₹' + metrics.money_recovered.toLocaleString('en-IN');
    document.getElementById('metricRate').textContent = metrics.recovery_rate + '%';
    document.getElementById('metricTime').textContent = metrics.avg_recovery_time_hours + 'h';

    // Update AI Insights
    if (metrics.risk_insight) {
      const dRisk = document.getElementById('deltaRisk');
      dRisk.textContent = metrics.risk_insight;
      dRisk.className = 'rf-metric-delta ' + (metrics.risk_insight.includes('↑') ? 'up' : 'down');
    }
    if (metrics.recovered_insight) {
      const dRec = document.getElementById('deltaRecovered');
      dRec.textContent = metrics.recovered_insight;
      dRec.className = 'rf-metric-delta ' + (metrics.recovered_insight.includes('↑') ? 'up' : 'down');
    }
    if (metrics.rate_insight) {
      const dRate = document.getElementById('deltaRate');
      dRate.textContent = metrics.rate_insight;
      dRate.className = 'rf-metric-delta ' + (metrics.rate_insight.includes('↑') ? 'up' : 'down');
    }
    if (metrics.time_insight) {
      const dTime = document.getElementById('deltaTime');
      dTime.textContent = metrics.time_insight;
      dTime.className = 'rf-metric-delta ' + (metrics.time_insight.includes('↑') ? 'up' : 'down');
    }
  } catch (error) {
    console.error("Error fetching metrics:", error);
  }
}

function renderStrategyChart() {
  const strategies = {};
  transactions.filter(t => t.status === 'recovered').forEach(t => {
    strategies[t.strategy] = (strategies[t.strategy] || 0) + t.amount;
  });
  const total = Object.values(strategies).reduce((a, b) => a + b, 0) || 1;
  const data = Object.entries(strategies).map(([name, value]) => ({
    name: name.split(' ').slice(0, 2).join(' '),
    value: Math.round((value / total) * 100),
    color: ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)'][Object.keys(strategies).indexOf(name) % 5]
  }));
  const max = Math.max(...data.map(d => d.value), 1);
  document.getElementById('strategyChart').innerHTML = data.map(d => `
    <div class="rf-bar" style="height: ${(d.value / max) * 100}%; background: ${d.color};">
        <div class="rf-bar-value">${d.value}%</div>
        <div class="rf-bar-label">${d.name}</div>
    </div>
    `).join('');
}

function renderFunnelChart() {
  const detected = transactions.length;
  // Simulate gateway failures vs detected webhooks for realistic funnel drop-off
  const failed = Math.floor(detected * 1.12) || 1;
  const scored = transactions.filter(t => t.potential > 20).length; // Exclude unrecoverable low scores
  const intervened = transactions.filter(t => ['retrying', 'recovered', 'failed', 'promise_to_pay', 'waiting_for_customer'].includes(t.status)).length; // Exclude pending/manual review
  const recovered = transactions.filter(t => t.status === 'recovered').length;

  const data = [
    { name: 'Failed', value: 100, color: 'var(--text-quaternary)' },
    { name: 'Detected', value: Math.round((detected / failed) * 100), color: 'var(--text-secondary)' },
    { name: 'Scored', value: Math.round((scored / failed) * 100), color: 'var(--chart-5)' },
    { name: 'Intervened', value: Math.round((intervened / failed) * 100), color: 'var(--chart-4)' },
    { name: 'Recovered', value: Math.round((recovered / failed) * 100), color: 'var(--positive)' },
  ];
  const max = 100;
  document.getElementById('funnelChart').innerHTML = data.map(d => `
    <div class="rf-bar" style="height: ${(d.value / max) * 100}%; background: ${d.color};">
        <div class="rf-bar-value">${d.value}%</div>
        <div class="rf-bar-label">${d.name}</div>
    </div>
    `).join('');
}

function renderTable() {
  const tbody = document.getElementById('txTable');
  const filtered = currentFilter === 'all' ? transactions : transactions.filter(t => t.status === currentFilter);
  const displayData = showHistory ? filtered : filtered.slice(0, 10);

  tbody.innerHTML = displayData.map((t) => {
    const idx = transactions.indexOf(t);
    const potColor = t.potential > 70 ? 'var(--positive)' : t.potential > 40 ? 'var(--warning)' : 'var(--danger)';
    const statusColor = t.status === 'recovered' ? 'positive' : t.status === 'retrying' ? 'warning' : t.status === 'failed' ? 'danger' : t.status === 'waiting_for_customer' ? 'chart-4' : t.status === 'promise_to_pay' ? 'chart-5' : 'text-secondary';
    const displayStatus = t.status.replace(/_/g, ' ');
    return `
    <tr onclick="showDetail(${idx})" style="cursor:pointer;">
        <td><code>${t.id}</code></td>
        <td class="rf-amount">₹${t.amount.toLocaleString('en-IN')}</td>
        <td>${t.reason}</td>
        <td>
            <div class="rf-recovery-bar"><div class="rf-recovery-bar-fill" style="width: ${t.potential}%; background: ${potColor};"></div></div>
            <div class="rf-recovery-score">${t.potential}% potential</div>
        </td>
        <td><span class="rf-strategy">${t.strategy}</span></td>
        <td><span class="rf-status ${t.status}"><span class="rf-dot" style="background: var(--${statusColor});"></span>${displayStatus}</span></td>
        <td><button class="rf-action-btn" onclick="event.stopPropagation();showDetail(${idx})">View AI decision</button></td>
    </tr>
      `}).join('');

  const historyLink = document.getElementById('historyLinkContainer');
  if (filtered.length > 10) {
    historyLink.style.display = 'block';
    historyLink.innerHTML = showHistory ? 'Hide older transactions ↑' : 'View full transaction history (' + (filtered.length - 10) + ' older) ↓';
  } else {
    historyLink.style.display = 'none';
  }
}

function showDetail(idx) {
  selectedTx = transactions[idx];
  const panel = document.getElementById('detailPanel');
  panel.classList.add('active');
  document.getElementById('detailTitle').textContent = `AI Decision: ${selectedTx.id}`;
  document.getElementById('scoreBreakdown').innerHTML = `
    <div style="font-size:14px;font-weight:600;margin-bottom:10px;">AI Model Inputs</div>
    <div class="rf-score-row"><span class="score-label">Amount</span><span class="score-value">₹${selectedTx.amount.toLocaleString('en-IN')}</span></div>
    <div class="rf-score-row"><span class="score-label">Customer LTV</span><span class="score-value">₹${selectedTx.ltv.toLocaleString('en-IN')}</span></div>
    <div class="rf-score-row"><span class="score-label">Recovery history</span><span class="score-value">${(selectedTx.history * 100).toFixed(0)}%</span></div>
    <div class="rf-score-row"><span class="score-label">Failure bucket</span><span class="score-value" style="text-transform: capitalize;">${selectedTx.bucket.replace('_', ' ')}</span></div>
    <div class="rf-score-row"><span class="score-label">Payment method</span><span class="score-value">${selectedTx.method}</span></div>
    <div class="rf-score-row" style="border-top:2px solid var(--border);margin-top:4px;padding-top:10px;"><span class="score-label">True AI Predicted Score</span><span class="score-value pos" style="font-size:18px;">${selectedTx.potential}%</span></div>
    `;
  document.getElementById('detailGrid').innerHTML = `
    <div class="rf-detail-item"><div class="rf-detail-item-label">Transaction ID</div><div class="rf-detail-item-value">${selectedTx.id}</div></div>
    <div class="rf-detail-item"><div class="rf-detail-item-label">Amount</div><div class="rf-detail-item-value">₹${selectedTx.amount.toLocaleString('en-IN')}</div></div>
    <div class="rf-detail-item"><div class="rf-detail-item-label">Failure reason</div><div class="rf-detail-item-value">${selectedTx.reason}</div></div>
    <div class="rf-detail-item"><div class="rf-detail-item-label">Failure bucket</div><div class="rf-detail-item-value">${selectedTx.bucket}</div></div>
    <div class="rf-detail-item"><div class="rf-detail-item-label">Customer LTV</div><div class="rf-detail-item-value">₹${selectedTx.ltv.toLocaleString('en-IN')}</div></div>
    <div class="rf-detail-item"><div class="rf-detail-item-label">Payment method</div><div class="rf-detail-item-value">${selectedTx.method}</div></div>
    <div class="rf-detail-item"><div class="rf-detail-item-label">Selected strategy</div><div class="rf-detail-item-value">${selectedTx.strategy}</div></div>
    <div class="rf-detail-item"><div class="rf-detail-item-label">Attempts Made</div><div class="rf-detail-item-value">${selectedTx.attempts_made !== undefined ? selectedTx.attempts_made : (selectedTx.potential > 60 ? '1/3' : '1/2')}</div></div>
    `;

  // If there is an active payment link, show a big pay now button
  if (selectedTx.payment_link_url && selectedTx.status === 'waiting_for_customer') {
    document.getElementById('detailGrid').innerHTML += `
        <div style="grid-column: 1 / -1; margin-top: 10px;">
            <a href="${selectedTx.payment_link_url}" target="_blank" style="display:inline-block; padding:8px 16px; background:var(--primary); color:white; border-radius:6px; text-decoration:none; font-weight:600;">🔗 Pay Now (Demo)</a>
        </div>
        `;
  }
  document.getElementById('auditTimeline').innerHTML = selectedTx.audit.map(a => {
    let dateStr = 'Now';
    if (a.timestamp) {
      const d = new Date(a.timestamp);
      if (!isNaN(d)) {
        dateStr = d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).replace(', ', '<br>');
      }
    } else if (a.time) {
      dateStr = a.time.replace(', ', '<br>');
    }
    let linkHtml = a.link_url ? `<br><a href="${a.link_url}" target="_blank" style="color:var(--primary); text-decoration:underline;">🔗 Open Link</a>` : '';
    let llmHtml = a.llm_message ? `<div style="margin-top:8px; padding:10px; background: rgba(59, 130, 246, 0.05); border-left: 3px solid var(--accent); border-radius: 4px; font-style: italic; color: var(--text-secondary);"><strong>✨ Gemini Generative AI:</strong><br>"${a.llm_message}"</div>` : '';
    return `
    <div class="rf-audit-item">
        <div class="rf-audit-time" style="font-size:12px; color:var(--text-secondary); width:60px; line-height:1.2;">${dateStr}</div>
        <div>
            <div class="rf-audit-action">${a.action}${linkHtml}</div>
            ${llmHtml}
            <div class="rf-audit-result ${a.result === 'success' ? 'success' : a.result === 'fail' ? 'fail' : a.result === 'warn' ? 'warn' : ''}">${a.result === 'success' ? '✓ Success' : a.result === 'fail' ? '✗ Failed' : a.result === 'warn' ? '⚠ Warning' : 'ℹ Info'}</div>
        </div>
    </div>
      `}).join('');
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function filterTable(status, event) {
  if (event) {
    document.querySelectorAll('.rf-filter-btn').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
  }
  currentFilter = status;
  renderTable();
}

function switchTab(tab) {
  document.querySelectorAll('.rf-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.rf-panel').forEach(p => p.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('tab-' + tab).classList.add('active');
}

async function updateConfig(key, value) {
  merchantConfig[key] = parseInt(value);
  const display = key === 'autoRetry' ? (value == 1 ? 'On' : 'Off') : value;
  const suffix = key === 'maxCost' ? '' : key === 'dndStart' || key === 'dndEnd' ? ':00' : '';
  document.getElementById('config' + key.charAt(0).toUpperCase() + key.slice(1)).textContent = display + suffix;

  // Sync the updated config with the backend
  const backendConfig = {
    max_retries: merchantConfig.maxRetries,
    max_cost_per_recovery: merchantConfig.maxCost,
    dnd_start_hour: merchantConfig.dndStart,
    dnd_end_hour: merchantConfig.dndEnd,
    min_recovery_score: merchantConfig.minScore,
    auto_retry_soft: merchantConfig.autoRetry === 1,
    channels_enabled: {
      smart_retry: true, sms: true, whatsapp: true, email: true, voice_call: true, payment_link: true
    }
  };

  try {
    await fetch('https://recoverflow-backened.onrender.com/merchants/merchant_default/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(backendConfig)
    });
  } catch (e) {
    console.error('Failed to sync config with backend:', e);
  }
}

function log(msg, type = 'info') {
  const logEl = document.getElementById('simLog');
  const time = new Date().toLocaleTimeString('en-IN', { hour12: false });
  const typeClass = type === 'success' ? 'log-success' : type === 'error' ? 'log-error' : type === 'warn' ? 'log-warn' : 'log-info';
  logEl.innerHTML += `<div><span class="log-time">[${time}]</span> <span class="${typeClass}">${msg}</span></div>`;
  logEl.scrollTop = logEl.scrollHeight;
}

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

async function runSimulation() {
  const btn = document.getElementById('simBtn');
  const logEl = document.getElementById('simLog');
  const progressBar = document.getElementById('simProgressBar');
  const progressFill = document.getElementById('simProgressFill');
  const resultPanel = document.getElementById('simResult');
  btn.disabled = true;
  logEl.style.display = 'block';
  logEl.innerHTML = '';
  progressBar.style.display = 'block';
  progressFill.style.width = '0%';
  resultPanel.style.display = 'none';

  const simTx = {
    id: 'pay_' + Math.random().toString(36).substr(2, 8).toUpperCase(),
    amount: [599, 1299, 2499, 4999, 9999, 15999][Math.floor(Math.random() * 6)],
    reason: ['Bank timeout', 'Insufficient funds', 'Network error', 'Expired card', 'UPI declined'][Math.floor(Math.random() * 5)],
    method: ['UPI', 'Credit Card', 'Debit Card'][Math.floor(Math.random() * 3)],
    ltv: Math.floor(Math.random() * 200000) + 5000,
    history: Math.random(),
    bucket: 'soft',
    audit: []
  };
  if (simTx.reason === 'Expired card') simTx.bucket = 'hard';
  else if (simTx.reason === 'Insufficient funds') simTx.bucket = 'customer_action';

  log(`Webhook received: payment.failed`, 'info');
  await sleep(600);
  progressFill.style.width = '10%';

  // Call the real backend to generate a failed transaction
  let newTx;
  try {
    const response = await fetch('https://recoverflow-backened.onrender.com/transactions/simulate', { method: 'POST' });
    if (!response.ok) throw new Error("API error");
    const simResult = await response.json();
    await fetchTransactions(); // Refresh the list from the backend
    newTx = transactions.find(t => t.id === simResult.txn_id) || transactions[0];
  } catch (e) {
    log(`Failed to connect to backend AI`, 'error');
    btn.disabled = false;
    return;
  }

  log(`Transaction: ${newTx.id} | Amount: ₹${newTx.amount.toLocaleString('en-IN')} | Reason: ${newTx.reason}`, 'info');
  await sleep(800);
  progressFill.style.width = '25%';

  log(`Running true Machine Learning scoring model...`, 'info');
  await sleep(700);
  const score = newTx.potential;
  log(`Recovery potential scored: ${score}%`, score > 60 ? 'success' : score > 30 ? 'warn' : 'error');
  await sleep(600);
  progressFill.style.width = '40%';

  log(`Selecting optimal strategy via AI...`, 'info');
  await sleep(500);
  const strategy = newTx.strategy;
  log(`Selected Strategy: ${strategy}`, 'info');
  await sleep(600);
  progressFill.style.width = '55%';

  log(`Checking merchant bounds (max retries: ${merchantConfig.maxRetries}, max cost: ₹${merchantConfig.maxCost})...`, 'info');
  await sleep(400);
  if (score < merchantConfig.minScore) {
    log(`Score ${score}% below your threshold (${merchantConfig.minScore}%). Routing to manual review.`, 'warn');
    progressFill.style.width = '100%';
    resultPanel.style.display = 'block';
    document.getElementById('simResultText').textContent = 'Manual review';
    document.getElementById('simResultText').style.color = 'var(--warning)';
    document.getElementById('simResultDetail').textContent = `Score ${score}% below merchant threshold of ${merchantConfig.minScore}%`;
    btn.disabled = false;
    renderAll();
    return;
  }

  log(`Bounds satisfied. Proceeding with recovery.`, 'success');
  await sleep(400);
  progressFill.style.width = '70%';

  log(`Executing recovery...`, 'info');
  await sleep(800);
  const recovered = newTx.status === 'recovered';
  progressFill.style.width = '90%';

  if (recovered) {
    log(`Recovery successful! ₹${newTx.amount.toLocaleString('en-IN')} recovered.`, 'success');
    // Fetch latest transaction from backend to get the REAL audit trail
    const latestTx = await fetch('https://recoverflow-backened.onrender.com/transactions/' + newTx.id).then(r => r.json()).catch(() => newTx);
    newTx = latestTx;
    resultPanel.style.display = 'block';
    document.getElementById('simResultText').textContent = '₹' + newTx.amount.toLocaleString('en-IN') + ' recovered';
    document.getElementById('simResultText').style.color = 'var(--positive)';
    document.getElementById('simResultDetail').textContent = `Strategy: ${strategy} | Score: ${score}% | Attempts: 1/1`;
  } else {
    log(`Recovery failed.`, 'error');
    // Fetch latest transaction from backend to get the REAL audit trail
    const latestTx = await fetch('https://recoverflow-backened.onrender.com/transactions/' + newTx.id).then(r => r.json()).catch(() => newTx);
    newTx = latestTx;
    resultPanel.style.display = 'block';
    document.getElementById('simResultText').textContent = 'Recovery failed';
    document.getElementById('simResultText').style.color = 'var(--danger)';
    document.getElementById('simResultDetail').textContent = `Strategy: ${strategy} | Score: ${score}% | All attempts exhausted`;
  }
  progressFill.style.width = '100%';
  btn.disabled = false;
  renderAll();
}

async function generateNewFailure() {
  try {
    const response = await fetch('https://recoverflow-backened.onrender.com/transactions/simulate', {
      method: 'POST'
    });
    if (!response.ok) throw new Error("Network response was not ok");
    await fetchTransactions(); // Refresh the list from the backend
  } catch (error) {
    console.error("Error simulating failure:", error);
  }
}

function renderAll() {
  renderMetrics();
  renderStrategyChart();
  renderFunnelChart();
  renderTable();
}
// Call the backend as soon as the page loads instead of just rendering empty data
fetchTransactions();
