import { useEffect, useState } from 'react';
import { api } from './api';
import type { PatientProfile, Report } from './types';
import PatientForm from './PatientForm';

const units:Record<string,string>={deg:'°','deg/s':'°/с',shoulder_width:'ШП','shoulder_width/s':'ШП/с',s:'с',ratio:''};
const names:Record<string,string>={shoulder_max:'Максимальный подъём плеча',shoulder_rom:'ROM плеча',elbow_min:'Минимальный угол локтя',elbow_max:'Максимальный угол локтя',elbow_rom:'ROM локтя',wrist_mean_speed:'Средняя скорость кисти',wrist_peak_speed:'Пиковая скорость кисти',wrist_path_length:'Длина траектории кисти',wrist_max_height:'Высота кисти',time_to_max:'Время максимума',max_lateral_tilt_change:'Изменение наклона корпуса'};
export default function PatientPanel({report,onUpdate}:{report:Report;onUpdate:(r:Report)=>void}) {
 const [profile,setProfile]=useState<PatientProfile>(report.patient_profile??{}),[busy,setBusy]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState(false);
 useEffect(()=>{const controller=new AbortController();api<PatientProfile>(`/api/studies/${report.study_id}/patient`,{signal:controller.signal}).then(setProfile).catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();},[report.study_id]);
 const save=async()=>{setBusy(true);setError('');setSaved(false);try{const result=await api<{patient_profile:PatientProfile;report:Report|null}>(`/api/studies/${report.study_id}/patient`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(profile)});setProfile(result.patient_profile);if(result.report)onUpdate(result.report);setSaved(true);}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
 const section=report.personalized;
 return <section className="card patient-panel"><div className="panel-heading"><h2>Пациент и персонализированный разбор</h2><span className="tag">Верхняя часть тела</span></div>
 <details className="patient-editor"><summary>История болезни и анкета пациента · заполнить / изменить</summary><form onSubmit={e=>{e.preventDefault();void save();}}><PatientForm value={profile} onChange={v=>{setProfile(v);setSaved(false);}} disabled={busy}/><button className="primary" disabled={busy} type="submit">{busy?'Сохранение…':'Сохранить анкету и обновить разбор'}</button><p className="caption">Повторная обработка видео не требуется. Разбор использует последнюю сохранённую анкету.</p></form></details>
 {error&&<p role="alert" className="error">{error}</p>}{saved&&<p role="status">Анкета сохранена, персонализированный раздел обновлён.</p>}
 {!section?<p>Добавьте или сохраните анкету, чтобы сформировать персонализированный раздел для этого исследования.</p>:<>
 <p className="patient-intro">{section.note}</p><p className="population-note">{section.population_note}</p>
 {!!section.priorities.length&&<div className="patient-priorities" role="alert"><h3>{section.status==='urgent_assessment'?'Сначала медицинская оценка':'Что проверить перед выбором методов'}</h3><ul>{section.priorities.map(x=><li key={x}>{x}</li>)}</ul></div>}
 <div className="patient-goals"><h3>Цели пациента</h3><p>{section.goals||'Цели пока не указаны.'}</p></div>
 <details className="patient-missing" open={section.missing_information.length>0}><summary>Недостающие сведения · {section.missing_information.length}</summary>{section.missing_information.length?<ul>{section.missing_information.map(x=><li key={x}>{x}</li>)}</ul>:<p>Основные поля заполнены. Полнота анкеты не подтверждает безопасность или пригодность лечения.</p>}</details>
 <details><summary>Измерения видео, связанные с этим пациентом · {section.measurements.length}</summary><div className="table-scroll"><table><thead><tr><th>Показатель</th><th>Сторона</th><th>Значение</th></tr></thead><tbody>{section.measurements.map(m=>{const [group,key]=m.metric.split('.');return <tr key={m.metric}><td>{names[key]??key}</td><td>{group==='left_arm'?'Левая':group==='right_arm'?'Правая':'Корпус'}</td><td>{m.value.toFixed(2)} {units[m.unit]??m.unit}</td></tr>;})}</tbody></table></div>{!section.measurements.length&&<p>Нет надёжных измерений; отсутствие результата не означает отсутствие нарушения.</p>}</details>
 <h3 className="patient-methods-title">Методы для обсуждения с лечащим специалистом</h3>
 {!section.options.length&&<p>Подбор пока не сформирован: уточните диагноз и возраст, качество измерений и доступность источников; при новых симптомах сначала нужна медицинская оценка.</p>}
 {section.options.map(o=><article className="rehab-option" key={o.id}><h4>{o.option}</h4><span className="tag">{o.status==='criteria_not_met'?'Сообщённые критерии не выполнены':'Пригодность требует очной оценки'}</span><p className="patient-method-basis">Цель: {o.patient_basis.goals||'не указана'}. Бытовые трудности: {o.patient_basis.daily_limitations||'не указаны'}.</p><p className="caption">Связанные показатели: {o.feature_links.map(m=>m.metric).join(', ')||'сопоставить с задачей при очной оценке'}. Видео не подтверждает показания к методу.</p><ul>{o.checks.map(x=><li key={x}>{x}</li>)}</ul><div className="evidence-citations">{o.evidence.map(s=><a key={s.id} href={s.url} target="_blank" rel="noreferrer">{s.title} · {s.year}</a>)}</div></article>)}
 </>}
 </section>;
}
