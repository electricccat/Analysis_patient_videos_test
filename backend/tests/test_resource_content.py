import httpx
import pytest
from backend.app import resource_content as content

ARTICLE = '<html><head><title>Инсульт</title></head><body><nav>Игнорировать</nav><main><h1>Реабилитация после инсульта</h1><p>Реабилитация после инсульта включает лечебную физкультуру и упражнения. Индивидуальная программа учитывает ограничения нагрузки и противопоказания. Работа с родственниками помогает организовать восстановление.</p><p>В материале рассматриваются ходьба, равновесие, спастичность и мышечный тонус. Отдельно описаны эрготерапия, бытовые навыки и помощь логопеда при восстановлении речи.</p><script>Украсть данные</script></main><footer>Контакты и реклама</footer></body></html>'


def test_article_extraction_ignores_navigation_scripts_and_footer():
    parser=content.ArticleText()
    parser.feed(ARTICLE)
    text=parser.text()
    assert 'Украсть' not in text and 'реклама' not in text and 'Игнорировать' not in text
    summary=content.summarize_text(text,'реабилитация после инсульта')
    assert summary['status']=='read'
    assert 'лечебные упражнения' in summary['short_summary']
    assert len(summary['key_points'])==5
    assert content.summarize_text('Мало текста','инсульт')['status']=='insufficient_text'
    assert content.summarize_text('Windows настройки компьютера. '*30,'инсульт')['status']=='content_mismatch'


def test_page_content_summary_and_unsupported_formats(monkeypatch):
    monkeypatch.setattr(content,'public_url',lambda url:None)
    source={'url':'https://example.org/stroke'}
    result=content.read_source(source,'инсульт',httpx.MockTransport(lambda r:httpx.Response(200,text=ARTICLE,headers={'Content-Type':'text/html; charset=utf-8'})))
    assert result['status']=='read' and result['characters_read']>300
    assert result['content_sha256'] and result['source_url']==source['url']
    result=content.read_source(source,'инсульт',httpx.MockTransport(lambda r:httpx.Response(200,content=b'PDF',headers={'Content-Type':'application/pdf'})))
    assert result['status']=='unsupported_format' and result['key_points']==[]
    result=content.read_source(source,'инсульт',httpx.MockTransport(lambda r:httpx.Response(503)))
    assert result['status']=='unavailable'


def test_youtube_metadata_is_not_presented_as_transcript():
    result=content.read_source({'url':'https://www.youtube.com/watch?v=LvTfeTnL-90'},'инсульт',
        httpx.MockTransport(lambda r:httpx.Response(200,json={'title':'Упражнения после инсульта — реабилитация видео','author_name':'Учебный канал'})))
    assert result['status']=='video_metadata' and result['channel']=='Учебный канал'
    assert result['video_id']=='LvTfeTnL-90'
    assert 'не анализировались' in result['note']
    mismatch=content.read_source({'url':'https://www.youtube.com/watch?v=LvTfeTnL-90'},'инсульт',
        httpx.MockTransport(lambda r:httpx.Response(200,json={'title':'Minecraft gaming','author_name':'Gaming'})))
    assert mismatch['status']=='content_mismatch'


def test_public_fetch_rejects_local_addresses_and_redirects(monkeypatch):
    monkeypatch.setattr(content.socket,'getaddrinfo',lambda *args,**kwargs:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError): content.public_url('https://example.org')
    for url in ('http://example.org','https://user:password@example.org','https://example.org:8000'):
        with pytest.raises(ValueError): content.public_url(url)
    requests=[]
    def validate(url):
        if '127.0.0.1' in url: raise ValueError('Private destination')
    monkeypatch.setattr(content,'public_url',validate)
    def redirect(request):
        requests.append(str(request.url))
        return httpx.Response(302,headers={'Location':'https://127.0.0.1/medical'})
    result=content.read_source({'url':'https://example.org/stroke'},'инсульт',httpx.MockTransport(redirect))
    assert result['status']=='unavailable' and requests==['https://example.org/stroke']


def test_enrichment_reads_duplicate_url_once_and_filters_mismatch(monkeypatch):
    calls=[]
    def read(source,topic,transport):
        calls.append(source['url'])
        return {'status':'read' if 'good' in source['url'] else 'content_mismatch','short_summary':'Кратко','key_points':[]}
    monkeypatch.setattr(content,'read_source',read)
    resources={'topic':'инсульт','groups':[{'status':'completed','sources':[{'url':'https://example.org/good'}]},
        {'status':'completed','sources':[{'url':'https://example.org/good'},{'url':'https://example.org/bad'}]}]}
    result=content.enrich_resources(resources)
    assert sorted(calls)==['https://example.org/bad','https://example.org/good']
    assert len(result['groups'][1]['sources'])==1
    assert result['groups'][0]['sources'][0]['content_review']['status']=='read'
