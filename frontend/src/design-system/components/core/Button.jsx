import React from 'react';

const sizes={
  sm:{padding:'6px 14px',fontSize:'var(--fs-ui-sm)',radius:'var(--radius-sm)'},
  md:{padding:'10px 20px',fontSize:'var(--fs-ui-md)',radius:'var(--radius-sm)'},
  lg:{padding:'14px 28px',fontSize:'var(--fs-ui-lg)',radius:'var(--radius-md)'}
};

export function Button({variant='primary',size='md',disabled=false,fullWidth=false,iconSrc,iconPosition='left',type='button',onClick,children,style}){
  const s=sizes[size]||sizes.md;
  const base={display:'inline-flex',alignItems:'center',justifyContent:'center',gap:'var(--space-2)',
    fontFamily:'var(--font-core)',fontWeight:'var(--fw-semibold)',fontSize:s.fontSize,lineHeight:1.2,
    padding:s.padding,borderRadius:s.radius,cursor:disabled?'not-allowed':'pointer',
    width:fullWidth?'100%':'auto',textAlign:'center',
    transition:'background var(--dur-fast) var(--ease-standard),color var(--dur-fast) var(--ease-standard),border-color var(--dur-fast) var(--ease-standard),transform var(--dur-fast) var(--ease-standard)',
    opacity:disabled?.45:1};
  const skins={
    primary:{background:'var(--brand-primary)',color:'var(--text-on-brand)',border:'var(--stroke-pill) solid var(--brand-primary)'},
    secondary:{background:'transparent',color:'var(--brand-primary)',border:'var(--stroke-pill) solid var(--border-brand)'},
    ghost:{background:'transparent',color:'var(--text-body)',border:'var(--stroke-pill) solid transparent'},
    inverse:{background:'var(--xy-white)',color:'var(--brand-primary)',border:'var(--stroke-pill) solid var(--xy-white)'}
  };
  const [hover,setHover]=React.useState(false);
  const [press,setPress]=React.useState(false);
  const hoverSkins={
    primary:{background:'var(--brand-primary-hover)',borderColor:'var(--brand-primary-hover)'},
    secondary:{background:'var(--surface-brand-tint)'},
    ghost:{background:'var(--surface-subtle)'},
    inverse:{background:'var(--xy-grey-100)',borderColor:'var(--xy-grey-100)'}
  };
  const icon=iconSrc?<img src={iconSrc} alt="" style={{width:'1.15em',height:'1.15em',objectFit:'contain'}}/>:null;
  return (
    <button type={type} disabled={disabled} onClick={onClick}
      onMouseEnter={()=>setHover(true)} onMouseLeave={()=>{setHover(false);setPress(false);}}
      onMouseDown={()=>setPress(true)} onMouseUp={()=>setPress(false)}
      style={{...base,...skins[variant],...(hover&&!disabled?hoverSkins[variant]:null),transform:press&&!disabled?'translateY(1px)':'none',...style}}>
      {iconPosition==='left'&&icon}{children}{iconPosition==='right'&&icon}
    </button>
  );
}
