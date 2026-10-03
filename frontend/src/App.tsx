import { useEffect, useState } from 'react';
import { Activity, ArrowUpRight, Upload, ShieldCheck, ChevronRight, Download, Trash2, CircleHelp, FileVideo, CheckCircle2, LoaderCircle } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from 'recharts';
import { api } from './api';
import type { Study, Report, Frame, PatientProfile } from './types';
import Player from './Player';
import EvidencePanel from './EvidencePanel';
import PatientForm from './PatientForm';
import PatientPanel from './PatientPanel';

const tasks = { unspecified: 'Не указано', forward_raise: 'Поднять руки вперёд', side_raise: 'Поднять руки в стороны', overhead: 'Поднять руку над головой', elbow: 'Сгибание / разгибание локтя', reach: 'Дотянуться до предмета', hand_to_mouth: 'Рука ко рту', opposite_shoulder: 'Рука к противоположному плечу', free: 'Произвольное движение' };
const names: Record<string,string> = { shoulder_max: 'Максимальный подъём плеча', shoulder_rom: 'ROM плеча (проекция)', shoulder_peak_angular_speed: 'Пиковая угловая скорость плеча', elbow_min: 'Минимальный угол локтя', elbow_max: 'Максимальный угол локтя', elbow_rom: 'ROM локтя', elbow_peak_angular_speed: 'Пиковая угловая скорость локтя', wrist_mean_speed: 'Средняя скорость кисти', wrist_peak_speed: 'Пиковая скорость кисти', wrist_max_height: 'Максимальная высота кисти над плечом', shoulder_girdle_rise: 'Подъём плечевого пояса', speed_variability_cv: 'Вариабельность скорости (CV)', wrist_path_length: 'Длина видимой траектории кисти', time_to_max: 'Время максимума от начала видео', elbow_at_shoulder_max: 'Угол локтя при максимальном подъёме', reach_duration: 'Длительность подъёма (оценка)', max_lateral_tilt_change: 'Изменение бокового наклона', shoulder_line_rom: 'Диапазон наклона линии плеч', head_lateral_range: 'Боковой диапазон положения носа' };
const reliability: Record<string,string> = { high: 'Высокая', medium: 'Средняя', low: 'Низкая' };
const units: Record<string,string> = { deg: '°', 'deg/s': '°/с', s: 'с', shoulder_width: 'ШП', 'shoulder_width/s': 'ШП/с', ratio: '' };
const format = (v: number | null | undefined, unit = '') => v == null ? 'Не определено' : `${v.toFixed(unit === 'deg' ? 1 : 2)} ${units[unit] ?? unit}`;

