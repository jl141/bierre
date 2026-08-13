# Front-end

Native ES modules, served as-is by the `StaticFiles` mount in `webapp/server.py`.
**No build step, no npm, no transpile** — what is in this directory is what the browser
runs, which is what keeps the local download forkable by someone who only has Python.

```
index.html      app shell only: skip link, header, nav, <main> outlet, footer, the two dialogs
app.js          entry point; fetches capabilities, builds the shell, starts the router
css/            tokens → base → components → layout, linked in that cascade order
lib/            dom.js store.js router.js api.js session.js storage.js format.js
views/          search.js results.js settings.js signin.js account.js
components/     nav.js account-menu.js footer.js status.js profile-dialog.js
```

`lib/api.js` owns the access token; `lib/session.js` owns everything that has to happen
around it — the silent refresh at boot, the capability refetch after a sign-in or sign-out,
the locale negotiation, and the plain-language copy for every failure the auth routes can
produce. A view never touches `access_token`, and a test asserts that.

Authority for the layout is `hyLdwJ/PRDs/PRD_UI_UX_REVAMP_AND_USER_FEATURES.md` §3.4.

## The four rules

1. **Build DOM with `h()` from `lib/dom.js`.** Paper titles, journals and URLs come from
   five third-party APIs; `innerHTML` plus hand-written escaping is one forgotten call
   site away from an injection. `tests/unit/test_static_shell.py` fails on `innerHTML`.
2. **The access token lives in a module variable in `lib/api.js`.** Never `localStorage`,
   never `sessionStorage`, never a readable cookie. A page reload losing it is the
   intended cost; the HttpOnly refresh cookie is the recovery path.
3. **Capability-gated affordances are absent, not disabled.** `GET /api/capabilities` is
   fetched once at boot, before the first render. Local mode shows no account UI at all.
   One field answers for the caller rather than the deployment: hosted `profile_write` is
   false while anonymous, so signing in or out has to refetch it.
4. **New CSS uses logical properties and tokens** (`padding-inline`, `border-block-end`,
   `var(--line)`), so the later RTL and dark-mode passes have nothing to undo.

## Adding a route

```js
// app.js
routes: [
  { path: "/", title: "Search", view: createSearchView({ store }) },
  { path: "/profiles/:id", title: "Profile", view: createProfileView({ store }) },
]
```

A view is `{mount(outlet, params), unmount()}`. The router moves focus to the view's
`<h1>` and sets `document.title` — do not do either from inside a view.
