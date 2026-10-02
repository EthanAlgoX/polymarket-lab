const $ = s => document.querySelector(s);
const escapeHtml = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const marketText = value => MarketLanguage.html(value);
const n = (v,d=2) => v === null || v === undefined || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('zh-CN',{maximumFractionDigits:d});
const money = v => v == null ? '—' : '$'+(v>=1e6 ? n(v/1e6,2)+'M' : v>=1e3 ? n(v/1e3,1)+'K' : n(v,2));
const price = v => v == null || !Number.isFinite(Number(v)) ? '—' : n(Number(v)*100,2)+'¢';
const time = (v,dateOnly=false) => !v ? '—' : new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false,...(dateOnly?{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}:{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'})});
const safeUrl = v => {try{const u=new URL(v);return u.protocol==='https:'?escapeHtml(u.href):'#'}catch{return '#'}};
const labels={sports:'体育',weather:'天气',crypto:'加密',economy:'经济 / 金融',politics:'政治 / 地缘',other:'其他'};
const state={category:'all',search:'',sort:'volume24h',minLiquidity:0,offset:0,limit:40,view:'markets',repoFilter:'highstar',selected:null,quantity:100,extraCost:.05,catalogSequence:0,detailSequence:0};
let currentData=null, researchData=null, timer=null, loadingDetail=false, detailQueued=false, catalogLoading=false, catalogAbort=null, detailAbort=null, detailOpener=null;
async function api(url, signal){
  const controller=new AbortController(), abort=()=>controller.abort();
  signal?.addEventListener('abort',abort,{once:true});
  if(signal?.aborted)controller.abort();
  const timeout=setTimeout(abort,25000);
  try {
    const res=await fetch(url,{headers:{Accept:'application/json'},signal:controller.signal});
    if(!res.ok){const data=await res.json().catch(()=>({}));throw new Error(typeof data.detail==='string'?data.detail:`接口请求失败（${res.status}）`);}
    return await res.json();
  } catch(error){if(error.name==='AbortError')throw new Error('接口响应超时或已取消，请刷新重试');throw error;}
  finally{clearTimeout(timeout);signal?.removeEventListener('abort',abort);}
}
function error(e){$('#banner').textContent=e.message;$('#banner').hidden=false}
function coverageText(data){const t={loading:'正在发现',sample:'初始样本',paginated:'事件分页遍历完成',partial:'部分覆盖',capped:'达到本轮遍历上限'};return `${data.refreshing?'事件目录正在遍历':t[data.coverage]||'目录快照'} · ${n(data.total,0)} 个接单市场${data.pages?' · 已读取 '+data.pages+' 页':''}`}
async function loadCatalog(force=true){
  if(catalogLoading&&!force)return;
  const sequence=++state.catalogSequence;
  catalogAbort?.abort(); catalogAbort=new AbortController(); catalogLoading=true;
  const params=new URLSearchParams({category:state.category,search:state.search,sort:state.sort,min_liquidity:state.minLiquidity,offset:state.offset,limit:state.limit});
  try{
    const [data,status]=await Promise.all([api('/api/catalog?'+params,catalogAbort.signal),api('/api/system/status',catalogAbort.signal)]);
    if(sequence!==state.catalogSequence)return;
    if(data.filteredTotal&&state.offset>=data.filteredTotal){state.offset=Math.floor((data.filteredTotal-1)/state.limit)*state.limit;loadCatalog();return;}
    if(!data.filteredTotal)state.offset=0;
    currentData=data; $('#banner').hidden=true;
    if(data.error){$('#banner').textContent='目录读取部分中断，当前显示已有快照：'+data.error;$('#banner').hidden=false;}
    renderCatalog(data,status);
  }catch(e){
    if(sequence!==state.catalogSequence)return;
    error(e);$('#live-status').textContent='数据连接异常 · 保留旧快照';$('#live-status').className='status';
    if(currentData)$('#updated').textContent='刷新失败 · 保留快照 '+(currentData.revision??'—')+' · '+time(currentData.updatedAt);
  }finally{if(sequence===state.catalogSequence)catalogLoading=false;}
}
function scannerMixText(selection){
  if(!selection)return '';
  const verified=selection.verification;
  const count=verified?verified.verifiedTotal:selection.selectedTotal;
  const distribution=Object.entries((verified?verified.categoryCounts:selection.categoryCounts)||{}).filter(([,total])=>total>0).map(([key,total])=>`${labels[key]||key} ${total}`).join(' · ');
  if(verified){
    const result=verified.failed?'最新元数据核验失败，暂停候选判断':`实际扫描 ${n(count??0,0)} 个市场${distribution?'：'+distribution:''}`;
    return `${result}。目录预选 ${n(verified.requestedTotal??selection.selectedTotal??0,0)} 个 · 来源快照 ${verified.sourceRevision??'—'} · 核验于 ${time(verified.verifiedAt)}。`;
  }
  return count?`目录预选 ${n(count,0)} 个市场${distribution?'：'+distribution:''}。尚未完成最新元数据核验；先过滤门槛，再轮流分配行业名额。`:'';
}
function renderCatalog(data,status){$('#total').textContent=n(data.filteredTotal,0);$('#volume').textContent=money(data.filteredVolume24h);$('#liquidity').textContent=money(data.filteredLiquidity);$('#candidates').innerHTML=n(data.candidateCount,0)+'<em> / '+n(data.scannerCount,0)+'</em>';$('#scan-scope').textContent=`全部 ${data.scannerCount} 个 Yes/No 样本 · ${data.scannerRefreshSeconds}s`;$('#total-scope').textContent=state.category==='all'?'当前筛选 · 全行业':'当前筛选 · '+labels[state.category];$('#coverage').textContent=coverageText(data);$('#updated').textContent='快照 '+(data.revision??'—')+' · '+time(data.updatedAt)+' · 上海时间';$('#scanner-mix').textContent=scannerMixText(data.scannerSelection);const healthy=status.gamma_status==='正常'&&status.clob_status==='正常';$('#live-status').textContent=healthy?'公开行情正常':'盘口链路未就绪';$('#live-status').className='status'+(healthy?' live':'');const max=Math.max(...data.categories.map(x=>x.volume24h),1);$('#categories').innerHTML=data.categories.map(x=>`<button class="category ${state.category===x.id?'active':''}" data-category="${x.id}" aria-pressed="${state.category===x.id}" title="${escapeHtml(x.label)}，24 小时成交量 ${money(x.volume24h)}，${x.count} 个市场"><span class="category-name">${escapeHtml(x.label)}<span class="category-count">${n(x.count,0)}</span></span><b class="category-vol">${money(x.volume24h)}</b><span class="category-bar"><i style="width:${100*x.volume24h/max}%"></i></span><small>全目录 24h 成交量</small></button>`).join('');$('#categories').querySelectorAll('[data-category]').forEach(b=>b.onclick=()=>{state.category=state.category===b.dataset.category?'all':b.dataset.category;state.offset=0;loadCatalog()});$('#result-count').textContent=(state.category==='all'?'全部行业':labels[state.category])+' · '+n(data.filteredTotal,0)+' 个市场';$('#market-rows').innerHTML=data.items.length?data.items.map(m=>`<tr><td><button class="market-title" data-inspect="${escapeHtml(m.id)}">${marketText(m.question)}</button><span class="market-event" title="${escapeHtml(m.event)}">${marketText(m.event)}</span></td><td><span class="tag">${escapeHtml(labels[m.category])}</span></td><td><div class="outcomes">${m.outcomes.slice(0,2).map((label,i)=>`<span>${marketText(label)}<b>${price(m.prices[i])}</b></span>`).join('')}${m.outcomes.length>2?'<span>还有 '+(m.outcomes.length-2)+' 个结果</span>':''}</div></td><td class="numeric">${money(m.volume24h)}</td><td class="numeric">${money(m.liquidity)}</td><td class="deadline">${time(m.endDate,true)}</td><td><button class="inspect-link" data-inspect="${escapeHtml(m.id)}">核验盘口</button></td></tr>`).join(''):'<tr><td colspan="7" class="empty">该筛选下没有开盘市场。可清空搜索或降低流动性条件。</td></tr>';$('#market-rows').querySelectorAll('[data-inspect]').forEach(b=>b.onclick=()=>openDetail(b.dataset.inspect));$('#page-info').textContent=data.filteredTotal?`${state.offset+1}–${Math.min(state.offset+state.limit,data.filteredTotal)} / ${n(data.filteredTotal,0)}`:'0 / 0';$('#previous').disabled=state.offset===0;$('#next').disabled=state.offset+state.limit>=data.filteredTotal}
function setView(view){if(!['markets','strategies','opensource'].includes(view))view='markets';state.view=view;window.scrollTo({top:0});for(const v of ['markets','strategies','opensource'])$('#'+v+'-view').hidden=v!==view;document.querySelectorAll('[data-view]').forEach(b=>{const active=b.dataset.view===view;b.classList.toggle('active',active);if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')});$('h1').textContent={markets:'开盘市场',strategies:'交易空间',opensource:'开源项目参考'}[view]}
async function loadResearch(){try{const data=await api('/api/research');$('#strategy-grid').innerHTML=data.strategies.categoryResearch.map(s=>`<article class="strategy"><h3>${escapeHtml(s.category)}</h3><p class="priority">${escapeHtml(s.priority)}</p><p>${escapeHtml(s.signal)}</p><span class="field-label">需要的数据</span><div class="requirements">${s.data.map(x=>`<span>${escapeHtml(x)}</span>`).join('')}</div><span class="field-label">容易失效的地方</span><p class="risk">${escapeHtml(s.failure)}</p><span class="field-label">下一步验证</span><p>${escapeHtml(s.validation)}</p><a href="${safeUrl(s.sources[0])}" target="_blank" rel="noopener">查看依据</a></article>`).join('');researchData=data;renderRepos();$('#repo-filters').querySelectorAll('[data-repo-filter]').forEach(button=>button.onclick=()=>{state.repoFilter=button.dataset.repoFilter;renderRepos()})}catch(e){error(e)}}
function renderRepos(){
  if(!researchData)return;
  const github=researchData.github,threshold=github.highStarReview?.threshold||200;
  let repos=github.repos.filter(repo=>state.repoFilter==='all'||(repo.stars>=threshold&&(state.repoFilter!=='active'||!repo.archived)));
  repos=repos.sort((a,b)=>b.stars-a.stars||a.id.localeCompare(b.id));
  $('#repo-review-date').textContent=`评审于 ${github.highStarReview?.checkedAt||'—'} · star 为当次 GitHub 快照`;
  $('#repo-review-count').textContent=`当前 ${repos.length} 个项目`;
  $('#repo-filters').querySelectorAll('[data-repo-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.repoFilter===state.repoFilter)));
  $('#repo-grid').innerHTML=repos.map(repo=>{
    const review=repo.review||{},learn=review.learn||[repo.descriptionZh],evidence=review.sources||repo.sources||[];
    return `<article class="repo"><div class="repo-top"><h3>${escapeHtml(repo.id)}</h3><span class="tag">${repo.archived?'已归档':repo.official?'官方':'社区'}</span></div><div class="repo-meta"><span class="repo-stars">${n(repo.stars,0)} stars</span> · ${escapeHtml(repo.language||'—')} · ${escapeHtml(repo.licenseVerified?repo.license:'许可未完整核验')}<br>最近代码推送 ${escapeHtml((repo.updatedAt||'').slice(0,10))}</div><ul>${learn.map(item=>`<li>${escapeHtml(item)}</li>`).join('')}</ul><p class="repo-decision">${escapeHtml(review.decision||'研究参考；未集成代码')}</p><p class="cautions">${(review.limits||repo.cautions||[]).map(escapeHtml).join(' ')}</p><div class="repo-evidence"><a href="${safeUrl(repo.url)}" target="_blank" rel="noopener">GitHub 仓库</a>${evidence[0]?`<a href="${safeUrl(evidence[0])}" target="_blank" rel="noopener">源码依据</a>`:''}</div></article>`;
  }).join('')||'<p class="empty">该筛选下暂无项目，可切换到全部研究参考。</p>';
}
function openDetail(id){
  detailOpener=document.activeElement;state.selected=id;state.detailSequence++;
  $('#drawer').hidden=false;$('#drawer-shade').hidden=false;
  document.querySelector('.site-content').inert=true;document.querySelector('.site-rail').inert=true;
  document.body.style.overflow='hidden';$('#detail-body').innerHTML='<div class="empty">正在读取实际买卖盘…</div>';
  $('#close-drawer').focus();loadDetail(true);
}
function closeDetail(){
  if(!state.selected)return;
  state.selected=null;state.detailSequence++;detailAbort?.abort();detailQueued=false;
  $('#drawer').hidden=true;$('#drawer-shade').hidden=true;
  document.querySelector('.site-content').inert=false;document.querySelector('.site-rail').inert=false;
  document.body.style.overflow='';
  if(detailOpener?.isConnected)detailOpener.focus();else document.querySelector('#market-rows [data-inspect]')?.focus();
}
function renderBook(book,label){if(!book)return `<article class="book"><h4>${marketText(label)}</h4><p class="muted">盘口不可用</p></article>`;const asks=book.asks||[];return `<article class="book"><h4>${marketText(label)}</h4><p class="book-head">最佳买 ${price(book.bids?.[0]?.price)} · 卖 ${price(asks[0]?.price)}</p><table><thead><tr><th>卖出价</th><th class="numeric">股数</th></tr></thead><tbody>${asks.length?asks.slice(0,8).map(x=>`<tr><td>${price(x.price)}</td><td class="numeric">${n(x.size,2)}</td></tr>`).join(''):'<tr><td colspan="2">当前无卖盘</td></tr>'}</tbody></table></article>`}
function calcHtml(m){if(m.available===false)return `<div class="calc"><div class="verdict negative">暂停盘口核验</div><p>${escapeHtml(m.unavailableReason||'最新市场状态或结果映射未通过核验')}</p><p>目录保留的是先前快照；当前不计算净差额或列为候选。可点击刷新盘口重新核验。</p></div>`;const c=m.calculation;if(!c)return `<div class="calc">${m.outcomes?.length>2?'该市场有 '+m.outcomes.length+' 个结果；下方显示各结果盘口，当前完整集计算仅支持互斥二元条件。':'缺少完整二元盘口，暂不计算。'}</div>`;let verdict=c.status==='VALID'?'费用后没有正差额':'计算未通过，暂停判断';if(['INVALID_BOOK','CROSSED_BOOK','INVALID_PAIR','INVALID_CALCULATION'].includes(c.status))verdict={INVALID_CALCULATION:'数值超出可计算范围，暂停判断',INVALID_BOOK:'盘口数据无效，暂停判断',CROSSED_BOOK:'买卖盘交叉，暂停判断',INVALID_PAIR:'两腿结果或 token 不匹配，暂停判断'}[c.status];else if(c.status==='FEE_UNKNOWN')verdict='费率未知，暂停净差判断';else if(c.status==='NO_ASKS')verdict='有一腿没有卖盘';else if(c.status==='MIN_ORDER_UNKNOWN')verdict='最小订单数量未知，暂停判断';else if(c.status==='BELOW_MIN_ORDER')verdict='低于最小订单数量';else if(c.status==='STALE')verdict='盘口过期，暂停判断';else if(c.status==='PARTIAL')verdict='深度不足，仅能计算部分数量';else if(Number(c.net_profit)>0&&c.status==='VALID')verdict='正差额候选，需核验双腿执行';const negative=!(c.status==='VALID'&&Number(c.net_profit)>0);return `<div class="calc"><div class="verdict ${negative?'negative':''}">${verdict}</div><dl><dt>共同可成交量</dt><dd>${n(c.executable_quantity)} / ${n(c.target_quantity)} 股</dd><dt>两腿逐档成本</dt><dd>${n(c.total_cost,5)} pUSD</dd><dt>完整集理论回收</dt><dd>${n(c.settlement_value,5)} pUSD</dd><dt>逐档估算手续费</dt><dd>${c.estimated_fees===null?'未知':n(c.estimated_fees,5)+' pUSD'}</dd><dt>滑点缓冲</dt><dd>${n(c.slippage_buffer,5)} pUSD</dd><dt>安全缓冲</dt><dd>${n(c.safety_buffer,5)} pUSD</dd><dt>其他成本假设</dt><dd>${n(c.extra_cost,5)} pUSD</dd><dt class="net">估算净差额</dt><dd class="net">${c.net_profit===null?'—':n(c.net_profit,5)+' pUSD'}</dd><dt>按总预算计的净收益率</dt><dd>${c.net_roi==null?'—':n(Number(c.net_roi)*100,3)+'%'}</dd></dl><p>两腿成交独立；其他成本是可调整假设，尚未实测合并或链上成本。费用基于 Gamma 的当前费率公式。最小订单 ${n(m.minimumOrderSize)} 股。</p></div>`}
async function loadDetail(force=false){
  if(!state.selected)return;
  if(loadingDetail&&!force){detailQueued=true;return;}
  if(force){detailAbort?.abort();detailQueued=false;}
  const controller=new AbortController();detailAbort=controller;
  const id=state.selected,seq=++state.detailSequence;loadingDetail=true;
  try{const m=await api(`/api/inspect/${encodeURIComponent(id)}?quantity=${encodeURIComponent(state.quantity)}&extra_cost=${encodeURIComponent(state.extraCost)}`,controller.signal);if(id!==state.selected||seq!==state.detailSequence)return;const full=force||!$('#detail-live');if(full){$('#detail-body').innerHTML=`<h3>${marketText(m.question)}</h3><div class="detail-meta"><span>${escapeHtml(labels[m.category])} · ${m.negRisk?'NegRisk 条件':'标准条件'}</span><span id="detail-time"></span></div><div class="drawer-links"><a href="https://polymarket.com/event/${encodeURIComponent(m.slug)}" target="_blank" rel="noopener">原始市场与规则</a><a href="https://docs.polymarket.com/trading/fees" target="_blank" rel="noopener">费用说明</a></div><div class="params"><label>每腿目标股数<input id="quantity" type="number" min="1" max="100000" step="any" required value="${state.quantity}"></label><label>其他成本 / pUSD<input id="extra-cost" type="number" min="0" max="10000" step="any" required value="${state.extraCost}"></label></div><div id="detail-live"></div><div class="detail-disclosure">展示价格不保证成交。完整集的回收需结算或合并；跨事件与多选结果不能仅因价格相加便认定套利。</div><p class="translation-note">中文为机器翻译，结算以英文原文为准。切换 English 可查看原文。</p><details><summary>结算规则</summary><div class="rules">${marketText(m.description||'公开接口未提供规则')}</div></details>`;$('#quantity').onchange=e=>{const v=Number(e.target.value);if(Number.isFinite(v)&&v>=1&&v<=100000&&e.target.checkValidity()){state.quantity=e.target.value;state.detailSequence++;loadDetail(false)}};$('#extra-cost').onchange=e=>{const v=Number(e.target.value);if(Number.isFinite(v)&&v>=0&&v<=10000&&e.target.checkValidity()){state.extraCost=e.target.value;state.detailSequence++;loadDetail(false)}}}['#quantity','#extra-cost'].forEach(selector=>{const input=$(selector);if(input)input.disabled=m.available===false;});$('#detail-time').textContent=(m.available===false?'暂停核验 · 读取于 ':'读取于 ')+time(m.asOf);$('#detail-live').innerHTML=calcHtml(m)+BookQuality.html(m.book_analytics,m.outcomes)+`<div class="books">${m.books.map((book,i)=>renderBook(book,m.outcomes[i])).join('')}</div>`}catch(e){if(id===state.selected&&seq===state.detailSequence){if(force)$('#detail-body').innerHTML=`<div class="detail-error">${escapeHtml(e.message)}</div>`;else {const node=$('#detail-time');if(node)node.textContent='刷新失败，旧快照仅供参考';const verdict=$('#detail-live .verdict');if(verdict){verdict.textContent='刷新失败，暂停净差判断';verdict.className='verdict negative'}}}}finally{
  if(controller===detailAbort){loadingDetail=false;if(detailQueued&&state.selected){detailQueued=false;loadDetail(false);}}
}}
document.addEventListener('DOMContentLoaded',()=>{document.querySelectorAll('[data-view]').forEach(b=>b.onclick=e=>{e.preventDefault();setView(b.dataset.view);if(location.hash!==`#${b.dataset.view}`)location.hash=b.dataset.view});window.addEventListener('hashchange',()=>setView(location.hash.slice(1)));setView(location.hash.slice(1));$('#search').oninput=e=>{clearTimeout(timer);timer=setTimeout(()=>{state.search=e.target.value;state.offset=0;loadCatalog()},250)};$('#sort').onchange=e=>{state.sort=e.target.value;state.offset=0;loadCatalog()};$('#min-liquidity').onchange=e=>{state.minLiquidity=Number(e.target.value);state.offset=0;loadCatalog()};$('#reset').onclick=()=>{state.category='all';state.search='';state.offset=0;state.minLiquidity=0;state.sort='volume24h';$('#search').value='';$('#min-liquidity').value='0';$('#sort').value='volume24h';loadCatalog()};$('#previous').onclick=()=>{state.offset=Math.max(0,state.offset-state.limit);loadCatalog()};$('#next').onclick=()=>{state.offset+=state.limit;loadCatalog()};$('#refresh').onclick=()=>{loadCatalog();loadDetail(true)};$('#close-drawer').onclick=closeDetail;$('#refresh-detail').onclick=()=>loadDetail(true);$('#drawer-shade').onclick=closeDetail;document.addEventListener('keydown',e=>{
  if(!state.selected)return;
  if(e.key==='Escape'){e.preventDefault();closeDetail();}
  if(e.key==='Tab'){
    const nodes=[...$('#drawer').querySelectorAll('button,a[href],input,select,summary,[tabindex]')].filter(node=>!node.disabled&&node.tabIndex>=0&&node.getClientRects().length);
    const first=nodes[0],last=nodes[nodes.length-1];
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}
    else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
  }
});loadCatalog();loadResearch();setInterval(()=>{if(state.view==='markets'&&!document.hidden)loadCatalog(false)},15000);setInterval(()=>{if(state.selected&&!document.hidden&&!loadingDetail)loadDetail()},5000)});
