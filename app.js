const SUPABASE_URL = "https://dalchqdooacrxtonyoee.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRhbGNocWRvb2Fjcnh0b255b2VlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA1MzM0NTQsImV4cCI6MjA4NjEwOTQ1NH0.4zsqZ0uXNuouoAU7STUb7PGWvOvkweZX6f6RUI8lun4";
const EMAIL_REDIRECT = "https://kiwi-design.github.io/portfolio-stalker/";

const supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

const emailEl = document.getElementById("email");
const passwordEl = document.getElementById("password");
const statusEl = document.getElementById("status");
const authPanelEl = document.getElementById("authPanel");
const signupBtn = document.getElementById("signup");
const loginBtn = document.getElementById("login");
const logoutBtn = document.getElementById("logout");
const postLoginPanel = document.getElementById("postLoginPanel");
const loggedInHintEl = document.getElementById("loggedInHint");

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

const refreshTxBtn = document.getElementById("refreshTx");
const txStatusEl = document.getElementById("txStatus");
const txListEl = document.getElementById("txList");

const addEditStatusEl = document.getElementById("addEditStatus");
const txSymbolEl = document.getElementById("txSymbol");
const txDateEl = document.getElementById("txDate");
const txSideEl = document.getElementById("txSide");
const txQtyEl = document.getElementById("txQty");
const txPriceEl = document.getElementById("txPrice");
const addTxBtn = document.getElementById("addTx");
const cancelEditBtn = document.getElementById("cancelEdit");

let editingTxId = null;

function setStatus(msg) { statusEl.textContent = msg; }
function setTxStatus(msg) { txStatusEl.textContent = msg; }
function setAddEditStatus(msg) { addEditStatusEl.textContent = msg; }

function setMenuOpen(isOpen) {
  menuEl.classList.toggle("open", isOpen);
  menuToggleBtn.setAttribute("aria-expanded", String(isOpen));
}

function setActiveTab(which) {
  [tabPortfolio, tabPerformance, tabTransactions, tabAddEdit, tabStatistics].forEach((b) => b.classList.remove("active"));
  [sectionPortfolio, sectionPerformance, sectionTransactions, sectionAddEdit, sectionStatistics].forEach((s) => s.classList.remove("active"));

  if (which === "portfolio") {
    tabPortfolio.classList.add("active");
    sectionPortfolio.classList.add("active");
  }
  if (which === "performance") {
    tabPerformance.classList.add("active");
    sectionPerformance.classList.add("active");
  }
  if (which === "transactions") {
    tabTransactions.classList.add("active");
    sectionTransactions.classList.add("active");
  }
  if (which === "addedit") {
    tabAddEdit.classList.add("active");
    sectionAddEdit.classList.add("active");
  }
  if (which === "statistics") {
    tabStatistics.classList.add("active");
    sectionStatistics.classList.add("active");
  }
}

function setLoggedInUI(email) {
  authPanelEl.classList.add("hidden");
  signupBtn.style.display = "none";
  loginBtn.style.display = "none";
  logoutBtn.style.display = "none";

  postLoginPanel.style.display = "grid";
  appBox.style.display = "none";
  loggedInHintEl.textContent = `Logged in as: ${email}\nUse the menu to open a section.`;
  setMenuOpen(false);
  setStatus("");
}

function setLoggedOutUI() {
  authPanelEl.classList.remove("hidden");
  signupBtn.style.display = "inline-block";
  loginBtn.style.display = "inline-block";
  logoutBtn.style.display = "none";

  postLoginPanel.style.display = "none";
  appBox.style.display = "none";
  loggedInHintEl.textContent = "";
  txListEl.innerHTML = "";
  setTxStatus("");
  setAddEditStatus("");
  setMenuOpen(false);
  exitEditMode();
  setStatus("Not logged in.");
}

async function getSessionOrThrow() {
  const { data, error } = await supabaseClient.auth.getSession();
  if (error) throw new Error(error.message);
  if (!data.session) throw new Error("Not logged in.");
  return data.session;
}

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
  txQtyEl.value = "";
  txPriceEl.value = "";
  setAddEditStatus("");
}

