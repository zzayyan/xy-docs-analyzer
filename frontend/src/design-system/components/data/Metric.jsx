import React from 'react';

export function Metric({value,label,delta,tone='brand',align='left',style}){
  const tones={brand:'var(--brand-primary)',ink:'var(--text-title)',secure:'var(--status-secure)'};
  return (
    <div style={{display:'flex',flexDirection:'column',gap:'var(--space-1)',alignItems:align==='center'?'center':'flex-start',textAlign:align,...style}}>
      <span style={{fontFamily:'var(--font-core)',fontWeight:'var(--fw-bold)',fontSize:'var(--fs-ui-xl)',lineHeight:1.05,letterSpacing:'var(--ls-title)',color:tones[tone]}}>{value}</span>
      <span style={{fontFamily:'var(--font-core)',fontSize:'var(--fs-ui-sm)',color:'var(--text-card-body)'}}>{label}</span>
      {delta&&<span style={{fontFamily:'var(--font-core)',fontSize:'var(--fs-ui-xs)',fontWeight:'var(--fw-semibold)',color:'var(--status-success)'}}>{delta}</span>}
    </div>
  );
}
