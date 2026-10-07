export const regions: Record<string,string> = {head:'Голова',trunk:'Корпус',right_arm:'Правая рука',left_arm:'Левая рука',right_hand:'Правая кисть',left_hand:'Левая кисть',right_leg:'Правая нога',left_leg:'Левая нога',right_foot:'Правая стопа',left_foot:'Левая стопа'};
const shapes: Record<string,string> = {
 head:'M105 18 Q130 0 155 18 L155 52 Q130 80 105 52 Z',
 trunk:'M99 80 Q130 65 161 80 L157 195 L103 195 Z',
 right_arm:'M96 79 L101 119 L80 160 L71 205 L51 199 L60 148 L77 88 Z',
 left_arm:'M164 79 L159 119 L180 160 L189 205 L209 199 L200 148 L183 88 Z',
 right_hand:'M51 204 L70 209 L65 245 Q48 259 43 239 Z',
 left_hand:'M209 204 L190 209 L195 245 Q212 259 217 239 Z',
 right_leg:'M103 201 L128 201 L124 281 L119 355 L94 355 L96 278 Z',
 left_leg:'M132 201 L157 201 L164 278 L166 355 L141 355 L136 281 Z',
 right_foot:'M94 361 L119 361 L120 386 L80 386 L80 375 Z',
 left_foot:'M141 361 L166 361 L180 375 L180 386 L140 386 Z',
};
export default function BodySelector({value,onChange,disabled=false}:{value:string[];onChange:(v:string[])=>void;disabled?:boolean}) {
 const toggle=(id:string)=>onChange(value.includes(id)?value.filter(x=>x!==id):[...value,id]);
 return <div className="body-selector"><p className="caption">Выберите несколько областей. Стороны анатомические: пациент изображён лицом к вам.</p><svg viewBox="0 0 260 400" role="group" aria-label="Выбор частей тела" className="body-map"><text x="15" y="22">ПРАВАЯ</text><text x="193" y="22">ЛЕВАЯ</text>{Object.entries(shapes).map(([id,d])=><path key={id} d={d} role="button" tabIndex={disabled?-1:0} aria-label={regions[id]} aria-pressed={value.includes(id)} className={value.includes(id)?'selected':''} onClick={()=>!disabled&&toggle(id)} onKeyDown={e=>{if(!disabled&&(e.key==='Enter'||e.key===' ')){e.preventDefault();toggle(id);}}}><title>{regions[id]}</title></path>)}</svg><div className="body-options">{Object.entries(regions).map(([id,label])=><label key={id}><input type="checkbox" disabled={disabled} checked={value.includes(id)} onChange={()=>toggle(id)}/>{label}</label>)}</div><p className="caption">Выбрано: {value.length}. Измерения и сохранённые ориентиры ограничены этими областями.</p></div>;
}
