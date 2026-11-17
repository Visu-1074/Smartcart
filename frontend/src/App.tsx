import { FormEvent, useEffect, useMemo, useState } from 'react'
import { ArrowRight, CheckCircle2, History, Minus, PackageCheck, Plus, Search, ScanLine, ShoppingBag, ShoppingCart, Sparkles, Trash2 } from 'lucide-react'
import { api, CatalogProduct, CartItem, CartPlatform, CheckoutPlatform, Listing, Order, PlatformStatus, streamSearch } from './api'
import BarcodeScanner from './BarcodeScanner'

type Page = 'search' | 'cart' | 'orders'
type Suggestion = { rows: { listing: Listing | CartItem; quantity: number; variant: string }[]; subtotal: number; fees: number; total: number }
const retailerPicks = [
  { name: 'Blue Tokai Vienna Roast Coffee Beans', detail: 'Whole bean coffee · 250 g', retailer: 'Blinkit', image: 'https://cdn.grofers.com/app/images/products/sliding_image/501450a.jpg', url: 'https://blinkit.com/prn/blue-tokai-vienna-roast-coffee-beans/prid/501450', note: 'Open Blinkit to see its current price and availability.' },
  { name: 'Minimalist SPF 50 PA++++ Sunscreen', detail: 'Broad-spectrum sunscreen · 50 g', retailer: 'Apollo Pharmacy', image: 'https://images.apollo247.in/uatpharma/pub/media/catalog/product/M/I/MIN0588_1-AUG23_1.jpg', url: 'https://perfmedicine.apollopharmacy.in/otc/minimalist-spf-50-pa-sunscreen-cream-50g', note: 'Apollo shows current offers and delivery availability.' },
]

