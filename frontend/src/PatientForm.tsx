import { useEffect, useState } from 'react';
import { api } from './api';
import type { PatientField, PatientProfile } from './types';

export default function PatientForm({value,onChange,disabled=false}:{value:PatientProfile;onChange:(v:PatientProfile)=>void;disabled?:boolean}) {
 const [schema,setSchema]=useState<{fields:PatientField[];defaults:PatientProfile}|null>(null);
 const [error,setError]=useState('');
 useEffect(()=>{const controller=new AbortController();api<{fields:PatientField[];defaults:PatientProfile}>('/api/patient-form',{signal:controller.signal}).then(setSchema).catch(e=>{if(!controller.signal.aborted)setError(e.message);});return()=>controller.abort();},[]);
 if(error)return <p className="error">Не удалось загрузить анкету: {error}</p>;
 if(!schema)return <p>Загрузка анкеты…</p>;
 const groups=[...new Set(schema.fields.map(f=>f.group))];
 return <div className="patient-form"><p className="patient-intro">Заполните известные сведения из выписки и очной оценки. Неизвестные поля можно оставить пустыми и дополнить после анализа. Сведения и видео сохраняются локально вместе с исследованием; анкета также входит в экспорт JSON. ФИО и контакты не нужны.</p>
 {groups.map((group,i)=><details key={group} open={i===0}><summary>{group}<span>{schema.fields.filter(f=>f.group===group&&value[f.key]!=null&&value[f.key]!==''&&value[f.key]!=='unknown').length} заполнено</span></summary><div className="patient-fields">{schema.fields.filter(f=>f.group===group).map(f=>{
 const current=value[f.key]??schema.defaults[f.key]??'';
 const change=(v:string)=>onChange({...value,[f.key]:f.kind==='number'?(v===''?null:Number(v)):v===''&&f.kind==='date'?null:v});
 return <label className={f.kind==='textarea'?'patient-field wide':'patient-field'} key={f.key}><span>{f.label}</span>
 {f.kind==='select'?<select disabled={disabled} value={String(current)} onChange={e=>change(e.target.value)}>{f.choices?.map(([v,label])=><option key={v} value={v}>{label}</option>)}</select>:f.kind==='textarea'?<textarea disabled={disabled} rows={3} maxLength={3000} value={String(current)} onChange={e=>change(e.target.value)}/>:<input disabled={disabled} type={f.kind==='number'?'number':f.kind==='date'?'date':'text'} min={f.minimum??undefined} max={f.kind==='date'?new Date().toLocaleDateString('en-CA'):f.maximum??undefined} step={f.key==='age'?1:.1} maxLength={300} value={current} onChange={e=>change(e.target.value)}/>}
 {f.hint&&<small>{f.hint}</small>}</label>;
 })}</div></details>)}</div>;
}
