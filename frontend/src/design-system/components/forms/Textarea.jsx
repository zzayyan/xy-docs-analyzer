import React from 'react';

export function Textarea({label,placeholder,value,onChange,rows=4,hint,disabled=false,id,style}){
  const [focus,setFocus]=React.useState(false);
  const tid=id||label?.toLowerCase().replace(/\s+/g,'-');
  return (
    <label htmlFor={tid} style={{display:'flex',flexDirection:'column',gap:'var(--space-2)',fontFamily:'var(--font-core)',...style}}>
      {label&&<span style={{fontSize:'var(--fs-ui-sm)',fontWeight:'var(--fw-semibold)',color:'var(--text-card-title)'}}>{label}</span>}
      <textarea id={tid} rows={rows} placeholder={placeholder} value={value} onChange={onChange} disabled={disabled}
        onFocus={()=>setFocus(true)} onBlur={()=>setFocus(false)}
        style={{fontFamily:'var(--font-core)',fontSize:'var(--fs-ui-md)',lineHeight:'var(--lh-body)',color:'var(--text-body)',background:'var(--surface-card)',
          border:'var(--stroke-hairline) solid '+(focus?'var(--focus-ring)':'var(--border-subtle)'),
          boxShadow:focus?'0 0 0 3px rgba(229,66,15,.16)':'none',
          borderRadius:'var(--radius-sm)',padding:'12px 14px',width:'100%',resize:'vertical',outline:'none'}}/>
      {hint&&<span style={{fontSize:'var(--fs-ui-xs)',color:'var(--text-muted)'}}>{hint}</span>}
    </label>
  );
}
