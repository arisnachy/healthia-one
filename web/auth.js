const authState = {
  enabled: false,
  ready: false,
  user: null,
  token: "",
  sdk: null,
};

let resolveAuthReady;
window.healthiaAuthReady = new Promise(resolve => { resolveAuthReady = resolve; });
window.healthiaAuth = {
  get enabled() { return authState.enabled; },
  get user() { return authState.user; },
  async getToken(forceRefresh = false) {
    if (!authState.enabled) return "";
    if (!authState.user || !authState.sdk) throw new Error("Debes iniciar sesión.");
    authState.token = await authState.sdk.getIdToken(authState.user, forceRefresh);
    return authState.token;
  },
  async signOut() {
    if (authState.sdk?.auth) await authState.sdk.signOut(authState.sdk.auth);
  },
};

const gate = document.querySelector("#authGate");
const appShell = document.querySelector("#app");
const authMessage = document.querySelector("#authMessage");
const emailForm = document.querySelector("#emailAuthForm");
const emailInput = document.querySelector("#authEmail");
const passwordInput = document.querySelector("#authPassword");
const nameInput = document.querySelector("#authName");
const googleButton = document.querySelector("#googleSignIn");
const modeButton = document.querySelector("#authModeToggle");
const submitButton = document.querySelector("#authSubmit");
let createMode = false;
let previousUid = "";

function setMessage(message, tone = "info") {
  if (!authMessage) return;
  authMessage.textContent = message || "";
  authMessage.dataset.tone = tone;
}

function showApp() {
  if (gate) gate.hidden = true;
  if (appShell) appShell.hidden = false;
}

function showGate() {
  if (appShell) appShell.hidden = true;
  if (gate) gate.hidden = false;
}

function finishReady() {
  if (authState.ready) return;
  authState.ready = true;
  resolveAuthReady?.(window.healthiaAuth);
  document.dispatchEvent(new CustomEvent("healthia:auth-ready"));
}

function syncMode() {
  if (nameInput) nameInput.closest("label").hidden = !createMode;
  if (submitButton) submitButton.textContent = createMode ? "Crear cuenta" : "Entrar";
  if (modeButton) modeButton.textContent = createMode ? "Ya tengo una cuenta" : "Crear cuenta con correo";
  setMessage("");
}

modeButton?.addEventListener("click", () => {
  createMode = !createMode;
  syncMode();
});

async function bootIdentity() {
  showGate();
  let config;
  try {
    const response = await fetch("/api/auth/config", {cache: "no-store"});
    if (!response.ok) throw new Error(`No se pudo leer la configuración de identidad (${response.status}).`);
    config = await response.json();
  } catch (error) {
    setMessage(error.message, "error");
    finishReady();
    return;
  }

  if (!config.enabled) {
    authState.enabled = false;
    showApp();
    finishReady();
    return;
  }

  authState.enabled = true;
  if (!config.ready) {
    setMessage("El acceso seguro está activado, pero falta registrar la aplicación web en Google Identity Platform/Firebase.", "error");
    finishReady();
    return;
  }

  try {
    const appModule = await import("https://www.gstatic.com/firebasejs/12.16.0/firebase-app.js");
    const authModule = await import("https://www.gstatic.com/firebasejs/12.16.0/firebase-auth.js");
    const firebaseApp = appModule.initializeApp(config.firebase);
    const auth = authModule.getAuth(firebaseApp);
    auth.useDeviceLanguage();
    authState.sdk = {...authModule, auth};

    googleButton?.addEventListener("click", async () => {
      googleButton.disabled = true;
      setMessage("Abriendo Google…");
      try {
        const provider = new authModule.GoogleAuthProvider();
        provider.setCustomParameters({prompt: "select_account"});
        await authModule.signInWithPopup(auth, provider);
      } catch (error) {
        setMessage(error?.message || "No se pudo iniciar sesión con Google.", "error");
      } finally {
        googleButton.disabled = false;
      }
    });

    emailForm?.addEventListener("submit", async event => {
      event.preventDefault();
      submitButton.disabled = true;
      setMessage(createMode ? "Creando tu cuenta…" : "Iniciando sesión…");
      try {
        const email = emailInput.value.trim();
        const password = passwordInput.value;
        if (createMode) {
          const credential = await authModule.createUserWithEmailAndPassword(auth, email, password);
          const displayName = nameInput.value.trim();
          if (displayName) await authModule.updateProfile(credential.user, {displayName});
          await credential.user.getIdToken(true);
        } else {
          await authModule.signInWithEmailAndPassword(auth, email, password);
        }
      } catch (error) {
        setMessage(error?.message || "No se pudo completar el acceso.", "error");
      } finally {
        submitButton.disabled = false;
      }
    });

    authModule.onIdTokenChanged(auth, async user => {
      authState.user = user;
      if (!user) {
        authState.token = "";
        showGate();
        setMessage("Inicia sesión para acceder únicamente a tus datos de HealthIA.");
        if (previousUid) {
          document.dispatchEvent(new CustomEvent("healthia:signed-out", {detail: {uid: previousUid}}));
          previousUid = "";
        }
        return;
      }
      authState.token = await authModule.getIdToken(user);
      previousUid = user.uid;
      showApp();
      setMessage("");
      finishReady();
      document.dispatchEvent(new CustomEvent("healthia:identity-changed", {
        detail: {uid: user.uid, email: user.email || "", displayName: user.displayName || ""},
      }));
    });
  } catch (error) {
    setMessage(`No se pudo cargar el acceso seguro: ${error?.message || error}`, "error");
    finishReady();
  }
}

syncMode();
bootIdentity();
