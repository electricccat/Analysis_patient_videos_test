import { useEffect, useState } from 'react';
import { Activity, ArrowUpRight, Upload, ShieldCheck, ChevronRight, Download, Trash2, CircleHelp, FileVideo, CheckCircle2, LoaderCircle, Video } from 'lucide-react';

import { api } from './api';
import type { Study, Report, Frame, PatientProfile } from './types';
import Player from './Player';
import BodySelector from './BodySelector';
import ReviewRegions from './ReviewRegions';
import ClinicalPanel from './ClinicalPanel';
import PatientForm from './PatientForm';
import PatientPanel from './PatientPanel';


const reliability: Record<string,string> = { high: 'Высокая', medium: 'Средняя', low: 'Низкая' };

export default function App() {
 const [studies,setStudies] = useState<Study[]>([]), [selected,setSelected] = useState<Study|null>(null);
 const [file,setFile] = useState<File|null>(null), [localUrl,setLocalUrl] = useState('');
 const [side,setSide] = useState('unknown');
 const [bodyParts,setBodyParts] = useState<string[]>(['left_arm']);
 const [photo,setPhoto] = useState<File|null>(null), [photoUrl,setPhotoUrl] = useState(''), [dischargeText,setDischargeText] = useState(''), [searchTopic,setSearchTopic] = useState('');
 const [patientProfile,setPatientProfile] = useState<PatientProfile>({});
 const [report,setReport] = useState<Report|null>(null), [frames,setFrames] = useState<Frame[]>([]);
 const [time,setTime] = useState(0), [error,setError] = useState(''), [busy,setBusy] = useState(false), [modelReady,setModelReady] = useState<boolean|null>(null);

 const [deletePrompt,setDeletePrompt] = useState<Study|null>(null);
 const [deleting,setDeleting] = useState(false);
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
 const choose = (study: Study|null) => { if (deleting) return; if (study && study.study_id === selected?.study_id) return; setSelected(study); setReport(null); setFrames([]); setTime(0); setError(''); setDeletePrompt(null); };
 useEffect(()=>{if(!photo){setPhotoUrl('');return;}const url=URL.createObjectURL(photo);setPhotoUrl(url);return()=>URL.revokeObjectURL(url);},[photo]);
 const upload = async () => {
   if (!file || !bodyParts.length) return;
   setBusy(true); setError('');
   try {
     const data = new FormData(); data.append('file',file); data.append('affected_side',side); data.append('task','unspecified'); data.append('selected_regions',JSON.stringify(bodyParts)); data.append('discharge_text',dischargeText); data.append('search_topic',searchTopic); if(photo)data.append('discharge_photo',photo);
     data.append('patient_profile',JSON.stringify(patientProfile));
     const study = await api<Study>('/api/studies',{method:'POST',body:data}); choose(study); setFile(null); setPhoto(null); setDischargeText(''); setPatientProfile({}); refresh();
   } catch(e) { setError((e as Error).message); } finally {setBusy(false);}
 };
 const remove = async () => {
   if (!deletePrompt || deleting) return;
   const target = deletePrompt;
   setDeleting(true); setError('');
   try {
     await api(`/api/studies/${target.study_id}`,{method:'DELETE'});
     if (selected?.study_id === target.study_id) {
       setSelected(null); setReport(null); setFrames([]); setTime(0);
     }
     setStudies(current=>current.filter(study=>study.study_id!==target.study_id));
     setDeletePrompt(null);
   } catch(e) {setError((e as Error).message);} finally {setDeleting(false);}
 };
 const pending = selected && ['queued','processing'].includes(selected.status);
 return <div className="app-shell">
   <aside className="sidebar"><a className="brand" href="/" aria-label="Кинема — главная"><Activity size={28}/><span>кинема<span className="brand-dot">.</span></span></a><div className="brand-sub">АНАЛИЗ ПАЦИЕНТА</div>
     <div className="nav-label">РАБОЧЕЕ ПРОСТРАНСТВО</div><button className={`nav-item ${!selected?'active':''}`} onClick={()=>choose(null)}><Upload size={18}/> Новое исследование <span>＋</span></button>
     <div className="nav-label study-label">ИССЛЕДОВАНИЯ <span>{studies.length.toString().padStart(2,'0')}</span></div>
     <div className="study-list">{studies.length === 0 && <p className="empty-side">Загруженные видео появятся здесь</p>}{studies.map((s,i)=><div className="study-row" key={s.study_id}><button className={`study-item ${selected?.study_id===s.study_id?'chosen':''}`} disabled={deleting} onClick={()=>choose(s)}><FileVideo size={17}/><div><strong>{s.title||`Исследование ${studies.length-i}`}</strong><small>{new Date(s.created_at).toLocaleDateString('ru-RU')} · {s.status==='completed'?'Готово':s.status==='failed'?'Ошибка':'В работе'}</small></div><ChevronRight size={14}/></button><button className="study-delete" aria-label={`Удалить ${s.title||`исследование ${studies.length-i}`}`} title={['queued','processing'].includes(s.status)?'Дождитесь завершения анализа':'Удалить исследование'} disabled={deleting||['queued','processing'].includes(s.status)} onClick={()=>{setError('');setDeletePrompt(s);}}><Trash2 size={16}/></button></div>)}</div>
     <div className="local-note"><ShieldCheck size={21}/><strong>Видео остаётся у вас</strong><p>Обработка на локальном сервере. Без отправки во внешние AI API.</p><span className="tag dark">MVP · v0.1</span></div>
   </aside>
   <main><header className="topbar"><span>Пациент <ChevronRight size={14}/> {selected?'Результаты исследования':'Новое исследование'}</span><span className="prototype"><span/> ИССЛЕДОВАТЕЛЬСКИЙ ПРОТОТИП</span></header>
   <div className="content"><div className="page-heading"><div><div className="eyebrow">ВИДЕО · ВЫПИСКА · НАБЛЮДЕНИЯ</div><h1>{report?'Детали состояния пациента.':'Выберите области исследования.'}</h1><p>{report?'Проверьте наблюдения, выписку и предварительные гипотезы.':'Загрузите видео и выписку, отметьте нужные части тела на схеме.'}</p></div><div className="heading-icon"><Activity size={38}/></div></div>
   {error && <div role="alert" className="error">{error}</div>}
   {deletePrompt && <div className="delete-overlay"><section className="delete-confirm" role="alertdialog" aria-modal="true" aria-labelledby="delete-title" aria-describedby="delete-description" onKeyDown={e=>{if(e.key==='Escape'&&!deleting)setDeletePrompt(null);if(e.key==='Tab'){const buttons=Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));const first=buttons[0],last=buttons[buttons.length-1];if(!first){e.preventDefault();}else if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}}}><h2 id="delete-title">Удалить исследование?</h2><p><strong>{deletePrompt.title||`Исследование ${studies.length-studies.findIndex(study=>study.study_id===deletePrompt.study_id)}`} · {new Date(deletePrompt.created_at).toLocaleDateString('ru-RU')}</strong></p><p id="delete-description">Исходное видео, копия, landmarks, метрики, анкета пациента и отчёт будут удалены без возможности восстановления.</p>{error&&<p role="alert" className="error">{error}</p>}<div className="actions"><button className="secondary" autoFocus disabled={deleting} onClick={()=>setDeletePrompt(null)}>Отмена</button><button className="delete" disabled={deleting} onClick={remove}>{deleting?'Удаление…':'Удалить все данные'}</button></div></section></div>}

   {(selected?.is_demo||report?.is_demo) && <div className="demo-notice" role="note"><strong>Демонстрационный пример · вымышленный пациент</strong><p>Анкета и очные результаты придуманы. Видео — схематическая анимация, метрики рассчитаны по заданным координатам без распознавания MediaPipe. Этот пример показывает работу интерфейса и правил подбора; он не подтверждает клиническую точность программы.</p></div>}
   {!selected && <>
     <div className="workflow"><span className="current"><b>01</b> Загрузка видео</span><ChevronRight size={16}/><span><b>02</b> Оценка выбранных областей</span><ChevronRight size={16}/><span><b>03</b> Результаты</span></div>
     <div className="upload-grid"><section className="card upload-card"><div className="panel-heading"><h2>Видео пациента</h2><span className="tag">Локальная обработка</span></div>
       <label className={`dropzone ${file?'has-file':''}`} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();setFile(e.dataTransfer.files[0]||null);}}><input type="file" accept=".mp4,.mov,.webm" onChange={e=>setFile(e.target.files?.[0]||null)}/><div className="upload-symbol"><Upload size={28}/></div><strong>{file?file.name:'Перетащите видео сюда'}</strong><span>{file?`${(file.size/1024/1024).toFixed(1)} МБ · нажмите для замены`:'или нажмите, чтобы выбрать файл'}</span><small>MP4, MOV, WebM · до 300 МБ · до 3 минут</small></label>
       <div className="camera-upload">
         <label className="primary camera-button"><input aria-label="Записать видео с камеры устройства" type="file" accept="video/*" capture="environment" disabled={busy} onChange={e=>{const recorded=e.currentTarget.files?.[0];if(recorded){setFile(recorded);setError('');}e.currentTarget.value='';}}/><Video size={19}/> Записать видео</label>
         <p className="caption">На телефоне откроется камера или меню выбора записи. После съёмки подтвердите видео — оно появится здесь для просмотра. Если камера не открывается, запишите видео обычной камерой и выберите файл выше.</p>
         <p className="caption">Снимайте до 3 минут, желательно в 1080p: камера неподвижна, выбранные области полностью видны. Видео отправится на компьютер только после нажатия «Начать анализ».</p>
       </div>
       {localUrl && <video className="source-preview" src={localUrl} controls playsInline preload="metadata"/>}
       {file && <p className="caption">Если браузер не воспроизводит MOV, после анализа будет доступна MP4-копия.</p>}
       <div className="upload-bottom"><ShieldCheck size={16}/><span>Видео не используется для обучения моделей.</span></div>
     </section><section className="card setup-card"><div className="panel-heading"><h2>Области исследования</h2><span className="tag">Можно несколько</span></div><BodySelector value={bodyParts} onChange={setBodyParts} disabled={busy}/><label className="field-label">Поражённая сторона</label><div className="segmented">{[['left','Левая'],['right','Правая'],['unknown','Неизвестно']].map(([value,label])=><button key={value} className={side===value?'selected':''} onClick={()=>setSide(value)}>{label}</button>)}</div><p className="caption">Проверьте, не зеркальная ли запись. Сторона поражения не выводится автоматически из схемы.</p>{modelReady===false&&<p className="error">Установите модель: python scripts/download_model.py</p>}</section></div>
     <section className="card"><h2>Фото медицинской выписки</h2><label className="field-label" htmlFor="discharge-photo">Прикрепить страницу выписки · JPG, PNG, WebP · до 12 МБ</label><input id="discharge-photo" type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={e=>setPhoto(e.target.files?.[0]||null)}/>{photoUrl&&<img className="discharge-preview" src={photoUrl} alt="Прикреплённая медицинская выписка"/>}<label className="field-label" htmlFor="discharge-text">Текст выписки (необязательно)</label><textarea id="discharge-text" rows={5} maxLength={30000} disabled={busy} value={dischargeText} onChange={e=>setDischargeText(e.target.value)}/><p className="caption">Фото распознаётся локально. После обработки сверьте текст с оригиналом. Если вы ввели текст вручную, он используется вместо OCR.</p><label className="field-label" htmlFor="search-topic">Тема автоматического поиска лечения и восстановления</label><input id="search-topic" maxLength={160} value={searchTopic} disabled={busy} placeholder="Например: реабилитация после инсульта" onChange={e=>setSearchTopic(e.target.value)}/><p className="caption">Укажите общий диагноз без персональных данных. Если поле пустое, для распознанных категорий (например, инсульт) подбирается общая тема автоматически. В поисковик отправляется только тема; фото, видео и выписка остаются на компьютере.</p></section>
     <section className="card"><div className="panel-heading"><h2>Анкета пациента и история болезни</h2><span className="tag">Связана с этим видео</span></div><PatientForm value={patientProfile} onChange={setPatientProfile} disabled={busy}/><button className="primary analyze-button" disabled={!file||!bodyParts.length||busy||modelReady!==true} onClick={upload}>{busy?<LoaderCircle className="spin" size={18}/>:<Activity size={18}/>} {busy?'Загрузка…':'Начать анализ'}<ArrowUpRight size={18}/></button></section>
     <section className="guide-grid">{[['01','Подготовьте кадр','Один человек, неподвижная камера. Выбранные области и соседние суставы полностью видны.'],['02','Сохраните детали','Достаточное освещение и контрастная одежда помогут отслеживать суставы.'],['03','Оцените измерения','Проверьте ориентиры, ракурс и распознанную выписку перед интерпретацией.']].map(([n,title,text])=><div key={n}><span>{n}</span><h3>{title}</h3><p>{text}</p></div>)}</section>
   </>}
   {pending && <section className="card progress-card"><LoaderCircle className="spin" size={36}/><h2>{selected.stage==='web_resources'?'Ищем материалы по лечению и восстановлению':'Оцениваем выбранные области и выписку'}</h2><p>Ориентиры выбранных областей → детали положения → выписка → гипотезы → материалы</p><progress max="1" value={selected.progress??undefined}/><span>{selected.processed_frames??0} кадров обработано · {selected.progress===null?'длительность уточняется':`${Math.round((selected.progress??0)*100)}%`}</span></section>}
   {selected && !pending && !report && selected.status==='completed' && <p>Загрузка результатов…</p>}
   {selected && !pending && <div className="result-actions"><strong>Результаты исследования</strong><div className="actions">{report && <a className="secondary" href={`/api/studies/${selected.study_id}/files/report`} download><Download size={15}/> JSON отчёт</a>}<button className="delete" disabled={deleting} onClick={()=>{setError('');setDeletePrompt(selected);}}><Trash2 size={16}/> Удалить</button></div></div>}

   {report && <>
     <div className="quality-bar"><ShieldCheck size={19}/><strong>Техническая надёжность: {reliability[report.pose_quality.level].toLowerCase()}</strong><span>{report.video_quality.decoded_frames} кадров</span><span>{report.video_quality.decoded_duration_seconds.toFixed(1)} с</span><span>Порог confidence ≥ {report.pose_quality.threshold}</span></div>
     <div className="analysis-grid"><section className="card player-card"><Player report={report} frames={frames} time={time} setTime={setTime}/></section><ReviewRegions key={report.study_id} report={report} onQueued={s=>{choose(s);refresh();}} setTime={setTime}/></div>
     <ClinicalPanel key={`clinical-${report.study_id}`} report={report} onUpdate={setReport}/>
     <details className="card quality-details"><summary>Качество распознавания и ограничения</summary><p>Человек не обнаружен: {report.pose_quality.no_person_frames} кадров. Несколько людей: {report.pose_quality.ambiguous_person_frames} кадров; такие кадры исключены.</p><div className="table-scroll"><table><thead><tr><th>Landmark</th><th>Покрытие кадров</th><th>Средний confidence</th></tr></thead><tbody>{Object.entries(report.pose_quality.landmarks).map(([name,q])=><tr key={name}><td>{name}</td><td>{(q.coverage*100).toFixed(1)}%</td><td>{q.mean_confidence.toFixed(2)}</td></tr>)}</tbody></table></div><ul>{report.limitations.map(l=><li key={l}>{l}</li>)}</ul><div className="actions"><a href={`/api/studies/${report.study_id}/files/landmarks`} download>Скачать landmarks</a><a href={`/api/studies/${report.study_id}/files/metrics`} download>Скачать метрики</a></div></details>
     <PatientPanel key={`patient-${report.study_id}`} report={report} onUpdate={next=>setReport(current=>current?.study_id===next.study_id?next:current)}/>

   </>}
   <footer><ShieldCheck size={17}/><span>Система поддержки решений · Предварительная оценка требует проверки врачом.</span><small>КИНЕМА / PATIENT REVIEW</small></footer>
   </div></main>
 </div>;
}
