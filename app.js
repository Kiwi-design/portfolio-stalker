// 1) Paste your Supabase details here
const SUPABASE_URL = "https://dalchqdooacrxtonyoee.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRhbGNocWRvb2Fjcnh0b255b2VlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA1MzM0NTQsImV4cCI6MjA4NjEwOTQ1NH0.4zsqZ0uXNuouoAU7STUb7PGWvOvkweZX6f6RUI8lun4";
const EMAIL_REDIRECT = "https://kiwi-design.github.io/portfolio-stalker/"; // keep your working redirect
const API_BASE = "https://portfolio-stalker.vercel.app";
const supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// --- Auth UI ---
const emailEl = document.getElementById("email");
const passwordEl = document.getElementById("password");
const statusEl = document.getElementById("status");
const authPanelEl = document.getElementById("authPanel");
const signupBtn = document.getElementById("signup");
const loginBtn = document.getElementById("login");
const logoutBtn = document.getElementById("logout");
const postLoginPanel = document.getElementById("postLoginPanel");
const loggedInHintEl = document.getElementById("loggedInHint");

// Menu + Sections
const menuEl = document.getElementById("menu");
const menuToggleBtn = document.getElementById("menuToggle");
const appBox = document.getElementById("appBox");

const tabPortfolio = document.getElementById("tabPortfolio");
const tabPerformance = document.getElementById("tabPerformance");
const tabTransactions = document.getElementById("tabTransactions");
const tabAddEdit = document.getElementById("tabAddEdit");
const tabStatistics = document.getElementById("tabStatistics");
const menuLogoutBtn = document.getElementById("menuLogout");

const sectionPortfolio = document.getElementById("sectionPortfolio");
const sectionPerformance = document.getElementById("sectionPerformance");
const sectionTransactions = document.getElementById("sectionTransactions");
const sectionAddEdit = document.getElementById("sectionAddEdit");
const sectionStatistics = document.getElementById("sectionStatistics");

// Portfolio UI
const loadPortfolioBtn = document.getElementById("loadPortfolio");
const portfolioStatusEl = document.getElementById("portfolioStatus");
const portfolioOutputEl = document.getElementById("portfolioOutput");

// Performance UI
const refreshPerfBtn = document.getElementById("refreshPerf");
const perfStatusEl = document.getElementById("perfStatus");
const perfOutputEl = document.getElementById("perfOutput");

// Statistics UI
const refreshStatsBtn = document.getElementById("refreshStats");
const statsStatusEl = document.getElementById("statsStatus");
const statsOutputEl = document.getElementById("statsOutput");

// Transactions UI
const refreshTxBtn = document.getElementById("refreshTx");
const txStatusEl = document.getElementById("txStatus");
const txListEl = document.getElementById("txList");

// Add/Edit UI
const addEditStatusEl = document.getElementById("addEditStatus");

const txSymbolEl = document.getElementById("txSymbol");
const txDateEl = document.getElementById("txDate");
const txSideEl = document.getElementById("txSide");
const txQtyEl = document.getElementById("txQty");
const txPriceEl = document.getElementById("txPrice");
const addTxBtn = document.getElementById("addTx");
const cancelEditBtn = document.getElementById("cancelEdit");

// --- Edit state ---
let editingTxId = null;

// Cache last backend payload
let lastPortfolioPayload = null;

function setStatus(msg) { statusEl.textContent = msg; }
function setTxStatus(msg) { txStatusEl.textContent = msg; }
function setAddEditStatus(msg) { addEditStatusEl.textContent = msg; }
function setPortfolioStatus(msg) { portfolioStatusEl.textContent = msg; }
function setPerfStatus(msg) { perfStatusEl.textContent = msg; }
function setStatsStatus(msg) { statsStatusEl.textContent = msg; }

