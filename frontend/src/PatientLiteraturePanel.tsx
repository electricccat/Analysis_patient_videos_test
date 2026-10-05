import { useState } from 'react';
import { BookOpen, RefreshCw, LoaderCircle } from 'lucide-react';
import { api } from './api';
import type { Report } from './types';
import { Source, Features } from './EvidencePanel';

const statuses: Record<string, string> = {completed: 'Поиск выполнен', partial: 'Часть запросов недоступна', unavailable: 'PubMed недоступен', needs_history: 'Уточните анкету', not_searched: 'Поиск не выполнен'};

export default function PatientLiteraturePanel({report, onUpdate}: {report: Report; onUpdate: (report: Report) => void}) {
 const [busy, setBusy] = useState(false), [error, setError] = useState('');
 const block = report.patient_literature;
 const refresh = async () => {
   setBusy(true); setError('');
   try {
     onUpdate(await api<Report>(`/api/studies/${report.study_id}/evidence`, {
       method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({patient_online: true}),
     }));
   } catch (e) { setError((e as Error).message); }
   finally { setBusy(false); }
 };
 return <section className="card">
   <div className="panel-heading"><h2><BookOpen size={20}/> Литература для оценки этого пациента</h2>
     <button className="secondary" disabled={busy} onClick={() => void refresh()}>{busy ? <LoaderCircle size={15} className="spin"/> : <RefreshCw size={15}/>} {busy ? 'Ищем материалы…' : 'Обновить подбор из интернета'}</button>
   </div>
   <p>Автоматический поиск после анализа видео и сохранения анкеты · верхняя конечность · до 3 тем и 5 публикаций на тему за последние 5 лет.</p>
   {error && <p className="error">{error}</p>}
   {!block ? <p>Для этого ранее сохранённого отчёта подбор ещё не выполнен. Нажмите «Обновить подбор из интернета».</p> : <>
     <p className="search-status">{statuses[block.status] ?? block.status} · {new Date(block.generated_at).toLocaleString('ru-RU')} · уникальных публикаций: {block.sources.length}</p>
     <p>{block.note}</p>
     {block.basis.length > 0 && <><h3>Что учтено при поиске</h3><ul>{block.basis.map(item => <li key={item}>{item}</li>)}</ul></>}
     <Features links={block.feature_links}/>
     <p className="caption">{block.privacy}</p>
     {block.warnings.map(warning => <p className="error" key={warning}>{warning}</p>)}
     {block.reviewed_sources.length > 0 && <details className="sources-list"><summary>Рекомендации и обзоры из проверенного каталога · {block.reviewed_sources.length}</summary>
       <p>Каталог по реабилитации взрослых после инсульта. Применимость к пациенту проверяет врач.</p>
       {block.reviewed_sources.map(source => <Source key={source.id} source={source}/>)}</details>}
     {block.groups.map(group => <div className="pubmed-search" key={group.topic}>
       <h3>{group.title}</h3><p>{group.reason}</p>
       {group.status === 'unavailable' ? <p>Ответ PubMed не получен. Повторите поиск позже.</p> : <p className="caption">{group.accessed_at ? new Date(group.accessed_at).toLocaleString('ru-RU') : ''} · найдено: {group.source_ids.length}</p>}
       {group.query && <details><summary>Поисковый запрос</summary><code className="query-text">{group.query}</code></details>}
       {group.status === 'completed' && !group.source_ids.length && <p>Публикаций с выбранными фильтрами не найдено. Это не означает отсутствие доказательств; врачу может понадобиться более широкий поиск.</p>}
       {group.source_ids.map(id => block.sources.find(source => source.id === id)).filter(source => source !== undefined).map(source => <Source key={source.id} source={source}/>)}
     </div>)}
   </>}
 </section>;
}
