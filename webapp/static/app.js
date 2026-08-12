/**
 * Entry point. Loaded as `<script type="module">`, so it is deferred by
 * definition and every import below is a real ES module served as-is: no
 * bundler, no npm, nothing between the source in the repo and the source in
 * the browser.
 *
 * Boot order matters. Capabilities are fetched first and awaited, because the
 * shell and the views render different things in local and hosted mode and a
 * capability arriving late would mean an account affordance flashing on screen
 * before it is taken away again.
 */

import { configureAuth, request } from "./lib/api.js";
import { createRouter } from "./lib/router.js";
import { createStore } from "./lib/store.js";
import { setLocale } from "./lib/format.js";
import { createAccountMenu } from "./components/account-menu.js";
import { createFooter } from "./components/footer.js";
import { createNav } from "./components/nav.js";
import { createSearchView } from "./views/search.js";

/**
 * What a machine with no account service looks like. Used when
 * `GET /api/capabilities` is unreachable — an old build of `server.py`, or a
 * download running with no network — because the local app must keep working
 * without one. It is deliberately the most restricted honest answer: no auth,
 * no accounts, local history.
 */
const LOCAL_CAPABILITIES = {
  mode: "local",
  auth: false,
  accounts: false,
  auth_methods: [],
  accounts_base: null,
  email_digest: false,
  history: "local",
  history_retention: null,
  max_subscriptions: 0,
  profile_write: true,
  ai_profile_generation: "byo_key_or_bierre_ca",
  shared_api_keys: false,
  locales: ["en"],
  default_locale: "en",
  legal_urls: { privacy: "/privacy", terms: "/terms", sources: "/data-sources" },
};

const store = createStore({
  capabilities: null,
  profiles: [],
  defaultProfile: "",
  settings: null,
  settingsDefaults: null,
  lastResult: null,
  user: null,
});

async function loadCapabilities() {
  try {
    return await request("/api/capabilities");
  } catch (error) {
    console.warn(`Capabilities unavailable (${error.message}); assuming local mode.`);
    return LOCAL_CAPABILITIES;
  }
}

async function boot() {
  const capabilities = await loadCapabilities();
  store.set({ capabilities });

  setLocale(capabilities.default_locale);
  document.documentElement.lang = capabilities.default_locale;

  const router = createRouter({
    outlet: document.getElementById("main"),
    routes: [
      { path: "/", title: "Search", view: createSearchView({ store }) },
    ],
  });

  configureAuth({
    accountsBase: capabilities.accounts_base,
    // A refresh that fails leaves the user anonymous. Only a deployment with a
    // sign-in flow has somewhere to send them.
    onUnauthenticated: () => {
      if (capabilities.auth) router.navigate("/signin");
    },
  });

  document.getElementById("app-nav").append(createNav({ store, router }));
  document.getElementById("app-footer").append(createFooter({ store }));

  const accountMenu = createAccountMenu({ store });
  if (accountMenu) document.getElementById("account-slot").append(accountMenu);

  router.start();
}

boot();
