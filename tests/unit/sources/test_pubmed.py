"""Unit tests for the PubMed adapter (esearch JSON + efetch XML)."""

from __future__ import annotations

import pytest

from core.sources import pubmed

ESEARCH = {"esearchresult": {"idlist": ["12345"]}}

EFETCH_XML = """
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345</PMID>
      <Article>
        <ArticleTitle>PubMed migrated path</ArticleTitle>
        <Journal><Title>Medical Journal</Title></Journal>
        <Abstract>
          <AbstractText>Study abstract</AbstractText>
          <AbstractText>Second part</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><ForeName>Ada</ForeName><LastName>Lovelace</LastName></Author>
          <Author><CollectiveName>The Study Group</CollectiveName></Author>
        </AuthorList>
        <ArticleDate><Year>2024</Year></ArticleDate>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">12345</ArticleId>
        <ArticleId IdType="doi">10.1000/pubmed</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
""".strip()


@pytest.fixture
def stub_transport(monkeypatch):
    """Stub both E-utilities calls; returns the recorded keyword arguments."""

    def install(*, esearch=ESEARCH, efetch=EFETCH_XML):
        captured: dict[str, dict] = {}

        def fake_json(_url, params, *_args, **kwargs):
            captured["esearch"] = kwargs
            captured["esearch_params"] = params
            return esearch

        def fake_text(_url, params, *_args, **kwargs):
            captured["efetch"] = kwargs
            captured["efetch_params"] = params
            return efetch

        monkeypatch.setattr(pubmed, "request_json", fake_json)
        monkeypatch.setattr(pubmed, "request_text", fake_text)
        return captured

    return install


def test_search_parses_the_article_xml(ctx, stub_transport, errors) -> None:
    stub_transport()

    paper = pubmed.search(ctx, "pubmed query")[0]

    assert paper.title == "PubMed migrated path"
    assert paper.authors == "Ada Lovelace; The Study Group"
    assert paper.year == "2024"
    assert paper.journal == "Medical Journal"
    assert paper.doi == "10.1000/pubmed"
    assert paper.abstract == "Study abstract Second part"
    assert paper.url == "https://pubmed.ncbi.nlm.nih.gov/12345/"
    assert paper.sources == ["PubMed"]
    assert errors == []


def test_the_year_falls_back_through_pubdate_then_medlinedate(ctx, stub_transport) -> None:
    xml = """
    <PubmedArticleSet><PubmedArticle><MedlineCitation><Article>
      <ArticleTitle>Old record</ArticleTitle>
      <PubDate><MedlineDate>1998 Nov-Dec</MedlineDate></PubDate>
    </Article></MedlineCitation></PubmedArticle></PubmedArticleSet>
    """.strip()
    stub_transport(efetch=xml)

    assert pubmed.search(ctx, "q")[0].year == "1998"


def test_identification_parameters_are_sent_on_both_e_utility_calls(make_ctx, stub_transport) -> None:
    captured = stub_transport()

    pubmed.search(make_ctx(email="me@example.org", api_keys={"ncbi": "k1"}, max_results=5), "q")

    for params in (captured["esearch_params"], captured["efetch_params"]):
        assert params["db"] == "pubmed"
        assert params["tool"] == "bierre"
        assert params["email"] == "me@example.org"
        assert params["api_key"] == "k1"
    assert captured["esearch_params"]["retmax"] == 5
    assert captured["efetch_params"]["id"] == "12345"


def test_no_ids_short_circuits_before_efetch(ctx, monkeypatch, errors) -> None:
    calls: list[str] = []
    monkeypatch.setattr(pubmed, "request_json", lambda *a, **k: {"esearchresult": {"idlist": []}})
    monkeypatch.setattr(pubmed, "request_text", lambda *a, **k: calls.append("efetch"))

    assert pubmed.search(ctx, "q") == []
    assert calls == []


def test_a_failed_esearch_returns_no_papers(ctx, monkeypatch) -> None:
    monkeypatch.setattr(pubmed, "request_json", lambda *a, **k: None)

    assert pubmed.search(ctx, "q") == []


def test_a_failed_efetch_returns_no_papers(ctx, stub_transport) -> None:
    stub_transport(efetch=None)

    assert pubmed.search(ctx, "q") == []


def test_malformed_xml_is_recorded_as_a_parse_error(ctx, stub_transport, errors) -> None:
    stub_transport(efetch="<PubmedArticleSet><broken>")

    assert pubmed.search(ctx, "q") == []
    assert errors[0]["error_type"] == "xml_parse_error"
    assert errors[0]["stage"] == "pubmed_efetch"


def test_each_stage_gets_its_own_http_overrides(make_ctx, stub_transport) -> None:
    captured = stub_transport()
    ctx = make_ctx(
        http_overrides={
            "pubmed_esearch": {"max_attempts": 4},
            "pubmed_efetch": {"max_attempts": 2, "backoff_max_seconds": 0.75},
        }
    )

    pubmed.search(ctx, "q")

    assert captured["esearch"]["max_attempts"] == 4
    assert captured["efetch"]["max_attempts"] == 2
    assert captured["efetch"]["backoff_max_seconds"] == 0.75


def test_pubmed_is_always_dispatched_serially() -> None:
    from core.config import Settings
    from core.sources.policy import SourceDispatchState

    assert pubmed.force_serial(Settings(), SourceDispatchState()) is True
