import { useCallback, useEffect, useState } from "react";
import { Check, ClipboardList, ExternalLink, Globe2, RefreshCw, Store, X } from "lucide-react";
import { api, send } from "./api";

type Product={id:string;sku:string;name:string;stock:number;price:number;published:boolean;featured:boolean;sort_order:number};
type Settings={slug:string;title:string;description:string;published:boolean};
type Order={id:string;customer_name:string;customer_phone:string;notes:string;total:number;currency:string;status:string;created:string;sale_id?:string;items:{name:string;quantity:string;unit_price:number}[]};
export default function StorefrontManager({tenant,currency}:{tenant:string;currency:string}) {
 const [cfg,setCfg]=useState<Settings>({slug:'',title:'',description:'',published:false});
 const [products,setProducts]=useState<Product[]>([]),[orders,setOrders]=useState<Order[]>([]),[status,setStatus]=useState('pending');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const base=`/api/v1/tenants/${encodeURIComponent(tenant)}/storefront`;
 const money=(value:number)=>new Intl.NumberFormat('en',{style:'currency',currency}).format(value/100);
 const load=useCallback(async()=>{setBusy(true);setError('');try{const [s,o]=await Promise.all([api<{settings:Settings|null;products:Product[]}>(base),api<{items:Order[]}>(base+`/orders?status=${status}`)]);setProducts(s.products);setCfg(s.settings||{slug:'',title:'',description:'',published:false});setOrders(o.items)}catch(e){setError((e as Error).message)}finally{setBusy(false)}},[base,status]);
 useEffect(()=>{void load()},[load]);
 async function save(){setBusy(true);setError('');try{const result=await send<{url:string}>(base,cfg,'PUT');setNotice(`Storefront saved: ${result.url}`);await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function toggle(product:Product){setBusy(true);setError('');try{await send(base+`/products/${encodeURIComponent(product.id)}`,{published:!product.published,featured:product.featured,sort_order:product.sort_order},'PUT');await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function action(order:Order,type:'accept'|'reject'|'fulfil'){
  const sale_id=type==='fulfil'?window.prompt('Enter the ID of the completed POS invoice for this order:'):null;
  if(type==='fulfil'&&!sale_id)return;
  setBusy(true);setError('');try{await send(base+`/orders/${order.id}/${type}`,type==='fulfil'?{sale_id}:{});await load()}catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 const link=cfg.slug?`${window.location.origin}/shop/${cfg.slug}`:'';
 return <div className="growth-suite">
  <section className="panel"><div className="growth-section-title"><div><span className="growth-kicker"><Globe2 size={14}/> ONLINE COMMERCE</span><h2>Branded online storefront</h2><p className="text-muted small">Share a product catalog and accept pickup requests. Payments are collected in-store using POS.</p></div>{link&&<a className="secondary" href={link} target="_blank" rel="noopener noreferrer">View store <ExternalLink size={14}/></a>}</div>
  {error&&<div className="alert alert-danger" role="alert">{error}</div>}{notice&&<div className="alert alert-success">{notice}</div>}
  <div className="growth-settings-grid"><label className="field"><span>Store address / slug</span><input value={cfg.slug} pattern="[a-z0-9][a-z0-9-]{2,47}" placeholder="city-grocery" onChange={e=>setCfg({...cfg,slug:e.target.value.toLowerCase().replace(/[^a-z0-9-]/g,'')})}/></label>
  <label className="field"><span>Store name</span><input value={cfg.title} maxLength={100} placeholder="Your retail brand" onChange={e=>setCfg({...cfg,title:e.target.value})}/></label>
  <label className="field growth-span"><span>Short introduction</span><textarea value={cfg.description} maxLength={500} rows={2} onChange={e=>setCfg({...cfg,description:e.target.value})}/></label></div>
  <div className="d-flex justify-content-between align-items-center flex-wrap gap-3"><label className="d-flex align-items-center gap-2"><input type="checkbox" checked={cfg.published} onChange={e=>setCfg({...cfg,published:e.target.checked})}/> Publish store to the public</label><button disabled={busy||!cfg.title.trim()||cfg.slug.length<3} className="primary" onClick={()=>void save()}><Check size={16}/> Save storefront</button></div>
  </section>
  <section className="panel"><div className="growth-section-title"><h3><Store size={18}/> Products available online</h3><span>{products.filter(p=>p.published).length} published</span></div><div className="growth-stack">{products.length?products.map(product=><div className="growth-listitem" key={product.id}><div><strong>{product.name}</strong><small>{product.sku} · Stock {product.stock} · {money(product.price)}</small></div><button disabled={busy} className={product.published?'secondary':'primary'} onClick={()=>void toggle(product)}>{product.published?'Unpublish':'Publish'}</button></div>):<p>No products found. Create products in Inventory first.</p>}</div></section>
  <section className="panel"><div className="growth-section-title"><h3><ClipboardList size={18}/> Online order requests</h3><div className="d-flex gap-2"><select className="form-select form-select-sm" value={status} onChange={e=>setStatus(e.target.value)}><option value="pending">Pending</option><option value="accepted">Accepted</option><option value="fulfilled">Fulfilled</option><option value="rejected">Rejected</option><option value="all">All</option></select><button className="secondary" onClick={()=>void load()} disabled={busy}><RefreshCw size={15}/></button></div></div>
  {orders.length?<div className="growth-stack">{orders.map(order=><div className="growth-listitem growth-order" key={order.id}><div><strong>{order.customer_name} · {money(order.total)}</strong><small>{order.customer_phone} · {new Date(order.created).toLocaleString()} · {order.status}</small><small>{order.items.map(i=>`${i.name} × ${i.quantity}`).join(' · ')}</small>{order.notes&&<small>Note: {order.notes}</small>}</div><div className="d-flex flex-wrap gap-2">{order.status==='pending'&&<><button className="primary" disabled={busy} onClick={()=>void action(order,'accept')}><Check size={14}/> Accept</button><button className="secondary" disabled={busy} onClick={()=>void action(order,'reject')}><X size={14}/> Reject</button></>}{order.status==='accepted'&&<button className="primary" disabled={busy} onClick={()=>void action(order,'fulfil')}>Link completed POS invoice</button>}</div></div>)}</div>:<p className="text-muted">No {status==='all'?'':status} orders yet.</p>}
  </section></div>
}
