// 1) Paste your Supabase details here
const SUPABASE_URL = "https://dalchqdooacrxtonyoee.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRhbGNocWRvb2Fjcnh0b255b2VlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA1MzM0NTQsImV4cCI6MjA4NjEwOTQ1NH0.4zsqZ0uXNuouoAU7STUb7PGWvOvkweZX6f6RUI8lun4";
const EMAIL_REDIRECT = "https://kiwi-design.github.io/portfolio-stalker/"; // keep your working redirect

const supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// Auth UI
const emailEl = document.getElementById("email");
const passwordEl = document.getElementById("password");
const statusEl = document.getElementById("status");
const signupBtn = document.getElementById("signup");
const loginBtn = document.getElementById("login");
const logoutBtn = document.getElementById("logout");

// Transaction UI
const txBox = document.getElementById("txBox");
const txListBox = document.getElementById("txListBox");
const txStatusEl = document.getElementById("txStatus");
const txListEl = document.getElementById("txList");

const txSymbolEl = document.getElementById("txSymbol");
const txDateEl = document.getElementById("txDate");
const txSideEl = document.getElementById("txSide");
const txQtyEl = document.getElementById("txQty");
const txPriceEl = document.getElementById("txPrice");
const addTxBtn = document.getElementById("addTx");

function setStatus(msg) { statusEl.textContent = msg; }
function setTxStatus(msg) { txStatusEl.textContent = msg; }

function setLoggedInUI(email) {
  signupBtn.style.display = "none";
  loginBtn.style.display = "none";
  logoutBtn.style.display = "inline-block";
  txBox.style.display = "block";
  txListBox.style.display = "block";
  setStatus(`Logged in as: ${email}`);
}

function setLoggedOutUI() {
  signupBtn.style.display = "inline-block";
  loginBtn.style.display = "inline-block";
  logoutBtn.style.display = "none";
  txBox.style.display = "none";
  txListBox.style.display = "none";
  setStatus("Not logged in.");
  setTxStatus("");
  txListEl.innerHTML = "";
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

// Init: check session
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

// Sign up (with explicit redirect)
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

// Log in
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

// Log out
logoutBtn.addEventListener("click", async () => {
  setStatus("Logging out...");
  const { error } = await supabaseClient.auth.signOut();
  if (error) {
    setStatus("Logout error: " + error.message);
    return;
  }
  setLoggedOutUI();
});

// Add transaction
addTxBtn.addEventListener("click", async () => {
  const symbol = txSymbolEl.value.trim().toUpperCase();
  const txn_date = txDateEl.value;
  const side = txSideEl.value;
  const quantity = Number(txQtyEl.value);
  const price = Number(txPriceEl.value);

  if (!symbol || !txn_date || !side || !quantity || !price) {
    setTxStatus("Please fill symbol, date, side, quantity, and price.");
    return;
  }

  setTxStatus("Saving transaction...");

  // Get current user (RLS uses auth.uid() on Supabase side)
  const { data: sessionData, error: sessionErr } = await supabaseClient.auth.getSession();
  if (sessionErr || !sessionData.session?.user) {
    setTxStatus("You are not logged in.");
    return;
  }

  const user_id = sessionData.session.user.id;

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
});
