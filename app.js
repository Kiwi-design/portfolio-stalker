// 1) Paste your Supabase details here
const SUPABASE_URL = "https://dalchqdooacrxtonyoee.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRhbGNocWRvb2Fjcnh0b255b2VlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA1MzM0NTQsImV4cCI6MjA4NjEwOTQ1NH0.4zsqZ0uXNuouoAU7STUb7PGWvOvkweZX6f6RUI8lun4";

// 2) Create client
const supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// 3) UI references
const emailEl = document.getElementById("email");
const passwordEl = document.getElementById("password");
const statusEl = document.getElementById("status");

const signupBtn = document.getElementById("signup");
const loginBtn = document.getElementById("login");
const logoutBtn = document.getElementById("logout");

function setStatus(msg) {
  statusEl.textContent = msg;
}

function setLoggedInUI(email) {
  signupBtn.style.display = "none";
  loginBtn.style.display = "none";
  logoutBtn.style.display = "inline-block";
  setStatus(`Logged in as: ${email}`);
}

function setLoggedOutUI() {
  signupBtn.style.display = "inline-block";
  loginBtn.style.display = "inline-block";
  logoutBtn.style.display = "none";
  setStatus("Not logged in.");
}

// 4) On load: check if already logged in
(async function init() {
  const { data, error } = await supabaseClient.auth.getSession();
  if (error) {
    setStatus("Session error: " + error.message);
    return;
  }

  const session = data.session;
  if (session?.user?.email) {
    setLoggedInUI(session.user.email);
  } else {
    setLoggedOutUI();
  }
})();

// 5) Sign up
signupBtn.addEventListener("click", async () => {
  const email = emailEl.value.trim();
  const password = passwordEl.value;

  if (!email || !password) {
    setStatus("Please enter email + password.");
    return;
  }

  setStatus("Signing up...");

  const { data, error } = await supabaseClient.auth.signUp({ email, password, options: {
    emailRedirectTo: "https://kiwi-design.github.io/portfolio-stalker/"
  } });

  if (error) {
    setStatus("Sign up error: " + error.message);
    return;
  }

  // Depending on your Supabase settings, this may create a session immediately
  if (data.session?.user?.email) {
    setLoggedInUI(data.session.user.email);
  } else {
    setStatus("Sign up successful. Check your email if confirmation is required, then log in.");
  }
});

// 6) Log in
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
});

// 7) Log out
logoutBtn.addEventListener("click", async () => {
  setStatus("Logging out...");
  const { error } = await supabaseClient.auth.signOut();
  if (error) {
    setStatus("Logout error: " + error.message);
    return;
  }
  setLoggedOutUI();
});
