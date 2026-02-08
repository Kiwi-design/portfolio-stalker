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
const signupBtn = document.getElementById("signup");
const loginBtn = document.getElementById("login");
const logoutBtn = document.getElementById("logout");

// Menu + Sections
const menuEl = document.getElementById("menu");
const appBox = document.getElementById("appBox");

const tabPortfolio = document.getElementById("tabPortfolio");
const tabPerformance = document.getElementById("tabPerformance");
const tabTransactions = document.getElementById("tabTransactions");
const tabAddEdit = document.getElementById("tabAddEdit");

const sectionPortfolio = document.getElementById("sectionPortfolio");
const sectionPerformance = document.getElementById("sectionPerformance");
const sectionTransactions = document.getElementById("sectionTransactions");
const sectionAddEdit = document.getElementById("sectionAddEdit");

// Portfolio UI
const loadPortfolioBtn = document.getElementById("loadPortfolio");
const portfolioStatusEl = document.getElementById("portfolioStatus");
const portfolioOutputEl = document.getElementById("portfolioOutput");

// Performance UI
const refreshPerfBtn = document.getElementById("refreshPerf");
const perfStatusEl = document.getElementById("perfStatus");
const perfOutputEl = document.getElementById("perfOutput");

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

// Cache last portfolio payload so Performance tab can render without refetch if desired
let lastPortfolioPayload = null;

function setStatus(msg) { statusEl.textContent = msg; }
function setTxStatus(msg) { txStatusEl.textContent = msg; }
function setAddEditStatus(msg) { addEditStatusEl.textContent = msg; }
function setPortfolioStatus(msg) { portfolioStatusEl.textContent = msg; }
function setPerfStatus(msg) { perfStatusEl.textContent = msg; }

function setActiveTab(which) {
  [tabPortfolio, tabPerformance, tabTransactions, tabAddEdit].forEach(b => b.classList.remove("active"));
  if (which === "portfolio") tabPortfolio.classList.add("active");
  if (which === "performance") tabPerformance.classList.add("active");
  if (which === "transactions") tabTransactions.classList.add("active");
  if (which === "addedit") tabAddEdit.classList.add("active");

  [sectionPortfolio, sectionPerformance, sectionTransactions, sectionAddEdit].forEach(s => s.classList.remove("active"));
  if (which === "portfolio") sectionPortfolio.classList.add("active");
  if (which === "performance") sectionPerformance.classList.add("active");
  if (which === "transactions") sectionTransactions.classList.add("active");
  if (which === "addedit") sectionAddEdit.classList.add("active");
}

tabPortfolio.addEventListener("click", () => setActiveTab("portfolio"));
tabPerformance.addEventListener("click", () => {
  setActiveTab("performance");
  // if we already have data, render instantly; otherwise prompt refresh
  if (lastPortfolioPayload?.performance) renderPerformance(lastPortfolioPayload);
});
tabTransactions.addEventListener("click", () => setActiveTab("transactions"));
tabAddEdit.addEventListener("click", () => setActiveTab("addedit"));

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
  signupBtn.style.display = "none";
  loginBtn.style.display = "none";
  logoutBtn.style.display = "inline-block";

  menuEl.style.display = "flex";
  appBox.style.display = "block";

  setStatus(`Logged in as: ${email}`);
  setActiveTab("portfolio");
}

