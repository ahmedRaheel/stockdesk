import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, BrainCircuit, ChartNoAxesCombined, RefreshCcw, ShieldCheck, TrendingDown } from "lucide-react";
import { api, send } from "./api";

type Flag = { type:string; invoice?:string; sku?:string; name?:string; discount_pct?:number; discount?:number; cost?:number; price?:number; reason:string };
type Advice = { type:string; product:string; sku:string; name:string; stock:string; reorder:string; suggested_minimum:string; reason:string };
type Report = { period_days:number; sales_count:number; sales_total_minor:number; recorded_discounts_minor:number; returned_invoices:number; return_rate_pct:number;
  reorder:Advice[]; leakage:{ discounts:Flag[]; below_cost:Flag[]; stock_out_adjustments:{product:string;quantity:number;notes:string;actor:string}[]; note:string }};
const prompts=["What should I reorder?","Which transactions need profit review?","Summarize my business performance"];
export default function GrowthCenter({tenant,currency}:{tenant:string;currency:string}) {
 const [days,setDays]=useState(30),[report,setReport]=useState<Report|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const [question,setQuestion]=useState(prompts[0]),[answer,setAnswer]=useState<{answer:string;evidence:unknown[];method:string;ai_commentary?:string}|null>(null),[tab,setTab]=useState<'growth'|'leakage'>('growth');
 const money=(value:number)=>new Intl.NumberFormat('en',{style:'currency',currency}).format(value/100);
 const load=useCallback(async()=>{setBusy(true);setError('');try{setReport(await api<Report>(`/api/v1/tenants/${encodeURIComponent(tenant)}/growth/insights?days=${days}`));setAnswer(null)}catch(e){setError((e as Error).message)}finally{setBusy(false)}},[tenant,days]);
 useEffect(()=>{void load()},[load]);
 async function ask(value:string){setQuestion(value);setBusy(true);setError('');try{setAnswer(await send<{answer:string;evidence:unknown[];method:string;ai_commentary?:string}>(`/api/v1/tenants/${encodeURIComponent(tenant)}/growth/ask?days=${days}`,{question:value}))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <div className="growth-suite">
  <section className="panel growth-hero d-flex flex-wrap justify-content-between gap-3 align-items-center">
   <div><span className="growth-kicker"><BrainCircuit size={15}/> INTELLIGENT RETAIL OPERATIONS</span><h2 className="mb-2">Growth &amp; Profit Center</h2>
    <p className="mb-0">Actionable inventory, revenue and risk insights grounded in your StockDesk transactions.</p></div>
   <div className="d-flex align-items-center gap-2"><select className="form-select form-select-sm" value={days} onChange={e=>setDays(Number(e.target.value))} aria-label="Analysis period"><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></select><button className="secondary" disabled={busy} onClick={()=>void load()}><RefreshCcw size={15}/> Refresh</button></div>
  </section>
  {error&&<div className="alert alert-danger" role="alert">{error}</div>}
  {report&&<>
   <div className="growth-kpis">
    <div className="growth-kpi"><span>Completed invoices</span><strong>{report.sales_count.toLocaleString()}</strong><small>In selected period</small></div>
    <div className="growth-kpi"><span>Recorded sales</span><strong>{money(report.sales_total_minor)}</strong><small>Completed POS invoices</small></div>
    <div className="growth-kpi"><span>Reorder attention</span><strong>{report.reorder.length}</strong><small>Products at or below threshold</small></div>
    <div className="growth-kpi"><span>Refund / return rate</span><strong>{report.return_rate_pct}%</strong><small>{report.returned_invoices} returned invoices</small></div>
   </div>
   <div className="growth-tabs"><button className={tab==='growth'?'active':''} onClick={()=>setTab('growth')}><ChartNoAxesCombined size={16}/> Growth Copilot</button><button className={tab==='leakage'?'active':''} onClick={()=>setTab('leakage')}><ShieldCheck size={16}/> Profit Leakage Review <span>{report.leakage.discounts.length+report.leakage.below_cost.length}</span></button></div>
   {tab==='growth'?<div className="growth-layout">
    <section className="panel"><div className="d-flex gap-2 align-items-center"><BrainCircuit size={20}/><h3>Ask the Growth Copilot</h3></div><p className="text-muted small">Evidence-based recommendations. No automatic pricing, purchase, or account changes.</p>
     <div className="growth-prompts">{prompts.map(p=><button className="secondary" key={p} disabled={busy} onClick={()=>void ask(p)}>{p}<ArrowRight size={13}/></button>)}</div>
     <form className="growth-question" onSubmit={e=>{e.preventDefault();void ask(question)}}><label htmlFor="growth-question" className="visually-hidden">Question</label><input id="growth-question" className="form-control" value={question} maxLength={300} onChange={e=>setQuestion(e.target.value)} /><button className="primary" disabled={busy||question.trim().length<3}>Ask</button></form>
     {answer&&<div className="growth-answer"><div className="growth-kicker">ANALYSIS · {answer.method==='auditable_rules'?'AUDITABLE RULES':answer.method}</div><p>{answer.answer}</p>{answer.ai_commentary&&<div className="growth-ai-note"><strong>Local AI interpretation</strong><p>{answer.ai_commentary}</p><small>AI-generated commentary; verify against the evidence above.</small></div>}<small>Based on current tenant data. Confirm recommendations before acting.</small></div>}
    </section>
    <section className="panel"><div className="growth-section-title"><h3>Priority restock opportunities</h3><span>{report.reorder.length} flagged</span></div>
     {report.reorder.length?<div className="growth-stack">{report.reorder.slice(0,10).map(item=><div className="growth-listitem" key={item.product}><div><strong>{item.name}</strong><small>{item.sku} · On hand {item.stock} / threshold {item.reorder}</small></div><span className="growth-pill">Review +{item.suggested_minimum}</span></div>)}</div>:<p className="text-muted">All active products are above their reorder thresholds.</p>}
    </section>
   </div>:<div className="growth-layout">
    <section className="panel"><div className="growth-section-title"><h3><AlertTriangle size={18}/> Unusually high discounts</h3><span>{report.leakage.discounts.length} cases</span></div><p className="text-muted small">Discounts at or above 20% of invoice subtotal. Approval may have been valid; review the transaction.</p>
      {report.leakage.discounts.length?<div className="growth-stack">{report.leakage.discounts.map(row=><div className="growth-listitem" key={row.invoice}><div><strong>Invoice {row.invoice}</strong><small>{row.reason}</small></div><span className="growth-pill">{row.discount_pct}% · {money(row.discount||0)}</span></div>)}</div>:<p className="text-muted">No invoices met this exception threshold.</p>}
    </section>
    <section className="panel"><div className="growth-section-title"><h3><TrendingDown size={18}/> Items priced below cost</h3><span>{report.leakage.below_cost.length} products</span></div>
      {report.leakage.below_cost.length?<div className="growth-stack">{report.leakage.below_cost.map(row=><div className="growth-listitem" key={row.sku}><div><strong>{row.name}</strong><small>SKU {row.sku} · Unit cost {money(row.cost||0)}</small></div><span className="growth-pill">Price {money(row.price||0)}</span></div>)}</div>:<p className="text-muted">No active products have a list price below their recorded cost.</p>}
    </section>
    <section className="panel growth-wide"><h3>Stock write-off review</h3><p className="text-muted small">Recent manual OUT movements. Investigate unusually large or repeated movements.</p><div className="growth-stack">{report.leakage.stock_out_adjustments.slice(0,12).map((row,i)=><div className="growth-listitem" key={i}><div><strong>{row.notes||'Inventory adjustment'}</strong><small>By {row.actor}</small></div><span>{String(row.quantity)} units</span></div>)}</div></section>
   </div>}
   <p className="growth-disclaimer"><ShieldCheck size={14}/> Insights are exceptions for staff review, not evidence of fraud or guaranteed incremental profit. Recorded sales exclude returned invoices.</p>
  </>}
 </div>
}