function setActiveTab(which) {
  [tabPortfolio, tabPerformance, tabTransactions, tabAddEdit, tabStatistics].forEach(b => b.classList.remove("active"));
  if (which === "portfolio") tabPortfolio.classList.add("active");
  if (which === "performance") tabPerformance.classList.add("active");
  if (which === "transactions") tabTransactions.classList.add("active");
  if (which === "addedit") tabAddEdit.classList.add("active");
  if (which === "statistics") tabStatistics.classList.add("active");

  [sectionPortfolio, sectionPerformance, sectionTransactions, sectionAddEdit, sectionStatistics].forEach(s => s.classList.remove("active"));
  if (which === "portfolio") sectionPortfolio.classList.add("active");
  if (which === "performance") sectionPerformance.classList.add("active");
  if (which === "transactions") sectionTransactions.classList.add("active");
  if (which === "addedit") sectionAddEdit.classList.add("active");
  if (which === "statistics") sectionStatistics.classList.add("active");
}

function setMenuOpen(isOpen) {
  menuEl.classList.toggle("open", isOpen);
  menuToggleBtn.setAttribute("aria-expanded", String(isOpen));
}

async function doLogout() {
  setStatus("Logging out...");
  const { error } = await supabaseClient.auth.signOut();
  if (error) { setStatus("Logout error: " + error.message); return; }
  setLoggedOutUI();
}

tabPortfolio.addEventListener("click", async () => {
  appBox.style.display = "block";
  setActiveTab("portfolio");
  setMenuOpen(false);
});
tabPerformance.addEventListener("click", () => {
  appBox.style.display = "block";
  setActiveTab("performance");
  if (lastPortfolioPayload?.performance) renderPerformance(lastPortfolioPayload);
  setMenuOpen(false);
});
tabTransactions.addEventListener("click", async () => {
  appBox.style.display = "block";
  setActiveTab("transactions");
  await refreshTransactions();
  setMenuOpen(false);
});
tabAddEdit.addEventListener("click", () => {
  appBox.style.display = "block";
  setActiveTab("addedit");
  setMenuOpen(false);
});
tabStatistics.addEventListener("click", () => {
  appBox.style.display = "block";
  setActiveTab("statistics");
  void refreshStatistics();
  setMenuOpen(false);
});

menuToggleBtn.addEventListener("click", (event) => {
  event.stopPropagation();
  const isOpen = !menuEl.classList.contains("open");
  setMenuOpen(isOpen);
});

menuEl.addEventListener("click", (event) => {
  event.stopPropagation();
});

document.addEventListener("click", () => {
  if (menuEl.classList.contains("open")) setMenuOpen(false);
});

menuLogoutBtn.addEventListener("click", async () => {
  setMenuOpen(false);
  await doLogout();
});

function enterEditMode(tx) {
  editingTxId = tx.id;
  txSymbolEl.value = tx.symbol;
  txDateEl.value = tx.txn_date;
  txSideEl.value = tx.side;
  txQtyEl.value = tx.quantity;
  txPriceEl.value = tx.price;

  addTxBtn.textContent = "Save changes";
  cancelEditBtn.style.display = "inline-block";
  setAddEditStatus(`Editing transaction ${tx.id}`);
  setActiveTab("addedit");
}

function exitEditMode() {
  editingTxId = null;
  addTxBtn.textContent = "Add transaction";
  cancelEditBtn.style.display = "none";
  setAddEditStatus("");
  txQtyEl.value = "";
  txPriceEl.value = "";
}

cancelEditBtn.addEventListener("click", () => exitEditMode());

function setLoggedInUI(email) {
  authPanelEl.classList.add("hidden");
  signupBtn.style.display = "none";
  loginBtn.style.display = "none";
  logoutBtn.style.display = "none";

  postLoginPanel.style.display = "grid";
  appBox.style.display = "none";
  setMenuOpen(false);

  loggedInHintEl.textContent = `Logged in as: ${email}
Use the menu to open a section.`;
  setStatus("");
}

function setLoggedOutUI() {
  authPanelEl.classList.remove("hidden");
  signupBtn.style.display = "inline-block";
  loginBtn.style.display = "inline-block";
  logoutBtn.style.display = "none";

  postLoginPanel.style.display = "none";
  appBox.style.display = "none";
  setMenuOpen(false);

  loggedInHintEl.textContent = "";
  setStatus("Not logged in.");
  setTxStatus("");
  setAddEditStatus("");
  setPortfolioStatus("");
  setPerfStatus("");
  setStatsStatus("");

  txListEl.innerHTML = "";
  portfolioOutputEl.innerHTML = "";
  perfOutputEl.innerHTML = "";
  statsOutputEl.innerHTML = "";
  lastPortfolioPayload = null;

  exitEditMode();
}