function setLoggedOutUI() {
  signupBtn.style.display = "inline-block";
  loginBtn.style.display = "inline-block";
  logoutBtn.style.display = "none";

  menuEl.style.display = "none";
  appBox.style.display = "none";

  setStatus("Not logged in.");
  setTxStatus("");
  setAddEditStatus("");
  setPortfolioStatus("");
  setPerfStatus("");

  txListEl.innerHTML = "";
  portfolioOutputEl.innerHTML = "";
  perfOutputEl.innerHTML = "";
  lastPortfolioPayload = null;

  exitEditMode();
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

  const { data, error } = await supabaseClient
    .from("transactions")
    .select("id, user_id, symbol, txn_date, side, quantity, price, created_at")
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
            <th>Symbol</th>
            <th>Side</th>
            <th class="num">Qty</th>
            <th class="num">Price</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
  `;

  for (const r of data) {
    html += `
      <tr>
        <td>${r.txn_date}</td>
        <td>${r.symbol}</td>
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
      const summary = `${btn.dataset.txn_date} ${btn.dataset.side} ${btn.dataset.symbol} qty=${btn.dataset.quantity} @ ${btn.dataset.price}`;
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

/* ---------- Portfolio + Performance (from backend) ---------- */

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
        <td class="num">${Number(price).toFixed(2)}</td>
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
  if (!perf.length) {
    perfOutputEl.innerHTML = "<p>No open positions to calculate performance.</p>";
    return;
  }

  let html = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Symbol</th>
            <th class="num">Quantity</th>
            <th class="num">Avg Cost</th>
            <th class="num">Current</th>
            <th>Currency</th>
            <th class="num">Unrealized (EUR)</th>
            <th class="num">Percentage</th>
          </tr>
        </thead>
        <tbody>
  `;

  for (const r of perf) {
    html += `
      <tr>
        <td>${r.name || ""}</td>
        <td>${r.symbol}</td>
        <td class="num">${Number(r.quantity).toFixed(4)}</td>
        <td class="num">${Number(r.avg_cost ?? 0).toFixed(4)}</td>
        <td class="num">${Number(r.current_price ?? 0).toFixed(4)}</td>
        <td>${r.currency || ""}</td>
        <td class="num">${Number(r.unrealized_eur ?? 0).toFixed(2)}</td>
        <td class="num">${Number(r.percent_unrealized ?? 0).toFixed(2)}%</td>
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
          </tr>
        </tfoot>
      </table>
    </div>
    <div class="muted" style="margin-top:8px;">
      Total % is portfolio-weighted: total_unrealized_eur / total_cost_basis_eur.
    </div>
  `;

  perfOutputEl.innerHTML = html;
}

async function loadPortfolioAndPerformance() {
  setPortfolioStatus("Loading portfolio...");
  setPerfStatus("Loading performance...");
  portfolioOutputEl.innerHTML = "";
  // keep perf table if already there, but will refresh
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

  } catch (e) {
    const msg = "Fetch failed:\n" + e.message;
    setPortfolioStatus(msg);
    setPerfStatus(msg);
  }
}

loadPortfolioBtn.addEventListener("click", loadPortfolioAndPerformance);
refreshPerfBtn.addEventListener("click", loadPortfolioAndPerformance);

/* ---------- Add / Edit submit ---------- */

addTxBtn.addEventListener("click", async () => {
  const symbol = txSymbolEl.value.trim().toUpperCase();
  const txn_date = txDateEl.value;
  const side = txSideEl.value;
  const quantity = Number(txQtyEl.value);
  const price = Number(txPriceEl.value);

  if (!symbol || !txn_date || !side || !Number.isFinite(quantity) || !Number.isFinite(price) || quantity <= 0 || price <= 0) {
    setAddEditStatus("Please fill symbol, date, side, quantity (>0), and price (>0).");
    return;
  }

  setAddEditStatus(editingTxId ? "Saving changes..." : "Saving transaction...");

  try {
    const session = await getSessionOrThrow();
    const user_id = session.user.id;

    let error;

    if (!editingTxId) {
      ({ error } = await supabaseClient.from("transactions").insert([{
        user_id, symbol, txn_date, side, quantity, price
      }]));
    } else {
      ({ error } = await supabaseClient
        .from("transactions")
        .update({ symbol, txn_date, side, quantity, price })
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
    // portfolio/performance will update when you click refresh

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
    await refreshTransactions();
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
  await refreshTransactions();
});

logoutBtn.addEventListener("click", async () => {
  setStatus("Logging out...");
  const { error } = await supabaseClient.auth.signOut();
  if (error) { setStatus("Logout error: " + error.message); return; }
  setLoggedOutUI();
});

/* ---------- Init ---------- */
(async function init() {
  const { data, error } = await supabaseClient.auth.getSession();
  if (error) { setStatus("Session error: " + error.message); return; }

  const session = data.session;
  if (session?.user?.email) {
    setLoggedInUI(session.user.email);
    await refreshTransactions();
  } else {
    setLoggedOutUI();
  }
})();
