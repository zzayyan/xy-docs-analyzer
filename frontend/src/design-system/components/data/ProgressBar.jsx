import React from 'react';

export function ProgressBar({value=0,label,tone='brand',showValue=true,style}){
  const tones={brand:'var(--brand-primary)',accent:'var(--brand-accent)',secure:'var(--status-secure)'};
  return (
    <div style={{display:'flex',flexDirection:'column',gap:'var(--space-2)',fontFamily:'var(--font-core)',...style}}>
      {(label||showValue)&&<div style={{display:'flex',justifyContent:'space-between',fontSize:'var(--fs-ui-xs)',color:'var(--text-card-body)'}}>
        <span>{label}</span>{showValue&&<span style={{fontWeight:'var(--fw-semibold)'}}>{Math.round(value)}%</span>}
      </div>}
      <div style={{height:8,borderRadius:'var(--radius-pill)',background:'var(--surface-raised)',overflow:'hidden'}}>
        <div style={{width:Math.max(0,Math.min(100,value))+'%',height:'100%',background:tones[tone],borderRadius:'var(--radius-pill)',
          transition:'width var(--dur-slow) var(--ease-out)'}}/>
      </div>
    </div>
  );
}