async function refreshPortfolioDailyValueOnLogin() {
  try {
    const { error } = await supabaseClient.rpc("refresh_portfolio_daily_value_on_login");
    if (error) throw error;
  } catch (e) {
    console.warn("Daily portfolio value refresh skipped:", e.message || e);
  }
}

async function getSessionOrThrow() {
  const { data, error } = await supabaseClient.auth.getSession();
  if (error) throw new Error(error.message);
  if (!data.session) throw new Error("Not logged in.");
  return data.session;
}

/* ---------- Transactions list ---------- */

async function refreshTransactions() {
  setTxStatus("Loading transactions...");

  try {
    await syncSecurityNamesForUserTransactions();
  } catch (e) {
    console.warn("Security-name sync skipped:", e.message || e);
  }

  const { data, error } = await supabaseClient
    .from("transactions")
    .select("id, user_id, symbol, security_name, txn_date, side, quantity, price, created_at")
    .order("txn_date", { ascending: false })
    .order("created_at", { ascending: false });

  if (error) {
    setTxStatus("Error loading transactions: " + error.message);
    return;
  }

  setTxStatus("");

  if (!data || data.length === 0) {
    txListEl.innerHTML = "<p>No transactions yet.</p>";
    return;
  }

  let html = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Security / ISIN</th>
            <th>Side</th>
            <th class="num">Qty</th>
            <th class="num">Price (EUR)</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
  `;

  for (const r of data) {
    const safeName = (r.security_name || "").trim();
    html += `
      <tr>
        <td>${r.txn_date}</td>
        <td>
          ${safeName ? `<div class="security-name">${safeName}</div>` : ""}
          <div class="isin-symbol">${r.symbol}</div>
        </td>
        <td>${r.side}</td>
        <td class="num">${Number(r.quantity).toFixed(4)}</td>
        <td class="num">${Number(r.price).toFixed(4)}</td>
        <td>
          <button class="editTx"
            data-id="${r.id}"
            data-symbol="${r.symbol}"
            data-txn_date="${r.txn_date}"
            data-side="${r.side}"
            data-quantity="${r.quantity}"
            data-price="${r.price}"
          >Edit</button>

          <button class="deleteTx danger" style="margin-left:8px;"
            data-id="${r.id}"
            data-symbol="${r.symbol}"
            data-txn_date="${r.txn_date}"
            data-side="${r.side}"
            data-quantity="${r.quantity}"
            data-price="${r.price}"
          >Delete</button>
        </td>
      </tr>
    `;
  }

  html += `
        </tbody>
      </table>
    </div>
  `;

  txListEl.innerHTML = html;

  txListEl.querySelectorAll(".editTx").forEach((btn) => {
    btn.addEventListener("click", () => {
      enterEditMode({
        id: btn.dataset.id,
        symbol: btn.dataset.symbol,
        txn_date: btn.dataset.txn_date,
        side: btn.dataset.side,
        quantity: Number(btn.dataset.quantity),
        price: Number(btn.dataset.price),
      });
    });
  });

  txListEl.querySelectorAll(".deleteTx").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      const summary = `${btn.dataset.txn_date} ${btn.dataset.side} ${btn.dataset.symbol} qty=${btn.dataset.quantity} @ ${btn.dataset.price} EUR`;
      if (!confirm(`Delete this transaction?\n\n${summary}`)) return;

      setTxStatus("Deleting...");

      try {
        const session = await getSessionOrThrow();
        const user_id = session.user.id;

        const { error } = await supabaseClient
          .from("transactions")
          .delete()
          .eq("id", id)
          .eq("user_id", user_id);

        if (error) {
          setTxStatus("Delete error: " + error.message);
          return;
        }

        if (editingTxId === id) exitEditMode();

        setTxStatus("Deleted ✅");
        await refreshTransactions();
      } catch (e) {
        setTxStatus("Error: " + e.message);
      }
    });
  });
}

refreshTxBtn.addEventListener("click", refreshTransactions);

function fmtPct(value) {
  if (!Number.isFinite(value)) return "—";
  return `${value.toFixed(2)}%`;
}

function fmtNum(value, digits = 2) {
  if (!Number.isFinite(value)) return "—";
  return Number(value).toFixed(digits);
}

function quantile(sortedVals, q) {
  if (!sortedVals.length) return null;
  const pos = (sortedVals.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  if (lo === hi) return sortedVals[lo];
  return sortedVals[lo] + (sortedVals[hi] - sortedVals[lo]) * (pos - lo);
}

function toISODate(d) {
  return d.toISOString().slice(0, 10);
}

function previousFriday(fromDate = new Date()) {
  const d = new Date(fromDate);
  const day = d.getUTCDay();
  const daysSinceFriday = (day + 2) % 7;
  d.setUTCDate(d.getUTCDate() - (daysSinceFriday === 0 ? 7 : daysSinceFriday));
  return toISODate(d);
}

async function buildPortfolioHistory() {
  const session = await getSessionOrThrow();
  const { data, error } = await supabaseClient
    .from("portfolio_daily_value")
    .select("valuation_date, portfolio_value_eur")
    .eq("user_id", session.user.id)
    .order("valuation_date", { ascending: true });

  if (error) throw new Error(`portfolio_daily_value error: ${error.message}`);

  const cleaned = (data || [])
    .map((row) => ({ date: row.valuation_date, value: Number(row.portfolio_value_eur) }))
    .filter((h) => Number.isFinite(h.value) && h.value > 0);

  const dailyReturns = [];
  for (let i = 1; i < cleaned.length; i += 1) {
    const prev = cleaned[i - 1].value;
    const cur = cleaned[i].value;
    if (prev > 0) dailyReturns.push({ date: cleaned[i].date, r: (cur - prev) / prev });
  }

  return { history: cleaned, dailyReturns };
}

function computeStatistics(history, dailyReturns) {
  const todayVal = history.at(-1)?.value || 0;
  if (!history.length || dailyReturns.length < 2) return null;

  let peak = history[0].value;
  let maxDrawdown = 0;
  for (const h of history) {
    peak = Math.max(peak, h.value);
    if (peak > 0) maxDrawdown = Math.min(maxDrawdown, (h.value / peak) - 1);
  }

  const oneYear = dailyReturns.slice(-252).map((x) => x.r);
  const mean = oneYear.reduce((a, b) => a + b, 0) / Math.max(oneYear.length, 1);
  const variance = oneYear.reduce((acc, r) => acc + ((r - mean) ** 2), 0) / Math.max(oneYear.length - 1, 1);
  const std = Math.sqrt(variance);

  const mkHorizon = (window) => {
    if (history.length <= window) return { varPct: null, cvarPct: null, varEur: null, cvarEur: null };
    const horizonReturns = [];
    for (let i = window; i < history.length; i += 1) {
      const base = history[i - window].value;
      const now = history[i].value;
      if (base > 0) horizonReturns.push((now / base) - 1);
    }
    const losses = horizonReturns.map((r) => -r).sort((a, b) => a - b);
    const varPct = quantile(losses, 0.95);
    const tail = losses.filter((l) => l >= varPct);
    const cvarPct = tail.length ? tail.reduce((a, b) => a + b, 0) / tail.length : null;
    return {
      varPct,
      cvarPct,
      varEur: Number.isFinite(varPct) ? varPct * todayVal : null,
      cvarEur: Number.isFinite(cvarPct) ? cvarPct * todayVal : null,
    };
  };

  const m3 = mkHorizon(63);
  const m6 = mkHorizon(126);

  return [
    { key: "max_drawdown", label: "Maximum drawdown", value: maxDrawdown * 100, unit: "%" },
    { key: "variance_1y", label: "Variance (1 year)", value: variance, unit: "return²" },
    { key: "std_1y", label: "STD (1 year)", value: std * 100, unit: "%" },
    { key: "var_3m_95", label: "3-months-95% VaR", value: m3.varPct * 100, unit: "%" },
    { key: "cvar_3m_95_eur", label: "3-months-95% CVaR (EUR)", value: m3.cvarEur, unit: "EUR" },
    { key: "var_6m_95", label: "6-months-95% VaR", value: m6.varPct * 100, unit: "%" },
    { key: "cvar_6m_95_eur", label: "6-months-95% CVaR (EUR)", value: m6.cvarEur, unit: "EUR" },
  ];
}

async function persistStatistics(stats) {
  const session = await getSessionOrThrow();
  const today = new Date().toISOString().slice(0, 10);
  const rows = stats.map((s) => ({
    user_id: session.user.id,
    as_of_date: today,
    metric_key: s.key,
    metric_label: s.label,
    metric_value: s.value,
    metric_unit: s.unit,
  }));

  const { error } = await supabaseClient
    .from("portfolio_statistics_history")
    .upsert(rows, { onConflict: "user_id,as_of_date,metric_key" });
  if (error) {
    setStatsStatus(`Stats computed, but storing history failed: ${error.message}`);
  }
}

async function loadHistoricalStatisticsRows() {
  const session = await getSessionOrThrow();
  const { data, error } = await supabaseClient
    .from("portfolio_statistics_history")
    .select("metric_key, as_of_date, metric_value")
    .eq("user_id", session.user.id)
    .order("as_of_date", { ascending: false });
  if (error) throw new Error(error.message);
  return data || [];
}

function renderStatistics(stats, historyRows) {
  const today = new Date().toISOString().slice(0, 10);
  const prevFri = previousFriday(new Date());
  const map = new Map();
  for (const r of historyRows) {
    if (!map.has(r.metric_key)) map.set(r.metric_key, new Map());
    map.get(r.metric_key).set(r.as_of_date, Number(r.metric_value));
  }

  let html = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Statistic</th>
            <th class="num">Today (${today})</th>
            <th class="num">Preceding Friday (${prevFri})</th>
            <th>Unit</th>
          </tr>
        </thead>
        <tbody>
  `;

  for (const s of stats) {
    const byDate = map.get(s.key) || new Map();
    const todayValue = byDate.get(today) ?? s.value;
    const prevValue = byDate.get(prevFri) ?? (() => {
      const prevCandidates = [...byDate.entries()]
        .filter(([d]) => d <= prevFri)
        .sort((a, b) => a[0].localeCompare(b[0]));
      return prevCandidates.length ? prevCandidates.at(-1)[1] : null;
    })();
    const digits = s.unit === "return²" ? 6 : 2;
    html += `
      <tr>
        <td>${s.label}</td>
        <td class="num">${fmtNum(todayValue, digits)}</td>
        <td class="num">${fmtNum(prevValue, digits)}</td>
        <td>${s.unit}</td>
      </tr>
    `;
  }

  html += `
        </tbody>
      </table>
    </div>
    <div class="muted" style="margin-top:10px;">
      <strong>How the statistics are computed:</strong><br/>
      • Maximum drawdown: minimum value of (Portfolio Value / Running Peak - 1).<br/>
      • Variance (1 year): sample variance of daily portfolio returns over the last 252 observations.<br/>
      • STD (1 year): square root of the 1-year variance.<br/>
      • 3M/6M 95% VaR (%): historical-simulation loss quantile (95th percentile) of rolling 3-month (63 days) and 6-month (126 days) returns.<br/>
      • 3M/6M 95% CVaR (EUR): average tail loss beyond VaR converted into EUR using current portfolio value.
    </div>
  `;
  statsOutputEl.innerHTML = html;
}

