"""Fixed NCBI endpoints and generic topic terms only. No arbitrary URL/query API."""
from datetime import datetime, timezone, date
from calendar import monthrange
from threading import Lock
import time
import re
from xml.etree import ElementTree as ET
import httpx
from .service import EvidenceRecord, priority

BASE = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
QUERIES = {
    'assessment': '(upper limb[Title/Abstract] OR upper extremity[Title/Abstract] OR arm[Title/Abstract]) AND (psychometric[Title/Abstract] OR validity[Title/Abstract] OR reliability[Title/Abstract] OR diagnostic accuracy[Title/Abstract] OR measurement properties[Title/Abstract] OR assessment tool[Title/Abstract])',
    'shoulder_pain': 'shoulder[Title/Abstract] AND pain[Title/Abstract]',
    'upper_limb_pain': '(upper limb[Title/Abstract] OR upper extremity[Title/Abstract] OR arm[Title/Abstract]) AND pain[Title/Abstract]',
    'spasticity': '(upper limb[Title/Abstract] OR upper extremity[Title/Abstract] OR arm[Title/Abstract]) AND spasticity[Title/Abstract]',
    'upper_limb': '(upper limb[Title/Abstract] OR upper extremity[Title/Abstract] OR arm[Title/Abstract]) AND (rehabilitation[Title/Abstract] OR training[Title/Abstract] OR therapy[Title/Abstract])',
    'shoulder_movement': '(shoulder[Title/Abstract] OR scapular[Title/Abstract]) AND rehabilitation[Title/Abstract]',
    'elbow_extension': 'elbow[Title/Abstract] AND (extension[Title/Abstract] OR reaching[Title/Abstract])',
    'reaching': 'reaching[Title/Abstract] AND (upper limb[Title/Abstract] OR upper extremity[Title/Abstract] OR arm[Title/Abstract]) AND (training[Title/Abstract] OR rehabilitation[Title/Abstract])',
    'trunk_control': 'trunk[Title/Abstract] AND (compensation[Title/Abstract] OR restraint[Title/Abstract] OR training[Title/Abstract])',
    'occupational_therapy': '(occupational therapy[Title/Abstract] OR occupational therapy[MeSH Terms]) AND (daily living[Title/Abstract] OR upper limb[Title/Abstract])',
    'bilateral_training': 'bilateral[Title/Abstract] AND (arm[Title/Abstract] OR upper limb[Title/Abstract]) AND training[Title/Abstract]',
    'mirror_therapy': 'mirror therapy[Title/Abstract] AND (arm[Title/Abstract] OR upper limb[Title/Abstract] OR upper extremity[Title/Abstract])',
    'cimt': '(constraint-induced movement therapy[Title/Abstract] OR CIMT[Title/Abstract])',
    'electrical_stimulation': 'electrical stimulation[Title/Abstract] AND (arm[Title/Abstract] OR upper limb[Title/Abstract] OR upper extremity[Title/Abstract])',
}
POPULATIONS = {
    'stroke': '(stroke[MeSH Terms] OR stroke[Title] OR poststroke[Title] OR post-stroke[Title])',
    'brain_injury': '(brain injuries, traumatic[MeSH Terms] OR traumatic brain injury[Title/Abstract])',
    'orthopedic': '(musculoskeletal diseases[MeSH Terms] OR upper extremity injuries[MeSH Terms])',
}
AGES = {'any': '', 'adult': '(adult[MeSH Terms] OR adults[Title/Abstract])',
        'child': '(child[MeSH Terms] OR adolescent[MeSH Terms] OR pediatric[Title/Abstract])'}
STAGES = {'any': '', 'early': '(acute[Title/Abstract] OR subacute[Title/Abstract])',
          'later': 'chronic[Title/Abstract]'}
network_lock = Lock()
cache = {}
last_request = 0.0


def publication_type(types):
    for pubmed_type, canonical in [('Practice Guideline','clinical_practice_guideline'),('Guideline','clinical_practice_guideline'),
        ('Systematic Review','systematic_review'),('Meta-Analysis','meta_analysis'),
        ('Randomized Controlled Trial','randomized_controlled_trial'),('Validation Study','validation_study'),('Observational Study','observational_study')]:
        if pubmed_type in types: return canonical
    return 'other'


