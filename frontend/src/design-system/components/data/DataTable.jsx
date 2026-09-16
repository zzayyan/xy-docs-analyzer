import React from 'react';

export function DataTable({columns=[],rows=[],dense=false,style}){
  const pad=dense?'8px 12px':'12px 16px';
  return (
    <table style={{width:'100%',borderCollapse:'collapse',fontFamily:'var(--font-core)',fontSize:'var(--fs-ui-sm)',...style}}>
      <thead>
        <tr>{columns.map(c=>(
          <th key={c.key||c} style={{textAlign:c.align||'left',padding:pad,fontWeight:'var(--fw-semibold)',fontSize:'var(--fs-ui-xs)',
            letterSpacing:'var(--ls-caps)',textTransform:'uppercase',color:'var(--text-muted)',
            borderBottom:'var(--stroke-hairline) solid var(--border-subtle)',background:'var(--surface-subtle)'}}>{c.label||c}</th>))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r,i)=>(
          <tr key={i}>{columns.map(c=>{const k=c.key||c;return (
            <td key={k} style={{textAlign:c.align||'left',padding:pad,color:'var(--text-body)',
              borderBottom:'var(--stroke-hairline) solid var(--border-subtle)'}}>{r[k]}</td>);})}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