async function refreshStatistics() {
  setStatsStatus("Computing statistics...");
  try {
    const { history, dailyReturns } = await buildPortfolioHistory();
    const stats = computeStatistics(history, dailyReturns);
    if (!stats) {
      setStatsStatus("Not enough history to compute statistics yet.");
      statsOutputEl.innerHTML = "";
      return;
    }

    await persistStatistics(stats);
    let historyRows = [];
    try {
      historyRows = await loadHistoricalStatisticsRows();
    } catch (_e) {
      // Table can be absent; keep showing current values only.
    }
    renderStatistics(stats, historyRows);
    setStatsStatus("Statistics refreshed ✅");
  } catch (e) {
    setStatsStatus(`Statistics error: ${e.message}`);
  }
}

refreshStatsBtn.addEventListener("click", refreshStatistics);

/* ---------- Portfolio + Performance ---------- */

function renderPortfolioTable(results) {
  let total_eur = 0;

  let html = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Symbol</th>
            <th class="num">Price</th>
            <th>Currency</th>
            <th class="num">Quantity</th>
            <th class="num">Value</th>
            <th class="num">Value (EUR)</th>
          </tr>
        </thead>
        <tbody>
  `;

  for (const r of results) {
    const price = r.price ?? 0;
    const qty = r.quantity ?? 0;
    const value = r.value ?? 0;
    const value_eur = r.value_eur ?? 0;
    const ccy = r.currency ?? "";
    total_eur += value_eur;

    html += `
      <tr>
        <td>${r.name || ""}</td>
        <td>${r.symbol}</td>
        <td class="num">${Number(price).toFixed(4)}</td>
        <td>${ccy}</td>
        <td class="num">${Number(qty).toFixed(4)}</td>
        <td class="num">${Number(value).toFixed(2)}</td>
        <td class="num">${Number(value_eur).toFixed(2)}</td>
      </tr>
    `;
  }

  html += `
        </tbody>
        <tfoot>
          <tr>
            <td colspan="6" class="num" style="font-weight:700; border-top:2px solid #ccc;">Total (EUR)</td>
            <td class="num" style="font-weight:700; border-top:2px solid #ccc;">${total_eur.toFixed(2)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  `;

  return html;
}

function renderPerformance(payload) {
  const perf = payload.performance || [];
  const totals = payload.performance_totals || {};

  let html = "";
  if (!perf.length) {
    html += "<p>No positions to calculate performance.</p>";
  } else {
    html += `
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th class="num">Quantity</th>
              <th class="num">Avg Cost (native)</th>
              <th class="num">Avg Sold (native)</th>
              <th class="num">Current (native)</th>
              <th>Currency</th>
              <th class="num">Unrealized (EUR)</th>
              <th class="num">Percentage</th>
              <th class="num">Realized (EUR)</th>
              <th class="num">Percentage</th>
            </tr>
          </thead>
          <tbody>
    `;

    for (const r of perf) {
      const isClosed = Math.abs(Number(r.quantity ?? 0)) <= 1e-12;
      html += `
        <tr${isClosed ? ' style="background:#ffecec;"' : ''}>
          <td>${r.name || ""}</td>
          <td class="num">${Number(r.quantity).toFixed(4)}</td>
          <td class="num">${Number(r.avg_cost ?? 0).toFixed(4)}</td>
          <td class="num">${Number(r.avg_sold ?? 0).toFixed(4)}</td>
          <td class="num">${Number(r.current_price ?? 0).toFixed(4)}</td>
          <td>${r.currency || ""}</td>
          <td class="num">${Number(r.unrealized_eur ?? 0).toFixed(2)}</td>
          <td class="num">${Number(r.percent_unrealized ?? 0).toFixed(2)}%</td>
          <td class="num">${Number(r.realized_eur ?? 0).toFixed(2)}</td>
          <td class="num">${Number(r.percent_realized ?? 0).toFixed(2)}%</td>
        </tr>
      `;
    }

    html += `
          </tbody>
          <tfoot>
            <tr>
              <td colspan="6" class="num" style="font-weight:700; border-top:2px solid #ccc;">Totals</td>
              <td class="num" style="font-weight:700; border-top:2px solid #ccc;">${Number(totals.total_unrealized_eur ?? 0).toFixed(2)}</td>
              <td class="num" style="font-weight:700; border-top:2px solid #ccc;">${Number(totals.total_percent ?? 0).toFixed(2)}%</td>
              <td class="num" style="font-weight:700; border-top:2px solid #ccc;">${Number(totals.total_realized_eur ?? 0).toFixed(2)}</td>
              <td class="num" style="font-weight:700; border-top:2px solid #ccc;">-</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <div class="muted" style="margin-top:8px;">
        Total % is portfolio-weighted: total_unrealized_eur / total_cost_basis_eur.
      </div>
    `;
  }

  html += '<div id="twrDailyTable" style="margin-top:14px;"></div>';
  perfOutputEl.innerHTML = html;
}


async function computeDailyTwrSeries(history) {
  if (!history.length) return [];

  const session = await getSessionOrThrow();
  const { data: txRows, error } = await supabaseClient
    .from("transactions")
    .select("txn_date, side, quantity, price")
    .eq("user_id", session.user.id)
    .order("txn_date", { ascending: true });

  if (error) throw new Error(`Transactions error: ${error.message}`);

  const netFlowByDate = new Map();
  for (const tx of txRows || []) {
    const quantity = Number(tx.quantity);
    const priceEur = Number(tx.price);
    if (!Number.isFinite(quantity) || !Number.isFinite(priceEur)) continue;
    const flow = tx.side === "BUY" ? (quantity * priceEur) : (-quantity * priceEur);
    netFlowByDate.set(tx.txn_date, (netFlowByDate.get(tx.txn_date) || 0) + flow);
  }

  const out = [];
  let cumulative = 1;
  for (let i = 1; i < history.length; i += 1) {
    const prev = history[i - 1];
    const cur = history[i];
    const flow = Number(netFlowByDate.get(cur.date) || 0);
    if (!(prev.value > 0)) continue;

    const largeCashFlow = Math.abs(flow) >= (0.15 * prev.value);
    const r = ((cur.value - flow) / prev.value) - 1;
    cumulative *= (1 + r);

    out.push({
      date: cur.date,
      marketValueEur: cur.value,
      netExternalFlowEur: flow,
      largeCashFlow,
      dailyPct: r * 100,
      cumulativePct: (cumulative - 1) * 100,
    });
  }

  return out;
}

function renderDailyTwrTable(rows) {
  const host = document.getElementById("twrDailyTable");
  if (!host) return;

  if (!rows.length) {
    host.innerHTML = '<p class="muted">No daily TWR history yet.</p>';
    return;
  }

  let html = `
    <h3 style="margin:0 0 8px 0;">Daily Time-Weighted Return (large cash flow policy: 15%)</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th class="num">Portfolio value (EUR)</th>
            <th class="num">Net external flow (EUR)</th>
            <th>Large cash flow (≥15%)</th>
            <th class="num">Daily TWR %</th>
            <th class="num">Cumulated TWR %</th>
          </tr>
        </thead>
        <tbody>
  `;

  for (const row of rows) {
    html += `
      <tr>
        <td>${row.date}</td>
        <td class="num">${fmtNum(row.marketValueEur, 2)}</td>
        <td class="num">${fmtNum(row.netExternalFlowEur, 2)}</td>
        <td>${row.largeCashFlow ? "Yes" : "No"}</td>
        <td class="num">${fmtPct(row.dailyPct)}</td>
        <td class="num">${fmtPct(row.cumulativePct)}</td>
      </tr>
    `;
  }

  html += `
        </tbody>
      </table>
    </div>
    <div class="muted" style="margin-top:8px;">
      Formula: daily TWR = ((V_t - CF_t) / V_{t-1}) - 1, where CF_t is net BUY/SELL cash flow in EUR.
    </div>
  `;

  host.innerHTML = html;
}

async function loadPortfolioAndPerformance() {
  setPortfolioStatus("Loading portfolio...");
  setPerfStatus("Loading performance...");
  portfolioOutputEl.innerHTML = "";

  try {
    const session = await getSessionOrThrow();
    const token = session.access_token;

    const res = await fetch(`${API_BASE}/api/portfolio`, {
      headers: { Authorization: `Bearer ${token}` }
    });

    const data = await res.json();
    if (!res.ok || data.status !== "ok") {
      const msg = "Backend error:\n" + JSON.stringify(data, null, 2);
      setPortfolioStatus(msg);
      setPerfStatus(msg);
      return;
    }

    lastPortfolioPayload = data;

    setPortfolioStatus("Portfolio loaded ✅");
    portfolioOutputEl.innerHTML = renderPortfolioTable(data.results || []);

    setPerfStatus("Performance loaded ✅");
    renderPerformance(data);

    const { history } = await buildPortfolioHistory();
    const twrRows = await computeDailyTwrSeries(history);
    renderDailyTwrTable(twrRows);

  } catch (e) {
    const msg = "Fetch failed:\n" + e.message;
    setPortfolioStatus(msg);
    setPerfStatus(msg);
  }
}

loadPortfolioBtn.addEventListener("click", loadPortfolioAndPerformance);
refreshPerfBtn.addEventListener("click", loadPortfolioAndPerformance);

async function fetchSecurityNameForISIN(symbol) {
  const session = await getSessionOrThrow();
  const token = session.access_token;

  const res = await fetch(`${API_BASE}/api/isin_name?isin=${encodeURIComponent(symbol)}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  const data = await res.json();
  if (!res.ok || data.status !== "ok" || !data.name) {
    const message = data?.message || `Unable to resolve security name for ${symbol}`;
    throw new Error(message);
  }
  return data.name;
}

async function syncSecurityNamesForUserTransactions() {
  const session = await getSessionOrThrow();
  const token = session.access_token;

  const res = await fetch(`${API_BASE}/api/isin_name`, {
    headers: { Authorization: `Bearer ${token}` }
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.message || "Could not sync ISIN security names");
  }
}

/* ---------- Add / Edit ---------- */

addTxBtn.addEventListener("click", async () => {
  const symbol = txSymbolEl.value.trim().toUpperCase();
  const txn_date = txDateEl.value;
  const side = txSideEl.value;
  const quantity = Number(txQtyEl.value);
  const price = Number(txPriceEl.value); // EUR price

  if (!symbol || !txn_date || !side || !Number.isFinite(quantity) || !Number.isFinite(price) || quantity <= 0 || price <= 0) {
    setAddEditStatus("Please fill symbol, date, side, quantity (>0), and price (>0). Price is in EUR.");
    return;
  }

  setAddEditStatus(editingTxId ? "Saving changes..." : "Saving transaction...");

  try {
    const session = await getSessionOrThrow();
    const user_id = session.user.id;
    const security_name = await fetchSecurityNameForISIN(symbol);

    let error;

    if (!editingTxId) {
      ({ error } = await supabaseClient.from("transactions").insert([{
        user_id, symbol, security_name, txn_date, side, quantity, price
      }]));
    } else {
      ({ error } = await supabaseClient
        .from("transactions")
        .update({ symbol, security_name, txn_date, side, quantity, price })
        .eq("id", editingTxId)
        .eq("user_id", user_id)
      );
    }

    if (error) {
      setAddEditStatus((editingTxId ? "Update error: " : "Insert error: ") + error.message);
      return;
    }

    if (editingTxId) {
      setAddEditStatus("Updated ✅");
      exitEditMode();
    } else {
      setAddEditStatus("Saved ✅");
      txQtyEl.value = "";
      txPriceEl.value = "";
    }

    await refreshTransactions();
  } catch (e) {
    setAddEditStatus("Error: " + e.message);
  }
});

/* ---------- Auth ---------- */

signupBtn.addEventListener("click", async () => {
  const email = emailEl.value.trim();
  const password = passwordEl.value;
  if (!email || !password) { setStatus("Please enter email + password."); return; }
  setStatus("Signing up...");

  const { data, error } = await supabaseClient.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: EMAIL_REDIRECT }
  });

  if (error) { setStatus("Sign up error: " + error.message); return; }

  if (data.session?.user?.email) {
    setLoggedInUI(data.session.user.email);
    await refreshPortfolioDailyValueOnLogin();
    await loadPortfolioAndPerformance();
  } else {
    setStatus("Sign up successful. Check your email if confirmation is required, then log in.");
  }
});

loginBtn.addEventListener("click", async () => {
  const email = emailEl.value.trim();
  const password = passwordEl.value;
  if (!email || !password) { setStatus("Please enter email + password."); return; }
  setStatus("Logging in...");

  const { data, error } = await supabaseClient.auth.signInWithPassword({ email, password });
  if (error) { setStatus("Login error: " + error.message); return; }

  setLoggedInUI(data.user.email);
  await refreshPortfolioDailyValueOnLogin();
  await loadPortfolioAndPerformance();
});

logoutBtn.addEventListener("click", async () => {
  await doLogout();
});

/* ---------- Init ---------- */
(async function init() {
  // Keep post-login content hidden while session is being resolved.
  setLoggedOutUI();

  const { data, error } = await supabaseClient.auth.getSession();
  if (error) { setStatus("Session error: " + error.message); return; }

  const session = data.session;
  if (session?.user?.email) {
    setLoggedInUI(session.user.email);
    await refreshPortfolioDailyValueOnLogin();
    await loadPortfolioAndPerformance();
  } else {
    setLoggedOutUI();
  }
})();
