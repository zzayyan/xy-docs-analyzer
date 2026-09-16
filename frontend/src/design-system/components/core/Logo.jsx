import React from 'react';

export function Logo({variant='full',height=44,label='XY Intelligence',basePath='assets/',style}){
  const srcs={full:basePath+'logo-xy-intelligence.png',mark:basePath+'logo-mark.png',wordmark:basePath+'logo-wordmark.png'};
  if(variant==='lockup'){
    return (
      <span style={{display:'inline-flex',alignItems:'center',gap:'var(--space-3)',...style}}>
        <img src={srcs.mark} alt="" style={{height,width:'auto',display:'block'}}/>
        <span style={{fontFamily:'var(--font-core)',fontWeight:'var(--fw-bold)',fontSize:height*0.52,letterSpacing:'var(--ls-title)',color:'var(--xy-ink-900)'}}>{label}</span>
      </span>
    );
  }
  return <img src={srcs[variant]} alt={label} style={{height,width:'auto',display:'block',...style}}/>;
}
