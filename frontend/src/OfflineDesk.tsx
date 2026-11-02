import { useEffect, useState } from 'react';
import { AlertTriangle, CloudUpload, HardDrive, RefreshCw, Trash2 } from 'lucide-react';
import { api, send } from './api';
import { newRequestId } from './requestId';

// Drafts are scoped by tenant AND authenticated user. This is not offline authorization.
type Device = { id: string; name: string; active: boolean };
type Draft = { id: string; tenant: string; owner: string; device: string; created: string; sale: Record<string, unknown>; error?: string };
const DB = 'stockdesk-local-drafts-v1';
function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains('drafts')) request.result.createObjectStore('drafts', { keyPath: 'id' }); };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function transaction<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = db.transaction('drafts', mode);
      const req = action(tx.objectStore('drafts'));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
      tx.onerror = () => reject(tx.error);
    });
  } finally { db.close(); }
}
export default function OfflineDesk({ tenant, owner }: { tenant: string; owner: string }) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [device, setDevice] = useState('');
  const [name, setName] = useState('Register terminal');
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [json, setJson] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  const base = `/api/v1/tenants/${tenant}`;
  async function loadLocal() {
    const all = await transaction<Draft[]>('readonly', store => store.getAll());
    setDrafts(all.filter(item => item.tenant === tenant && item.owner === owner).sort((a,b) => b.created.localeCompare(a.created)));
  }
  async function loadDevices() {
    const result = await api<{items: Device[]}>(`${base}/offline/devices`);
    setDevices(result.items);
    setDevice(previous => result.items.some(d => d.id === previous && d.active) ? previous : result.items.find(d => d.active)?.id || '');
  }
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener('online', update); window.addEventListener('offline', update);
    loadLocal().catch(e => setError(e.message));
    if (navigator.onLine) loadDevices().catch(e => setError(e.message));
    return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update); };
  }, [tenant, owner]);
  async function perform(fn: () => Promise<void>) {
    setError(''); setMessage(''); setBusy(true);
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : 'Operation failed'); } finally { setBusy(false); }
  }
  async function register() {
    await perform(async () => {
      const added = await send<{id:string}>(`${base}/offline/devices`, {name: name.trim()});
      await loadDevices(); setDevice(added.id); setMessage('Terminal registered for your account.');
    });
  }
  async function saveDraft() {
    await perform(async () => {
      if (!device) throw Error('Connect and register a terminal before creating drafts.');
      const sale = JSON.parse(json) as Record<string, unknown>;
      if (!sale || Array.isArray(sale) || !Array.isArray(sale.items) || !sale.items.length || typeof sale.expected !== 'number')
        throw Error('Provide a checkout object with items and expected total (integer minor currency units).');
      // Strip caller-supplied IDs; one stable operation and checkout request ID survive retries.
      const id = newRequestId();
      const draft: Draft = { id, tenant, owner, device, created: new Date().toISOString(), sale: {...sale, request: id} };
      await transaction('readwrite', store => store.put(draft));
      setJson(''); await loadLocal(); setMessage('Draft saved locally. No payment or sale has been posted.');
    });
  }
  async function remove(item: Draft) {
    await perform(async () => { await transaction('readwrite', store => store.delete(item.id)); await loadLocal(); setMessage('Local draft discarded.'); });
  }
  async function replay(item: Draft) {
    if (!online || !window.confirm('Submit this draft to the server? Prices, stock, tax and permissions will be checked again. A successful replay creates a real sale.')) return;
    await perform(async () => {
      try {
        const result = await send<{status:string}>(`${base}/offline/devices/${item.device}/replay`, {operation_id: item.id, sale: item.sale});
        if (result.status !== 'accepted') throw Error(`Unexpected replay status: ${result.status}`);
        await transaction('readwrite', store => store.delete(item.id));
        await loadLocal(); setMessage('Sale accepted by server. Verify the issued receipt before completing handover.');
      } catch (e) {
        const updated = {...item, error: e instanceof Error ? e.message : 'Unknown conflict'};
        await transaction('readwrite', store => store.put(updated)); await loadLocal();
        throw e;
      }
    });
  }
  return <div className="offline-desk container-fluid px-0">
    <div className="alert alert-warning d-flex align-items-start gap-2" role="note"><AlertTriangle size={19}/><div><strong>Controlled local drafts — not offline checkout.</strong> Drafts only become sales after server acceptance. Do not take payment while disconnected. Browser storage is unencrypted and may be cleared; avoid entering customer payment information. Server verification, stock checks and receipts require connectivity.</div></div>
    <div className="row g-4">
      <div className="col-12 col-xl-5"><section className="panel h-100"><div className="d-flex align-items-center justify-content-between mb-3"><h2><HardDrive size={18}/> Terminal registration</h2><span className={`badge ${online?'text-bg-success':'text-bg-secondary'}`}>{online?'Network available':'Offline'}</span></div>
        <p>Devices belong to the signed-in cashier and selected business.</p><label className="field">Registered terminal<select value={device} onChange={e=>setDevice(e.target.value)}><option value="">Choose terminal</option>{devices.filter(d=>d.active).map(d=><option value={d.id} key={d.id}>{d.name}</option>)}</select></label>
        <div className="d-flex gap-2 mt-3"><input aria-label="Terminal name" maxLength={100} value={name} onChange={e=>setName(e.target.value)}/><button className="primary" disabled={busy||!online||!name.trim()} onClick={register}>Register</button><button className="secondary" disabled={busy||!online} onClick={()=>perform(loadDevices)} aria-label="Refresh devices"><RefreshCw size={16}/></button></div>
      </section></div>
      <div className="col-12 col-xl-7"><section className="panel h-100"><h2>Local checkout draft</h2><p>For technical recovery and supervised testing, paste a checkout request JSON object generated by your POS workflow. The server validates it during replay.</p>
        <label className="field">Checkout JSON<textarea rows={6} className="form-control font-monospace" placeholder='{"items":[{"id":"product-id","quantity":1}],"expected":1000,"payment":"cash","tendered":1000}' value={json} onChange={e=>setJson(e.target.value)}/></label>
        <button className="primary mt-3" disabled={busy||!device||!json.trim()} onClick={saveDraft}>Save draft locally</button></section></div>
    </div>
    <section className="panel mt-4"><div className="d-flex align-items-center justify-content-between flex-wrap gap-2"><h2>Pending local drafts <span className="badge text-bg-light">{drafts.length}</span></h2><button className="secondary" onClick={()=>perform(loadLocal)} disabled={busy}><RefreshCw size={16}/> Refresh</button></div>
      {drafts.length===0?<p className="py-3 mb-0">No locally saved drafts for this account and business.</p>:<div className="table-responsive"><table className="table align-middle"><thead><tr><th>Created</th><th>Items</th><th>Expected total</th><th>State</th><th>Actions</th></tr></thead><tbody>{drafts.map(item=><tr key={item.id}><td>{new Date(item.created).toLocaleString()}</td><td>{Array.isArray(item.sale.items)?item.sale.items.length:'—'}</td><td>{String(item.sale.expected)}</td><td>{item.error?<span className="text-danger">Conflict: {item.error}</span>:'Awaiting confirmation'}</td><td><div className="d-flex gap-2"><button className="primary" disabled={busy||!online} onClick={()=>replay(item)}><CloudUpload size={16}/> Verify & submit</button><button className="secondary" disabled={busy} onClick={()=>remove(item)} aria-label="Discard draft"><Trash2 size={16}/></button></div></td></tr>)}</tbody></table></div>}
    </section>{error&&<div className="alert alert-danger" role="alert">{error}</div>}{message&&<div className="alert alert-success" role="status">{message}</div>}
  </div>;
}
