from copy import deepcopy
from .service import ReviewedCatalogService, feature_topics
from .pubmed import PubMedSearch
from ..recommendations.service import grounded_sections
from ..recommendations.safety import SAFETY
from ..patient import personalized_section


def enrich_report(report, *, online=False, topic=None, catalog=None, search=None):
    result = deepcopy(report)
    try:
        bundle = (catalog or ReviewedCatalogService()).retrieve(result)
    except (OSError,ValueError,KeyError):
        topics, links = feature_topics(result)
        bundle = {'catalog_version':'unavailable','mode':'reviewed_catalog','topics':topics,'feature_links':links,
                  'sources':[],'search_results':[],'warnings':['Каталог источников не прошёл проверку. Медицинский контекст не сформирован; измерения сохранены.'],
                  'online_search':{'status':'not_requested'},'selection_note':'Проверенные источники недоступны.'}
    if online:
        if topic not in bundle['topics']:
            raise ValueError('Тема недоступна: нет соответствующих надёжных измерений.')
        try:
            found = (search or PubMedSearch()).search(topic)
            bundle['search_results'] = found['sources']
            bundle['online_search'] = {'status':'completed', **{k:v for k,v in found.items() if k!='sources'}}
        except Exception:
            # Connectivity must never erase measurements or invent evidence.
            bundle['online_search'] = {'status':'unavailable','topic':topic}
            bundle['warnings'].append('PubMed недоступен или ответ не прошёл проверку. Новые публикации не использованы; измерения и проверенный каталог сохранены.')
    else:
        # Keep existing independently verified discovery without promoting it to evidence.
        previous = result.get('evidence',{})
        bundle['search_results'] = previous.get('search_results',[])
        bundle['online_search'] = previous.get('online_search',bundle['online_search'])
    contexts, options, disagreements = grounded_sections(bundle)
    result.update(schema_version='1.1',evidence=bundle,evidence_status='reviewed_catalog' if bundle['sources'] else 'no_usable_evidence',
                  clinical_context=contexts,rehabilitation_options=options,evidence_disagreements=disagreements,
                  safety_screen=deepcopy(SAFETY))
    result['personalized'] = personalized_section(result)
    return result
