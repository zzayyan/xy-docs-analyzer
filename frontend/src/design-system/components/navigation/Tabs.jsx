import React from 'react';

export function Tabs({tabs=[],activeIndex=0,onChange,variant='underline',style}){
  return (
    <div role="tablist" style={{display:'flex',alignItems:'center',gap:variant==='pill'?'var(--space-3)':'var(--space-6)',
      borderBottom:variant==='underline'?'var(--stroke-hairline) solid var(--border-subtle)':'none',...style}}>
      {tabs.map((t,i)=>{
        const active=i===activeIndex;
        const pill={background:active?'var(--xy-red-300)':'var(--surface-card)',color:active?'var(--xy-white)':'var(--text-card-body)',
          border:'var(--stroke-pill) solid '+(active?'var(--xy-red-300)':'var(--border-brand-soft)'),borderRadius:'var(--radius-sm)',padding:'8px 18px'};
        const under={background:'transparent',color:active?'var(--brand-primary)':'var(--text-muted)',border:'none',
          borderBottom:'3px solid '+(active?'var(--brand-primary)':'transparent'),padding:'10px 2px'};
        return <button key={t} role="tab" aria-selected={active} onClick={()=>onChange&&onChange(i)}
          style={{fontFamily:'var(--font-core)',fontSize:'var(--fs-ui-md)',fontWeight:active?'var(--fw-semibold)':'var(--fw-medium)',cursor:'pointer',
            ...(variant==='pill'?pill:under)}}>{t}</button>;
      })}
    </div>
  );
}
