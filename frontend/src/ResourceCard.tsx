import {useState} from 'react';
import type {WebSource} from './types';

export default function ResourceCard({source}:{source:WebSource}) {
 const [showVideo,setShowVideo]=useState(false);
 const review=source.content_review;
 const videoId=review?.video_id&&/^[A-Za-z0-9_-]{11}$/.test(review.video_id)?review.video_id:null;
 return <article className="resource-card"><h4><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a></h4>
 <p className="caption">{source.domain}{source.language==='ru'?' · На русском':''}{review?.channel?` · Канал: ${review.channel}`:''}</p>
 {source.source_kind==='clinic_program'&&<p className="caption">Описание программы клиники; это не клиническая рекомендация.</p>}
 {source.source_kind==='course_preview'&&<p className="caption">Бесплатный фрагмент коммерческого курса.</p>}
 <strong>Кратко</strong><p>{review?.short_summary||'Обзор по тексту страницы пока не сформирован. Повторите поиск для чтения материалов.'}</p>
 {!!review?.key_points.length&&<><strong>Что важно</strong><ul>{review.key_points.map(p=><li key={p}>{p}</li>)}</ul></>}
 {review?.note&&<p className="caption">{review.note}</p>}
 {review?.checked_at&&<p className="caption">Проверка: {new Date(review.checked_at).toLocaleString('ru-RU')}</p>}
 {videoId&&<><button className="secondary" onClick={()=>setShowVideo(v=>!v)}>{showVideo?'Скрыть видео':'Показать видео здесь'}</button>{showVideo&&<iframe className="resource-video" src={`https://www.youtube-nocookie.com/embed/${videoId}`} title={review?.video_title||source.title} loading="lazy" allow="encrypted-media; picture-in-picture" allowFullScreen/>}</>}
 <p><a href={source.url} target="_blank" rel="noreferrer">Открыть оригинал ↗</a></p>
 </article>;
}
