import React from 'react';

export function Badge({tone='brand',children,style}){
  const tones={
    brand:{bg:'var(--brand-primary)',fg:'var(--xy-white)'},
    accent:{bg:'var(--brand-accent)',fg:'var(--xy-white)'},
    secure:{bg:'var(--status-secure)',fg:'var(--xy-ink-900)'},
    neutral:{bg:'var(--xy-grey-200)',fg:'var(--text-card-body)'},
    outline:{bg:'transparent',fg:'var(--brand-primary)',bd:'var(--border-brand)'}
  }[tone];
  return <span style={{display:'inline-flex',alignItems:'center',padding:'3px 10px',borderRadius:'var(--radius-pill)',
    background:tones.bg,color:tones.fg,border:tones.bd?'var(--stroke-hairline) solid '+tones.bd:'none',
    fontFamily:'var(--font-core)',fontWeight:'var(--fw-semibold)',fontSize:'var(--fs-ui-xs)',letterSpacing:'.02em',whiteSpace:'nowrap',...style}}>{children}</span>;
}
