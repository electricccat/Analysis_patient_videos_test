import {useState} from 'react';
import BodySelector from './BodySelector';
import {api} from './api';
import type {Report,Study} from './types';

export default function ReviewRegions({report,onQueued,setTime}:{report:Report;onQueued:(s:Study)=>void;setTime:(t:number)=>void}) {
 const [selected,setSelected]=useState<string[]>(report.selected_regions||[]);
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const analyze=async()=>{
   setBusy(true);setError('');
   try {onQueued(await api<Study>(`/api/studies/${report.study_id}/reanalyze`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({selected_regions:selected})}));}
   catch(e){setError((e as Error).message);}finally{setBusy(false);}
 };
 return <section className="card"><h2>Области исследования и детали</h2>
 {!report.selected_regions?.length&&<p className="caption">В этом исследовании области ещё не выбраны. Отметьте их на схеме и запустите анализ сохранённого видео.</p>}
 <BodySelector value={selected} onChange={setSelected} disabled={busy}/>
 <button className="primary" disabled={busy||!selected.length} onClick={analyze}>{busy?'Подготовка…':'Анализировать выбранные области'}</button>
 <p className="caption">Видео загружать заново не нужно. Результат появится в новом исследовании вместе с копией анкеты и выписки; текущий отчёт сохранится.</p>
 {error&&<p role="alert" className="error">{error}</p>}
 {!!report.body_details?.length&&<h3>Результаты текущего исследования</h3>}
 {report.body_details?.map(d=><article className="body-detail" key={d.region}><h3>{d.label}</h3><p>{d.statement}</p><p className="caption">Надёжные ориентиры в {Math.round(d.coverage*100)}% кадров</p>{d.timestamp!==null&&<button className="secondary" onClick={()=>setTime(d.timestamp!)}>Показать кадр · {d.timestamp.toFixed(2)} с</button>}</article>)}
 </section>;
}
