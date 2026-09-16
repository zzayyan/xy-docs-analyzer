import React from 'react';

export function BrandIcon({name,size=56,ring=false,ringTone='brand',alt='',style}){
  const src=/^(\.|\/|https?:)/.test(name)?name:`assets/icons/${name}.png`;
  const img=<img src={src} alt={alt} style={{width:ring?size*0.58:size,height:ring?size*0.58:size,objectFit:'contain',display:'block'}}/>;
  if(!ring) return <span style={{display:'inline-flex',...style}}>{img}</span>;
  const tones={brand:'var(--xy-red-500)',secure:'var(--status-secure)',ink:'var(--xy-ink-700)'};
  return (
    <span style={{display:'inline-flex',alignItems:'center',justifyContent:'center',width:size,height:size,borderRadius:'var(--radius-pill)',background:tones[ringTone],border:'var(--stroke-icon-ring) solid var(--xy-white)',...style}}>{img}</span>
  );
}