def parse_articles(xml, allowed_ids, topic, accessed_at):
    """Bibliography checked against requested PMIDs, never promoted to reviewed claims."""
    if len(xml) > 2_000_000 or '<!ENTITY' in xml.upper():
        raise ValueError('Unsafe/oversized NCBI response')
    root = ET.fromstring(xml)
    results = []
    for article in root.findall('PubmedArticle'):
        pmid = article.findtext('MedlineCitation/PMID','')
        if pmid not in allowed_ids or not pmid.isdigit(): continue
        node = article.find('MedlineCitation/Article')
        if node is None: continue
        title_node = node.find('ArticleTitle')
        title = ''.join(title_node.itertext()).strip() if title_node is not None else ''
        types = [p.text or '' for p in node.findall('PublicationTypeList/PublicationType')]
        if set(types).intersection({'Retracted Publication','Retraction of Publication','Published Erratum'}) or article.find("MedlineCitation/CommentsCorrectionsList/CommentsCorrections[@RefType='RetractionIn']") is not None:
            continue
        year_text = node.findtext('Journal/JournalIssue/PubDate/Year') or node.findtext('Journal/JournalIssue/PubDate/MedlineDate','')
        match = re.search(r'\b(?:19|20)\d{2}\b',year_text)
        authors = []
        for author in node.findall('AuthorList/Author'):
            name = author.findtext('CollectiveName') or ' '.join(filter(None,[author.findtext('LastName'),author.findtext('Initials')]))
            if name: authors.append(name)
        doi = next((item.text for item in article.findall('PubmedData/ArticleIdList/ArticleId') if item.get('IdType')=='doi'),None)
        if doi and not re.fullmatch(r'10\.\d{4,9}/\S+',doi): doi = None
        if not title or not match or not authors: continue
        results.append(EvidenceRecord(id=f'pubmed_{pmid}',title=title,authors_or_organization=', '.join(authors),
            year=int(match.group()),url=f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/',doi=doi,
            publication_type=publication_type(types),accessed_at=accessed_at,verified=True,
            verification_scope='bibliographic_metadata',topics=[topic],
            summary='Проверены библиографические данные PubMed. Содержание и клиническая применимость не оценены; публикация не используется для автоматических медицинских утверждений.',
            evidence_strength='Не оценена. Тип публикации сам по себе не определяет качество доказательств.',locator=f'PMID: {pmid}'))
    return sorted(results,key=priority)


class PubMedSearch:
    def __init__(self, transport=None, timeout=12):
        self.transport = transport
        self.timeout = timeout

    def search(self, topic, *, refresh=False, condition='stroke', age_group='any', stage='any'):
        if topic not in QUERIES: raise ValueError('Unsupported evidence topic')
        if condition not in POPULATIONS or age_group not in AGES or stage not in STAGES:
            raise ValueError('Unsupported population filters')
        query = POPULATIONS[condition] + ' AND (' + QUERIES[topic] + ')'
        for terms in (AGES[age_group], STAGES[stage]):
            if terms: query += ' AND (' + terms + ')'
        if topic == 'assessment':
            query += ' AND (guideline[pt] OR systematic review[pt] OR meta-analysis[pt] OR validation study[pt])'
        else:
            query += ' AND (guideline[pt] OR systematic review[pt] OR meta-analysis[pt] OR randomized controlled trial[pt] OR observational study[pt])'
        today = datetime.now(timezone.utc).date()
        earliest = date(today.year-5,today.month,min(today.day,monthrange(today.year-5,today.month)[1]))
        query += f' AND ("{earliest:%Y/%m/%d}"[Date - Publication] : "{today:%Y/%m/%d}"[Date - Publication])'
        cache_key = (topic, condition, age_group, stage)
        with network_lock:
            existing = cache.get(cache_key) if self.transport is None and not refresh else None
            if existing and time.monotonic()-existing[0] < 86400:
                return {**existing[1],'from_cache':True}
            def fetch(client, endpoint, params):
                global last_request
                remaining = .36 - (time.monotonic()-last_request)
                if remaining > 0 and self.transport is None: time.sleep(remaining)
                response = client.get(BASE+endpoint,params=params)
                last_request = time.monotonic()
                response.raise_for_status()
                if len(response.content)>2_000_000: raise ValueError('Oversized NCBI response')
                return response
            with httpx.Client(timeout=self.timeout,follow_redirects=False,transport=self.transport,headers={'User-Agent':'KinemaResearchPrototype/0.2'}) as client:
                response = fetch(client,'esearch.fcgi',{'db':'pubmed','term':query,'retmode':'json','retmax':5,'sort':'relevance','tool':'kinema'})
                identifiers = response.json()['esearchresult']['idlist']
                identifiers = [str(x) for x in identifiers if re.fullmatch(r'\d{1,12}',str(x))][:5]
                accessed = datetime.now(timezone.utc).isoformat()
                records = []
                if identifiers:
                    response = fetch(client,'efetch.fcgi',{'db':'pubmed','id':','.join(identifiers),'retmode':'xml','tool':'kinema'})
                    records = parse_articles(response.text,set(identifiers),topic,accessed)
                result = {'topic':topic,'query':query,'accessed_at':accessed,'sources':[r.model_dump() for r in records],'from_cache':False}
                if self.transport is None: cache[cache_key]=(time.monotonic(),result)
                return result
