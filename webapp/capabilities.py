"""The body of ``GET /api/capabilities``.

The shape is frozen in ``webapp/schemas/capabilities.json`` and the front-end
renders account affordances only where a capability is true, so a wrong answer
here is a UI that offers something the backend cannot service. Two rules keep it
honest:

* ``mode`` comes from ``deployment.mode`` in the settings file. Everything the
  schema derives from the mode is derived here too, rather than configured
  twice.
* Capabilities that describe a feature this slice does not ship — outbound
  digest mail, subscriptions, shared search keys — report the absent answer.
  They become configurable when the phase that implements them lands.

``profile_write`` is the one per-request field: in hosted mode it answers for
*this caller*, so an anonymous boot correctly reports false and a client must
refetch after signing in.
"""

from __future__ import annotations

from typing import Any

from core.config import Settings

LOCALES = ["en"]
DEFAULT_LOCALE = "en"
LEGAL_URLS = {"privacy": "/privacy", "terms": "/terms", "sources": "/data-sources"}
HISTORY_RETENTION = {"runs": 200, "months": 12}


def build_capabilities(settings: Settings, *, authenticated: bool) -> dict[str, Any]:
    deployment = settings.deployment
    hosted = deployment.is_hosted
    return {
        "mode": deployment.mode,
        "auth": hosted,
        "accounts": hosted,
        "auth_methods": list(deployment.auth_methods) if hosted else [],
        "accounts_base": deployment.accounts_base if hosted else None,
        "email_digest": False,
        "history": "server" if hosted else "local",
        "history_retention": dict(HISTORY_RETENTION) if hosted else None,
        "max_subscriptions": 0,
        "profile_write": authenticated or not hosted,
        "ai_profile_generation": "account" if hosted else "byo_key_or_bierre_ca",
        "shared_api_keys": False,
        "locales": list(LOCALES),
        "default_locale": DEFAULT_LOCALE,
        "legal_urls": dict(LEGAL_URLS),
    }
