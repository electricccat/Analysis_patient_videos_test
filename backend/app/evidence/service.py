"""Only reviewed content grounds clinical text; no patient data leave this service."""
from datetime import date
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlparse
import json
import math
from pydantic import BaseModel, Field, field_validator

ALLOWED_HOSTS = {'www.nice.org.uk', 'www.cochrane.org', 'pubmed.ncbi.nlm.nih.gov',
                 'www.strokeguideline.org', 'www.who.int', 'www.ahajournals.org'}
RANK = {'clinical_practice_guideline': 0, 'systematic_review': 1,
        'meta_analysis': 1, 'randomized_controlled_trial': 2, 'validation_study': 2, 'observational_study': 3, 'other': 4}
CATALOG = Path(__file__).with_name('catalog.json')
CATALOG_REVIEW_MAX_DAYS = 180


class EvidenceRecord(BaseModel):
    id: str
    title: str
    authors_or_organization: str
    year: int
    url: str
    doi: str | None = None
    publication_type: str
    summary: str
    accessed_at: str
    verified: bool
    verification_scope: Literal['reviewed_content', 'bibliographic_metadata']
    evidence_strength: str
    topics: list[str] = Field(default_factory=list)
    locator: str | None = None
    publication_status: str = 'published'

    @field_validator('url')
    @classmethod
    def trusted_source(cls, value):
        parsed = urlparse(value)
        if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password or parsed.port not in (None,443):
            raise ValueError('Untrusted evidence source')
        return value


class EvidenceService(Protocol):
    def retrieve(self, measured_features: dict) -> dict: ...


def reliable(metric):
    value = metric.get('value')
    return (isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value)
            and metric.get('status') == 'measured' and metric.get('technical_reliability') in ('high','medium')
            and metric.get('coverage',0) >= .6)


def feature_topics(report):
    """Topics indicate what was measured, never a diagnosis or treatment eligibility."""
    topics, links = set(), []
    for group in ('left_arm','right_arm'):
        for key in ('shoulder_max','elbow_max','wrist_mean_speed'):
            metric = report.get('metrics',{}).get(group,{}).get(key,{})
            if reliable(metric):
                links.append({'metric': f'{group}.{key}', **{k: metric[k] for k in ('value','unit','technical_reliability')}})
                topics.update(('upper_limb','task_practice','occupational_therapy','mirror_therapy','cimt','electrical_stimulation'))
                topics.add('shoulder_movement' if key=='shoulder_max' else 'elbow_extension' if key=='elbow_max' else 'reaching')
    if all(any(link['metric'].startswith(group) for link in links) for group in ('left_arm','right_arm')):
        topics.add('bilateral_training')
    trunk = report.get('metrics',{}).get('trunk',{}).get('max_lateral_tilt_change',{})
    if reliable(trunk):
        topics.add('trunk_control')
        links.append({'metric': 'trunk.max_lateral_tilt_change', **{k:trunk[k] for k in ('value','unit','technical_reliability')}})
    return sorted(topics), links


def priority(record):
    return RANK.get(record.publication_type,4), -record.year, record.id


class ReviewedCatalogService:
    def __init__(self, catalog_path=CATALOG, as_of=None):
        self.catalog_path = catalog_path
        self.as_of = as_of or date.today()

    def retrieve(self, measured_features):
        topics, links = feature_topics(measured_features)
        payload = json.loads(self.catalog_path.read_text(encoding='utf-8'))
        records, warnings = [], []
        for raw in payload['sources']:
            record = EvidenceRecord.model_validate(raw)
            age = (self.as_of - date.fromisoformat(record.accessed_at[:10])).days
            if set(record.topics).intersection(topics) and record.verified and record.verification_scope == 'reviewed_content':
                if 0 <= age <= CATALOG_REVIEW_MAX_DAYS:
                    records.append(record)
                else:
                    warnings.append(f'Источник {record.id} требует повторной проверки актуальности и не использован для рекомендаций.')
        records.sort(key=priority)
        return {'catalog_version':payload['version'], 'mode':'reviewed_catalog',
                'topics':topics, 'feature_links':links, 'sources':[r.model_dump() for r in records],
                'search_results':[], 'warnings':warnings, 'online_search':{'status':'not_requested'},
                'selection_note':'Тематическая релевантность не подтверждает клиническую применимость. Каталог не является исчерпывающим обзором; дата проверки и год публикации указаны отдельно.'}
