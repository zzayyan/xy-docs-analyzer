import React from 'react';

export function Card({variant='outline',title,body,iconSrc,align='center',children,style}){
  const variants={
    outline:{background:'var(--surface-card)',border:'var(--stroke-card) solid var(--border-brand)',borderRadius:'var(--radius-lg)',boxShadow:'none'},
    accent:{background:'var(--surface-card)',border:'var(--stroke-card) solid var(--brand-accent)',borderRadius:'var(--radius-lg)',boxShadow:'none'},
    quiet:{background:'var(--surface-card)',border:'var(--stroke-hairline) solid var(--border-subtle)',borderRadius:'var(--radius-md)',boxShadow:'var(--shadow-sm)'},
    tint:{background:'var(--surface-brand-tint)',border:'var(--stroke-hairline) solid var(--border-brand-soft)',borderRadius:'var(--radius-md)',boxShadow:'none'}
  };
  return (
    <div style={{padding:'var(--space-6)',display:'flex',flexDirection:'column',gap:'var(--space-3)',alignItems:align==='center'?'center':'flex-start',textAlign:align,...variants[variant],...style}}>
      {iconSrc&&<img src={iconSrc} alt="" style={{width:56,height:56,objectFit:'contain'}}/>}
      {title&&<div style={{font:'var(--type-card-title)',fontSize:'var(--fs-ui-lg)',color:'var(--text-card-title)'}}>{title}</div>}
      {body&&<p style={{margin:0,font:'var(--type-card-body)',fontSize:'var(--fs-ui-sm)',color:'var(--text-card-body)'}}>{body}</p>}
      {children}
    </div>
  );
}
