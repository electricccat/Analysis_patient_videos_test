"""Local patient history and conservative, evidence-linked upper-limb context."""
from datetime import date
from typing import Literal
from pydantic import ConfigDict, Field, create_model
from .evidence.service import reliable


def field(key, label, group, kind='text', *, choices=None, minimum=None, maximum=None, hint=''):
    return dict(key=key, label=label, group=group, kind=kind, choices=choices,
                minimum=minimum, maximum=maximum, hint=hint)


YES_NO = [['unknown', 'Неизвестно / не оценено'], ['yes', 'Да'], ['no', 'Нет']]
FIELDS = [
    field('patient_code', 'Код пациента', 'Общие сведения', hint='Используйте код вместо ФИО. Не указывайте паспорт, адрес или контакты.'),
    field('age', 'Возраст, лет', 'Общие сведения', 'number', minimum=0, maximum=120),
    field('sex', 'Пол', 'Общие сведения', 'select', choices=[['unknown','Не указан'],['female','Женский'],['male','Мужской'],['other','Другой']]),
    field('dominant_hand', 'Ведущая рука до заболевания', 'Общие сведения', 'select', choices=[['unknown','Неизвестно'],['left','Левая'],['right','Правая'],['both','Обе']]),
    field('condition', 'Основная группа заболевания', 'История болезни', 'select', choices=[['unknown','Не определена'],['stroke','Инсульт'],['brain_injury','Черепно-мозговая травма'],['orthopedic','Травма / заболевание суставов и мышц'],['other_neurological','Другое неврологическое заболевание'],['other','Другое']]),
    field('diagnosis', 'Диагноз и его формулировка из медицинских документов', 'История болезни', hint='Диагноз не устанавливается по видео.'),
    field('diagnosis_confirmed', 'Диагноз подтверждён врачом', 'История болезни', 'select', choices=YES_NO),
    field('onset_date', 'Дата заболевания / травмы', 'История болезни', 'date'),
    field('history', 'Течение заболевания и изменения функции руки', 'История болезни', 'textarea'),
    field('previous_function', 'Функция рук и самостоятельность до заболевания', 'История болезни', 'textarea'),
    field('surgeries', 'Операции, переломы, вывихи, повреждения сухожилий и даты', 'История болезни', 'textarea'),
    field('comorbidities', 'Сопутствующие заболевания', 'История болезни', 'textarea', hint='Включая сердечно-сосудистые заболевания, диабет, эпилепсию, остеопороз и заболевания суставов, если известны.'),
    field('medications', 'Препараты, дозы, недавние изменения и нежелательные эффекты', 'История болезни', 'textarea', hint='Только сведения для специалиста; приложение не меняет медикаментозное лечение.'),
    field('allergies', 'Аллергии и реакции на лечение', 'История болезни', 'textarea'),
    field('medical_clearance', 'Врач оценил возможность реабилитационной нагрузки', 'Безопасность и ограничения', 'select', choices=YES_NO),
    field('medical_restrictions', 'Ограничения врача и противопоказания', 'Безопасность и ограничения', 'textarea', hint='Запреты движений/нагрузки, послеоперационный режим. Если ограничений нет, укажите это явно.'),
    field('pain_rest', 'Боль в покое, 0–10', 'Безопасность и ограничения', 'number', minimum=0, maximum=10),
    field('pain_movement', 'Боль при движении, 0–10', 'Безопасность и ограничения', 'number', minimum=0, maximum=10),
    field('pain_details', 'Где болит, как давно и что усиливает боль', 'Безопасность и ограничения', 'textarea'),
    field('shoulder_instability', 'Подвывих / нестабильность плеча по оценке специалиста', 'Безопасность и ограничения', 'select', choices=YES_NO),
    field('recent_injury', 'Недавняя травма, незажившая операция или повреждение кожи', 'Безопасность и ограничения', 'select', choices=YES_NO),
    field('cardiorespiratory_symptoms', 'Боль в груди, выраженная одышка, обмороки при нагрузке', 'Безопасность и ограничения', 'select', choices=YES_NO),
    field('new_neurological_symptoms', 'Новые или внезапно усилившиеся неврологические симптомы', 'Безопасность и ограничения', 'select', choices=YES_NO),
    field('fatigue', 'Утомляемость и переносимость занятий', 'Безопасность и ограничения', 'textarea'),
    field('falls', 'Падения, головокружение, устойчивость сидя и при перемещениях', 'Безопасность и ограничения', 'textarea'),
    field('implanted_device', 'Кардиостимулятор или другое имплантированное электронное устройство', 'Безопасность и ограничения', 'select', choices=YES_NO),
    field('assessment_source', 'Кто предоставил данные о функции руки', 'Очная оценка верхней конечности', 'select', choices=[['unknown','Не указано'],['patient','Пациент / близкий'],['clinician','Медицинский специалист']]),
    field('assessment_date', 'Дата очной оценки', 'Очная оценка верхней конечности', 'date'),
    field('strength', 'Сила мышц плеча, локтя, кисти; шкала и результаты', 'Очная оценка верхней конечности', 'textarea', hint='Например, MRC по мышечным группам; не выводится из углов видео.'),
    field('spasticity', 'Повышенный тонус / спастичность по очной оценке', 'Очная оценка верхней конечности', 'select', choices=YES_NO),
    field('tone_details', 'Тонус: мышцы, шкала, значения и дата', 'Очная оценка верхней конечности', 'textarea'),
    field('passive_rom', 'Пассивная амплитуда, контрактуры и болезненные ограничения', 'Очная оценка верхней конечности', 'textarea'),
    field('sensation', 'Чувствительность и ощущение положения конечности', 'Очная оценка верхней конечности', 'textarea'),
    field('hand_function', 'Захват, отпускание, мелкая моторика и применение кисти', 'Очная оценка верхней конечности', 'textarea'),
    field('wrist_extension', 'Активное разгибание запястья при очной оценке, °', 'Очная оценка верхней конечности', 'number', minimum=0, maximum=90),
    field('finger_extension', 'Активное разгибание пальцев при очной оценке, °', 'Очная оценка верхней конечности', 'number', minimum=0, maximum=90),
    field('vision_attention', 'Нарушения зрения / внимания / неглект', 'Очная оценка верхней конечности', 'select', choices=YES_NO),
    field('cognition_communication', 'Понимание инструкций, память, речь и настроение', 'Очная оценка верхней конечности', 'textarea'),
    field('functional_scales', 'Функциональные шкалы, результаты и даты', 'Очная оценка верхней конечности', 'textarea', hint='При наличии: Fugl-Meyer UE, ARAT, Barthel. Без самостоятельного вычисления по видео.'),
    field('daily_limitations', 'Какие повседневные действия затруднены', 'Цели и условия реабилитации', 'textarea', hint='Еда, одевание, гигиена, работа с предметами и другие конкретные задачи.'),
    field('goals', 'Приоритетные цели пациента', 'Цели и условия реабилитации', 'textarea', hint='Что человек хочет снова делать рукой; срок и критерий успеха обсудите со специалистом.'),
    field('current_rehabilitation', 'Текущая программа, упражнения и специалисты', 'Цели и условия реабилитации', 'textarea'),
    field('previous_treatment', 'Предыдущее лечение, эффект и нежелательные реакции', 'Цели и условия реабилитации', 'textarea'),
    field('support_environment', 'Помощь близких, условия дома, оборудование и доступность занятий', 'Цели и условия реабилитации', 'textarea'),
    field('video_context', 'Условия видео: задание, помощь, боль, усталость, положение тела', 'Цели и условия реабилитации', 'textarea'),
    field('information_source', 'Источник анамнеза и даты документов', 'Цели и условия реабилитации', 'textarea', hint='Пациент, близкий, выписка, заключение специалиста. Свободный текст сохраняется как сообщённая информация, без автоматической медицинской интерпретации.'),
]