export default function App() {
  const [page, setPage] = useState<Page>('search')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('all')
  const [categories, setCategories] = useState<{ id: string; label: string }[]>([])
  const [platformInfo, setPlatformInfo] = useState<{ id: string; name: string; mode: string; api_source?: string; data_source?: string; color: string; delivery_fee: number; free_delivery_threshold: number }[]>([])
  const [includeDemo, setIncludeDemo] = useState(true)
  const [results, setResults] = useState<Listing[]>([])
  const [catalogProducts, setCatalogProducts] = useState<CatalogProduct[]>([])
  const [platformStatuses, setPlatformStatuses] = useState<PlatformStatus[]>([])
  const [cart, setCart] = useState<CartItem[]>([])
  const [cartPlatforms, setCartPlatforms] = useState<CartPlatform[]>([])
  const [cartTotal, setCartTotal] = useState(0)
  const [orders, setOrders] = useState<Order[]>([])
  const [variants, setVariants] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [scanner, setScanner] = useState(false)
  const [toast, setToast] = useState('')
  const [sheet, setSheet] = useState<{ name: string; rows: Listing[] } | null>(null)
  const [selectedProduct, setSelectedProduct] = useState<Listing | null>(null)
  const [checkout, setCheckout] = useState<CheckoutPlatform[]>([])

  const refreshCart = async () => {
    try {
      const data = await api.cart()
      setCart(data.items); setCartPlatforms(data.platforms); setCartTotal(data.total)
    } catch (e) { setError(message(e)) }
  }
  useEffect(() => {
    void refreshCart()
    void api.platforms().then(data => { setCategories(data.categories); setPlatformInfo(data.platforms) }).catch(e => setError(message(e)))
    void api.orders().then(setOrders).catch(() => {})
  }, [])

  const runSearch = async (event?: FormEvent, useDemo = includeDemo, searchTerm = query, searchCategory = category) => {
    event?.preventDefault()
    if (!searchTerm.trim() && searchCategory === 'all') return
    setLoading(true); setError(''); setResults([]); setCatalogProducts([]); setPlatformStatuses([])
    try {
      const completed = await streamSearch(searchTerm.trim(), searchCategory, '', useDemo, (rows, statuses) => { setResults(rows); setPlatformStatuses(statuses) })
      setResults(completed.results); setPlatformStatuses(completed.statuses)
      if (searchTerm.trim()) {
        const catalog = await api.catalogSearch(searchTerm.trim(), searchCategory)
        setCatalogProducts(catalog.results)
      }
    } catch (e) { setError(message(e)) } finally { setLoading(false) }
  }
  const selectCategory = (id: string) => {
    setCategory(id); setPage('search'); setSheet(null); setSelectedProduct(null)
    if (id === 'all' && !query.trim()) {
      setResults([]); setCatalogProducts([]); setPlatformStatuses([]); setError(''); return
    }
    void runSearch(undefined, includeDemo, query, id)
  }
  const runDemo = async () => {
    setQuery('headphones'); setCategory('all'); setIncludeDemo(true); setPage('search')
    setLoading(true); setError(''); setResults([]); setCatalogProducts([]); setPlatformStatuses([])
    try {
      const completed = await streamSearch('headphones', 'all', '', true, (rows, statuses) => { setResults(rows); setPlatformStatuses(statuses) })
      setResults(completed.results); setPlatformStatuses(completed.statuses)
    } catch (e) { setError(message(e)) } finally { setLoading(false) }
  }
  const add = async (row: Listing) => {
    const variant = variants[row.id] ?? ''
    if (row.variants.length && !variant) { setError('Choose a size or colour before adding this item.'); return }
    try {
      await api.add(row, variant, ''); await refreshCart(); setToast(`Added to cart from ${row.platform_name}`); window.setTimeout(() => setToast(''), 2500); setSheet(null); setSelectedProduct(null); setError('')
    } catch (e) { setError(message(e)) }
  }
  const update = async (id: number, quantity: number) => { if (quantity < 1) return; try { await api.quantity(id, quantity); await refreshCart() } catch (e) { setError(message(e)) } }
  const remove = async (id: number) => { try { await api.remove(id); await refreshCart() } catch (e) { setError(message(e)) } }
  const scanned = async (code: string, continuous = false) => {
    if (!continuous) setScanner(false)
    setLoading(true); setError('')
    try { const data = await api.scan(code, '', includeDemo); setQuery(data.product_name); setResults(data.results); setPlatformStatuses(data.platforms); setCategory(data.category); setSheet(data.results.length ? { name: data.product_name, rows: data.results } : null); setPage('search') }
    catch (e) { setError(message(e)) } finally { setLoading(false) }
  }
  const beginCheckout = async () => { try { const data = await api.checkout(); setCheckout(data.platforms); setOrders(await api.orders()) } catch (e) { setError(message(e)) } }
  const saveAmazonSession = async (sessionId: string) => { try { await api.saveAmazonSession(sessionId); setCheckout(previous => previous.map(item => item.session_id === sessionId ? { ...item, session_id: undefined } : item)); setToast('Amazon session saved encrypted on this device'); window.setTimeout(() => setToast(''), 2800) } catch (e) { setError(message(e)) } }
  const goto = (next: Page) => { setScanner(false); setSheet(null); setPage(next); if (next === 'orders') void api.orders().then(setOrders) }
  const goHome = () => { setScanner(false); setSheet(null); setSelectedProduct(null); setPage('search'); setQuery(''); setCategory('all'); setResults([]); setCatalogProducts([]); setPlatformStatuses([]); setError(''); setLoading(false); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  const groupCart = useMemo(() => cart.reduce<Record<string, CartItem[]>>((groups, item) => { (groups[item.platform] ??= []).push(item); return groups }, {}), [cart])
  const suggestion = useMemo<Suggestion | null>(() => {
    if (!cart.length) return null
    const unique = new Map<string, CartItem>()
    for (const item of cart) if (!unique.has(item.product_id)) unique.set(item.product_id, item)
    const currentSubtotals = new Map<string, number>()
    const rows: Suggestion['rows'] = []
    const deliveryFor = (platformId: string, subtotal: number) => {
      const config = platformInfo.find(platform => platform.id === platformId)
      return !config ? 0 : config.free_delivery_threshold > 0 && subtotal >= config.free_delivery_threshold ? 0 : config.delivery_fee
    }
    for (const item of unique.values()) {
      const alternatives = results.filter(row => row.price_is_current !== false && row.same_product_id === item.product_id && (!item.variant || row.variants.length === 0 || row.variants.includes(item.variant)))
      const candidates: (Listing | CartItem)[] = [...alternatives, item]
      const picked = candidates.sort((a, b) => {
        const aSubtotal = currentSubtotals.get(a.platform) ?? 0, bSubtotal = currentSubtotals.get(b.platform) ?? 0
        const aMarginal = a.price * item.quantity + deliveryFor(a.platform, aSubtotal + a.price * item.quantity) - deliveryFor(a.platform, aSubtotal)
        const bMarginal = b.price * item.quantity + deliveryFor(b.platform, bSubtotal + b.price * item.quantity) - deliveryFor(b.platform, bSubtotal)
        return aMarginal - bMarginal
      })[0]
      rows.push({ listing: picked, quantity: item.quantity, variant: item.variant })
      currentSubtotals.set(picked.platform, (currentSubtotals.get(picked.platform) ?? 0) + picked.price * item.quantity)
    }
    const byPlatform = new Map<string, number>()
    for (const row of rows) byPlatform.set(row.listing.platform, (byPlatform.get(row.listing.platform) ?? 0) + row.listing.price * row.quantity)
    let fees = 0
    for (const [id, subtotal] of byPlatform) {
      fees += deliveryFor(id, subtotal)
    }
    const subtotal = rows.reduce((sum, row) => sum + row.listing.price * row.quantity, 0)
    return { rows, subtotal, fees, total: subtotal + fees }
  }, [cart, results, platformInfo])

  return <div className="app-shell">
    <header className="topbar"><div className="brand" role="button" tabIndex={0} onClick={goHome} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') goHome() }}><div className="brand-icon"><ShoppingBag size={19}/></div><span>smart<span className="brand-accent">cart</span></span></div><nav className="category-navigation" aria-label="Shop by category">{(categories.length ? categories.filter(item => item.id !== 'all') : [{ id: 'grocery_quick_commerce', label: 'Grocery' }, { id: 'electronics', label: 'Electronics' }, { id: 'fashion', label: 'Fashion' }, { id: 'beauty', label: 'Beauty' }, { id: 'pharmacy', label: 'Pharmacy' }, { id: 'home_furniture', label: 'Home' }, { id: 'books', label: 'Books' }, { id: 'baby_kids', label: 'Baby' }]).map(item => <button type="button" key={item.id} className={category === item.id ? 'active' : ''} aria-current={category === item.id ? 'page' : undefined} onClick={() => selectCategory(item.id)}>{item.label}</button>)}</nav><div className="topbar-actions"><button className="header-orders" onClick={() => goto('orders')}><History size={16}/><span>Orders</span></button><button className="cart-shortcut" onClick={() => goto('cart')} aria-label="Open cart"><ShoppingCart size={17}/><span>Cart</span><b>{cart.reduce((n, i) => n + i.quantity, 0)}</b></button></div></header>
    <main>
      <section className="hero"><div className="eyebrow"><Sparkles size={14}/> INDIA-WIDE PRICE COMPARISON</div><h1>Find the best price.<br/><span>Everywhere.</span></h1><p>Compare Indian stores in one place and shop with confidence.</p>
        <form className="searchbar" onSubmit={runSearch}><Search size={20}/><input id="product-search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search a product, brand, or model…"/><button type="button" className="scan-button" onClick={() => setScanner(true)}><ScanLine size={17}/><span>Scan</span></button><button className="search-submit" type="submit"><span>Search</span><ArrowRight size={17}/></button></form>
        <div className="search-options"><label className="demo-toggle"><input type="checkbox" checked={includeDemo} onChange={e => { setIncludeDemo(e.target.checked); if (query.trim()) void runSearch(undefined, e.target.checked) }}/> Include demo listings</label><button className="mobile-scan" onClick={() => setScanner(true)} type="button"><ScanLine size={16}/> Scan with camera</button></div>
        <button className="demo-launch" type="button" onClick={() => void runDemo()}><Sparkles size={15}/> Start 2-minute demo <span>Headphones price comparison</span></button>
        <div className="api-ready-note">Search includes your imported Amazon India, Flipkart, BlinkIT and Zepto datasets. Their prices are historical or sample values, clearly labeled, and retailer links open for a current check.</div>
      </section>
      {page === 'search' && !query.trim() && <section className="retailer-picks"><div className="retailer-picks-head"><div><span className="eyebrow">REAL RETAILER LISTINGS</span><h2>Shop products you can actually find</h2></div><p>Open the retailer page for current price, stock and delivery options.</p></div><div className="retailer-picks-grid">{retailerPicks.map(product => <article className="retailer-pick" key={product.retailer}><div className="retailer-pick-image"><img src={product.image} alt={product.name} loading="lazy"/><span>Retailer verified page</span></div><div className="retailer-pick-info"><span className="retailer-name">{product.retailer}</span><h3>{product.name}</h3><p>{product.detail}</p><small>{product.note}</small><a href={product.url} target="_blank" rel="noreferrer">View live listing <ArrowRight size={15}/></a></div></article>)}</div></section>}
      <div className="content"><div className="section-head"><div><span className="eyebrow">SMART COMPARISON</span><h2>{page === 'search' ? 'Price comparison' : page === 'cart' ? 'Your cart' : 'Order history'}</h2></div>{page === 'cart' && <button className="outline" onClick={() => setScanner(true)}><ScanLine size={16}/> Scan with camera</button>}</div>
        {error && <div className="alert">{error}<button onClick={() => setError('')}>×</button></div>}
        {page === 'search' && <>
          {category === 'pharmacy' && <div className="notice pharmacy-notice">Prescription medicines require a valid prescription. SmartCart does not place orders for prescription-only drugs. Price comparisons are informational only; SmartCart does not provide health advice.</div>}
          {includeDemo && <div className="notice demo-notice"><b>Demo mode:</b> sample listings and prices are for demonstrating the app; they are not live retailer offers.</div>}
          {category === 'grocery_quick_commerce' && <div className="quick-search"><b>Popular grocery searches</b>{['biscuits','tea','rice','snacks'].map(term => <button key={term} onClick={() => { setQuery(term); void runSearch(undefined, includeDemo, term) }}>{term}</button>)}<small>Dataset and demo prices from BigBasket, JioMart, Blinkit, and Zepto are not live offers.</small></div>}
          {loading && <div className="loading"><span className="spinner"/>Finding the best prices…</div>}
          {results.some(row => row.price_is_current === false) && <div className="notice snapshot-notice"><b>Dataset prices are historical or sample values.</b> These imported records are useful for a product-search demo, but they are not current retailer offers. SmartCart will not add them to your cart; open the retailer to check today's listing.</div>}
          {platformStatuses.length > 0 && <div className="platform-statuses"><span>Stores with matches</span>{platformStatuses.filter(status => (status.count ?? 0) > 0 || status.status !== 'ok').map(status => <span title={status.reason} className={`status-chip ${status.status}`} key={status.platform}>{status.platform_name}: {status.status === 'ok' ? `${status.count} offers` : status.status === 'pincode_required' ? 'pincode needed' : status.status === 'blocked' ? 'blocked · mock fallback' : status.fallback === 'demo' ? 'demo offers · live API unavailable' : 'unavailable'}</span>)}{platformStatuses.some(status => status.status === 'ok' && (status.count ?? 0) === 0) && <small className="status-note">Stores with no matching products are hidden.</small>}</div>}
          {!loading && results.length === 0 && catalogProducts.length === 0 ? <div className="empty"><div className="empty-icon"><Search/></div><h3>{query ? (includeDemo ? 'No matching products yet' : 'No matching snapshot products') : 'Ready when you are'}</h3><p>{includeDemo ? 'No demo catalogue items match this search.' : 'The connected Amazon and Flipkart export covers smartphone listings captured in February 2023. Try searching Redmi, Samsung, or Xiaomi. Current prices still need a live retailer API.'}</p>{!includeDemo && <button className="secondary" onClick={() => { setIncludeDemo(true); if (query.trim()) void runSearch(undefined, true) }}>Show demo catalogue</button>}<div className="suggestions"><button onClick={() => { setQuery('Redmi'); void runSearch(undefined, includeDemo) }}>Redmi phones</button><button onClick={() => { setQuery('Samsung'); void runSearch(undefined, includeDemo) }}>Samsung phones</button></div></div> : results.length > 0 && <div className="results"><div className="results-meta"><span>{results.length} listings</span><span>Sorted by lowest listed price · snapshots marked</span></div>{results.map((row, index) => <article className={`product-card ${index === 0 ? 'best' : ''}`} key={row.id}>
            <img className="product-open-image" src={row.image_url} alt={`View details for ${row.title}`} onClick={() => setSelectedProduct(row)}/><div className="product-info">{index === 0 && row.price_is_current !== false && <span className="best-tag">BEST PRICE</span>}<h3 className="product-open-title" onClick={() => setSelectedProduct(row)}>{row.title}</h3><button className="detail-trigger" onClick={() => setSelectedProduct(row)}>View product details</button><span className="store-chip" title={row.data_source} style={{ '--store-color': row.platform_color } as React.CSSProperties}>{row.platform_name} <i/> {row.price_is_current === false ? 'Dataset' : row.mode}</span><span className="store">★ {row.rating.toFixed(1)} · {row.review_count.toLocaleString()} reviews <span>·</span> {row.price_is_current === false ? (row.snapshot_date || 'Dataset price') : row.delivery_eta}</span><span className={`availability ${row.price_is_current === false ? 'snapshot-availability' : ''}`}><i/> {row.availability}</span>{row.price_is_current !== false && <span className="match-badge">{Math.round(row.same_product_confidence * 100)}% same product match</span>}
              {row.warranty && <span className="product-extra">{row.warranty} · {row.emi_offer}</span>}{row.seller_name && <span className="product-extra">Seller: {row.seller_name}{row.seller_rating ? ` · ★ ${row.seller_rating}` : ''}</span>}{row.is_rx && <span className="rx-pill">Prescription required · informational only</span>}
            </div><div className="product-action"><div><strong>₹{row.price.toLocaleString('en-IN')}</strong>{row.price_is_current === false ? <span className="snapshot-price-label">Dataset price · not current</span> : <><del>MRP ₹{row.mrp.toLocaleString('en-IN')}</del><span className="discount">{row.discount_percent}% off</span></>}</div>{row.price_is_current === false ? <a className="add-btn" href={row.url} target="_blank" rel="noreferrer">Check retailer <ArrowRight size={14}/></a> : row.variants.length > 0 ? <select className="variant-select" value={variants[row.id] ?? ''} onChange={e => setVariants(value => ({ ...value, [row.id]: e.target.value }))}><option value="">Choose size / colour</option>{row.variants.map(variant => <option key={variant}>{variant}</option>)}</select> : row.is_rx ? <a className="add-btn" href={row.url} target="_blank" rel="noreferrer">Open retailer</a> : <button className="add-btn" onClick={() => void add(row)}><Plus size={16}/><span>Add</span></button>}</div>
          </article>)}</div>}
          {catalogProducts.length > 0 && <section className="catalog-section"><div className="catalog-heading"><div><span className="eyebrow">PRODUCT IDENTITY CATALOG</span><h3>Catalog product matches</h3></div><span>Open Food Facts · Open Beauty Facts · Supplied datasets</span></div><p>Catalog records can help identify products and show source photos. This section does not provide current prices or store availability.</p><div className="catalog-grid">{catalogProducts.map(product => <article className="catalog-card" key={`${product.source}-${product.code}`}>{product.image_url ? <img src={product.image_url} alt={product.title} loading="lazy"/> : <div className="catalog-no-image">No photo</div>}<div><span className="catalog-source">{product.source}</span><h4>{product.title}</h4>{product.brand && <span>{product.brand}</span>}<small>{[product.quantity, product.countries].filter(Boolean).join(' · ')}</small><a href={product.source_url} target="_blank" rel="noreferrer">View source record <ArrowRight size={13}/></a></div></article>)}</div></section>}
        </>}
        {page === 'cart' && <>{cart.length === 0 ? <div className="empty"><div className="empty-icon"><ShoppingCart/></div><h3>Your cart is waiting</h3><p>Add products from any store to bring them together here.</p><button className="primary" onClick={() => goto('search')}>Explore prices <ArrowRight size={16}/></button></div> : <div className="cart-layout"><div className="cart-groups">{Object.entries(groupCart).map(([platform, items]) => { const summary = cartPlatforms.find(group => group.platform === platform); return <section className="platform-group" key={platform}><h3><span className="store-mark">{(summary?.platform_name ?? platform).slice(0, 1)}</span>{summary?.platform_name ?? platform}<span className="count">{items.length} items</span></h3>{items.map(item => <div className="cart-row" key={item.id}><img src={item.image_url} alt=""/><div className="cart-title"><b>{item.title}</b>{item.variant && <span>Variant: {item.variant}</span>}<span>₹{item.price.toLocaleString('en-IN')} each</span>{item.is_rx && <span className="rx-pill">Rx · retailer prescription process required</span>}</div><div className="stepper"><button onClick={() => void update(item.id, item.quantity - 1)}><Minus size={14}/></button><span>{item.quantity}</span><button onClick={() => void update(item.id, item.quantity + 1)}><Plus size={14}/></button></div><b className="line-price">₹{(item.price * item.quantity).toLocaleString('en-IN')}</b><button className="icon-button" onClick={() => void remove(item.id)} aria-label="Remove item"><Trash2 size={16}/></button></div>)}<div className="platform-totals"><span>Subtotal <b>₹{summary?.subtotal.toLocaleString('en-IN') ?? '0'}</b></span><span>Delivery <b>{summary?.delivery_fee ? `₹${summary.delivery_fee}` : 'Free'}</b></span><span>Estimated total <b>₹{summary?.estimated_total.toLocaleString('en-IN') ?? '0'}</b></span></div></section> })}</div>
            <aside className="summary"><span className="eyebrow">ORDER SUMMARY</span><h3>One cart. Many stores.</h3><div className="summary-line"><span>Estimated total</span><b>₹{cartTotal.toLocaleString('en-IN')}</b></div>{suggestion && <div className="basket-suggestion"><b>Cheapest basket suggestion</b><span>₹{suggestion.total.toLocaleString('en-IN')} estimated total</span>{suggestion.rows.map(item => <small key={`${item.listing.product_id}-${item.listing.platform}`}>{item.listing.title} → {item.listing.platform_name} · ₹{item.listing.price.toLocaleString('en-IN')}</small>)}</div>}<p className="muted">Checkout is prepared separately for each marketplace. You’ll confirm payment on the store.</p><button className="primary full" onClick={() => void beginCheckout()}>Continue to checkout <ArrowRight size={16}/></button></aside></div>}</>}
        {page === 'orders' && (orders.length === 0 ? <div className="empty"><div className="empty-icon"><History/></div><h3>No orders yet</h3><p>Orders you prepare at each store will appear here.</p></div> : <div className="orders-list">{orders.map(order => <article className="order-card" key={order.id}><div className="order-head"><div><span className="store-mark">{order.platform.slice(0, 1)}</span><b>{order.platform}</b></div><span className="status-pill">{order.status.replace(/_/g, ' ')}</span></div><div className="order-items">{order.items.map((item, i) => <div key={i}><span>{item.item} × {item.quantity}</span><b>₹{(item.price_paid * item.quantity).toLocaleString('en-IN')}</b></div>)}</div><footer>{new Date(order.timestamp).toLocaleString()} <span>{order.confirmation_ref}</span></footer></article>)}</div>)}
      </div>
    </main>
    <nav className="mobile-nav"><button className={page === 'search' ? 'active' : ''} onClick={() => goto('search')}><Search/>Compare</button><button className={page === 'cart' ? 'active' : ''} onClick={() => goto('cart')}><ShoppingCart/>Cart{cart.length > 0 && <i/>}</button><button className={page === 'orders' ? 'active' : ''} onClick={() => goto('orders')}><History/>Orders</button></nav>
    {toast && <div className="toast"><CheckCircle2 size={18}/>{toast}</div>}
    {scanner && <BarcodeScanner onClose={() => setScanner(false)} onDetected={scanned}/>}
    {sheet && <div className="scrim sheet-scrim" onClick={() => setSheet(null)}><section className="bottom-sheet" onClick={e => e.stopPropagation()}><div className="sheet-handle"/><button className="x" onClick={() => setSheet(null)}>×</button><span className="eyebrow">SCAN RESULTS</span><h2>{sheet.name}</h2><p className="muted">Cheapest options are shown first.</p>{sheet.rows.map((row, i) => <div className={`sheet-row ${i === 0 ? 'best' : ''}`} key={row.id}><div><b>{row.platform_name}</b><small>{row.title} · {Math.round(row.same_product_confidence * 100)}% match</small></div><strong>₹{row.price.toLocaleString('en-IN')}</strong><button className="add-btn" onClick={() => void add(row)}>Add</button></div>)}</section></div>}
    {selectedProduct && <div className="scrim product-scrim" onClick={() => setSelectedProduct(null)}><section className="modal product-modal" role="dialog" aria-modal="true" aria-label={`${selectedProduct.title} details`} onClick={e => e.stopPropagation()}><button className="x" onClick={() => setSelectedProduct(null)} aria-label="Close product details">×</button><div className="product-detail-top"><img src={selectedProduct.image_url} alt={selectedProduct.title}/><div><span className="eyebrow">PRODUCT DETAILS · {selectedProduct.category.replace(/_/g, ' ')}</span><h2>{selectedProduct.title}</h2><p>{selectedProduct.same_product_id === 'headphones-anc' ? 'Soundcore Space One is an over-ear wireless headphone with adaptive active noise cancellation and Hi-Res audio.' : 'Product listing details and store offers.'}</p>{selectedProduct.warranty && <small>{selectedProduct.warranty}</small>}{selectedProduct.same_product_id === 'headphones-anc' && <a className="brand-product-link" href="https://www.soundcore.com/products/space-one-a3035011" target="_blank" rel="noreferrer">Open official Soundcore product page <ArrowRight size={13}/></a>}</div></div><div className="notice demo-notice"><b>Demo listing:</b> prices shown are sample values for the project presentation.</div><h3 className="offer-heading">Compare this product across stores</h3><div className="detail-offers">{results.filter(row => row.same_product_id === selectedProduct.same_product_id).map(row => <article className="detail-offer" key={row.id}><span className="store-chip" style={{ '--store-color': row.platform_color } as React.CSSProperties}>{row.platform_name}</span><div><strong>₹{row.price.toLocaleString('en-IN')}</strong><del>MRP ₹{row.mrp.toLocaleString('en-IN')}</del><small>{row.delivery_eta} · {row.availability}</small>{row.seller_name && <small>{row.seller_name}</small>}</div>{row.price_is_current === false ? <a className="secondary" href={row.url} target="_blank" rel="noreferrer">Check retailer</a> : <button className="add-btn" onClick={() => void add(row)}>Add to cart</button>}</article>)}</div><p className="product-detail-foot">★ {selectedProduct.rating.toFixed(1)} rating · {selectedProduct.review_count.toLocaleString()} reviews · Listing match {Math.round(selectedProduct.same_product_confidence * 100)}%</p></section></div>}
    {checkout.length > 0 && <div className="scrim"><section className="modal checkout-modal"><button className="x" onClick={() => setCheckout([])}>×</button><div className="empty-icon success"><PackageCheck/></div><span className="eyebrow">CHECKOUT READY</span><h2>Review with each store</h2><p className="muted">SmartCart stops before payment. Complete OTP login if Amazon asks, review your basket, and make the final payment decision on the retailer site.</p>{checkout.map((item, index) => <article className="checkout-row" key={`${item.platform}-${index}`}><div><b>{item.platform}</b><span className="status-pill">{item.status.replace(/_/g, ' ')}</span><small>{item.message}</small></div><div className="checkout-actions">{item.session_id && <button className="secondary" onClick={() => void saveAmazonSession(item.session_id!)}>Save encrypted session</button>}<a className="primary" href={item.checkout_url} target="_blank" rel="noreferrer">Open on store <ArrowRight size={15}/></a></div></article>)}<button className="secondary full" onClick={() => { setCheckout([]); goto('orders') }}>View order history</button></section></div>}
  </div>
}

function message(error: unknown) { return error instanceof Error ? error.message : 'Something went wrong. Please try again.' }
