import {useEffect,useState} from 'react';
import {api,send} from './api';
import {newRequestId} from './requestId';

type Plan={id:string;code:string;name:string;monthly_price:number;currency:string;max_stores:number};
type Current={status:string;plan_name:string;ends:string}|null;
export default function BillingSettings({tenant}:{tenant:string}) {
  const [plans,setPlans]=useState<Plan[]>([]),[current,setCurrent]=useState<Current>(null),
    [busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{api<{items:Plan[];subscription:Current}>(`/api/v1/tenants/${tenant}/billing/plans`)
    .then(v=>{setPlans(v.items);setCurrent(v.subscription);}).catch(e=>setError(String(e)));},[tenant]);
  async function checkout(plan:Plan){
    setError('');setBusy(true);
    try {
      const result=await send<{url:string}>(`/api/v1/tenants/${tenant}/billing/checkout`,{
        plan:plan.id,request:newRequestId()});
      if(!result.url.startsWith('https://checkout.stripe.com/')) throw Error('Invalid payment checkout destination');
      window.location.assign(result.url);
    }catch(e){setError(e instanceof Error?e.message:'Unable to open checkout');setBusy(false);}
  }
  return <section className="panel mt-4"><div className="panel-heading"><h2>Subscription & billing</h2></div>
    <p>Subscriptions are activated by verified payment-provider events, not the browser returning from checkout.</p>
    {current&&<p className="alert alert-info mb-3"><strong>{current.plan_name}:</strong> {current.status} · Period ends {new Date(current.ends).toLocaleDateString()}</p>}
    {plans.length===0?<p className="hint">No live billing plans are configured. Your platform administrator must connect a matching Stripe price.</p>:
      <div className="row g-3">{plans.map(plan=><div className="col-md-6" key={plan.id}><div className="border rounded-3 p-3 h-100">
        <h3 className="h5">{plan.name}</h3>
        <p>{new Intl.NumberFormat('en',{style:'currency',currency:plan.currency}).format(plan.monthly_price/100)} / month</p>
        <small>Up to {plan.max_stores} stores</small><div className="mt-3">
          <button className="primary" disabled={busy} onClick={()=>checkout(plan)}>Subscribe securely</button></div>
      </div></div>)}</div>}
    {error&&<div className="alert alert-danger mt-3" role="alert">{error}</div>}
  </section>;
}