function renderTransactions(rows) {
  if (!rows.length) {
    txListEl.innerHTML = '<div class="muted">No transactions yet.</div>';
    return;
  }

  let html = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Symbol</th>
            <th>Date</th>
            <th>Side</th>
            <th class="num">Quantity</th>
            <th class="num">Price (EUR)</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
  `;

  for (const tx of rows) {
    html += `
      <tr>
        <td>${tx.security_name || ""}</td>
        <td>${tx.symbol}</td>
        <td>${tx.txn_date}</td>
        <td>${tx.side}</td>
        <td class="num">${Number(tx.quantity).toFixed(4)}</td>
        <td class="num">${Number(tx.price).toFixed(4)}</td>
        <td>
          <div class="btn-row">
            <button class="edit-btn" data-id="${tx.id}" type="button">Edit</button>
            <button class="danger delete-btn" data-id="${tx.id}" type="button">Delete</button>
          </div>
        </td>
      </tr>
    `;
  }

  html += "</tbody></table></div>";
  txListEl.innerHTML = html;

  txListEl.querySelectorAll(".edit-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.dataset.id);
      const tx = rows.find((r) => Number(r.id) === id);
      if (tx) enterEditMode(tx);
    });
  });

  txListEl.querySelectorAll(".delete-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.dataset.id);
      const ok = window.confirm(`Delete transaction ${id}?`);
      if (!ok) return;

      try {
        const session = await getSessionOrThrow();
        const { error } = await supabaseClient
          .from("transactions")
          .delete()
          .eq("id", id)
          .eq("user_id", session.user.id);

        if (error) {
          setTxStatus(`Delete error: ${error.message}`);
          return;
        }

        if (editingTxId === id) exitEditMode();
        setTxStatus("Deleted ✅");
        await refreshTransactions();
      } catch (e) {
        setTxStatus(`Delete error: ${e.message}`);
      }
    });
  });
}

async function refreshTransactions() {
  setTxStatus("Loading transactions...");
  try {
    const session = await getSessionOrThrow();
    const { data, error } = await supabaseClient
      .from("transactions")
      .select("id,user_id,symbol,security_name,txn_date,side,quantity,price,created_at")
      .eq("user_id", session.user.id)
      .order("txn_date", { ascending: false })
      .order("created_at", { ascending: false });

    if (error) {
      setTxStatus(`Error loading transactions: ${error.message}`);
      return;
    }

    renderTransactions(data || []);
    setTxStatus(`${(data || []).length} transaction(s).`);
  } catch (e) {
    setTxStatus(`Error loading transactions: ${e.message}`);
  }
}

async function saveTransaction() {
  try {
    const session = await getSessionOrThrow();
    const symbol = String(txSymbolEl.value || "").trim().toUpperCase();
    const txn_date = String(txDateEl.value || "").trim();
    const side = String(txSideEl.value || "").trim().toUpperCase();
    const quantity = Number(txQtyEl.value);
    const price = Number(txPriceEl.value);

    if (!symbol || !txn_date || !["BUY", "SELL"].includes(side) || !Number.isFinite(quantity) || quantity <= 0 || !Number.isFinite(price) || price <= 0) {
      setAddEditStatus("Please provide valid symbol, date, side, quantity and price.");
      return;
    }

    if (editingTxId) {
      const { error } = await supabaseClient
        .from("transactions")
        .update({ symbol, txn_date, side, quantity, price })
        .eq("id", editingTxId)
        .eq("user_id", session.user.id);
      if (error) throw error;
      setAddEditStatus(`Saved transaction ${editingTxId} ✅`);
      exitEditMode();
    } else {
      const { error } = await supabaseClient
        .from("transactions")
        .insert([{ user_id: session.user.id, symbol, txn_date, side, quantity, price }]);
      if (error) throw error;
      setAddEditStatus("Transaction added ✅");
    }

    await refreshTransactions();
    setActiveTab("transactions");
  } catch (e) {
    setAddEditStatus(`Save error: ${e.message}`);
  }
}

async function doSignup() {
  setStatus("Signing up...");
  const email = emailEl.value.trim();
  const password = passwordEl.value;
  if (!email || !password) {
    setStatus("Provide email and password.");
    return;
  }

  const { error } = await supabaseClient.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: EMAIL_REDIRECT },
  });

  if (error) {
    setStatus(`Signup error: ${error.message}`);
    return;
  }

  setStatus("Signup successful. Check your email to confirm your account.");
}

async function doLogin() {
  setStatus("Logging in...");
  const email = emailEl.value.trim();
  const password = passwordEl.value;
  if (!email || !password) {
    setStatus("Provide email and password.");
    return;
  }

  const { error } = await supabaseClient.auth.signInWithPassword({ email, password });
  if (error) {
    setStatus(`Login error: ${error.message}`);
    return;
  }

  setStatus("Logged in ✅");
}

async function doLogout() {
  setStatus("Logging out...");
  const { error } = await supabaseClient.auth.signOut();
  if (error) {
    setStatus(`Logout error: ${error.message}`);
    return;
  }
  setLoggedOutUI();
}

signupBtn.addEventListener("click", doSignup);
loginBtn.addEventListener("click", doLogin);
logoutBtn.addEventListener("click", doLogout);

menuLogoutBtn.addEventListener("click", async () => {
  setMenuOpen(false);
  await doLogout();
});

menuToggleBtn.addEventListener("click", (event) => {
  event.stopPropagation();
  setMenuOpen(!menuEl.classList.contains("open"));
});

menuEl.addEventListener("click", (event) => event.stopPropagation());
document.addEventListener("click", () => setMenuOpen(false));

const openTab = (tab) => async () => {
  appBox.style.display = "block";
  setActiveTab(tab);
  if (tab === "transactions") await refreshTransactions();
  setMenuOpen(false);
};

tabPortfolio.addEventListener("click", openTab("portfolio"));
tabPerformance.addEventListener("click", openTab("performance"));
tabTransactions.addEventListener("click", openTab("transactions"));
tabAddEdit.addEventListener("click", openTab("addedit"));
tabStatistics.addEventListener("click", openTab("statistics"));

refreshTxBtn.addEventListener("click", refreshTransactions);
addTxBtn.addEventListener("click", saveTransaction);
cancelEditBtn.addEventListener("click", exitEditMode);

supabaseClient.auth.onAuthStateChange(async (_event, session) => {
  if (!session) {
    setLoggedOutUI();
    return;
  }

  setLoggedInUI(session.user.email || "");
  appBox.style.display = "block";
  setActiveTab("transactions");
  await refreshTransactions();
});

(async function init() {
  const { data } = await supabaseClient.auth.getSession();
  if (!data.session) {
    setLoggedOutUI();
    return;
  }

  setLoggedInUI(data.session.user.email || "");
  appBox.style.display = "block";
  setActiveTab("transactions");
  await refreshTransactions();
})();
