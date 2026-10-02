const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const marketText = value => MarketLanguage.html(value);
const num = (value, digits=4) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('zh-CN', {maximumFractionDigits:digits});
const pct = value => value == null || !Number.isFinite(Number(value)) ? '—' : `${(Number(value)*100).toFixed(3)}%`;
const dateText = value => !value || !Number.isFinite(new Date(value).getTime()) ? '—' : new Date(value).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai',hour12:false});
const calculationStatus = {
  VALID:'通过盘口计算', FEE_UNKNOWN:'手续费未知，暂停净差判断', NO_ASKS:'有一腿没有卖盘',
  MIN_ORDER_UNKNOWN:'最小订单数量未知，暂停判断', BELOW_MIN_ORDER:'低于最小订单数量', STALE:'盘口过期，暂停判断', PARTIAL:'深度不足，仅有部分数量',
  INVALID_CALCULATION:'数值超出可计算范围，暂停判断', INVALID_BOOK:'盘口数据无效，暂停判断', CROSSED_BOOK:'买卖盘交叉，暂停判断', INVALID_PAIR:'两腿结果或 token 不匹配，暂停判断',
};
const recording = new Set();
const records = {offset:0, appliedOffset:0, limit:100};
let refreshing = false;

function requestMessage(detail, fallback) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => `${(item.loc || []).filter(x => x !== 'body').join('.')}: ${item.msg || '参数无效'}`).join('；');
  return fallback;
}
async function api(path, options={}) {
  const abort = new AbortController(), timeout = setTimeout(() => abort.abort(), 25000);
  try {
    const response = await fetch(path, {headers:{Accept:'application/json','Content-Type':'application/json'}, ...options, signal:abort.signal});
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(requestMessage(body.detail, `HTTP ${response.status}`));
    }
    return await response.json();
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('接口响应超时，请刷新重试');
    throw error;
  } finally { clearTimeout(timeout); }
}
function showError(error) { const box=$('#error'); if(box){box.textContent=`数据请求失败：${error.message}`;box.classList.remove('hidden');} }
function clearError() { $('#error')?.classList.add('hidden'); }
function bookTable(book) {
  if (!book || !book.asks?.length) return '<div class="empty">当前卖盘为空</div>';
  return `<table>${book.asks.length>20?`<caption>显示前 20 档 · 共 ${book.asks.length} 档</caption>`:''}<thead><tr><th>价格</th><th>数量</th></tr></thead><tbody>${book.asks.slice(0,20).map(x=>`<tr><td>${num(x.price,6)}</td><td>${num(x.size,4)}</td></tr>`).join('')}</tbody></table>`;
}
async function dashboard() {
  const [data, markets, s] = await Promise.all([api('/api/dashboard'), api('/api/markets?limit=8'), api('/api/system/status')]);
  $('#active-markets').textContent=s.active_market_count; $('#binary-markets').textContent=s.binary_market_count;
  $('#subscribed-tokens').textContent=s.subscribed_tokens; $('#opportunity-count').textContent=s.opportunity_count;
  $('#paper-count').textContent=data.paper_trade_count; $('#paper-profit').textContent=num(data.estimated_paper_profit,6);
  const healthy=s.gamma_status==='正常'&&s.clob_status==='正常';
  $('#system-pill').textContent=healthy?'公开数据链路正常':'公开数据链路未就绪'; $('#system-pill').className=`pill ${healthy?'ok':'waiting'}`;
  $('#last-update').textContent=`最后订单簿：${dateText(s.last_orderbook_refresh)}`;
  $('#connections').innerHTML=[['Gamma API',s.gamma_status],['CLOB API',s.clob_status],['Market WebSocket',s.websocket_status],['地区状态',s.geoblock_status]].map(x=>`<div class="connection"><b>${esc(x[0])}</b><span>${esc(x[1])}</span></div>`).join('');
  $('#runtime').innerHTML=`<dt>启动时间</dt><dd>${dateText(s.started_at)}</dd><dt>最后市场刷新</dt><dd>${dateText(s.last_market_refresh)}</dd><dt>WebSocket 消息</dt><dd>${num(s.websocket_messages,0)}</dd><dt>最近错误</dt><dd>${esc(s.recent_error||'无')}</dd>`;
  const h=s.public_http||{};
  $('#http-metrics').innerHTML=`<span>公开 API 请求 <b>${num(h.calls,0)}</b></span><span>实际重试 <b>${num(h.retries,0)}</b></span><span>限流响应 <b>${num(h.rate_limited,0)}</b></span><span>最近等待 <b>${num(h.last_retry_delay,2)} 秒</b></span>`;
  $('#market-preview').innerHTML=markets.items.length?markets.items.map(m=>`<tr><td><a href="/markets/${encodeURIComponent(m.market_id)}">${marketText(m.question)}</a></td><td>${num(m.liquidity,2)}</td><td>${num(m.volume,2)}</td><td>${m.fee_rate!=null?`${num(Number(m.fee_rate)*100,2)}%`:m.fees_enabled===false?'无费用':m.fee_reason?'手续费未知':'待核验'}</td><td>${esc(calculationStatus[m.calculation?.status]||'等待订单簿')}</td></tr>`).join(''):'<tr><td colspan="5" class="empty">当前没有满足过滤条件的真实市场</td></tr>';
}
function filterOpportunities() {
  const query=($('#search')?.value || '').trim().toLowerCase();
  document.querySelectorAll('#opportunity-table tr[data-market-search]').forEach(row => {
    row.hidden=!!query&&!`${row.dataset.marketSearch} ${row.textContent}`.toLowerCase().includes(query);
  });
}
async function opportunities() {
  const data=await api('/api/opportunities'), body=$('#opportunity-table');
  body.innerHTML=data.items.length?data.items.map(({market:m,calculation:c})=>`<tr data-market-search="${esc(m.question)}"><td>${marketText(m.question)}</td><td>${num(c.yes_average_price,6)}</td><td>${num(c.no_average_price,6)}</td><td>${num(c.executable_quantity,4)}</td><td>${num(c.total_cost,6)}</td><td>${num(c.estimated_fees,6)}</td><td class="${Number(c.net_profit)>=0?'positive':'negative'}">${num(c.net_profit,6)}</td><td>${pct(c.net_roi)}</td><td><a class="button small ghost" href="/markets/${encodeURIComponent(m.market_id)}">详情</a> <button class="button small" data-trade="${esc(m.market_id)}" ${recording.has(m.market_id)?'disabled':''}>${recording.has(m.market_id)?'正在保存…':'保存模拟'}</button></td></tr>`).join(''):'<tr><td colspan="9" class="empty">当前暂无符合过滤条件的机会</td></tr>';
  filterOpportunities();
}
async function recordTrade(button) {
  const id=button.dataset.trade;
  if(recording.has(id))return;
  recording.add(id); button.disabled=true; button.textContent='正在保存…'; clearError();
  try { const result=await api('/api/paper-trades',{method:'POST',body:JSON.stringify({market_id:id})}); alert(`已保存模拟记录 #${result.id}（非真实成交）`); }
  catch(error){showError(error);}
  finally { recording.delete(id); document.querySelectorAll('[data-trade]').forEach(node=>{if(node.dataset.trade===id){node.disabled=false;node.textContent='保存模拟';}}); }
}
async function marketDetail() {
  const m=await api(`/api/markets/${encodeURIComponent(document.body.dataset.marketId)}`);
  $('#market-summary').innerHTML=`<h2>${marketText(m.question)}</h2><p class="muted">${marketText(m.description||'暂无描述')}</p><dl><dt>Condition ID</dt><dd><code>${esc(m.condition_id)}</code></dd><dt>Yes Token</dt><dd><code>${esc(m.yes_token_id)}</code></dd><dt>No Token</dt><dd><code>${esc(m.no_token_id)}</code></dd><dt>数据源</dt><dd>Polymarket 官方公开接口</dd></dl>`;
  $('#book-analytics').innerHTML=BookQuality.html(m.book_analytics,['Yes','No']); $('#yes-book').innerHTML=bookTable(m.yes_orderbook); $('#no-book').innerHTML=bookTable(m.no_orderbook);
  const c=m.calculation;
  $('#calculation').innerHTML=c?`<p class="${c.status==='VALID'?'muted':'negative'}">${esc(calculationStatus[c.status]||'计算状态未知，暂停判断')} · ${m.is_candidate===true&&c.status==='VALID'?'通过当前候选门槛':'未通过当前候选门槛'}</p><p class="muted">计算于 ${dateText(m.calculation_as_of)} · REST 订单簿快照；页面展示盘口可能已由 WebSocket 更新。</p><dl><dt>目标数量</dt><dd>${num(c.target_quantity)}</dd><dt>共同可执行量</dt><dd>${num(c.executable_quantity)}</dd><dt>毛利润</dt><dd>${num(c.gross_profit,6)}</dd><dt>预计费用</dt><dd>${c.estimated_fees==null?'手续费未知':num(c.estimated_fees,6)}</dd><dt>滑点缓冲</dt><dd>${num(c.slippage_buffer,6)}</dd><dt>安全缓冲</dt><dd>${num(c.safety_buffer,6)}</dd><dt>预计净收益</dt><dd>${num(c.net_profit,6)}</dd><dt>预计净收益率</dt><dd>${pct(c.net_roi)}</dd></dl>`:'<div class="empty">尚无可追溯的订单簿计算</div>';
  if(c&&Array.isArray(m.calculation_orderbooks))$('#calculation').innerHTML+=`<details class="calculation-source"><summary>查看此次计算使用的 REST 卖盘</summary>${m.calculation_orderbooks.map((book,index)=>`<h3>${marketText(index===0?'Yes':'No')}</h3><p class="muted">Token <code>${esc(book?.asset_id||'未知')}</code> · 时间戳 ${esc(book?.timestamp||'未知')}</p>${bookTable(book)}`).join('')}</details>`;
}
function recordPagination(items) {
  records.appliedOffset=records.offset;
  $('#record-page').textContent=items.length?`第 ${records.offset+1}–${records.offset+Math.min(items.length,records.limit)} 条`:'当前页暂无记录';
  $('#record-previous').disabled=records.offset===0; $('#record-next').disabled=items.length<=records.limit;
  return items.slice(0,records.limit);
}
async function paperTrades() {
  const data=await api(`/api/paper-trades?limit=${records.limit+1}&offset=${records.offset}`), items=recordPagination(data.items);
  $('#paper-table').innerHTML=items.length?items.map(x=>`<tr><td>${dateText(x.created_at)}</td><td>${marketText(x.market_question)}</td><td>${num(x.target_quantity)}</td><td>${num(x.executable_quantity)}</td><td>${num(x.total_cost,6)}</td><td>${num(x.net_profit,6)}</td><td>${esc(x.status)}</td><td>${esc(x.trigger_type)}</td></tr>`).join(''):'<tr><td colspan="8" class="empty">尚无模拟交易记录</td></tr>';
}
async function history() {
  const data=await api(`/api/opportunities/history?limit=${records.limit+1}&offset=${records.offset}`), items=recordPagination(data.items);
  $('#history-table').innerHTML=items.length?items.map(x=>`<tr><td>${marketText(x.question)}</td><td>${dateText(x.first_seen)}</td><td>${dateText(x.last_seen)}</td><td>${num(x.max_net_profit,6)}</td><td>${pct(x.max_net_roi)}</td><td>${num(x.max_quantity)}</td><td>${esc(x.status)}</td></tr>`).join(''):'<tr><td colspan="7" class="empty">尚无历史有效机会</td></tr>';
}
async function settingsPage() {
  const values=await api('/api/settings'), form=$('#settings-form');
  Object.entries(values).forEach(([key,value])=>{if(form.elements[key])form.elements[key].value=value;});
  let saving=false;
  form.addEventListener('input',()=>{if(!saving){$('#settings-result').textContent='有未保存的修改';$('#settings-result').dataset.state='dirty';}});
  form.addEventListener('submit',async event=>{
    event.preventDefault(); if(saving||!form.reportValidity())return;
    const body=Object.fromEntries(new FormData(form)), button=form.querySelector('[type="submit"]'), result=$('#settings-result');
    saving=true; button.disabled=true; result.textContent='正在保存…';result.dataset.state='pending';clearError();
    const inputs=[...form.querySelectorAll('input')];inputs.forEach(input=>input.disabled=true);
    try { await api('/api/settings',{method:'PUT',body:JSON.stringify(body)}); result.textContent='已保存，下一轮盘口刷新采用新参数';result.dataset.state='saved'; }
    catch(error){result.textContent='保存失败，请重试';result.dataset.state='error';showError(error);}
    finally{saving=false;button.disabled=false;inputs.forEach(input=>input.disabled=false);}
  });
}
let logItems=[];
function renderLogs() {
  $('#log-table').innerHTML=logItems.filter(x=>!$('#log-level').value||x.level===$('#log-level').value).map(x=>`<tr><td>${dateText(x.created_at)}</td><td>${esc(x.level)}</td><td>${esc(x.source)}</td><td>${esc(x.event)}</td><td>${esc(x.message)}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">暂无匹配事件</td></tr>';
}
async function logs(){ const data=await api('/api/logs');logItems=data.items;renderLogs(); }
async function refreshPage(run) {
  if(refreshing)return;
  refreshing=true;
  const button=$('#refresh'); if(button)button.disabled=true;
  try { await run(); clearError(); if($('#snapshot-state'))$('#snapshot-state').textContent=`页面读取于 ${dateText(new Date())} · 上海时间`; }
  catch(error){
    records.offset=records.appliedOffset;
    showError(error); if($('#snapshot-state'))$('#snapshot-state').textContent='刷新失败，已有数据是旧快照，请刷新后再判断';
    if($('#system-pill')){$('#system-pill').textContent='页面刷新失败';$('#system-pill').className='pill waiting';}
  } finally { refreshing=false;if(button)button.disabled=false; }
}
document.addEventListener('DOMContentLoaded',()=>{
  const clock=()=>{$('#clock').textContent=dateText(new Date());}; clock();setInterval(clock,1000);
  const routes={dashboard,opportunities,market:marketDetail,'paper-trades':paperTrades,history,settings:settingsPage,logs}, run=routes[document.body.dataset.page];
  if(run)refreshPage(run);
  if(['dashboard','opportunities','market','logs'].includes(document.body.dataset.page))setInterval(()=>{if(!document.hidden)refreshPage(run);},5000);
  $('#refresh')?.addEventListener('click',()=>refreshPage(run));
  $('#search')?.addEventListener('input',filterOpportunities);
  $('#opportunity-table')?.addEventListener('click',event=>{const button=event.target.closest('[data-trade]');if(button)recordTrade(button);});
  if($('#opportunity-table'))new MutationObserver(filterOpportunities).observe($('#opportunity-table'),{childList:true,subtree:true,characterData:true});
  $('#log-level')?.addEventListener('change',renderLogs);
  $('#record-previous')?.addEventListener('click',()=>{if(refreshing)return;records.offset=Math.max(0,records.offset-records.limit);refreshPage(run);});
  $('#record-next')?.addEventListener('click',()=>{if(refreshing)return;records.offset+=records.limit;refreshPage(run);});
});
