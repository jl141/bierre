"""Unit tests for core.http.request_json resilience and compatibility behavior."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bierre.core.util.http import request_json, request_text
from core.sources import openalex, pubmed, semantic_scholar
from core.sources.base import SearchContext


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        json_data: Any | None = None,
        json_error: Exception | None = None,
        headers: dict[str, str] | None = None,
        reason: str = "",
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self._json_error = json_error
        self.headers = headers or {}
        self.reason = reason
        self.text = text

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._json_data


class ScriptedSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any] | None, timeout: Any, headers: dict[str, str]) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout, "headers": headers})
        if not self._responses:
            raise AssertionError("No scripted response left")
        return self._responses.pop(0)


def test_success_single_attempt_returns_json_object():
    errors: list[dict[str, Any]] = []
    session = ScriptedSession(
        [
            FakeResponse(
                status_code=200,
                json_data={"ok": True},
                headers={"Content-Type": "application/json"},
                text='{"ok":true}',
            )
        ]
    )

    with patch("core.http._get_session", return_value=session):
        data = request_json("https://api.example.org/works", {"q": "hydrogel"}, 5, errors, "test")

    assert data == {"ok": True}
    assert len(session.calls) == 1
    assert errors == []


def test_retry_then_success_on_503():
    errors: list[dict[str, Any]] = []
    sleeps: list[float] = []
    session = ScriptedSession(
        [
            FakeResponse(status_code=503, reason="Service Unavailable", headers={"Content-Type": "application/json"}),
            FakeResponse(
                status_code=200,
                json_data=[1, 2, 3],
                headers={"Content-Type": "application/json"},
                text="[1,2,3]",
            ),
        ]
    )

    with (
        patch("core.http._get_session", return_value=session),
        patch("core.http._sleep", side_effect=sleeps.append),
        patch("core.http._jitter_random", return_value=0.0),
    ):
        data = request_json("https://api.example.org/works", None, 5, errors, "test")

    assert data == [1, 2, 3]
    assert len(session.calls) == 2
    assert len(sleeps) == 1
    assert sleeps[0] == 0.5
    assert errors == []


def test_429_retry_after_is_respected():
    errors: list[dict[str, Any]] = []
    sleeps: list[float] = []
    session = ScriptedSession(
        [
            FakeResponse(
                status_code=429,
                reason="Too Many Requests",
                headers={"Retry-After": "2", "Content-Type": "application/json"},
            ),
            FakeResponse(
                status_code=200,
                json_data="ok",
                headers={"Content-Type": "application/json"},
                text='"ok"',
            ),
        ]
    )

    with (
        patch("core.http._get_session", return_value=session),
        patch("core.http._sleep", side_effect=sleeps.append),
    ):
        data = request_json("https://api.example.org/works", None, 5, errors, "test")

    assert data == "ok"
    assert len(session.calls) == 2
    assert sleeps == [2.0]
    assert errors == []


def test_non_retryable_4xx_records_error_without_retry():
    errors: list[dict[str, Any]] = []
    session = ScriptedSession(
        [FakeResponse(status_code=404, reason="Not Found", headers={"Content-Type": "application/json"})]
    )

    with patch("core.http._get_session", return_value=session):
        data = request_json("https://api.example.org/works", {"q": "x"}, 5, errors, "test")

    assert data is None
    assert len(session.calls) == 1
    assert len(errors) == 1
    error = errors[0]
    assert error["error_type"] == "network_or_api_error"
    assert error["status_code"] == 404
    assert error["retryable"] is False
    assert error["attempt_count"] == 1


def test_json_parse_error_path_is_structured():
    errors: list[dict[str, Any]] = []
    session = ScriptedSession(
        [
            FakeResponse(
                status_code=200,
                json_error=ValueError("bad json"),
                headers={"Content-Type": "application/json"},
                text="{broken",
            )
        ]
    )

    with patch("core.http._get_session", return_value=session):
        data = request_json("https://api.example.org/works", None, 5, errors, "test")

    assert data is None
    assert len(errors) == 1
    error = errors[0]
    assert error["error_type"] == "json_parse_error"
    assert error["url"].startswith("https://api.example.org/works")
    assert error["attempt_count"] == 1


def test_error_url_redacts_sensitive_query_params():
    errors: list[dict[str, Any]] = []
    session = ScriptedSession(
        [FakeResponse(status_code=401, reason="Unauthorized", headers={"Content-Type": "application/json"})]
    )

    with patch("core.http._get_session", return_value=session):
        request_json(
            "https://api.example.org/works",
            {"api_key": "super-secret", "token": "another-secret", "q": "safe"},
            5,
            errors,
            "test",
        )

    assert len(errors) == 1
    redacted_url = errors[0]["url"]
    assert "super-secret" not in redacted_url
    assert "another-secret" not in redacted_url
    assert "api_key=REDACTED" in redacted_url
    assert "token=REDACTED" in redacted_url


def test_tuple_timeout_is_forwarded_to_transport():
    errors: list[dict[str, Any]] = []
    session = ScriptedSession(
        [
            FakeResponse(
                status_code=200,
                json_data={"ok": 1},
                headers={"Content-Type": "application/json"},
                text='{"ok":1}',
            )
        ]
    )

    timeout = (1, 7)
    with patch("core.http._get_session", return_value=session):
        request_json("https://api.example.org/works", None, timeout, errors, "test")

    assert session.calls[0]["timeout"] == timeout


def test_openalex_adapter_still_works_via_request_json():
    errors: list[dict[str, Any]] = []
    ctx = SearchContext(max_results=3, timeout=10, email="", api_keys={}, errors=errors)
    session = ScriptedSession(
        [
            FakeResponse(
                status_code=200,
                json_data={
                    "results": [
                        {
                            "title": "Rechargeable coating paper",
                            "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
                            "publication_year": 2025,
                            "primary_location": {
                                "source": {"display_name": "Materials Journal"},
                                "landing_page_url": "https://example.org/paper",
                            },
                            "doi": "https://doi.org/10.1000/example",
                            "abstract_inverted_index": {"rechargeable": [0], "coating": [1]},
                            "open_access": {"is_oa": True, "oa_status": "gold"},
                            "cited_by_count": 12,
                        }
                    ]
                },
                headers={"Content-Type": "application/json"},
                text='{"results":[{}]}',
            )
        ]
    )

    with patch("core.http._get_session", return_value=session):
        papers = openalex.search(ctx, "rechargeable coating")

    assert len(papers) == 1
    assert papers[0].title == "Rechargeable coating paper"
    assert papers[0].authors == "Ada Lovelace"
    assert papers[0].oa_status == "gold"
    assert errors == []


def test_request_text_retries_then_returns_body():
    errors: list[dict[str, Any]] = []
    sleeps: list[float] = []
    session = ScriptedSession(
        [
            FakeResponse(status_code=503, reason="Service Unavailable"),
            FakeResponse(status_code=200, text="<xml>ok</xml>"),
        ]
    )

    with (
        patch("core.http._get_session", return_value=session),
        patch("core.http._sleep", side_effect=sleeps.append),
        patch("core.http._jitter_random", return_value=0.0),
    ):
        data = request_text("https://api.example.org/xml", None, 5, errors, "test")

    assert data == "<xml>ok</xml>"
    assert len(session.calls) == 2
    assert sleeps == [0.5]
    assert errors == []


def test_semantic_scholar_adapter_still_works_via_request_json():
    errors: list[dict[str, Any]] = []
    ctx = SearchContext(max_results=3, timeout=10, email="", api_keys={}, errors=errors)
    session = ScriptedSession(
        [
            FakeResponse(
                status_code=200,
                json_data={
                    "data": [
                        {
                            "title": "Semantic Scholar Paper",
                            "authors": [{"name": "Grace Hopper"}],
                            "year": 2023,
                            "venue": "Comp Journal",
                            "externalIds": {"DOI": "10.1000/semantic"},
                            "abstract": "Paper abstract",
                            "url": "https://example.org/semantic",
                            "openAccessPdf": {"url": "https://example.org/semantic.pdf"},
                            "citationCount": 9,
                            "influentialCitationCount": 2,
                        }
                    ]
                },
                headers={"Content-Type": "application/json"},
                text='{"data":[{}]}',
            )
        ]
    )

    with patch("core.http._get_session", return_value=session):
        papers = semantic_scholar.search(ctx, "semantic query")

    assert len(papers) == 1
    assert papers[0].title == "Semantic Scholar Paper"
    assert papers[0].authors == "Grace Hopper"
    assert papers[0].citation_count == 9
    assert errors == []


def test_pubmed_adapter_still_works_with_json_and_xml_helpers():
    errors: list[dict[str, Any]] = []
    ctx = SearchContext(max_results=3, timeout=10, email="", api_keys={}, errors=errors)
    esearch = {"esearchresult": {"idlist": ["12345"]}}
    efetch_xml = """
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>12345</PMID>
          <Article>
            <ArticleTitle>PubMed migrated path</ArticleTitle>
            <Journal><Title>Medical Journal</Title></Journal>
            <Abstract><AbstractText>Study abstract</AbstractText></Abstract>
            <AuthorList>
              <Author><ForeName>Ada</ForeName><LastName>Lovelace</LastName></Author>
            </AuthorList>
            <ArticleDate><Year>2024</Year></ArticleDate>
          </Article>
        </MedlineCitation>
        <PubmedData>
          <ArticleIdList>
            <ArticleId IdType="doi">10.1000/pubmed</ArticleId>
          </ArticleIdList>
        </PubmedData>
      </PubmedArticle>
    </PubmedArticleSet>
    """.strip()

    with (
        patch("core.sources.pubmed.request_json", return_value=esearch),
        patch("core.sources.pubmed.request_text", return_value=efetch_xml),
    ):
        papers = pubmed.search(ctx, "pubmed query")

    assert len(papers) == 1
    assert papers[0].title == "PubMed migrated path"
    assert papers[0].authors == "Ada Lovelace"
    assert papers[0].doi == "10.1000/pubmed"
    assert errors == []


def test_request_json_max_attempts_override_disables_retry_when_one():
    errors: list[dict[str, Any]] = []
    sleeps: list[float] = []
    session = ScriptedSession([FakeResponse(status_code=503, reason="Service Unavailable")])

    with (
        patch("core.http._get_session", return_value=session),
        patch("core.http._sleep", side_effect=sleeps.append),
    ):
        data = request_json(
            "https://api.example.org/works",
            None,
            5,
            errors,
            "test",
            max_attempts=1,
        )

    assert data is None
    assert len(session.calls) == 1
    assert sleeps == []
    assert errors
    assert errors[0]["retryable"] is True
    assert errors[0]["attempt_count"] == 1


def test_semantic_scholar_stage_override_forwarding():
    errors: list[dict[str, Any]] = []
    ctx = SearchContext(
        max_results=3,
        timeout=10,
        email="",
        api_keys={},
        http_overrides={
            "semantic_scholar": {
                "max_attempts": 5,
                "backoff_base_seconds": 0.1,
                "backoff_max_seconds": 1.0,
                "retryable_status_codes": [429, 500, 503],
                "ignored_key": "drop-me",
            }
        },
        errors=errors,
    )

    with patch("core.sources.semantic_scholar.request_json", return_value={"data": []}) as mock_req:
        semantic_scholar.search(ctx, "semantic query")

    kwargs = mock_req.call_args.kwargs
    assert kwargs["max_attempts"] == 5
    assert kwargs["backoff_base_seconds"] == 0.1
    assert kwargs["backoff_max_seconds"] == 1.0
    assert kwargs["retryable_status_codes"] == [429, 500, 503]
    assert "ignored_key" not in kwargs


def test_pubmed_stage_override_forwarding():
    errors: list[dict[str, Any]] = []
    ctx = SearchContext(
        max_results=3,
        timeout=10,
        email="",
        api_keys={},
        http_overrides={
            "pubmed_esearch": {"max_attempts": 4},
            "pubmed_efetch": {"max_attempts": 2, "backoff_max_seconds": 0.75},
        },
        errors=errors,
    )
    esearch = {"esearchresult": {"idlist": ["12345"]}}

    with (
        patch("core.sources.pubmed.request_json", return_value=esearch) as mock_json,
        patch("core.sources.pubmed.request_text", return_value="<PubmedArticleSet />") as mock_text,
    ):
        pubmed.search(ctx, "pubmed query")

    esearch_kwargs = mock_json.call_args.kwargs
    efetch_kwargs = mock_text.call_args.kwargs
    assert esearch_kwargs["max_attempts"] == 4
    assert efetch_kwargs["max_attempts"] == 2
    assert efetch_kwargs["backoff_max_seconds"] == 0.75


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("All request_json tests passed.")
