from datetime import UTC, datetime
from unittest.mock import patch
import pytest
from crawl_check import item_status, list_candidates, normalize
from inspect_sources import AuditFetcher
from news_insight.net.safe_fetch import FetchBlocked, FetchResponse


def test_board_identity_drops_sessions_but_keeps_article_id():
    recipe={'strip_session':True,'normalize_query':['b_board_id','b_idx']}
    url='https://www.etri.re.kr/kor/bbs/view.etri;jsessionid=abc?nowPage=2&b_idx=10&b_board_id=ETRI06'
    assert normalize(url,recipe)=='https://www.etri.re.kr/kor/bbs/view.etri?b_board_id=ETRI06&b_idx=10'
    assert normalize(url.replace('abc','def'),recipe)==normalize(url,recipe)
    assert normalize(url.replace('b_idx=10','b_idx=11'),recipe)!=normalize(url,recipe)


def test_listing_drops_foreign_hosts_categories_and_duplicate_links():
    html='''<a href="/news/item">One</a><a href="/news/item">Again</a>
    <a href="https://other.example/news/item">Foreign</a><a href="/news/business-news">Category</a>'''
    recipe={'link_selector':'a[href]','link_pattern':'/news/','exclude_pattern':'business-news$'}
    rows=list_candidates(html,'https://example.org/news/',recipe)
    assert len(rows)==1 and rows[0]['url']=='https://example.org/news/item'


def test_explicit_board_dates_sort_pinned_archives_last():
    recipe={'row_selector':'tr','link_selector':'a','title_selector':'a','date_selector':'.date','date_format':'%Y.%m.%d','timezone':'Asia/Seoul','link_pattern':'/article/'}
    html='<table><tr><td><a href="/article/old">Old</a></td><td class="date">2025.01.01</td></tr><tr><td><a href="/article/new">New</a></td><td class="date">2026.10.01</td></tr></table>'
    rows=list_candidates(html,'https://example.org/',recipe)
    assert rows[0]['title']=='New'
    assert rows[0]['published_at']==datetime(2026,9,30,15,tzinfo=UTC)


@pytest.mark.parametrize(('date','expected'),[(None,'missing_date'),('2025-10-01T00:00:00+00:00','old'),('2026-12-01T00:00:00+00:00','future_date'),('2026-10-01T00:00:00+00:00','recent')])
def test_no_date_invention_or_future_articles(date,expected):
    assert item_status({'url':'https://example.org/a','title':'A','published_at':date},datetime(2026,10,5,tzinfo=UTC),30)==expected


@pytest.mark.parametrize('status',[403,406,429,500])
def test_robots_uncertainty_fails_closed(status):
    response=FetchResponse('https://example.org/robots.txt',status,{},b'','text/plain',(),0)
    with patch('news_insight.net.safe_fetch.SafeFetcher._validate_target'),patch('news_insight.net.safe_fetch.SafeFetcher.fetch',return_value=response):
        with AuditFetcher() as fetcher:
            with pytest.raises(FetchBlocked,match='robots blocked'):
                fetcher._validate_target('https://example.org/article')


def test_github_matrix_is_theme_free_and_has_unique_scope_keys():
    from github_matrix import targets
    rows=list(targets(['python','rust'],['ko','en']))
    assert len(rows)==6
    assert len({r['url'] for r in rows})==6
    assert all('topic' not in r['url'] for r in rows)
    full=list(targets(['python','rust'],['ko','en'],True))
    assert len(full)==6
