"""Bounded public-page reading and local, grounded thematic summaries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import ipaddress
import re
import socket
from urllib.parse import urlparse, parse_qs
import httpx

MAX_PAGE = 2_000_000


def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Only public HTTPS pages can be read')
    addresses = socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('Private network destination rejected')


def youtube_id(url):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    value = None
    if host in ('youtube.com','www.youtube.com','m.youtube.com') and parsed.path == '/watch':
        value = parse_qs(parsed.query).get('v',[''])[0]
    elif host == 'youtu.be':
        value = parsed.path.lstrip('/').split('/')[0]
    elif host in ('youtube.com','www.youtube.com') and parsed.path.startswith('/shorts/'):
        value = parsed.path.split('/')[2]
    return value if value and re.fullmatch(r'[A-Za-z0-9_-]{11}',value) else None


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[]
        self.lines=[]
        self.main_lines=[]
        self.current=[]
        self.title=[]

    def handle_starttag(self,tag,attrs):
        if tag in ('p','li','h1','h2','h3','h4','div','br'):
            self.flush()
        if tag not in ('br','img','meta','link','input','hr','source','wbr','area','embed'):
            self.stack.append(tag)

    def handle_endtag(self,tag):
        if tag in ('p','li','h1','h2','h3','h4','div','article','main'):
            self.flush()
        if tag in self.stack:
            self.stack=self.stack[:len(self.stack)-1-self.stack[::-1].index(tag)]

    def handle_data(self,data):
        if 'title' in self.stack:
            self.title.append(data)
        if not any(t in self.stack for t in ('script','style','noscript','nav','footer','header','form','aside','head')):
            self.current.append(data)

    def flush(self):
        text=re.sub(r'\s+',' ',' '.join(self.current)).strip()
        self.current=[]
        if len(text)>=35:
            self.lines.append(text)
            if 'article' in self.stack or 'main' in self.stack:
                self.main_lines.append(text)

    def text(self):
        self.flush()
        lines = self.main_lines if sum(map(len,self.main_lines))>=300 else self.lines
        return '\n'.join(dict.fromkeys(lines))[:100000]


THEMES = [
    (r'лечебн\w* физкультур|\bлфк\b|physiotherap|physical therapy|exercise|упражнен', 'лечебные упражнения', 'Рассматриваются лечебные упражнения и восстановление двигательных навыков.'),
    (r'спастич|мышечн\w* тонус|spasticity', 'мышечный тонус', 'Есть сведения о спастичности или повышенном мышечном тонусе.'),
    (r'ходьб|равновеси|баланс|gait|balance|walking', 'ходьба и равновесие', 'Обсуждается восстановление ходьбы или равновесия.'),
    (r'кист[ьи]|верхн\w* конечност|\bрук[аиу]\b|upper limb|hand function', 'функция руки и кисти', 'Материал затрагивает восстановление функции руки или кисти.'),
    (r'эрготерап|occupational therapy|бытов\w* навык', 'самостоятельность в быту', 'Освещены эрготерапия или навыки самостоятельности в быту.'),
    (r'логопед|восстановлен\w* реч|speech therapy|aphasia', 'речь и коммуникация', 'Обсуждается восстановление речи и коммуникации.'),
    (r'индивидуальн\w* (?:программ|подход|план)|individuali[sz]ed|personalised', 'индивидуальная программа', 'В тексте рассматривается индивидуальный подбор программы восстановления.'),
    (r'противопоказан|ограничени\w* нагруз|contraindication|precaution', 'ограничения и безопасность', 'Упоминаются противопоказания или ограничения нагрузки; их следует сверить с выпиской.'),
    (r'семь[яи]|родственник|caregiver|family support', 'помощь близких', 'Рассматривается участие семьи или помощников в восстановлении.'),
]


def summarize_text(text,topic):
    # Generated prose describes subjects present in the text. It never invents dosages,
    # outcome probabilities, evidence strength, or a personalised treatment regimen.
    if len(text.strip())<300:
        return {'status':'insufficient_text','short_summary':'На странице недостаточно доступного текста для краткого обзора.','key_points':[]}
    normalized=text.casefold()
    from .clinical_review import search_context, MEDICAL_TERMS
    _,terms=search_context(topic)
    if not terms or not any(t in normalized for t in terms) or not any(t in normalized for t in MEDICAL_TERMS):
        return {'status':'content_mismatch','short_summary':'Прочитанный текст не подтвердил связь с диагнозом и реабилитацией.','key_points':[]}
    found=[(name,point) for pattern,name,point in THEMES if re.search(pattern,normalized)]
    return {'status':'read','short_summary':'Материал о реабилитации. Основные темы: '+', '.join(name for name,_ in found[:4])+'.' if found else 'Материал посвящён реабилитации по указанной теме; конкретные методы требуют просмотра оригинала.',
            'key_points':[point for _,point in found[:5]], 'method':'local_thematic_summary',
            'note':'Краткий тематический обзор составлен по доступному тексту страницы. Эффективность методов и применимость к пациенту не оценены.'}


def read_source(source,topic,transport=None):
    url=source['url']
    checked_at=datetime.now(timezone.utc).isoformat()
    try:
        with httpx.Client(timeout=7,transport=transport,follow_redirects=False,headers={'User-Agent':'Kinema/0.2 (public rehabilitation reading)'}) as client:
            video_id=youtube_id(url)
            if video_id:
                response=client.get('https://www.youtube.com/oembed',params={'url':f'https://www.youtube.com/watch?v={video_id}','format':'json'})
                response.raise_for_status()
                if len(response.content)>100000:
                    raise ValueError('Oversized video metadata')
                info=response.json()
                if not isinstance(info,dict) or not info.get('title') or not info.get('author_name'):
                    raise ValueError('Invalid video metadata')
                from .clinical_review import relevant_source
                if not relevant_source({'title':str(info.get('title','')),'summary':'','url':url},topic,'video'):
                    return {'status':'content_mismatch','short_summary':'Название видео не подтвердило связь с реабилитацией по теме.','key_points':[]}
                return {'status':'video_metadata','short_summary':'Учебный ролик по теме восстановления. Доступны название и автор; содержание упражнений без просмотра или расшифровки не пересказывается.',
                        'key_points':['Название и канал проверены через YouTube.','Перед выполнением упражнений уточните ограничения из выписки.'],
                        'video_id':video_id,'channel':str(info.get('author_name',''))[:200],'video_title':str(info.get('title',''))[:500],
                        'checked_at':checked_at,'method':'youtube_oembed','note':'Видео и субтитры автоматически не анализировались.'}
            current=url
            for _ in range(4):
                public_url(current)
                with client.stream('GET',current) as response:
                    if response.is_redirect:
                        current=str(response.url.join(response.headers.get('location','')))
                        continue
                    response.raise_for_status()
                    if 'html' not in response.headers.get('content-type','').lower():
                        return {'status':'unsupported_format','short_summary':'Этот формат не удалось прочитать автоматически. Откройте оригинал.','key_points':[],'checked_at':checked_at}
                    content=bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content)>MAX_PAGE:
                            raise ValueError('Oversized page')
                    encoding=response.encoding or 'utf-8'
                    parser=ArticleText()
                    parser.feed(content.decode(encoding,errors='replace'))
                    text=parser.text()
                    return {**summarize_text(text,topic),'checked_at':checked_at,'content_sha256':sha256(text.encode()).hexdigest(),'characters_read':len(text),'source_url':current}
            raise ValueError('Too many redirects')
    except (httpx.HTTPError,OSError,ValueError,UnicodeError,LookupError):
        return {'status':'unavailable','short_summary':'Страницу не удалось прочитать. Краткое содержание не сформировано.','key_points':[],'checked_at':checked_at}


def enrich_resources(resources,transport=None):
    result={**resources,'groups':[{**g,'sources':[dict(s) for s in g['sources']]} for g in resources['groups']]}
    # Read each URL once; Russian resources and YouTube are prioritised.
    sources={s['url']:s for g in result['groups'] for s in g['sources']}
    ordered=sorted(sources.values(),key=lambda s:0 if s.get('language')=='ru' or youtube_id(s['url']) else 1)[:14]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={s['url']:pool.submit(read_source,s,result['topic'],transport) for s in ordered}
        summaries={url:f.result() for url,f in futures.items()}
    for group in result['groups']:
        group['sources']=[{**s,'content_review':summaries.get(s['url'],{'status':'not_read','short_summary':'Оригинал ещё не прочитан автоматически.','key_points':[]})} for s in group['sources'] if summaries.get(s['url'],{}).get('status')!='content_mismatch']
        if not group['sources'] and group['status']=='completed':
            group['status']='no_relevant_results'
    return result
