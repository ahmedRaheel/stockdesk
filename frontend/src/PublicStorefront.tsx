import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ArrowRight, Minus, Package, Plus, Search, ShieldCheck, ShoppingBag, Store, X } from "lucide-react";
import { api, send } from "./api";
import { newRequestId } from "./requestId";
import "./growth-suite.css";
type Product={id:string;sku:string;name:string;price:number;stock:number;barcode:string;featured:boolean};
type Catalog={store:{slug:string;title:string;description:string;currency:string};items:Product[];order_mode:string};
export default function PublicStorefront(){
 const slug=decodeURIComponent(window.location.pathname.replace(/^\/shop\//,'').split('/')[0]);
 const [catalog,setCatalog]=useState<Catalog|null>(null),[cart,setCart]=useState<Record<string,number>>({}),[query,setQuery]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [name,setName]=useState(''),[phone,setPhone]=useState(''),[email,setEmail]=useState(''),[notes,setNotes]=useState('');
 const [confirmation,setConfirmation]=useState<{id:string;message:string}|null>(null);
 const [requestId,setRequestId]=useState(()=>newRequestId());
 const load=useCallback(async()=>{setError('');try{setCatalog(await api<Catalog>(`/api/storefronts/${encodeURIComponent(slug)}`))}catch(e){setError((e as Error).message)}},[slug]);
 useEffect(()=>{void load()},[load]);
 function change(id:string,quantity:number,max:number){setCart(old=>{const next={...old};if(quantity<=0)delete next[id];else next[id]=Math.min(max,quantity);return next})}
 const selected=(catalog?.items||[]).filter(p=>!!cart[p.id]);
 const total=selected.reduce((sum,p)=>sum+p.price*cart[p.id],0);
 const formatter=new Intl.NumberFormat('en',{style:'currency',currency:catalog?.store.currency||'PKR'});
 const money=(minor:number)=>formatter.format(minor/100);
 async function submit(e:FormEvent){e.preventDefault();if(!selected.length||busy)return;setBusy(true);setError('');try{const response=await send<{id:string;message:string}>(`/api/storefronts/${encodeURIComponent(slug)}/orders`,{request_id:requestId,customer_name:name,customer_phone:phone,customer_email:email,notes,items:selected.map(p=>({product:p.id,quantity:cart[p.id]}))});setConfirmation(response);setCart({});setRequestId(newRequestId())}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <div className="public-shop"><header className="shop-bar"><a href="/" className="shop-logo"><span><Store size={21}/></span> {catalog?.store.title||'StockDesk Store'}</a><span className="shop-trust"><ShieldCheck size={16}/> Pickup requests · Pay at store</span></header>
 <div className="shop-container"><section className="shop-hero"><span className="growth-kicker">SHOP LOCAL, SHOP SMART</span><h1>{catalog?.store.title||'Your neighborhood store'}</h1><p>{catalog?.store.description||'Browse available items and request pickup from your local retailer.'}</p><span className="shop-hero-pill"><ShoppingBag size={15}/> Live product catalog</span></section>
 {error&&<div className="alert alert-danger" role="alert">{error}</div>}
 {confirmation&&<div className="shop-success"><ShieldCheck size={24}/><div><strong>Order request received</strong><p>{confirmation.message}</p><small>Reference: {confirmation.id}</small></div><button className="secondary" onClick={()=>setConfirmation(null)}><X size={15}/></button></div>}
 <div className="shop-content"><section><div className="shop-products-head"><div><h2>Browse products</h2><p>Prices and quantities are refreshed when you open the catalog. Availability is confirmed by staff.</p></div><label className="shop-search"><Search size={16}/><input aria-label="Search products" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search by name or SKU"/></label></div>
 <div className="shop-products">{catalog?.items.filter(p=>(p.name+' '+p.sku).toLowerCase().includes(query.toLowerCase())).map((p,i)=><article className="shop-card" key={p.id}><div className={`shop-image shop-image-${i%4}`}><Package size={40}/>{p.featured&&<span>Featured</span>}</div><div className="shop-card-body"><small>{p.sku}</small><h3>{p.name}</h3><p>Available: {p.stock} units</p><div className="shop-card-foot"><strong>{money(p.price)}</strong><div className="shop-qty">{(cart[p.id]||0)>0&&<button aria-label={`Remove one ${p.name}`} onClick={()=>change(p.id,(cart[p.id]||0)-1,p.stock)}><Minus size={14}/></button>}<span>{cart[p.id]||''}</span><button aria-label={`Add ${p.name}`} onClick={()=>change(p.id,(cart[p.id]||0)+1,p.stock)}><Plus size={14}/></button></div></div></div></article>)}
 {!catalog&&<p>Loading products…</p>}{catalog&&catalog.items.length===0&&<p className="text-muted">No products are published yet.</p>}</div></section>
 <aside className="shop-checkout"><h2><ShoppingBag size={21}/> Pickup request</h2><p>Reserve your shopping list for review. Your store will confirm it before collection.</p>
 {selected.length?<div className="shop-cart">{selected.map(p=><div key={p.id}><span>{p.name}<small>{cart[p.id]} × {money(p.price)}</small></span><strong>{money(p.price*cart[p.id])}</strong></div>)}</div>:<div className="shop-cart-empty"><ShoppingBag size={32}/><span>Your bag is empty.</span></div>}
 <div className="shop-total"><span>Estimated total</span><strong>{money(total)}</strong></div>
 <form onSubmit={submit}><label>Full name<input required maxLength={150} value={name} onChange={e=>setName(e.target.value)} placeholder="Your name"/></label><label>Mobile number<input required minLength={6} maxLength={30} value={phone} onChange={e=>setPhone(e.target.value)} placeholder="Mobile for confirmation"/></label><label>Email (optional)<input type="email" maxLength={254} value={email} onChange={e=>setEmail(e.target.value)} placeholder="name@example.com"/></label><label>Pickup notes (optional)<textarea maxLength={500} rows={2} value={notes} onChange={e=>setNotes(e.target.value)}/></label><button className="primary" type="submit" disabled={busy||selected.length===0}> {busy?'Submitting…':'Request pickup'} <ArrowRight size={16}/></button></form>
 <small className="shop-policy">No online payment is collected. Submitting this form does not guarantee stock reservation or a confirmed sale.</small></aside></div>
 </div><footer className="shop-footer">Powered by StockDesk · Retail made simpler</footer></div>
}
