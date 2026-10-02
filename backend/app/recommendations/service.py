"""Reviewed topic-to-literature rules. Their selection is not treatment eligibility."""
RULES = [
    {'id':'task_practice','topic':'task_practice','category':'therapeutic_exercise',
     'option':'Контролируемое достижение цели и повторение функциональных задач',
     'statement':'Повторение функциональных задач рассматривается в рекомендациях; обзор сообщает небольшие улучшения функции руки при низком качестве доказательств.',
     'evidence':['nice_ng236','cochrane_rtt_2016'],
     'evidence_strength':'Клиническая рекомендация; низкое качество доказательств для функции руки/кисти в Cochrane.',
     'eligibility':'Специалист должен проверить доступное активное движение, боль, утомление, цель задания и потребность в помощи. Видео не оценивает силу и переносимость.'},
    {'id':'trunk_control','topic':'trunk_control','category':'therapeutic_exercise',
     'option':'Оценка и тренировка контроля туловища в функциональной задаче',
     'statement':'Обзор тренировок туловища показывает возможные улучшения с низкой или очень низкой уверенностью для многих исходов. Наклон на видео сам по себе не доказывает патологическую компенсацию.',
     'evidence':['cochrane_trunk_2023'],
     'evidence_strength':'Систематический обзор; очень низкая–низкая уверенность для многих исходов, зависит от сравнения.',
     'eligibility':'Нужно оценить баланс и роль туловища в конкретной задаче. Ограничение или фиксация туловища автоматически не предлагаются.'},
    {'id':'bilateral','topic':'bilateral_training','category':'therapeutic_exercise',
     'option':'Обсуждение одно- или двусторонней практики',
     'statement':'Рекомендации допускают оба подхода в зависимости от задачи. Старый обзор указывает на возможное преимущество одностороннего подхода; универсальный выбор не установлен.',
     'evidence':['uk_stroke_2023','cochrane_overview_2014'],
     'evidence_strength':'Клинические рекомендации и обзор 2014 года; сравнительные данные неоднозначны и требуют актуализации.',
     'eligibility':'Нужно подтвердить сопоставимость заданий и оценить функцию обеих рук; индекс асимметрии не выбирает метод лечения.'},
    {'id':'mirror','topic':'mirror_therapy','category':'physiotherapy',
     'option':'Зеркальная терапия как возможное дополнение к программе',
     'statement':'Зеркальная терапия рассматривается как дополнение к реабилитации. Эффект зависит от сравниваемого вмешательства.',
     'evidence':['nice_ng236','cochrane_mirror_2018'],
     'evidence_strength':'Умеренное качество для двигательной функции в Cochrane; условная клиническая рекомендация.',
     'eligibility':'Нужно оценить зрение, внимание, когнитивные возможности, этап восстановления и цели. Видео не подтверждает пригодность метода.'},
    {'id':'electrical','topic':'electrical_stimulation','category':'physiotherapy',
     'option':'Обсуждение показаний к электростимуляции со специалистом',
     'statement':'NICE не рекомендует рутинную электростимуляцию руки; пробное применение возможно при определённых условиях и под контролем специалиста.',
     'evidence':['nice_ng236'],
     'evidence_strength':'Условная клиническая рекомендация NICE 1.13.14–17; не универсальный метод.',
     'eligibility':'Требуются проверка сокращения мышц, движения против сопротивления и оценка безопасности устройства. Эти параметры по pose estimation не определяются.'},
    {'id':'ot','topic':'occupational_therapy','category':'occupational_therapy',
     'option':'Функциональные reach-задачи, бытовые действия и адаптация среды',
     'statement':'Эрготерапия с фокусом на повседневных действиях может улучшать ADL; качество доказательств в обзоре низкое.',
     'evidence':['cochrane_ot_2017'],
     'evidence_strength':'Систематический обзор; низкое качество доказательств.',
     'eligibility':'Эрготерапевт оценивает захват, перемещение предметов, одевание и другие цели ADL, затем выбирает задачу и адаптацию. Кисть и пальцы в MVP не измеряются.'},
    {'id':'cimt','topic':'cimt','category':'therapeutic_exercise',
     'option':'CIMT — только вопрос для очной оценки пригодности',
     'statement':'Рекомендации связывают рассмотрение CIMT с активным разгибанием запястья не менее 20° и пальцев не менее 10°. Эти критерии в MVP не измеряются.',
     'evidence':['uk_stroke_2023'],
     'evidence_strength':'Клиническая рекомендация с критериями отбора; индивидуальная пригодность не определена.',
     'eligibility':'Нужна очная оценка кисти, пальцев и переносимости. Нельзя самостоятельно ограничивать другую руку на основании этого отчёта.'},
]


def grounded_sections(bundle):
    approved = {s['id']:s for s in bundle['sources'] if s['verified'] and s['verification_scope']=='reviewed_content' and s.get('publication_status')=='published'}
    contexts, options = [], []
    for rule in RULES:
        if rule['topic'] not in bundle['topics'] or not all(key in approved for key in rule['evidence']):
            continue
        links = [link for link in bundle['feature_links'] if (link['metric'].startswith('trunk.') if rule['topic']=='trunk_control' else not link['metric'].startswith('trunk.'))]
        if not links: continue
        citations = [approved[key] for key in rule['evidence']]
        reason = 'Измерены: ' + ', '.join(link['metric'] for link in links) + '. Это основание для тематического поиска, а не доказательство показаний.'
        contexts.append({'id':rule['id'],'level':'literature_context','statement':rule['statement'],
                         'reason':reason,'feature_links':links,'evidence':citations,
                         'confidence':'Индивидуальная клиническая применимость не определена.',
                         'evidence_strength':rule['evidence_strength'],'requires_clinician_review':True})
        options.append({'id':rule['id'],'category':rule['category'],'option':rule['option'],
                        'reason':reason,'feature_links':links,'evidence':citations,'evidence_strength':rule['evidence_strength'],
                        'clinician_checks':rule['eligibility'],'applicability':'not_assessed',
                        'requires_clinician_review':True,
                        'disclaimer':'Не является индивидуальным назначением. Необходима оценка лечащего врача/реабилитолога.'})
    disagreements = []
    if 'bilateral_training' in bundle['topics'] and {'uk_stroke_2023','cochrane_overview_2014'} <= approved.keys():
        disagreements.append({'topic':'Односторонняя и двусторонняя практика',
                              'statement':'Старый обзор допускает преимущество односторонней тренировки; рекомендации 2023 года допускают оба подхода. Популяции, задачи и даты различаются; универсальное преимущество не устанавливается.',
                              'evidence':[approved['uk_stroke_2023'],approved['cochrane_overview_2014']]})
    if 'upper_limb' in bundle['topics'] and {'nice_ng236','uk_stroke_2023'} <= approved.keys():
        disagreements.append({'topic':'Роботизированная тренировка руки — различия рекомендаций',
                              'statement':'NICE 1.13.18 не рекомендует её в программе верхней конечности; UK/Ireland 4.18 I допускает дополнение, предпочтительно в исследовании. Автоматический выбор не выполняется.',
                              'evidence':[approved['nice_ng236'],approved['uk_stroke_2023']]})
    return contexts, options, disagreements
