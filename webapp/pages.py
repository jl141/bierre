"""The three real (non-hash) paths the SPA router cannot own.

Mail clients and OAuth providers link straight at a URL and will not run a hash
router, so ``/auth/callback``, ``/accounts/verify`` and ``/unsubscribe`` have to
exist as server-rendered documents. They are deliberately tiny: enough shell to
look like the app, then a hand-off into the hash router.

Only ``/auth/callback`` does anything in this slice. It reads the fragment the
account service redirects with — a fragment never reaches the server, which is
the point of using one for a credential — and leaves the rest to the SPA. Magic
link and OAuth are the flows that will populate that fragment; neither ships
here, so the page's whole job today is to land cleanly.

Nothing from the URL is ever echoed into the markup. These pages carry
one-time tokens, and a token rendered into HTML is both an injection sink and a
value that ends up in a screenshot or a bug report.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(include_in_schema=False)

_CALLBACK_SCRIPT = """
      const params = new URLSearchParams(location.hash.slice(1));
      if (params.get("error")) {
        document.getElementById("page-status").textContent =
          "Sign-in could not be completed. Open the sign-in page and try again.";
      } else {
        location.replace("/#/");
      }
"""


def _page(*, title: str, heading: str, message: str, script: str = "") -> HTMLResponse:
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — bierre</title>
  <meta name="robots" content="noindex">
  <link rel="stylesheet" href="/css/tokens.css">
  <link rel="stylesheet" href="/css/base.css">
  <link rel="stylesheet" href="/css/components.css">
  <link rel="stylesheet" href="/css/layout.css">
</head>
<body>
  <main id="main" tabindex="-1">
    <h1>{heading}</h1>
    <p id="page-status">{message}</p>
    <p><a href="/#/">Continue to bierre</a></p>
  </main>
{f'  <script type="module">{script}  </script>' if script else ''}
</body>
</html>
"""
    return HTMLResponse(body, headers={"Cache-Control": "no-store"})


@router.get("/auth/callback")
def auth_callback() -> HTMLResponse:
    return _page(
        title="Signing in",
        heading="Signing you in",
        message="One moment.",
        script=_CALLBACK_SCRIPT,
    )


@router.get("/accounts/verify")
def accounts_verify() -> HTMLResponse:
    return _page(
        title="Email verification",
        heading="Email verification is not enabled yet",
        message="Nothing in bierre currently requires a verified email address, so this link has nothing to confirm.",
    )


@router.get("/unsubscribe")
def unsubscribe() -> HTMLResponse:
    return _page(
        title="Unsubscribe",
        heading="Email digests are not enabled yet",
        message="bierre sends no mail, so there is no subscription to cancel.",
    )
