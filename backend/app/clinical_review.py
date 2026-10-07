"""Transparent differential hypotheses and bounded public-web discovery."""
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse
import xml.etree.ElementTree as ET
import re
from copy import deepcopy
from pathlib import Path
import json
import httpx

SEARCH_CATEGORIES = [
    ('guidelines', 'Клинические рекомендации', 'реабилитация клинические рекомендации'),
    ('exercise', 'Реабилитация и ЛФК', 'реабилитация ЛФК упражнения'),
    ('cases', 'Восстановление других пациентов', 'реабилитация история восстановления пациента'),
    ('video', 'Видео восстановления на YouTube', 'реабилитация восстановление упражнения site:youtube.com/watch'),
    ('photo', 'Фото и истории восстановления', 'реабилитация восстановление фото история пациента'),
]
CONDITIONS = [
    (('инсульт', 'stroke', 'постинсульт'), 'stroke', ('инсульт', 'stroke', 'poststroke', 'post-stroke')),
    (('дцп', 'церебральн', 'cerebral palsy'), 'cerebral palsy', ('дцп', 'церебральн', 'cerebral palsy')),
    (('черепно-мозгов', 'brain injury', 'чмт'), 'traumatic brain injury', ('черепно-мозгов', 'brain injury', 'чмт')),
    (('перелом', 'fracture'), 'fracture', ('перелом', 'fracture')),
    (('ортопед', 'orthopedic', 'orthopaedic'), 'orthopedic', ('ортопед', 'orthopedic', 'orthopaedic')),
]
MEDICAL_TERMS = ('реабилит', 'лфк', 'лечебн', 'физиотерап', 'восстановлен', 'rehabilitat', 'physiotherap', 'physical therapy', 'occupational therapy')
CATEGORY_TERMS = {
    'guidelines': ('guideline', 'recommendation', 'рекомендац', 'руководств', 'протокол'),
    'exercise': ('exercise', 'physiotherap', 'physical therapy', 'лфк', 'упражнен', 'физиотерап', 'лечебн'),
    'cases': ('case report', 'case study', 'story', 'истори', 'клинический случай'),
    'video': ('video', 'youtube', 'видео', 'rutube'),
    'photo': ('photo', 'picture', 'image', 'story', 'фото', 'истори'),
}
TOPIC_STOPWORDS = {'реабилитация', 'реабилитации', 'реабилитацию', 'восстановление', 'восстановления', 'после', 'при', 'лечение', 'лечения', 'лфк', 'rehabilitation', 'recovery', 'treatment', 'after', 'exercises', 'therapy', 'the', 'and', 'для', 'пациента'}
TRUSTED_GUIDELINES = ('nice.org.uk', 'who.int', 'nhs.uk', 'stroke.org', 'strokeguideline.org', 'aapmr.org', 'aafp.org', 'cochranelibrary.com', 'pubmed.ncbi.nlm.nih.gov', 'pmc.ncbi.nlm.nih.gov', 'cr.minzdrav.gov.ru', 'minzdrav.gov.ru', 'nmicrk.ru', 'rehabrus.ru', 'neurology.ru')


def search_context(topic):
    lower = topic.casefold()
    for aliases, query, terms in CONDITIONS:
        if any(alias in lower for alias in aliases):
            return query, terms
    terms = tuple(w for w in re.findall(r'[a-zа-яё]{4,}', lower) if w not in TOPIC_STOPWORDS)
    return topic, terms


def relevant_source(source, topic, category):
    """Conservative lexical relevance, not a claim of clinical correctness."""
    if category not in CATEGORY_TERMS:
        return False
    url = source.get('url', '')
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        return False
    host = parsed.hostname.lower()
    # Don't use URL query parameters as evidence: they can just repeat the search.
    text = (str(source.get('title', ''))+' '+str(source.get('summary', ''))).casefold()
    _, condition_terms = search_context(topic)
    if not condition_terms or not any(term in text for term in condition_terms):
        return False
    if not any(term in text for term in MEDICAL_TERMS):
        return False
    from .resource_content import youtube_id
    video_link = category == 'video' and youtube_id(url) is not None
    if not video_link and not any(term in text for term in CATEGORY_TERMS[category]):
        return False
    if category == 'guidelines' and not any(host == domain or host.endswith('.'+domain) for domain in TRUSTED_GUIDELINES):
        return False
    return True


