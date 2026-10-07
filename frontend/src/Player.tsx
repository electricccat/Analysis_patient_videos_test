import { useEffect, useRef, useState } from 'react';
import type { Frame, Report } from './types';

const edges = [['left_shoulder','right_shoulder'],['left_shoulder','left_elbow'],['left_elbow','left_wrist'],['right_shoulder','right_elbow'],['right_elbow','right_wrist'],['left_shoulder','left_hip'],['right_shoulder','right_hip'],['left_hip','right_hip'],['left_hip','left_knee'],['left_knee','left_ankle'],['right_hip','right_knee'],['right_knee','right_ankle'],['left_heel','left_foot_index'],['right_heel','right_foot_index'],['left_wrist','left_index'],['right_wrist','right_index']];

export default function Player({ report, frames, time, setTime }: { report: Report; frames: Frame[]; time: number; setTime: (t: number) => void }) {
 const video = useRef<HTMLVideoElement>(null), canvas = useRef<HTMLCanvasElement>(null);
 const [overlay, setOverlay] = useState(true);
 useEffect(() => {
   if (video.current && Math.abs(video.current.currentTime - time) > .12) video.current.currentTime = time;
 }, [time]);
 useEffect(() => {
   let handle: number;
   const paint = () => {
     const v = video.current, c = canvas.current;
     if (v && c) {
       const width = report.video_quality.width, height = report.video_quality.height;
       if (c.width !== width) c.width = width;
       if (c.height !== height) c.height = height;
       const ctx = c.getContext('2d')!;
       ctx.clearRect(0, 0, width, height);
       const t = v.currentTime;
       // Binary search: no stale skeleton across tracking gaps.
       let lo = 0, hi = frames.length - 1;
       while (lo < hi) { const mid = Math.floor((lo + hi + 1) / 2); if (frames[mid].timestamp <= t) lo = mid; else hi = mid - 1; }
       const frame = frames[lo];
       const good = (p: Frame['landmarks'][string] | undefined) => p && p.confidence >= report.pose_quality.threshold && p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1;
       const color = (name: string) => name.startsWith('left') ? '#54e2bd' : '#ffb86b';
       if (overlay && frame && Math.abs(frame.timestamp - t) <= .15) {
         ctx.lineWidth = Math.max(3, width / 300);
         for (const [a,b] of edges) { const p = frame.landmarks[a], q = frame.landmarks[b]; if (good(p) && good(q)) { ctx.strokeStyle = color(a); ctx.beginPath(); ctx.moveTo(p.x*width,p.y*height); ctx.lineTo(q.x*width,q.y*height); ctx.stroke(); } }
         for (const [name,p] of Object.entries(frame.landmarks)) if (good(p)) { ctx.fillStyle = color(name); ctx.beginPath(); ctx.arc(p.x*width,p.y*height,Math.max(4,width/160),0,2*Math.PI); ctx.fill(); }
       }
     }
     handle = requestAnimationFrame(paint);
   };
   handle = requestAnimationFrame(paint);
   return () => cancelAnimationFrame(handle);
 }, [frames, report, overlay]);
 return <>
   <div className="panel-heading"><h3>Видео пациента</h3><span className="tag">{report.video_quality.width} × {report.video_quality.height}</span></div>
   <div className="video-stage" style={{aspectRatio: `${report.video_quality.width}/${report.video_quality.height}`}}>
     <video ref={video} src={`/api/studies/${report.study_id}/files/preview`} controls playsInline preload="metadata" onTimeUpdate={e => setTime(e.currentTarget.currentTime)} onSeeked={e => setTime(e.currentTarget.currentTime)} />
     <canvas ref={canvas} aria-label="Ориентиры выбранных областей"/>
   </div>
   <div className="player-options"><label><input type="checkbox" checked={overlay} onChange={e=>setOverlay(e.target.checked)}/> Ориентиры</label><span>{time.toFixed(2)} с</span></div>
   <input aria-label="Временная шкала видео" className="timeline" type="range" min="0" max={report.video_quality.decoded_duration_seconds} step="0.01" value={time} onChange={e=>setTime(Number(e.target.value))}/>
   <div className="events">{report.events.map((event,i)=><button key={i} onClick={()=>setTime(event.timestamp)}><span>{event.timestamp.toFixed(2)} с</span>{event.label}</button>)}</div>
   <p className="caption">Показана совместимая копия исходного видео без звука. <a href={`/api/studies/${report.study_id}/files/original`}>Скачать оригинал</a>. Цвета обозначают анатомические стороны пациента.</p>
 </>;
}
