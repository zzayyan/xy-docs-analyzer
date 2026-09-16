import React from 'react';

export function SideNav({items=[],activeId,onSelect,footer,style}){
  return (
    <aside style={{width:'var(--app-sidebar-w)',flex:'0 0 auto',display:'flex',flexDirection:'column',justifyContent:'space-between',
      background:'var(--surface-subtle)',borderRight:'var(--stroke-hairline) solid var(--border-subtle)',padding:'var(--space-5) var(--space-4)',...style}}>
      <nav style={{display:'flex',flexDirection:'column',gap:'var(--space-1)'}}>
        {items.map(it=>{
          const active=it.id===activeId;
          return (
            <button key={it.id} onClick={()=>onSelect&&onSelect(it.id)}
              style={{display:'flex',alignItems:'center',gap:'var(--space-3)',width:'100%',textAlign:'left',cursor:'pointer',
                fontFamily:'var(--font-core)',fontSize:'var(--fs-ui-sm)',fontWeight:active?'var(--fw-semibold)':'var(--fw-medium)',
                color:active?'var(--brand-primary)':'var(--text-card-body)',
                background:active?'var(--surface-card)':'transparent',
                border:'var(--stroke-hairline) solid '+(active?'var(--border-brand-soft)':'transparent'),
                borderRadius:'var(--radius-sm)',padding:'9px 12px'}}>
              {it.iconSrc&&<img src={it.iconSrc} alt="" style={{width:18,height:18,objectFit:'contain'}}/>}
              <span style={{flex:1}}>{it.label}</span>
              {it.meta&&<span style={{fontSize:'var(--fs-ui-xs)',color:'var(--text-muted)'}}>{it.meta}</span>}
            </button>
          );
        })}
      </nav>
      {footer&&<div style={{paddingTop:'var(--space-4)',borderTop:'var(--stroke-hairline) solid var(--border-subtle)'}}>{footer}</div>}
    </aside>
  );
}