definitions = {}
for item in FIELDS:
    if item['kind'] == 'select':
        definitions[item['key']] = (Literal[tuple(c[0] for c in item['choices'])], 'unknown')
    elif item['kind'] == 'number':
        typ = int if item['key'] == 'age' else float
        definitions[item['key']] = (typ | None, Field(default=None, ge=item['minimum'], le=item['maximum'], allow_inf_nan=False, strict=True))
    elif item['kind'] == 'date':
        definitions[item['key']] = (date | None, None)
    else:
        definitions[item['key']] = (str, Field(default='', max_length=3000 if item['kind'] == 'textarea' else 300))
PatientProfile = create_model('PatientProfile', __config__=ConfigDict(extra='forbid', str_strip_whitespace=True), **definitions)


def validate_profile(profile):
    parsed = PatientProfile.model_validate(profile)
    today = date.today()
    for key in ('onset_date', 'assessment_date'):
        value = getattr(parsed, key)
        if value and value > today:
            raise ValueError('Дата заболевания или оценки не может быть в будущем.')
    return parsed.model_dump(mode='json')


def personalized_section(report):
    """No parsing of free text into diagnoses, clearance, or contraindications."""
    p = validate_profile(report.get('patient_profile') or {})
    required = ['age', 'condition', 'diagnosis', 'diagnosis_confirmed', 'onset_date', 'medical_clearance',
                'medical_restrictions', 'pain_rest', 'pain_movement', 'shoulder_instability', 'recent_injury',
                'cardiorespiratory_symptoms', 'new_neurological_symptoms', 'assessment_source', 'assessment_date',
                'strength', 'spasticity', 'passive_rom', 'sensation', 'hand_function', 'vision_attention',
                'cognition_communication', 'daily_limitations', 'goals', 'current_rehabilitation', 'information_source']
    missing = [f['label'] for f in FIELDS if f['key'] in required and p[f['key']] in (None, '', 'unknown')]
    priorities = []
    for key, message in [
        ('new_neurological_symptoms', 'Сообщены новые неврологические симптомы: сначала нужна срочная медицинская оценка. При внезапных симптомах обращайтесь в экстренную службу.'),
        ('cardiorespiratory_symptoms', 'Сообщены симптомы при нагрузке: требуется медицинская оценка до выбора нагрузки. При текущей боли в груди, выраженной одышке или обмороке обращайтесь в экстренную службу.'),
        ('shoulder_instability', 'Указана нестабильность плеча: специалист должен определить допустимые движения и поддержку руки.'),
        ('recent_injury', 'Указана недавняя травма / операция / повреждение кожи: нужно уточнить ограничения восстановления.'),
    ]:
        if p[key] == 'yes': priorities.append(message)
    if any(p[k] is not None and p[k] > 0 for k in ('pain_rest', 'pain_movement')):
        priorities.append('Сообщена боль: необходимо выяснить причину и согласовать допустимые движения; видео не определяет причину боли.')
    if p['medical_restrictions']:
        priorities.append('Указанные ограничения врача должны быть проверены специалистом перед выбором методов; свободный текст не распознаётся как разрешение или запрет автоматически.')
    if p['spasticity'] == 'yes':
        priorities.append('Сообщено повышение тонуса: нужна очная оценка его влияния на функцию и пассивную амплитуду. Препараты и лечение спастичности по видео не подбираются.')
    urgent = p['new_neurological_symptoms'] == 'yes' or p['cardiorespiratory_symptoms'] == 'yes'
    eligible_population = (p['condition'] == 'stroke' and p['diagnosis_confirmed'] == 'yes'
                           and p['age'] is not None and p['age'] >= 18)
    measurements = []
    side = report.get('affected_side', 'unknown')
    for group in ('left_arm', 'right_arm', 'trunk'):
        if side in ('left','right') and group.endswith('_arm') and group != f'{side}_arm': continue
        for key, m in report.get('metrics', {}).get(group, {}).items():
            if reliable(m): measurements.append({'metric': f'{group}.{key}', 'value': m['value'], 'unit': m['unit'], 'technical_reliability': m['technical_reliability']})
    options = []
    if eligible_population and not urgent:
        for option in report.get('rehabilitation_options', []):
            links = [x for x in option['feature_links'] if side not in ('left','right') or not x['metric'].startswith(('left_arm.','right_arm.')) or x['metric'].startswith(f'{side}_arm.')]
            if not links:
                continue
            checks = [option['clinician_checks']]
            status = 'requires_assessment'
            if p['medical_clearance'] != 'yes' or priorities:
                checks.append('Сначала уточнить боль, ограничения и допуск к нагрузке из анкеты.')
            if option['id'] == 'cimt':
                clinician_values = p['assessment_source'] == 'clinician' and bool(p['assessment_date'])
                values = [p['wrist_extension'], p['finger_extension']]
                if clinician_values and all(v is not None for v in values):
                    if values[0] < 20 or values[1] < 10:
                        status = 'criteria_not_met'
                        checks.append('Сообщённые очные углы ниже критериев 20° запястья / 10° пальцев; CIMT не предлагается как подходящий метод.')
                    else:
                        checks.append('Сообщённые углы достигают критериев, но переносимость, риск падений и другие условия ещё требуют очной оценки. Это не разрешение ограничивать другую руку.')
                else:
                    checks.append('Для оценки критериев нужны углы запястья и пальцев, измеренные специалистом, и дата оценки; видео MVP их не измеряет.')
            if option['id'] == 'electrical' and p['implanted_device'] != 'no':
                checks.append('Нужно проверить имплантированные устройства и безопасность конкретного аппарата; электростимуляция автоматически не разрешается.')
            if option['id'] == 'mirror' and p['vision_attention'] != 'no':
                checks.append('Нужно уточнить зрение, внимание и способность выполнять задание.')
            options.append({'id': option['id'], 'option': option['option'], 'status': status,
                            'patient_basis': {'goals': p['goals'], 'daily_limitations': p['daily_limitations'],
                                              'affected_side': side, 'task': report.get('task', 'unspecified')},
                            'feature_links': links,
                            'checks': checks, 'evidence': option['evidence'], 'requires_clinician_review': True})
    return {'scope': 'upper_body', 'rule_version': '1.0', 'status': 'urgent_assessment' if urgent else 'requires_clinician_review',
            'population_note': 'Каталог методов относится к взрослым после подтверждённого инсульта. Для другого диагноза, неизвестного возраста или ребёнка автоматический подбор по этому каталогу не выполняется.' if not eligible_population else 'Диагноз, возраст и история указаны в анкете; приложение не подтверждает их независимо.',
            'missing_information': missing, 'priorities': priorities, 'measurements': measurements,
            'goals': p['goals'], 'options': options, 'requires_clinician_review': True,
            'note': 'Персонализированный контекст связывает сообщённую историю и цели с измерениями и литературой. Он не устанавливает диагноз и не назначает лечение, препараты, дозы или нагрузку. Пустое поле означает неизвестность, а не отсутствие проблемы.'}
