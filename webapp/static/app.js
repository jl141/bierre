/**
 * Entry point. Loaded as `<script type="module">`, so it is deferred by
 * definition and every import below is a real ES module served as-is: no
 * bundler, no npm, nothing between the source in the repo and the source in
 * the browser.
 *
 * Boot order matters, and it is the same reason twice. Capabilities are fetched
 * first and awaited, because the shell and the views render different things in
 * local and hosted mode and a capability arriving late would mean an account
 * affordance flashing on screen before it is taken away again. The silent
 * refresh is then awaited before the router starts, so the first route already
 * knows whether it has a user — `#/account` opened in a new tab must not bounce
 * to sign-in while its session is still being restored.
 */

import { configureAuth, request } from "./lib/api.js";
import { createRouter } from "./lib/router.js";
import { createSession } from "./lib/session.js";
import { createStore } from "./lib/store.js";
import { setLocale } from "./lib/format.js";
import { createAccountMenu } from "./components/account-menu.js";
import { createFooter } from "./components/footer.js";
import { createNav } from "./components/nav.js";
import { createAccountView } from "./views/account.js";
import { createHomeView } from "./views/home.js";
import { createProfileEditorView, createProfilesView } from "./views/profiles.js";
import { createSearchView } from "./views/search.js";
import { createSigninView } from "./views/signin.js";

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
  // The profile the search view will run. `#/profiles` sets it when the user
  // presses Use; the search view keeps it in step with its own dropdown.
  profileSelection: null,
  settings: null,
  settingsDefaults: null,
  lastResult: null,
  user: null,
  // Message and address one route leaves for `#/signin` to display: an expired
  // session, or a just-created account.
  authNotice: null,
  // The same idea for the profile routes: what the previous one just did.
  profileNotice: null,
  // A parsed import waiting to be reviewed in the editor. Held in the store
  // rather than in a query string because it is a whole profile, not an id.
  profileDraft: null,
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

  const session = createSession({ store });

  // The views need to navigate and the router needs the views, so one of the two
  // references has to be late. This is it.
  let router = null;
  const navigation = { navigate: (path) => router.navigate(path) };

  configureAuth({
    accountsBase: capabilities.accounts_base,
    // A refresh that fails mid-session leaves the user anonymous. Only a
    // deployment with a sign-in flow has somewhere to send them.
    onUnauthenticated: () => {
      if (!capabilities.auth) return;
      store.set({
        user: null,
        authNotice: { message: "Your session has expired. Sign in again." },
      });
      navigation.navigate("/signin");
    },
  });

  // One editor view instance serves both editor routes, so the form is built
  // once and its element ids stay unique. `/profiles/new` is listed before
  // `/profiles/:id` because the router takes the first pattern that matches and
  // `new` would otherwise be read as an id.
  const profileEditor = createProfileEditorView({ store, router: navigation });

  const routes = [
    { path: "/", title: "Home", view: createHomeView({ store }) },
    { path: "/search", title: "Search", view: createSearchView({ store }) },
    { path: "/profiles", title: "Domain profiles", view: createProfilesView({ store, router: navigation }) },
    { path: "/profiles/new", title: "New profile", view: profileEditor },
    { path: "/profiles/:id", title: "Profile", view: profileEditor },
  ];

  if (capabilities.auth) {
    routes.push(
      {
        path: "/signin",
        title: "Sign in",
        view: createSigninView({ store, session, router: navigation, mode: "signin" }),
      },
      {
        path: "/account",
        title: "Account",
        view: createAccountView({ store, session, router: navigation }),
      },
    );
    // Signup is a separate route, not a mode toggle, so it is linkable and so the
    // switch between the two announces a new page.
    if ((capabilities.auth_methods || []).includes("password")) {
      routes.push({
        path: "/signup",
        title: "Create an account",
        view: createSigninView({ store, session, router: navigation, mode: "signup" }),
      });
    }
  }

  router = createRouter({ outlet: document.getElementById("main"), routes });

  await session.restore();

  document.getElementById("app-nav").append(createNav({ store, router }));
  document.getElementById("app-footer").append(createFooter({ store }));

  const accountMenu = createAccountMenu({ store, session, router: navigation });
  if (accountMenu) document.getElementById("account-slot").append(accountMenu);

  router.start();
}

boot();
