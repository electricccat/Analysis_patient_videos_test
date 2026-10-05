"""Local patient-to-topic matching; only allowlisted cohort terms reach NCBI."""
from datetime import date, datetime, timezone
from .pubmed import PubMedSearch, POPULATIONS
from .service import feature_topics
from ..patient import validate_profile

NOTE = ('Подбор помогает врачу найти материалы для оценки функции верхней конечности и обсуждения реабилитации. '
        'Соответствие темы не подтверждает диагноз, показания или пригодность метода для пациента. '
        'Онлайн-публикации проверены только библиографически; содержание, критерии включения и ограничения нужно изучить врачу.')
PRIVACY = ('В PubMed отправляются общие категории заболевания, возраста, срока и темы. '
           'Код пациента, точный возраст и даты, диагноз свободным текстом, анамнез, лекарства, видео и значения метрик не передаются.')
CONDITIONS = {'stroke': 'Инсульт', 'brain_injury': 'Черепно-мозговая травма',
              'orthopedic': 'Заболевания и травмы опорно-двигательного аппарата'}


def patient_literature(report, *, search=None, as_of=None):
    p = validate_profile(report.get('patient_profile') or {})
    today = as_of or date.today()
    topics, links = feature_topics(report)
    result = {'status': 'not_searched', 'generated_at': datetime.now(timezone.utc).isoformat(),
              'basis': [], 'groups': [], 'sources': [], 'reviewed_sources': [], 'warnings': [],
              'feature_links': links, 'note': NOTE, 'privacy': PRIVACY,
              'requires_clinician_review': True}
    condition = p['condition']
    if condition not in POPULATIONS:
        result['status'] = 'needs_history'
        result['warnings'].append('Выберите в анкете инсульт, ЧМТ или ортопедическую группу. Для других заболеваний нужен более точный справочник; неподходящая популяция не подставляется автоматически.')
        return result
    result['basis'].append('Группа из анкеты: ' + CONDITIONS[condition])
    if p['diagnosis_confirmed'] != 'yes':
        result['warnings'].append('Диагноз не отмечен как подтверждённый врачом. Поиск использует сообщённую группу заболевания, без подтверждения диагноза.')
    age_group = 'any' if p['age'] is None else 'adult' if p['age'] >= 18 else 'child'
    result['basis'].append('Возрастная группа: ' + {'any': 'не указана', 'adult': 'взрослые', 'child': 'дети и подростки'}[age_group])
    stage = 'any'
    if p['onset_date'] and condition == 'stroke':
        days = (today - date.fromisoformat(p['onset_date'])).days
        stage = 'early' if days <= 180 else 'later'
        result['basis'].append('Срок по дате заболевания: ' + ('до 6 месяцев' if days <= 180 else 'более 6 месяцев') + ' (поисковая категория, не клиническая стадия)')
    if not links:
        result['warnings'].append('Нет надёжных видеометрических данных: темы выбраны только по анкете; отсутствие измерений не означает отсутствие нарушения.')
    result['warnings'].extend(report.get('personalized', {}).get('priorities', []))
    if condition == 'orthopedic':
        result['warnings'].append('Ортопедическая группа широкая: конкретная травма, операция и ограничения из свободного текста не интерпретируются автоматически.')
    plan = [('assessment', 'Оценка и диагностические инструменты', 'Группа заболевания и возраст из анкеты; материалы об оценке функции руки.', 'any')]
    movement = next((t for t in ('reaching', 'elbow_extension', 'shoulder_movement') if t in topics), 'upper_limb')
    plan.append((movement, 'Реабилитация верхней конечности',
                 'Тема доступных надёжных измерений; значения углов не трактуются как диагноз.' if links else 'Общая тема верхней конечности по анкете.', stage))
    if p['spasticity'] == 'yes':
        plan.append(('spasticity', 'Сообщённая спастичность', 'Спастичность отмечена в анкете; по видео она не устанавливается.', 'any'))
    elif p['shoulder_instability'] == 'yes':
        plan.append(('shoulder_pain', 'Оценка плеча', 'В анкете сообщена нестабильность плеча; причину и ограничения нужно уточнить очно.', 'any'))
    elif any(p[k] is not None and p[k] > 0 for k in ('pain_rest', 'pain_movement')):
        plan.append(('upper_limb_pain', 'Боль и функция руки', 'Сообщена боль; причина и локализация уточняются врачом, а не выводятся из видео.', 'any'))
    else:
        plan.append(('occupational_therapy', 'Повседневная функция и эрготерапия', 'Материалы об оценке бытовой функции руки; цели и трудности сопоставляются врачом.', 'any'))
    search = search or PubMedSearch(timeout=6)
    sources = {}
    failures = 0
    for topic, title, reason, query_stage in plan:
        group = {'topic': topic, 'title': title, 'reason': reason, 'source_ids': [], 'status': 'unavailable'}
        try:
            found = search.search(topic, refresh=True, condition=condition, age_group=age_group, stage=query_stage)
            group.update(status='completed', query=found['query'], accessed_at=found['accessed_at'])
            for source in found['sources']:
                sources[source['id']] = source
                group['source_ids'].append(source['id'])
        except Exception:
            failures += 1
            result['warnings'].append(f'PubMed: не удалось получить материалы раздела «{title}». Измерения и анкета сохранены.')
        result['groups'].append(group)
    result['sources'] = list(sources.values())
    result['status'] = 'unavailable' if failures == len(plan) else 'partial' if failures else 'completed'
    # This reviewed catalog concerns adult stroke, not other populations.
    if condition == 'stroke' and age_group == 'adult' and p['diagnosis_confirmed'] == 'yes':
        result['reviewed_sources'] = [s for s in report.get('evidence', {}).get('sources', [])
                                      if s.get('verified') and s.get('verification_scope') == 'reviewed_content']
    return result


def with_patient_literature(report, **kwargs):
    return {**report, 'patient_literature': patient_literature(report, **kwargs)}
