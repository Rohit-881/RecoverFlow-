
    // ===== STATE =====
    let transactions = []; // Start with an empty array

    // Fetch real data from the backend
    async function fetchTransactions() {
      try {
        // We assume your FastAPI backend has an endpoint at GET /transactions
        const response = await fetch('http://localhost:8000/transactions');
    if (!response.ok) throw new Error("Network response was not ok");

    transactions = await response.json();

    // Re-render the dashboard metrics, charts, and tables with the new data
    renderAll(); 
      } catch (error) {
        console.error("Error fetching data from backend:", error);
      }
    }

    let merchantConfig = {maxRetries: 3, maxCost: 50, dndStart: 22, dndEnd: 8, minScore: 20, autoRetry: 1 };
    let currentFilter = 'all';
    let selectedTx = null;
    let showHistory = false;

    function toggleHistory() {
        showHistory = !showHistory;
    renderTable();
    }

    async function renderMetrics() {
      try {
        const response = await fetch('http://localhost:8000/metrics');
    const metrics = await response.json();

    document.getElementById('metricRisk').textContent = '₹' + metrics.revenue_at_risk.toLocaleString('en-IN');
    document.getElementById('metricRecovered').textContent = '₹' + metrics.money_recovered.toLocaleString('en-IN');
    document.getElementById('metricRate').textContent = metrics.recovery_rate + '%';
    document.getElementById('metricTime').textContent = metrics.avg_recovery_time_hours + 'h';
      } catch (error) {
        console.error("Error fetching metrics:", error);
      }
    }

    function renderStrategyChart() {
      const strategies = { };
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
      const intervened = transactions.filter(t => ['retrying', 'recovered', 'failed'].includes(t.status)).length; // Exclude pending/manual review
      const recovered = transactions.filter(t => t.status === 'recovered').length;

    const data = [
    {name: 'Failed', value: 100, color: 'var(--text-quaternary)' },
    {name: 'Detected', value: Math.round((detected / failed) * 100), color: 'var(--text-secondary)' },
    {name: 'Scored', value: Math.round((scored / failed) * 100), color: 'var(--chart-5)' },
    {name: 'Intervened', value: Math.round((intervened / failed) * 100), color: 'var(--chart-4)' },
    {name: 'Recovered', value: Math.round((recovered / failed) * 100), color: 'var(--positive)' },
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
    const statusColor = t.status === 'recovered' ? 'positive' : t.status === 'retrying' ? 'warning' : t.status === 'failed' ? 'danger' : t.status === 'waiting_for_customer' ? 'chart-4' : 'text-secondary';
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
    const base = 50;
      const amountBonus = selectedTx.amount > 10000 ? 15 : selectedTx.amount > 5000 ? 10 : 0;
      const ltvBonus = selectedTx.ltv > 50000 ? 10 : selectedTx.ltv > 20000 ? 5 : 0;
      const historyBonus = selectedTx.history > 0.7 ? 20 : selectedTx.history > 0.4 ? 10 : 0;
    const bucketBonus = selectedTx.bucket === 'soft' ? 20 : selectedTx.bucket === 'customer_action' ? 5 : -30;
    const methodBonus = selectedTx.method === 'UPI' ? 5 : 0;
    document.getElementById('scoreBreakdown').innerHTML = `
    <div style="font-size:14px;font-weight:600;margin-bottom:10px;">Score breakdown</div>
    <div class="rf-score-row"><span class="score-label">Base score</span><span class="score-value">${base}</span></div>
    <div class="rf-score-row"><span class="score-label">Amount (₹${selectedTx.amount.toLocaleString('en-IN')})</span><span class="score-value ${amountBonus >= 0 ? 'pos' : 'neg'}">${amountBonus >= 0 ? '+' : ''}${amountBonus}</span></div>
    <div class="rf-score-row"><span class="score-label">Customer LTV (₹${selectedTx.ltv.toLocaleString('en-IN')})</span><span class="score-value ${ltvBonus >= 0 ? 'pos' : 'neg'}">${ltvBonus >= 0 ? '+' : ''}${ltvBonus}</span></div>
    <div class="rf-score-row"><span class="score-label">Recovery history (${(selectedTx.history * 100).toFixed(0)}%)</span><span class="score-value ${historyBonus >= 0 ? 'pos' : 'neg'}">${historyBonus >= 0 ? '+' : ''}${historyBonus}</span></div>
    <div class="rf-score-row"><span class="score-label">Failure bucket (${selectedTx.bucket})</span><span class="score-value ${bucketBonus >= 0 ? 'pos' : 'neg'}">${bucketBonus >= 0 ? '+' : ''}${bucketBonus}</span></div>
    <div class="rf-score-row"><span class="score-label">Payment method (${selectedTx.method})</span><span class="score-value ${methodBonus >= 0 ? 'pos' : 'neg'}">${methodBonus >= 0 ? '+' : ''}${methodBonus}</span></div>
    <div class="rf-score-row" style="border-top:2px solid var(--border);margin-top:4px;padding-top:10px;"><span class="score-label">Final score</span><span class="score-value" style="font-size:18px;">${selectedTx.potential}%</span></div>
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
                dateStr = d.toLocaleString('en-US', {month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit', hour12: false}).replace(', ', '<br>');
            }
        } else if (a.time) {
            dateStr = a.time.replace(', ', '<br>');
        }
        let linkHtml = a.link_url ? `<br><a href="${a.link_url}" target="_blank" style="color:var(--primary); text-decoration:underline;">🔗 Open Link</a>` : '';
        return `
    <div class="rf-audit-item">
        <div class="rf-audit-time" style="font-size:12px; color:var(--text-secondary); width:60px; line-height:1.2;">${dateStr}</div>
        <div>
            <div class="rf-audit-action">${a.action}${linkHtml}</div>
            <div class="rf-audit-result ${a.result === 'success' ? 'success' : a.result === 'fail' ? 'fail' : a.result === 'warn' ? 'warn' : ''}">${a.result === 'success' ? '✓ Success' : a.result === 'fail' ? '✗ Failed' : a.result === 'warn' ? '⚠ Warning' : 'ℹ Info'}</div>
        </div>
    </div>
      `}).join('');
    panel.scrollIntoView({behavior: 'smooth', block: 'nearest' });
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

    function updateConfig(key, value) {
        merchantConfig[key] = parseInt(value);
    const display = key === 'autoRetry' ? (value == 1 ? 'On' : 'Off') : value;
    const suffix = key === 'maxCost' ? '' : key === 'dndStart' || key === 'dndEnd' ? ':00' : '';
    document.getElementById('config' + key.charAt(0).toUpperCase() + key.slice(1)).textContent = display + suffix;
    }

    function log(msg, type = 'info') {
      const logEl = document.getElementById('simLog');
    const time = new Date().toLocaleTimeString('en-IN', {hour12: false });
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
    log(`Transaction: ${simTx.id} | Amount: ₹${simTx.amount.toLocaleString('en-IN')} | Reason: ${simTx.reason}`, 'info');
    await sleep(800);
    progressFill.style.width = '25%';

    log(`Running recovery scoring model...`, 'info');
    await sleep(700);
    const base = 50;
      const amountBonus = simTx.amount > 10000 ? 15 : simTx.amount > 5000 ? 10 : 0;
      const ltvBonus = simTx.ltv > 50000 ? 10 : simTx.ltv > 20000 ? 5 : 0;
      const historyBonus = simTx.history > 0.7 ? 20 : simTx.history > 0.4 ? 10 : 0;
    const bucketBonus = simTx.bucket === 'soft' ? 20 : simTx.bucket === 'customer_action' ? 5 : -30;
    const score = Math.min(100, Math.max(0, base + amountBonus + ltvBonus + historyBonus + bucketBonus));
    simTx.potential = score;
    log(`Recovery potential scored: ${score}%`, score > 60 ? 'success' : score > 30 ? 'warn' : 'error');
    await sleep(600);
    progressFill.style.width = '40%';

    log(`Selecting optimal strategy...`, 'info');
    await sleep(500);
    let strategy, maxAttempts, timing;
    if (score < 20) {strategy = 'Skip — manual review'; maxAttempts = 0; timing = 'N/A'; }
      else if (simTx.bucket === 'soft' && score > 70) {strategy = 'Alt-gateway immediate retry'; maxAttempts = 2; timing = 'Now + 5 min'; }
      else if (simTx.bucket === 'customer_action' && score > 50) {strategy = 'Delayed retry + SMS/WhatsApp'; maxAttempts = 3; timing = 'Predicted payday'; }
      else if (simTx.bucket === 'hard' && score > 30) {strategy = 'Card update → dunning sequence'; maxAttempts = 1; timing = 'T+1, T+3, T+7'; }
    else {strategy = 'Manual review queue'; maxAttempts = 1; timing = 'Business hours'; }
    simTx.strategy = strategy;
    log(`Selected: ${strategy} | Max attempts: ${maxAttempts} | Timing: ${timing}`, 'info');
    await sleep(600);
    progressFill.style.width = '55%';

    log(`Checking merchant bounds (max retries: ${merchantConfig.maxRetries}, max cost: ₹${merchantConfig.maxCost})...`, 'info');
    await sleep(400);
    if (score < merchantConfig.minScore) {
        log(`Score ${score}% below minimum threshold (${merchantConfig.minScore}%). Routing to manual review.`, 'warn');
    progressFill.style.width = '100%';
    simTx.status = 'failed';
    simTx.audit = [
    {time: new Date().toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), action: `Webhook received: payment.failed — ${simTx.reason} (Gateway: HDFC)`, result: 'fail', strategy: 'Detection', cost_inr: 0.0 },
    {time: new Date().toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), action: `Scored ${score}% — below min threshold`, result: 'warn', strategy: 'AI Scoring', cost_inr: 0.0 },
    {time: new Date().toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), action: 'Routed to manual review', result: 'info', strategy: 'Strategy Router', cost_inr: 0.0 }
    ];
    resultPanel.style.display = 'block';
    document.getElementById('simResultText').textContent = 'Manual review';
    document.getElementById('simResultText').style.color = 'var(--warning)';
    document.getElementById('simResultDetail').textContent = `Score ${score}% below merchant threshold of ${merchantConfig.minScore}%`;
    btn.disabled = false;
    transactions.unshift(simTx);
    renderAll();
    return;
      }
    log(`Bounds satisfied. Proceeding with recovery.`, 'success');
    await sleep(400);
    progressFill.style.width = '70%';

    log(`Executing recovery...`, 'info');
    await sleep(800);
      const recovered = Math.random() > 0.35;
    progressFill.style.width = '90%';

    if (recovered) {
        log(`Recovery successful! ₹${simTx.amount.toLocaleString('en-IN')} recovered.`, 'success');
    simTx.status = 'recovered';
    simTx.audit = [
    {time: new Date().toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), action: `Webhook received: payment.failed — ${simTx.reason} (Gateway: HDFC)`, result: 'fail', strategy: 'Detection', cost_inr: 0.0 },
    {time: new Date().toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), action: `Classified failure: ${simTx.bucket} | Scored recovery potential: ${score}%`, result: 'info', strategy: 'AI Scoring', cost_inr: 0.0 },
    {time: new Date().toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), action: `Selected strategy: ${strategy} (Optimiser routing)`, result: 'info', strategy: 'Strategy Router', cost_inr: 0.0 },
    {time: new Date().toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), action: `₹${simTx.amount.toLocaleString('en-IN')} recovered successfully via ${simTx.method}`, result: 'success', strategy: strategy, cost_inr: 2.50 }
    ];
    resultPanel.style.display = 'block';
    document.getElementById('simResultText').textContent = '₹' + simTx.amount.toLocaleString('en-IN') + ' recovered';
    document.getElementById('simResultText').style.color = 'var(--positive)';
    document.getElementById('simResultDetail').textContent = `Strategy: ${strategy} | Score: ${score}% | Attempts: 1/${maxAttempts}`;
      } else {
        log(`Recovery failed after ${maxAttempts} attempts.`, 'error');
    simTx.status = 'failed';
    simTx.audit = [
    {time: new Date().toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), action: `Webhook received: payment.failed — ${simTx.reason} (Gateway: HDFC)`, result: 'fail', strategy: 'Detection', cost_inr: 0.0 },
    {time: new Date().toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), action: `Classified failure: ${simTx.bucket} | Scored recovery potential: ${score}%`, result: 'info', strategy: 'AI Scoring', cost_inr: 0.0 },
    {time: new Date().toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), action: `Selected strategy: ${strategy} (Optimiser routing)`, result: 'info', strategy: 'Strategy Router', cost_inr: 0.0 },
    {time: new Date().toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }), action: `Max attempts (${maxAttempts}) exhausted`, result: 'fail', strategy: strategy, cost_inr: 5.00 }
    ];
    resultPanel.style.display = 'block';
    document.getElementById('simResultText').textContent = 'Recovery failed';
    document.getElementById('simResultText').style.color = 'var(--danger)';
    document.getElementById('simResultDetail').textContent = `Strategy: ${strategy} | Score: ${score}% | All attempts exhausted`;
      }
    progressFill.style.width = '100%';
    btn.disabled = false;
    transactions.unshift(simTx);
    renderAll();
    }

    async function generateNewFailure() {
      try {
        const response = await fetch('http://localhost:8000/transactions/simulate', {
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