def filter_resources(resources):
    result = deepcopy(resources)
    topic = result.get('topic', '')
    for group in result.get('groups', []):
        candidates = group.get('sources', [])
        unique = {}
        for source in candidates:
            if relevant_source(source, topic, group.get('id')):
                unique.setdefault(source['url'], {**source, 'relevance':'topic_and_rehabilitation_match'})
        group['sources'] = list(unique.values())[:6]
        group['rejected_count'] = group.get('rejected_count', 0) + len(candidates)-len(unique)
        if group.get('status') != 'unavailable':
            group['status'] = 'completed' if group['sources'] else 'no_relevant_results'
    result['relevance_version'] = 1
    result['note'] = 'Поиск включает русскоязычные сайты и YouTube. Ссылки проверяются на связь с диагнозом и реабилитацией. Краткие обзоры составлены по доступному тексту страниц; для видео отдельно указано, прочитан ли текст или только название и канал. Применимость методов к пациенту и эффективность лечения автоматически не оцениваются.'
    return result


def filter_report_resources(report):
    if report.get('web_resources'):
        return {**report, 'web_resources':filter_resources(report['web_resources'])}
    return report


def curated_resources(topic, category):
    """Reviewed discovery links; no patient-specific treatment claims."""
    try:
        catalog = json.loads(Path(__file__).with_name('recovery_resources.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [{**source, 'domain':urlparse(source['url']).hostname, 'verification':'curated_resource'}
            for source in catalog['sources'] if category in source['categories'] and relevant_source(source, topic, category)]


def clinical_review(report, discharge):
    profile = report.get('patient_profile', {})
    text = (str(profile.get('history') or '') + ' ' + str(discharge.get('text') or '')).lower()
    diagnosis = str(profile.get('diagnosis') or '').strip()
    if not diagnosis:
        match = re.search(r'(?:основной\s+диагноз|диагноз|diagnosis)\s*[:\-]\s*(.{3,400}?)(?=\n|рекомендации\s*[:\-]|лечение\s*[:\-]|$)', str(discharge.get('text') or ''), re.I)
        diagnosis = match.group(1).strip() if match else ''
    # Preserve documented diagnosis separately; never label it an independent finding.
    flexed = [d for d in report.get('body_details', []) if d['region'].endswith('_arm') and d['value'] is not None and d['value'] < 130]
    hypotheses = []
    if flexed:
        hypotheses.append({'title': 'Сгибательная установка руки: возможный неврологический или ортопедический синдром',
            'basis': [f"{d['label']}: внутренний угол локтя {d['value']:.1f}°" for d in flexed],
            'alternatives': ['Произвольная поза во время записи', 'Боль или ограничение сустава / контрактура', 'Парез со спастичностью после поражения ЦНС'],
            'checks': ['Пассивное разгибание и боль', 'Сила, рефлексы, чувствительность', 'Тонус при разной скорости пассивного движения; шкалы Tardieu / Ashworth']})
    if any(word in text for word in ('инсульт', 'постинсульт', 'stroke')) and not re.search(r'(?:не|нет|без|исключ[\w]*)\s+(?:\w+\s+){0,2}(?:инсульт|stroke)', text):
        hypotheses.append({'title': 'Возможные последствия инсульта — по анамнезу / тексту выписки', 'basis': ['В анамнезе или выписке встречается упоминание инсульта; контекст и отрицания нужно проверить.'],
            'alternatives': ['Другая причина пареза', 'Сопутствующее ортопедическое ограничение'], 'checks': ['Сверить дату и сторону поражения с документами и видео', 'Проверить неврологический статус и заключение врача']})
    if not hypotheses:
        hypotheses.append({'title': 'Недостаточно данных для независимой диагностической гипотезы', 'basis': ['Поза и видимые ориентиры не позволяют установить причину нарушения.'],
            'alternatives': ['Неврологическая причина', 'Ортопедическая причина', 'Вариант позы без заболевания'], 'checks': ['Осмотр и проверенная выписка', 'Уточнить жалобы, начало заболевания, силу, тонус и пассивную амплитуду']})
    return {'documented_diagnosis': diagnosis or None, 'discharge_text': discharge.get('text', ''), 'discharge_status': discharge.get('status', 'not_attached'),
            'hypotheses': hypotheses, 'status': 'preliminary', 'note': 'Гипотезы сформированы локальными правилами, а не диагностической нейросетью. Подтверждённый диагноз в анкете не заменяет независимую проверку. Проценты вероятности не вычисляются.'}


def discover(report, topic, transport=None):
    """Only a user-confirmed generic diagnosis/topic leaves the local server."""
    if not isinstance(topic, str) or not 2 <= len(topic.strip()) <= 160 or any(ord(c)<32 for c in topic):
        raise ValueError('Укажите общую тему или диагноз длиной 2–160 символов без персональных данных.')
    topic = topic.strip()
    query_topic, _ = search_context(topic)
    query_topic = {'stroke':'инсульт','cerebral palsy':'ДЦП','traumatic brain injury':'черепно-мозговая травма','fracture':'перелом','orthopedic':'ортопедическая реабилитация'}.get(query_topic,topic)
    groups, warnings = [], []
    with httpx.Client(timeout=8, transport=transport, follow_redirects=False) as client:
        for key, label, suffix in SEARCH_CATEGORIES:
            query = f'{query_topic} {suffix}'
            sources, state = [], 'unavailable'
            try:
                response = client.get('https://www.bing.com/search', params={'q':query, 'format':'rss', 'mkt':'ru-RU'})
                response.raise_for_status()
                raw = response.content
                if len(raw)>1_000_000 or b'<!ENTITY' in raw.upper() or b'<!DOCTYPE' in raw.upper():
                    raise ValueError('Unsafe response')
                root = ET.fromstring(raw)
                if root.tag != 'rss':
                    raise ValueError('Unexpected search response')
                for item in root.findall('./channel/item')[:20]:
                    url = item.findtext('link', '')
                    parsed = urlparse(url)
                    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                        continue
                    title=item.findtext('title', '')[:500]
                    description=item.findtext('description', '')[:1000]
                    sources.append({'title':title, 'url':url, 'summary':description, 'language':'ru' if re.search('[а-яё]',title+description,re.I) else 'other',
                                    'domain': parsed.hostname, 'verification': 'search_snippet_only'})
                state = 'completed' if sources else 'no_results'
            except (httpx.HTTPError, ValueError, ET.ParseError):
                warnings.append(f'{label}: поисковик недоступен или вернул неподходящий ответ.')
            curated = curated_resources(topic, key)
            if key == 'video':
                from .resource_content import youtube_id
                sources = [s for s in sources if youtube_id(s['url'])]
                curated = [s for s in curated if youtube_id(s['url'])]
            if curated:
                sources = sorted(curated + sources,key=lambda s:0 if s.get('language')=='ru' else 1)
                state = 'completed'
            groups.append({'id':key, 'title':label, 'query':query, 'status':state, 'sources':sources,
                           'search_url':'https://www.google.com/search?'+urlencode({'q':query})})
    from .resource_content import enrich_resources
    return enrich_resources(filter_resources({'topic': topic, 'generated_at':datetime.now(timezone.utc).isoformat(), 'groups':groups, 'warnings':warnings}),transport)


def suggested_topic(report):
    """Use a fixed public category; never send extracted patient text to search."""
    profile = report.get('patient_profile', {})
    diagnosis = str(report.get('clinical_review', {}).get('documented_diagnosis') or '').lower()
    for words, topic in [(('инсульт', 'stroke'), 'реабилитация после инсульта'),
                         (('дцп', 'церебральный паралич'), 'реабилитация при церебральном параличе'),
                         (('черепно-мозгов', 'brain injury'), 'реабилитация после черепно-мозговой травмы'),
                         (('перелом',), 'реабилитация после перелома')]:
        if any(word in diagnosis for word in words):
            return topic
    return {'stroke':'реабилитация после инсульта', 'brain_injury':'реабилитация после черепно-мозговой травмы',
            'orthopedic':'ортопедическая реабилитация'}.get(profile.get('condition'), '')
