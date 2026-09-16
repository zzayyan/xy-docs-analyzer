import React from 'react';

export function Pill({tone='outline',size='md',children,style}){
  const pad=size==='sm'?'4px 12px':'8px 18px';
  const fs=size==='sm'?'var(--fs-ui-sm)':'var(--fs-ui-md)';
  const tones={
    outline:{background:'var(--xy-white)',color:'var(--xy-grey-600)',border:'var(--stroke-pill) solid var(--xy-red-500)'},
    filled:{background:'var(--xy-red-300)',color:'var(--xy-white)',border:'var(--stroke-pill) solid var(--xy-red-300)'},
    soft:{background:'var(--surface-brand-tint)',color:'var(--brand-primary)',border:'var(--stroke-pill) solid var(--border-brand-soft)'},
    neutral:{background:'var(--surface-subtle)',color:'var(--text-card-body)',border:'var(--stroke-pill) solid var(--border-subtle)'}
  };
  return <span style={{display:'inline-flex',alignItems:'center',justifyContent:'center',fontFamily:'var(--font-core)',fontWeight:'var(--fw-semibold)',fontSize:fs,lineHeight:1.2,padding:pad,borderRadius:'var(--radius-sm)',whiteSpace:'nowrap',...tones[tone],...style}}>{children}</span>;
}
