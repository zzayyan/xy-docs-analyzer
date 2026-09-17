import React from 'react';

export function Alert({tone='info',title,children,iconSrc,onDismiss,style}){
  const tones={
    info:{bg:'var(--surface-info-soft)',bd:'var(--xy-blue-400)',fg:'var(--text-info-soft)'},
    success:{bg:'var(--surface-success-soft)',bd:'var(--status-success)',fg:'var(--text-success-soft)'},
    warning:{bg:'var(--surface-warning-soft)',bd:'var(--brand-accent)',fg:'var(--text-warning-soft)'},
    danger:{bg:'var(--surface-danger-soft)',bd:'var(--brand-primary)',fg:'var(--text-danger-soft)'},
    secure:{bg:'var(--surface-secure-soft)',bd:'var(--status-secure)',fg:'var(--text-secure-soft)'}
  }[tone];
  return (
    <div role="status" style={{display:'flex',gap:'var(--space-3)',alignItems:'flex-start',padding:'var(--space-4)',
      background:tones.bg,border:'var(--stroke-hairline) solid '+tones.bd,borderRadius:'var(--radius-sm)',
      fontFamily:'var(--font-core)',fontSize:'var(--fs-ui-sm)',color:tones.fg,...style}}>
      {iconSrc&&<img src={iconSrc} alt="" style={{width:20,height:20,objectFit:'contain',flex:'0 0 auto'}}/>}
      <div style={{flex:1,display:'flex',flexDirection:'column',gap:'var(--space-1)'}}>
        {title&&<strong style={{fontWeight:'var(--fw-semibold)'}}>{title}</strong>}
        <span style={{lineHeight:'var(--lh-body)'}}>{children}</span>
      </div>
      {onDismiss&&<button onClick={onDismiss} aria-label="Dismiss" style={{background:'none',border:'none',cursor:'pointer',color:'inherit',fontSize:16,lineHeight:1,opacity:.6}}>&times;</button>}
    </div>
  );
}
