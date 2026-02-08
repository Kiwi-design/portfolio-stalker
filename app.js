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

// --- App UI ---
const appBox = document.getElementById("appBox");

// Transactions UI
const txStatusEl = document.getElementById("txStatus");
const txListEl = document.getElementById("txList");

const txSymbolEl = document.getElementById("txSymbol");
const txDateEl = document.getElementById("txDate");
const txSideEl = document.getElementById("txSide");
const txQtyEl = document.getElementById("txQty");
const txPriceEl = document.getElementById("txPrice");
const addTxBtn = document.getElementById("addTx");

// Portfolio UI
const loadPortfolioBtn = document.getElementById("loadPortfolio");
const portfolioStatusEl = document.getElementById("portfolioStatus");
const portfolioOutputEl = document.getElementById("portfolioOutput");

function setStatus(msg) { statusEl.textContent = msg; }
function setTxStatus(msg) { txStatusEl.textContent = msg; }
function setPortfolioStatus(msg) { portfolioStatusEl.textContent = msg; }

function setLoggedInUI(email) {
  signupBtn.style.display = "none";
  loginBtn.style.display = "none";
  logoutBtn.style.display = "inline-block";
  appBox.style.display = "block";
  setStatus(`Logged in as: ${email}`);
}

function setLoggedOutUI() {
  signupBtn.style.display = "inline-block";
  loginBtn.style.display = "inline-block";
  logoutBtn.style.display = "none";
  appBox.style.display = "none";
  setStatus("Not logged in.");
  setTxStatus("");
  setPortfolioStatus("");
  txListEl.innerHTML = "";
  portfolioOutputEl.innerHTML = "";
}

async function getSessionOrThrow() {
  const { data, error } = await supabaseClient.auth.getSession();
  if (error) throw new Error(error.message);
  if (!data.session) throw new Error("Not logged in.");
  return data.session;
}

async function refreshTransactions() {
  setTxStatus("Loading transactions...");

  const { data, error } = await supabaseClient
    .from("transactions")
    .select("id, symbol, txn_date, side, quantity, price, created_at")
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
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Symbol</th>
          <th>Side</th>
          <th class="num">Qty</th>
          <th class="num">Price</th>
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
      </tr>
    `;
  }

  html += `</tbody></table>`;
  txListEl.innerHTML = html;
}

function renderPortfolioTable(results) {
  let total_eur = 0;

  let html = `
    <table style="min-width: 820px;">
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
          <td colspan="6" style="text-align:right; font-weight:bold; border-top:2px solid #ccc; padding-top:10px;">
            Total (EUR)
          </td>
          <td class="num" style="font-weight:bold; border-top:2px solid #ccc; padding-top:10px;">
            ${total_eur.toFixed(2)}
          </td>
        </tr>
      </tfoot>
    </table>
  `;

  return html;
}

// ----- Init (restore session if already logged in) -----
(async function init() {
  const { data, error } = await supabaseClient.auth.getSession();
  if (error) {
    setStatus("Session error: " + error.message);
    return;
  }

  const session = data.session;
  if (session?.user?.email) {
    setLoggedInUI(session.user.email);
    await refreshTransactions();
  } else {
    setLoggedOutUI();
  }
})();

// ----- Auth handlers -----
signupBtn.addEventListener("click", async () => {
  const email = emailEl.value.trim();
  const password = passwordEl.value;

  if (!email || !password) {
    setStatus("Please enter email + password.");
    return;
  }

  setStatus("Signing up...");

  const { data, error } = await supabaseClient.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: EMAIL_REDIRECT }
  });

  if (error) {
    setStatus("Sign up error: " + error.message);
    return;
  }

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

  if (!email || !password) {
    setStatus("Please enter email + password.");
    return;
  }

  setStatus("Logging in...");

  const { data, error } = await supabaseClient.auth.signInWithPassword({ email, password });

  if (error) {
    setStatus("Login error: " + error.message);
    return;
  }

  setLoggedInUI(data.user.email);
  await refreshTransactions();
});

logoutBtn.addEventListener("click", async () => {
  setStatus("Logging out...");

  const { error } = await supabaseClient.auth.signOut();
  if (error) {
    setStatus("Logout error: " + error.message);
    return;
  }

  setLoggedOutUI();
});

// ----- Add transaction -----
addTxBtn.addEventListener("click", async () => {
  const symbol = txSymbolEl.value.trim().toUpperCase();
  const txn_date = txDateEl.value;
  const side = txSideEl.value;
  const quantity = Number(txQtyEl.value);
  const price = Number(txPriceEl.value);

  if (!symbol || !txn_date || !side || !Number.isFinite(quantity) || !Number.isFinite(price) || quantity <= 0 || price <= 0) {
    setTxStatus("Please fill symbol, date, side, quantity (>0), and price (>0).");
    return;
  }

  setTxStatus("Saving transaction...");

  try {
    const session = await getSessionOrThrow();
    const user_id = session.user.id;

    const { error } = await supabaseClient.from("transactions").insert([{
      user_id,
      symbol,
      txn_date,
      side,
      quantity,
      price
    }]);

    if (error) {
      setTxStatus("Insert error: " + error.message);
      return;
    }

    setTxStatus("Saved ✅");
    txQtyEl.value = "";
    txPriceEl.value = "";

    await refreshTransactions();
  } catch (e) {
    setTxStatus("Error: " + e.message);
  }
});

// ----- Load portfolio (calls Python backend on Vercel) -----
loadPortfolioBtn.addEventListener("click", async () => {
  setPortfolioStatus("Loading portfolio...");
  portfolioOutputEl.innerHTML = "";

  try {
    const session = await getSessionOrThrow();
    const token = session.access_token;

    const res = await fetch(`${API_BASE}/api/portfolio`, {
      headers: { Authorization: `Bearer ${token}` }
    });

    const data = await res.json();

    if (!res.ok || data.status !== "ok") {
      setPortfolioStatus("Backend error:\n" + JSON.stringify(data, null, 2));
      return;
    }

    setPortfolioStatus("Portfolio loaded ✅");

    const results = data.results || [];
    portfolioOutputEl.innerHTML = renderPortfolioTable(results);

  } catch (e) {
    setPortfolioStatus("Fetch failed:\n" + e.message);
  }
});
