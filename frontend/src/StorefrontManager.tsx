import { useCallback, useEffect, useState } from 'react';
import { Camera, Check, ClipboardList, ExternalLink, Globe2, ImagePlus, RefreshCw, Store, Trash2, X } from 'lucide-react';
import { api, send } from './api';

type Product = {
  id: string; sku: string; name: string; stock: number; price: number;
  published: boolean; featured: boolean; sort_order: number; has_image: boolean; image_updated?: string;
};
type Settings = { slug: string; title: string; description: string; published: boolean };
type Order = {
  id: string; customer_name: string; customer_phone: string; notes: string;
  total: number; currency: string; status: string; created: string; sale_id?: string;
  items: { name: string; quantity: string; unit_price: number }[];
};

function readImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result ?? '');
      const base64 = value.split(',')[1];
      if (!base64) reject(new Error('Could not read this product photo.'));
      else resolve(base64);
    };
    reader.onerror = () => reject(new Error('Could not read this product photo.'));
    reader.readAsDataURL(file);
  });
}

export default function StorefrontManager({ tenant, currency }: { tenant: string; currency: string }) {
  const [settings, setSettings] = useState<Settings>({ slug: '', title: '', description: '', published: false });
  const [products, setProducts] = useState<Product[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [status, setStatus] = useState('pending');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const base = `/api/v1/tenants/${encodeURIComponent(tenant)}/storefront`;
  const money = (value: number) => new Intl.NumberFormat('en', { style: 'currency', currency }).format(value / 100);
  const storeUrl = settings.slug ? `${window.location.origin}/shop/${settings.slug}` : '';
  const publishedCount = products.filter(product => product.published).length;

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [s, o] = await Promise.all([
        api<{ settings: Settings | null; products: Product[] }>(base),
        api<{ items: Order[] }>(`${base}/orders?status=${status}`),
      ]);
      setSettings(s.settings ?? { slug: '', title: '', description: '', published: false });
      setProducts(s.products);
      setOrders(o.items);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [base, status]);

  useEffect(() => { void load(); }, [load]);

  async function perform(action: () => Promise<string>) {
    setBusy(true); setError(''); setNotice('');
    try { setNotice(await action()); await load(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function save() {
    await perform(async () => {
      await send(base, settings, 'PUT');
      return settings.published ? 'Your storefront is live. Share its link with customers.' : 'Storefront saved as an unpublished draft.';
    });
  }

  async function toggle(product: Product) {
    await perform(async () => {
      await send(`${base}/products/${encodeURIComponent(product.id)}`,
        { published: !product.published, featured: product.featured, sort_order: product.sort_order }, 'PUT');
      return `${product.name} ${product.published ? 'unpublished' : 'published'} successfully.`;
    });
  }

  async function uploadPhoto(product: Product, file?: File) {
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setError('Choose a JPEG, PNG or WebP photo.'); return;
    }
    if (file.size > 2_000_000) { setError('Product photos must be 2 MB or smaller.'); return; }
    await perform(async () => {
      const image_base64 = await readImage(file);
      await send(`${base}/products/${encodeURIComponent(product.id)}/image`, { image_base64 }, 'PUT');
      return `Photo saved for ${product.name}.`;
    });
  }

  async function deletePhoto(product: Product) {
    if (!window.confirm(`Remove the storefront photo for ${product.name}?`)) return;
    await perform(async () => {
      await api(`${base}/products/${encodeURIComponent(product.id)}/image`, { method: 'DELETE' });
      return `Photo removed for ${product.name}.`;
    });
  }

  async function decide(order: Order, operation: 'accept' | 'reject' | 'fulfil') {
    const sale_id = operation === 'fulfil'
      ? window.prompt('Enter the ID of the completed POS invoice matching this order:') : null;
    if (operation === 'fulfil' && !sale_id) return;
    await perform(async () => {
      await send(`${base}/orders/${order.id}/${operation}`,
        operation === 'fulfil' ? { sale_id } : {});
      return `Order ${operation === 'fulfil' ? 'fulfilled' : operation + 'ed'} successfully.`;
    });
  }

  return <div className="growth-suite storefront-admin">
    <section className="panel growth-hero storefront-admin-hero">
      <div className="growth-kicker"><Globe2 size={14} /> YOUR DIGITAL SHOP</div>
      <div className="growth-section-title mb-0">
        <div>
          <h2>Make your store everyone's next stop.</h2>
          <p>Publish your catalog, share your link, and convert browsers into pickup customers—without an online payment setup.</p>
        </div>
        <div className="storefront-hero-actions">
          <span className={`badge ${settings.published ? 'text-bg-success' : 'text-bg-secondary'}`}>
            {settings.published ? 'Public store live' : 'Unpublished draft'}
          </span>
          {storeUrl && <a className="secondary" href={storeUrl} target="_blank" rel="noopener noreferrer">
            Preview store <ExternalLink size={15} />
          </a>}
        </div>
      </div>
      <div className="storefront-stats">
        <div><strong>{publishedCount}</strong><span>Products online</span></div>
        <div><strong>{orders.filter(order => order.status === 'pending').length}</strong><span>Requests in this view</span></div>
        <div><strong>{products.filter(product => product.has_image).length}</strong><span>Product photos</span></div>
      </div>
    </section>

    {error && <div className="alert alert-danger" role="alert">{error}</div>}
    {notice && <div className="alert alert-success" role="status">{notice}</div>}

    <section className="panel">
      <div className="growth-section-title"><h3><Store size={18} /> Brand settings</h3><span>Changes require Save</span></div>
      <div className="growth-settings-grid">
        <label className="field"><span>Store link</span><input value={settings.slug} pattern="[a-z0-9][a-z0-9-]{2,47}" placeholder="city-grocery" onChange={e => setSettings({ ...settings, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '') })} /></label>
        <label className="field"><span>Display name</span><input value={settings.title} maxLength={100} placeholder="Your retail brand" onChange={e => setSettings({ ...settings, title: e.target.value })} /></label>
        <label className="field growth-span"><span>Customer introduction</span><textarea value={settings.description} maxLength={500} rows={2} placeholder="Tell customers what makes your shop special." onChange={e => setSettings({ ...settings, description: e.target.value })} /></label>
      </div>
      <div className="d-flex justify-content-between align-items-center flex-wrap gap-3 mt-3">
        <label className="d-flex align-items-center gap-2"><input type="checkbox" checked={settings.published} onChange={e => setSettings({ ...settings, published: e.target.checked })} /> Publish storefront</label>
        <button disabled={busy || !settings.title.trim() || settings.slug.length < 3} className="primary" onClick={() => void save()}><Check size={16} /> Save storefront</button>
      </div>
      {storeUrl && <p className="storefront-share-link">Shareable URL: <a href={storeUrl} target="_blank" rel="noopener noreferrer">{storeUrl}</a></p>}
    </section>

    <section className="panel">
      <div className="growth-section-title"><div><h3><ImagePlus size={18} /> Online product showcase</h3><span>Photograph your top products for a richer customer experience.</span></div><span className="growth-pill">{publishedCount} published</span></div>
      <div className="storefront-product-list">
        {products.map(product => <div className="storefront-product-row" key={product.id}>
          <div className="storefront-thumb">
            {product.has_image ? <img loading="lazy" alt="" src={`${base}/products/${encodeURIComponent(product.id)}/image?v=${encodeURIComponent(product.image_updated ?? "")}`} /> : <Camera size={23} />}
          </div>
          <div className="storefront-product-name"><strong>{product.name}</strong><small>{product.sku} · Stock {product.stock} · {money(product.price)}</small></div>
          <div className="storefront-product-actions">
            <label className="secondary storefront-photo-upload" title="Upload a product image">
              <ImagePlus size={15} /> {product.has_image ? 'Replace photo' : 'Add photo'}
              <input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={event => { void uploadPhoto(product, event.target.files?.[0]); event.target.value = ''; }} />
            </label>
            {product.has_image && <button className="secondary" disabled={busy} title="Remove photo" aria-label={`Remove photo for ${product.name}`} onClick={() => void deletePhoto(product)}><Trash2 size={15} /></button>}
            <button disabled={busy} className={product.published ? 'secondary' : 'primary'} onClick={() => void toggle(product)}>{product.published ? 'Unpublish' : 'Publish'}</button>
          </div>
        </div>)}
        {!products.length && <p className="text-muted mb-0">No products found. Add products in Inventory first.</p>}
      </div>
    </section>

    <section className="panel">
      <div className="growth-section-title"><h3><ClipboardList size={18} /> Customer pickup requests</h3><div className="d-flex gap-2"><select className="form-select form-select-sm" value={status} onChange={e => setStatus(e.target.value)} aria-label="Filter orders"><option value="pending">Pending</option><option value="accepted">Accepted</option><option value="fulfilled">Fulfilled</option><option value="rejected">Rejected</option><option value="all">All</option></select><button className="secondary" onClick={() => void load()} disabled={busy} aria-label="Refresh orders"><RefreshCw size={15} /></button></div></div>
      {orders.length ? <div className="growth-stack">{orders.map(order => <div className="growth-listitem growth-order" key={order.id}>
        <div><strong>{order.customer_name} · {money(order.total)}</strong><small>{order.customer_phone} · {new Date(order.created).toLocaleString()} · {order.status}</small><small>{order.items.map(item => `${item.name} × ${item.quantity}`).join(' · ')}</small>{order.notes && <small>Note: {order.notes}</small>}</div>
        <div className="d-flex flex-wrap gap-2">{order.status === 'pending' && <><button className="primary" disabled={busy} onClick={() => void decide(order, 'accept')}><Check size={14} /> Accept</button><button className="secondary" disabled={busy} onClick={() => void decide(order, 'reject')}><X size={14} /> Reject</button></>}{order.status === 'accepted' && <button className="primary" disabled={busy} onClick={() => void decide(order, 'fulfil')}>Link completed POS invoice</button>}</div>
      </div>)}</div> : <p className="text-muted">No {status === 'all' ? '' : status} orders yet.</p>}
      <p className="growth-disclaimer mt-3 mb-0">Order requests do not reserve stock or charge customers. Link a matching, completed POS sale to mark an order fulfilled.</p>
    </section>
  </div>;
}
