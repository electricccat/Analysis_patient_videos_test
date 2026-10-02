import math
from ..evidence.enrich import enrich_report

LIMITATIONS = [
    'Измеряются проекции на плоскость изображения, а не клинический трёхмерный ROM. Клиническая валидность этих показателей не установлена.',
    'Подъём плеча приближённо оценивается относительно линии плечо–таз. Сгибание и отведение не разделяются.',
    'Движение плечевого пояса — смещение точки плеча относительно таза; движение лопатки отдельно не определяется.',
    'Поворот корпуса, движения вне плоскости и движение камеры не удалось надёжно определить по этому видео.',
    'Положение головы — координаты носа относительно плеч; ориентация головы не определяется.',
    'Асимметрия всего видео сопоставима только для одинакового задания обеими руками. Поражённая сторона указана пользователем.',
    'Вариабельность скорости — описательный показатель, не валидированная оценка плавности. Число остановок не определяется надёжно в MVP.',
    'Фазы отмечаются эвристически для одного доминирующего подъёма. Повторные циклы и произвольные задания требуют проверки.',
    'Низкоуверенные и отсутствующие точки исключены; пропуски не заполняются. Экстремумы могут быть занижены при пропусках.',
    'Модель не валидирована для пациентов после инсульта. Видео не позволяет оценить боль, подвывих, спастичность, чувствительность или противопоказания.'
]


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def build_report(analysis, metadata):
    observations = []
    for side, label in [('left', 'Левой'), ('right', 'Правой')]:
        arm = analysis['metrics'][f'{side}_arm']
        maximum = arm['shoulder_max']
        if maximum['value'] is not None:
            observations.append({'level': 'measurement', 'statement': f'{label} рукой достигнут максимальный проекционный угол подъёма {maximum["value"]:.1f}°.',
                                 'metric': f'{side}_arm.shoulder_max', 'technical_reliability': maximum['technical_reliability']})
        minimum, maximum = arm['elbow_min'], arm['elbow_max']
        if minimum['value'] is not None and maximum['value'] is not None:
            observations.append({'level': 'measurement', 'statement': f'Угол {"левого" if side == "left" else "правого"} локтя изменялся от {minimum["value"]:.1f}° до {maximum["value"]:.1f}°.',
                                 'metric': f'{side}_arm.elbow_rom', 'technical_reliability': minimum['technical_reliability']})
    trunk = analysis['metrics']['trunk']['max_lateral_tilt_change']
    if trunk['value'] is not None:
        observations.append({'level': 'measurement', 'statement': f'Максимальное изменение бокового наклона корпуса относительно первых 0,5 с составило {trunk["value"]:.1f}°.',
                             'metric': 'trunk.max_lateral_tilt_change', 'technical_reliability': trunk['technical_reliability']})
    comparison = analysis['asymmetry']['shoulder_rom']
    if comparison['index_percent'] is not None:
        observations.append({'level': 'algorithmic_observation', 'statement': f'ROM проекционного угла плеча: слева {comparison["left"]:.1f}°, справа {comparison["right"]:.1f}°. Симметричный индекс различия {comparison["index_percent"]:.1f}%. Это не оценка тяжести нарушения.',
                             'metric': 'asymmetry.shoulder_rom', 'technical_reliability': 'medium'})
    return enrich_report(clean({**analysis, **metadata, 'schema_version': '1.0', 'observations': observations,
                  'limitations': LIMITATIONS, 'clinical_context': [], 'rehabilitation_options': [],
                  'evidence_status': 'not_enabled_in_measurement_mvp',
                  'safety': 'Индивидуальный план требует оценки специалистом. Видео не оценивает боль, сердечно-сосудистое состояние, нестабильность сустава, подвывих плеча, спастичность, чувствительность, когнитивные нарушения, головокружение, риск падения, сопутствующие заболевания и противопоказания.'}))