export default function App() {
 const [studies,setStudies] = useState<Study[]>([]), [selected,setSelected] = useState<Study|null>(null);
 const [file,setFile] = useState<File|null>(null), [localUrl,setLocalUrl] = useState('');
 const [side,setSide] = useState('unknown'), [task,setTask] = useState('unspecified');
 const [patientProfile,setPatientProfile] = useState<PatientProfile>({});
 const [report,setReport] = useState<Report|null>(null), [frames,setFrames] = useState<Frame[]>([]);
 const [time,setTime] = useState(0), [error,setError] = useState(''), [busy,setBusy] = useState(false), [modelReady,setModelReady] = useState<boolean|null>(null);
 const [tab,setTab] = useState<'analysis'|'report'>('analysis'), [chart,setChart] = useState('shoulder_angle');
 const [deletePrompt,setDeletePrompt] = useState(false);
 const refresh = () => api<Study[]>('/api/studies').then(setStudies).catch(e=>setError(e.message));
 useEffect(()=>{ refresh(); api<{model_ready:boolean}>('/api/health').then(x=>setModelReady(x.model_ready)).catch(()=>setError('Сервер недоступен. Запустите FastAPI на порту 8000.')); },[]);
 useEffect(()=>{
   if (!file) { setLocalUrl(''); return; }
   const url = URL.createObjectURL(file); setLocalUrl(url); return ()=>URL.revokeObjectURL(url);
 },[file]);
 useEffect(()=>{
   if (!selected) return;
   let cancelled = false, timer: ReturnType<typeof setTimeout>;
   const poll = async () => {
     try {
       const current = await api<Study>(`/api/studies/${selected.study_id}`);
       if (cancelled) return;
       setSelected(current);
       if (current.status === 'completed') {
         const [r,l] = await Promise.all([api<Report>(`/api/studies/${current.study_id}/report`),api<{frames:Frame[]}>(`/api/studies/${current.study_id}/files/landmarks`)]);
         if (!cancelled) { setReport(r); setFrames(l.frames); refresh(); }
       } else if (current.status === 'failed') { setError(current.error || 'Не удалось обработать видео.'); refresh(); }
       else timer = setTimeout(poll, 1000);
     } catch (e) { if (!cancelled) setError((e as Error).message); }
   };
   poll(); return ()=>{ cancelled = true; clearTimeout(timer); };
 },[selected?.study_id]);
 const choose = (study: Study|null) => { if (study && study.study_id === selected?.study_id) return; setSelected(study); setReport(null); setFrames([]); setTime(0); setError(''); setDeletePrompt(false); };
 const upload = async () => {
   if (!file) return;
   setBusy(true); setError('');
   try {
     const data = new FormData(); data.append('file',file); data.append('affected_side',side); data.append('task',task);
     data.append('patient_profile',JSON.stringify(patientProfile));
     const study = await api<Study>('/api/studies',{method:'POST',body:data}); choose(study); setFile(null); setPatientProfile({}); refresh();
   } catch(e) { setError((e as Error).message); } finally {setBusy(false);}
 };
 const remove = async () => {
   if (!selected) return;
   try { await api(`/api/studies/${selected.study_id}`,{method:'DELETE'}); choose(null); refresh(); }
   catch(e) {setError((e as Error).message);}
 };
 const pending = selected && ['queued','processing'].includes(selected.status);
 const chartOptions: Record<string,{label:string;unit:string;keys:string[]}> = {
   shoulder_angle: {label:'Угол плеча',unit:'°',keys:['left_shoulder_angle','right_shoulder_angle']},
   elbow_angle: {label:'Угол локтя',unit:'°',keys:['left_elbow_angle','right_elbow_angle']},
   wrist_speed: {label:'Скорость кисти',unit:'ШП/с',keys:['left_wrist_speed','right_wrist_speed']},
   wrist_y: {label:'Положение кисти по вертикали',unit:'ШП · вниз +',keys:['left_wrist_y','right_wrist_y']},
   wrist_x: {label:'Положение кисти по горизонтали',unit:'ШП',keys:['left_wrist_x','right_wrist_x']},
   trunk_tilt: {label:'Изменение наклона корпуса',unit:'°',keys:['trunk_tilt']},
 };
 return <div className="app-shell">
   <aside className="sidebar"><a className="brand" href="/" aria-label="Кинема — главная"><Activity size={28}/><span>кинема<span className="brand-dot">.</span></span></a><div className="brand-sub">ЛАБОРАТОРИЯ ДВИЖЕНИЯ</div>
     <div className="nav-label">РАБОЧЕЕ ПРОСТРАНСТВО</div><button className={`nav-item ${!selected?'active':''}`} onClick={()=>choose(null)}><Upload size={18}/> Новое исследование <span>＋</span></button>
     <div className="nav-label study-label">ИССЛЕДОВАНИЯ <span>{studies.length.toString().padStart(2,'0')}</span></div>
     <div className="study-list">{studies.length === 0 && <p className="empty-side">Загруженные видео появятся здесь</p>}{studies.map((s,i)=><button className={`study-item ${selected?.study_id===s.study_id?'chosen':''}`} key={s.study_id} onClick={()=>choose(s)}><FileVideo size={17}/><div><strong>{s.title||`Исследование ${studies.length-i}`}</strong><small>{new Date(s.created_at).toLocaleDateString('ru-RU')} · {s.status==='completed'?'Готово':s.status==='failed'?'Ошибка':'В работе'}</small></div><ChevronRight size={14}/></button>)}</div>
     <div className="local-note"><ShieldCheck size={21}/><strong>Видео остаётся у вас</strong><p>Обработка на локальном сервере. Без отправки во внешние AI API.</p><span className="tag dark">MVP · v0.1</span></div>
   </aside>
   <main><header className="topbar"><span>Верхняя конечность <ChevronRight size={14}/> {selected?'Результаты исследования':'Новое исследование'}</span><span className="prototype"><span/> ИССЛЕДОВАТЕЛЬСКИЙ ПРОТОТИП</span></header>
   <div className="content"><div className="page-heading"><div><div className="eyebrow">ОБЪЕКТИВНОЕ ИЗМЕРЕНИЕ ДВИЖЕНИЯ</div><h1>{report?'От движения — к данным.':'Каждое движение имеет значение.'}</h1><p>{report?'Исследуйте траектории, суставные углы и различия между сторонами.':'Загрузите видео, чтобы увидеть движение верхних конечностей во времени.'}</p></div><div className="heading-icon"><Activity size={38}/></div></div>
   {error && <div role="alert" className="error">{error}</div>}
   {(selected?.is_demo||report?.is_demo) && <div className="demo-notice" role="note"><strong>Демонстрационный пример · вымышленный пациент</strong><p>Анкета и очные результаты придуманы. Видео — схематическая анимация, метрики рассчитаны по заданным координатам без распознавания MediaPipe. Этот пример показывает работу интерфейса и правил подбора; он не подтверждает клиническую точность программы.</p></div>}
   {!selected && <>
     <div className="workflow"><span className="current"><b>01</b> Загрузка видео</span><ChevronRight size={16}/><span><b>02</b> Анализ движения</span><ChevronRight size={16}/><span><b>03</b> Результаты</span></div>
     <div className="upload-grid"><section className="card upload-card"><div className="panel-heading"><h2>Видео пациента</h2><span className="tag">Локальная обработка</span></div>
       <label className={`dropzone ${file?'has-file':''}`} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();setFile(e.dataTransfer.files[0]||null);}}><input type="file" accept=".mp4,.mov,.webm" onChange={e=>setFile(e.target.files?.[0]||null)}/><div className="upload-symbol"><Upload size={28}/></div><strong>{file?file.name:'Перетащите видео сюда'}</strong><span>{file?`${(file.size/1024/1024).toFixed(1)} МБ · нажмите для замены`:'или нажмите, чтобы выбрать файл'}</span><small>MP4, MOV, WebM · до 300 МБ · до 3 минут</small></label>
       {localUrl && <video className="source-preview" src={localUrl} controls/>}
       {file && <p className="caption">Если браузер не воспроизводит MOV, после анализа будет доступна MP4-копия.</p>}
       <div className="upload-bottom"><ShieldCheck size={16}/><span>Видео не используется для обучения моделей.</span></div>
     </section><section className="card setup-card"><div className="panel-heading"><h2>Параметры исследования</h2><span className="step-number">01 / 03</span></div><label className="field-label">Поражённая сторона <CircleHelp size={14}/></label><div className="segmented">{[['left','Левая'],['right','Правая'],['unknown','Неизвестно']].map(([value,label])=><button key={value} className={side===value?'selected':''} onClick={()=>setSide(value)}>{label}</button>)}</div><p className="caption">Анатомическая сторона пациента, независимо от положения на экране.</p><label className="field-label" htmlFor="task">Задание <span>Необязательно</span></label><select id="task" value={task} onChange={e=>setTask(e.target.value)}>{Object.entries(tasks).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><p className="caption">Движение можно анализировать и без выбора упражнения.</p><div className="setup-note"><Activity size={19}/><p>Плечи, локти, запястья, положение головы и корпуса — в одном исследовании.</p></div><p className="caption">Ниже можно заполнить историю болезни и цели пациента, затем начать анализ видео.</p>{modelReady===false && <p className="error">Установите модель: python scripts/download_model.py</p>}</section></div>
     <section className="card"><div className="panel-heading"><h2>Анкета пациента и история болезни</h2><span className="tag">Связана с этим видео</span></div><PatientForm value={patientProfile} onChange={setPatientProfile} disabled={busy}/><button className="primary analyze-button" disabled={!file||busy||modelReady!==true} onClick={upload}>{busy?<LoaderCircle className="spin" size={18}/>:<Activity size={18}/>} {busy?'Загрузка…':'Начать анализ'}<ArrowUpRight size={18}/></button></section>
     <section className="guide-grid">{[['01','Подготовьте кадр','Один человек, неподвижная камера, плечи и таз видны. Кисти остаются в кадре.'],['02','Сохраните детали','Достаточное освещение и контрастная одежда помогут отслеживать суставы.'],['03','Оцените измерения','Проверьте скелет и качество распознавания перед интерпретацией результатов.']].map(([n,title,text])=><div key={n}><span>{n}</span><h3>{title}</h3><p>{text}</p></div>)}</section>
   </>}
   {pending && <section className="card progress-card"><LoaderCircle className="spin" size={36}/><h2>Извлекаем движение из видео</h2><p>Распознавание позы → нормализация → расчёт метрик → отчёт</p><progress max="1" value={selected.progress??undefined}/><span>{selected.processed_frames??0} кадров обработано · {selected.progress===null?'длительность уточняется':`${Math.round((selected.progress??0)*100)}%`}</span></section>}
   {selected && !pending && !report && selected.status==='completed' && <p>Загрузка результатов…</p>}
   {selected && !pending && <div className="result-actions"><div className="tabs"><button className={tab==='analysis'?'active':''} onClick={()=>setTab('analysis')}>Анализ движения</button><button className={tab==='report'?'active':''} onClick={()=>setTab('report')}>Объективный отчёт</button></div><div className="actions">{report && <a className="secondary" href={`/api/studies/${selected.study_id}/files/report`} download><Download size={15}/> JSON отчёт</a>}<button className="delete" onClick={()=>setDeletePrompt(true)}><Trash2 size={16}/> Удалить</button></div></div>}
   {deletePrompt && <div className="delete-confirm" role="alert"><p>Удалить исследование полностью? Исходное видео, копия, landmarks, метрики, анкета пациента и отчёт будут удалены.</p><button className="delete" onClick={remove}>Удалить все данные</button><button className="secondary" onClick={()=>setDeletePrompt(false)}>Отмена</button></div>}
   {report && <>
     <div className="quality-bar"><ShieldCheck size={19}/><strong>Техническая надёжность: {reliability[report.pose_quality.level].toLowerCase()}</strong><span>{report.video_quality.decoded_frames} кадров</span><span>{report.video_quality.decoded_duration_seconds.toFixed(1)} с</span><span>Порог confidence ≥ {report.pose_quality.threshold}</span></div>
     {tab==='analysis' ? <>
       <div className="metric-cards">{[['left_arm','shoulder_max','Левое плечо'],['right_arm','shoulder_max','Правое плечо'],['left_arm','elbow_rom','ROM левого локтя'],['trunk','max_lateral_tilt_change','Изменение наклона корпуса']].map(([group,key,label])=>{const m=report.metrics[group][key];return <div className="card metric-card" key={label}><span>{label}</span><strong>{format(m.value,m.unit)}</strong><small>Надёжность: {reliability[m.technical_reliability]} · {Math.round(m.coverage*100)}% кадров</small></div>;})}</div>
       <div className="analysis-grid"><section className="card player-card"><Player report={report} frames={frames} time={time} setTime={setTime}/></section><section className="card chart-card"><div className="panel-heading"><h3>Движение во времени</h3><span className="tag">2D</span></div><select aria-label="Показатель графика" value={chart} onChange={e=>setChart(e.target.value)}>{Object.entries(chartOptions).map(([key,o])=><option key={key} value={key}>{o.label}</option>)}</select><div className="chart-legend"><span><i className="left-color"/> Левая</span><span><i className="right-color"/> Правая</span><small>{chartOptions[chart].unit}</small></div><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><LineChart data={report.series} onClick={(state)=>{const label=state?.activeLabel;if(label!=null && Number.isFinite(Number(label)))setTime(Number(label));}}><CartesianGrid stroke="#e8eeea" strokeDasharray="3 3"/><XAxis dataKey="timestamp" type="number" domain={['dataMin','dataMax']} tickFormatter={x=>Number(x).toFixed(1)} unit=" с" tick={{fontSize:11}}/><YAxis tick={{fontSize:11}} width={42}/><Tooltip labelFormatter={x=>`${Number(x).toFixed(2)} с`} formatter={(v)=>typeof v==='number'?v.toFixed(2):'Нет данных'}/><ReferenceLine x={time} stroke="#304d43" strokeDasharray="4 3"/>{chartOptions[chart].keys.map((key,i)=><Line key={key} dataKey={key} name={chart==='trunk_tilt'?'Корпус':i===0?'Левая':'Правая'} stroke={i===0?'#299e80':'#db9654'} dot={false} strokeWidth={2} isAnimationActive={false} connectNulls={false}/>)}</LineChart></ResponsiveContainer></div><p className="caption">Нажмите на график, чтобы перейти к моменту видео. Разрывы означают отсутствие надёжных данных. ШП — исходная медианная ширина плеч.</p><div className="context-note"><CircleHelp size={17}/><p>Углы — проекции в плоскости камеры. Они не заменяют клиническую оценку амплитуды.</p></div></section></div>
       <section className="card"><div className="panel-heading"><h3>Сравнение сторон</h3><span className="caption">Индекс = 200 × |Л − П| / (|Л| + |П|)</span></div><div className="table-scroll"><table><thead><tr><th>Показатель</th><th>Левая</th><th>Правая</th><th>Индекс различия</th></tr></thead><tbody>{Object.entries(report.asymmetry).map(([key,m])=><tr key={key}><td>{names[key]}</td><td>{format(m.left,m.unit)}</td><td>{format(m.right,m.unit)}</td><td>{m.index_percent==null?'Не определён':`${m.index_percent.toFixed(1)}%`}</td></tr>)}</tbody></table></div><p className="caption">Сравнивайте стороны только при сопоставимых заданиях. Индекс не характеризует тяжесть заболевания.</p></section>
     </> : <><section className="card"><div className="panel-heading"><h2>Непосредственно измеренные данные</h2><CheckCircle2 size={21}/></div>{report.observations.filter(o=>o.level==='measurement').map((o,i)=><p className="observation" key={i}>{o.statement}<small>Техническая надёжность: {reliability[o.technical_reliability]}</small></p>)}{!report.observations.length && <p>Данный показатель не удалось надёжно определить по этому видео.</p>}</section><section className="card"><h3>Алгоритмически обнаруженные особенности</h3>{report.observations.filter(o=>o.level==='algorithmic_observation').map((o,i)=><p key={i}>{o.statement}</p>)}<p className="caption">Обнаруженные различия не означают диагноз или патологию.</p></section><section className="card"><h3>Все рассчитанные метрики</h3><div className="table-scroll"><table><thead><tr><th>Показатель</th><th>Сторона</th><th>Значение</th><th>Кадры</th><th>Надёжность</th></tr></thead><tbody>{Object.entries(report.metrics).flatMap(([group,values])=>Object.entries(values).map(([key,m])=><tr key={group+key}><td>{names[key]||key}</td><td>{group==='left_arm'?'Левая':group==='right_arm'?'Правая':'Корпус'}</td><td title={m.status}>{format(m.value,m.unit)}</td><td>{Math.round(m.coverage*100)}%</td><td>{reliability[m.technical_reliability]}</td></tr>))}</tbody></table></div></section></>}
     <details className="card quality-details"><summary>Качество распознавания и ограничения</summary><p>Человек не обнаружен: {report.pose_quality.no_person_frames} кадров. Несколько людей: {report.pose_quality.ambiguous_person_frames} кадров; такие кадры исключены.</p><div className="table-scroll"><table><thead><tr><th>Landmark</th><th>Покрытие кадров</th><th>Средний confidence</th></tr></thead><tbody>{Object.entries(report.pose_quality.landmarks).map(([name,q])=><tr key={name}><td>{name}</td><td>{(q.coverage*100).toFixed(1)}%</td><td>{q.mean_confidence.toFixed(2)}</td></tr>)}</tbody></table></div><ul>{report.limitations.map(l=><li key={l}>{l}</li>)}</ul><div className="actions"><a href={`/api/studies/${report.study_id}/files/landmarks`} download>Скачать landmarks</a><a href={`/api/studies/${report.study_id}/files/metrics`} download>Скачать метрики</a></div></details>
     <PatientPanel key={`patient-${report.study_id}`} report={report} onUpdate={next=>setReport(current=>current?.study_id===next.study_id?next:current)}/>
     <EvidencePanel key={report.study_id} report={report} onUpdate={next=>setReport(current=>current?.study_id===next.study_id?next:current)}/>
   </>}
   <footer><ShieldCheck size={17}/><span>Система поддержки решений · Измерение движения не является диагнозом.</span><small>КИНЕМА / MEASUREMENT FIRST</small></footer>
   </div></main>
 </div>;
}
