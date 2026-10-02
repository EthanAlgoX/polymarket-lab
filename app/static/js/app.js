const $ = selector => document.querySelector(selector);
const t = (en, zh) => window.SiteLanguage ? window.SiteLanguage.t(en, zh) : en;
const message = value => window.SiteLanguage ? window.SiteLanguage.message(value) : String(value ?? '');
const locale = () => window.SiteLanguage?.getLanguage() === 'zh' ? 'zh-CN' : 'en-US';
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const marketText = value => MarketLanguage.html(value);
const num = (value, digits=4) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString(locale(), {maximumFractionDigits:digits});
const pct = value => value == null || !Number.isFinite(Number(value)) ? '—' : `${(Number(value)*100).toFixed(3)}%`;
const dateText = value => !value || !Number.isFinite(new Date(value).getTime()) ? '—' : new Date(value).toLocaleString(locale(), {timeZone:'Asia/Shanghai',hour12:false});
const calculationStatus = () => ({
  VALID:t('Book calculation valid','通过盘口计算'), FEE_UNKNOWN:t('Unknown fees; net-profit assessment paused','手续费未知，暂停净差判断'), NO_ASKS:t('One leg has no asks','有一腿没有卖盘'),
  MIN_ORDER_UNKNOWN:t('Unknown minimum order size; assessment paused','最小订单数量未知，暂停判断'), BELOW_MIN_ORDER:t('Below minimum order size','低于最小订单数量'), STALE:t('Stale order book; assessment paused','盘口过期，暂停判断'), PARTIAL:t('Insufficient depth; partial quantity only','深度不足，仅有部分数量'),
  INVALID_CALCULATION:t('Values exceed calculation limits; assessment paused','数值超出可计算范围，暂停判断'), INVALID_BOOK:t('Invalid order book; assessment paused','盘口数据无效，暂停判断'), CROSSED_BOOK:t('Crossed order book; assessment paused','买卖盘交叉，暂停判断'), INVALID_PAIR:t('Outcome or token mismatch; assessment paused','两腿结果或 token 不匹配，暂停判断'),
});
const recording = new Set();
const records = {offset:0, appliedOffset:0, limit:100};
const pageData = {};
let refreshing = false, settingsBound = false, logItems = [], lastRead = null, lastError = null, refreshFailed = false;

function requestMessage(detail, fallback) {
  if (typeof detail === 'string') return message(detail);
  if (Array.isArray(detail)) return detail.map(item => `${(item.loc || []).filter(x => x !== 'body').join('.')}: ${message(item.msg || t('Invalid parameter','参数无效'))}`).join('; ');
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
    if (error.name === 'AbortError') throw new Error(t('Request timed out. Refresh to try again.','接口响应超时，请刷新重试'));
    throw error;
  } finally { clearTimeout(timeout); }
}
function showError(error) { lastError=error;const box=$('#error'); if(box){box.textContent=`${t('Data request failed: ','数据请求失败：')}${message(error.message)}`;box.classList.remove('hidden');} }
function clearError() { lastError=null;$('#error')?.classList.add('hidden'); }
function bookTable(book) {
  if (!book || !book.asks?.length) return `<div class="empty">${t('No asks available','当前卖盘为空')}</div>`;
  return `<table>${book.asks.length>20?`<caption>${t(`Showing the first 20 of ${book.asks.length} levels`,`显示前 20 档 · 共 ${book.asks.length} 档`)}</caption>`:''}<thead><tr><th>${t('Price','价格')}</th><th>${t('Quantity','数量')}</th></tr></thead><tbody>${book.asks.slice(0,20).map(x=>`<tr><td>${num(x.price,6)}</td><td>${num(x.size,4)}</td></tr>`).join('')}</tbody></table>`;
}
function renderDashboard(data, markets, s) {
  $('#active-markets').textContent=s.active_market_count; $('#binary-markets').textContent=s.binary_market_count;
  $('#subscribed-tokens').textContent=s.subscribed_tokens; $('#opportunity-count').textContent=s.opportunity_count;
  $('#paper-count').textContent=data.paper_trade_count; $('#paper-profit').textContent=num(data.estimated_paper_profit,6);
  const healthy=s.gamma_status==='正常'&&s.clob_status==='正常';
  $('#system-pill').textContent=s.live_scanner_enabled===false?t('Local offline mode','本地离线模式'):healthy?t('Public data connections healthy','公开数据链路正常'):t('Public data connections not ready','公开数据链路未就绪'); $('#system-pill').className=`pill ${healthy?'ok':'waiting'}`;
  $('#last-update').textContent=`${t('Last order book: ','最后订单簿：')}${dateText(s.last_orderbook_refresh)}`;
  $('#connections').innerHTML=[['Gamma API',s.gamma_status],['CLOB API',s.clob_status],['Market WebSocket',s.websocket_status],[t('Region status','地区状态'),s.geoblock_status]].map(x=>`<div class="connection"><b>${esc(x[0])}</b><span>${esc(message(x[1]))}</span></div>`).join('');
  $('#runtime').innerHTML=`<dt>${t('Started at','启动时间')}</dt><dd>${dateText(s.started_at)}</dd><dt>${t('Market metadata fetched','市场元数据 API 拉取')}</dt><dd>${dateText(s.last_market_refresh)}</dd><dt>${t('WebSocket messages','WebSocket 消息')}</dt><dd>${num(s.websocket_messages,0)}</dd><dt>${t('Latest error','最近错误')}</dt><dd>${esc(s.recent_error?message(s.recent_error):t('None','无'))}</dd>`;
  const h=s.public_http||{};
  $('#http-metrics').innerHTML=`<span>${t('Public API requests','公开 API 请求')} <b>${num(h.calls,0)}</b></span><span>${t('Retries','实际重试')} <b>${num(h.retries,0)}</b></span><span>${t('Rate-limit responses','限流响应')} <b>${num(h.rate_limited,0)}</b></span><span>${t('Last wait','最近等待')} <b>${num(h.last_retry_delay,2)} ${t('s','秒')}</b></span>`;
  $('#market-preview').innerHTML=markets.items.length?markets.items.map(m=>`<tr><td><a href="/markets/${encodeURIComponent(m.market_id)}">${marketText(m.question)}</a></td><td>${num(m.liquidity,2)}</td><td>${num(m.volume,2)}</td><td>${m.fee_rate!=null?`${num(Number(m.fee_rate)*100,2)}%`:m.fees_enabled===false?t('No fee','无费用'):m.fee_reason?t('Unknown fees','手续费未知'):t('Unverified','待核验')}</td><td>${esc(calculationStatus()[m.calculation?.status]||t('Awaiting order book','等待订单簿'))}</td></tr>`).join(''):`<tr><td colspan="5" class="empty">${t('No real markets currently match these filters','当前没有满足过滤条件的真实市场')}</td></tr>`;
}
async function dashboard() {
  const values = await Promise.all([api('/api/dashboard'), api('/api/markets?limit=8'), api('/api/system/status')]);
  pageData.dashboard=values;renderDashboard(...values);
}
function filterOpportunities() {
  const query=($('#search')?.value || '').trim().toLowerCase();
  document.querySelectorAll('#opportunity-table tr[data-market-search]').forEach(row => {
    row.hidden=!!query&&!`${row.dataset.marketSearch} ${row.textContent}`.toLowerCase().includes(query);
  });
}
function renderOpportunities(data) {
  const body=$('#opportunity-table');
  body.innerHTML=data.items.length?data.items.map(({market:m,calculation:c})=>`<tr data-market-search="${esc(m.question)}"><td>${marketText(m.question)}</td><td>${num(c.yes_average_price,6)}</td><td>${num(c.no_average_price,6)}</td><td>${num(c.executable_quantity,4)}</td><td>${num(c.total_cost,6)}</td><td>${num(c.estimated_fees,6)}</td><td class="${Number(c.net_profit)>=0?'positive':'negative'}">${num(c.net_profit,6)}</td><td>${pct(c.net_roi)}</td><td><a class="button small ghost" href="/markets/${encodeURIComponent(m.market_id)}">${t('Details','详情')}</a> <button class="button small" data-trade="${esc(m.market_id)}" ${recording.has(m.market_id)?'disabled':''}>${recording.has(m.market_id)?t('Saving…','正在保存…'):t('Save simulation','保存模拟')}</button></td></tr>`).join(''):`<tr><td colspan="9" class="empty">${t('No opportunities currently match these filters','当前暂无符合过滤条件的机会')}</td></tr>`;
  filterOpportunities();
}
async function opportunities() { const data=await api('/api/opportunities');pageData.opportunities=data;renderOpportunities(data); }
async function recordTrade(button) {
  const id=button.dataset.trade;
  if(recording.has(id))return;
  recording.add(id); button.disabled=true; button.textContent=t('Saving…','正在保存…'); clearError();
  try { const result=await api('/api/paper-trades',{method:'POST',body:JSON.stringify({market_id:id})}); alert(t(`Simulation #${result.id} saved (no real execution)`,`已保存模拟记录 #${result.id}（非真实成交）`)); }
  catch(error){showError(error);}
  finally { recording.delete(id); document.querySelectorAll('[data-trade]').forEach(node=>{if(node.dataset.trade===id){node.disabled=false;node.textContent=t('Save simulation','保存模拟');}}); }
}
function renderMarketDetail(m) {
  $('#market-summary').innerHTML=`<h2>${marketText(m.question)}</h2><p class="muted">${m.description?marketText(m.description):t('No description available','暂无描述')}</p><dl><dt>Condition ID</dt><dd><code>${esc(m.condition_id)}</code></dd><dt>Yes Token</dt><dd><code>${esc(m.yes_token_id)}</code></dd><dt>No Token</dt><dd><code>${esc(m.no_token_id)}</code></dd><dt>${t('Data source','数据源')}</dt><dd>${t('Official public Polymarket APIs','Polymarket 官方公开接口')}</dd></dl>`;
  $('#book-analytics').innerHTML=BookQuality.html(m.book_analytics,['Yes','No']); $('#yes-book').innerHTML=bookTable(m.yes_orderbook); $('#no-book').innerHTML=bookTable(m.no_orderbook);
  const c=m.calculation;
  $('#calculation').innerHTML=c?`<p class="${c.status==='VALID'?'muted':'negative'}">${esc(calculationStatus()[c.status]||t('Unknown calculation status; assessment paused','计算状态未知，暂停判断'))} · ${m.is_candidate===true&&c.status==='VALID'?t('Meets current candidate thresholds','通过当前候选门槛'):t('Below current candidate thresholds','未通过当前候选门槛')}</p><p class="muted">${t('Calculated at ','计算于 ')}${dateText(m.calculation_as_of)}${t(' · REST order book snapshot; displayed books may have since changed through WebSocket updates.',' · REST 订单簿快照；页面展示盘口可能已由 WebSocket 更新。')}</p><dl><dt>${t('Target quantity','目标数量')}</dt><dd>${num(c.target_quantity)}</dd><dt>${t('Common executable quantity','共同可执行量')}</dt><dd>${num(c.executable_quantity)}</dd><dt>${t('Gross profit','毛利润')}</dt><dd>${num(c.gross_profit,6)}</dd><dt>${t('Estimated fees','预计费用')}</dt><dd>${c.estimated_fees==null?t('Unknown fees','手续费未知'):num(c.estimated_fees,6)}</dd><dt>${t('Slippage buffer','滑点缓冲')}</dt><dd>${num(c.slippage_buffer,6)}</dd><dt>${t('Safety buffer','安全缓冲')}</dt><dd>${num(c.safety_buffer,6)}</dd><dt>${t('Estimated net profit','预计净收益')}</dt><dd>${num(c.net_profit,6)}</dd><dt>${t('Estimated net ROI','预计净收益率')}</dt><dd>${pct(c.net_roi)}</dd></dl>`:`<div class="empty">${t('No traceable order book calculation available','尚无可追溯的订单簿计算')}</div>`;
  if(c&&Array.isArray(m.calculation_orderbooks))$('#calculation').innerHTML+=`<details class="calculation-source"><summary>${t('Show REST asks used in this calculation','查看此次计算使用的 REST 卖盘')}</summary>${m.calculation_orderbooks.map((book,index)=>`<h3>${marketText(index===0?'Yes':'No')}</h3><p class="muted">Token <code>${esc(book?.asset_id||t('Unknown','未知'))}</code> · ${t('Timestamp','时间戳')} ${esc(book?.timestamp||t('Unknown','未知'))}</p>${bookTable(book)}`).join('')}</details>`;
}
async function marketDetail() { const m=await api(`/api/markets/${encodeURIComponent(document.body.dataset.marketId)}`);pageData.market=m;renderMarketDetail(m); }
function recordPagination(items, languageOnly=false) {
  const offset=languageOnly?records.appliedOffset:records.offset;
  if(!languageOnly)records.appliedOffset=offset;
  $('#record-page').textContent=items.length?t(`Records ${offset+1}–${offset+Math.min(items.length,records.limit)}`,`第 ${offset+1}–${offset+Math.min(items.length,records.limit)} 条`):t('No records on this page','当前页暂无记录');
  $('#record-previous').disabled=offset===0; $('#record-next').disabled=items.length<=records.limit;
  return items.slice(0,records.limit);
}
function renderPaperTrades(data, languageOnly=false) {
  const items=recordPagination(data.items,languageOnly);
  $('#paper-table').innerHTML=items.length?items.map(x=>`<tr><td>${dateText(x.created_at)}</td><td>${marketText(x.market_question)}</td><td>${num(x.target_quantity)}</td><td>${num(x.executable_quantity)}</td><td>${num(x.total_cost,6)}</td><td>${num(x.net_profit,6)}</td><td>${esc(message(x.status))}</td><td>${esc(message(x.trigger_type))}</td></tr>`).join(''):`<tr><td colspan="8" class="empty">${t('No simulation records yet','尚无模拟交易记录')}</td></tr>`;
}
async function paperTrades() { const data=await api(`/api/paper-trades?limit=${records.limit+1}&offset=${records.offset}`);pageData['paper-trades']=data;renderPaperTrades(data); }
function renderHistory(data, languageOnly=false) {
  const items=recordPagination(data.items,languageOnly);
  $('#history-table').innerHTML=items.length?items.map(x=>`<tr><td>${marketText(x.question)}</td><td>${dateText(x.first_seen)}</td><td>${dateText(x.last_seen)}</td><td>${num(x.max_net_profit,6)}</td><td>${pct(x.max_net_roi)}</td><td>${num(x.max_quantity)}</td><td>${esc(message(x.status))}</td></tr>`).join(''):`<tr><td colspan="7" class="empty">${t('No valid opportunities recorded yet','尚无历史有效机会')}</td></tr>`;
}
async function history() { const data=await api(`/api/opportunities/history?limit=${records.limit+1}&offset=${records.offset}`);pageData.history=data;renderHistory(data); }
function renderSettingsResult() {
  const result=$('#settings-result');if(!result)return;
  const copy={dirty:t('You have unsaved changes','有未保存的修改'),pending:t('Saving…','正在保存…'),saved:t('Saved. New parameters apply at the next order book refresh.','已保存，下一轮盘口刷新采用新参数'),error:t('Save failed. Try again.','保存失败，请重试')};
  if(copy[result.dataset.state])result.textContent=copy[result.dataset.state];
}
async function settingsPage() {
  const values=await api('/api/settings'), form=$('#settings-form');
  Object.entries(values).forEach(([key,value])=>{if(form.elements[key])form.elements[key].value=value;});
  if(settingsBound)return;settingsBound=true;
  let saving=false;
  form.addEventListener('input',()=>{if(!saving){$('#settings-result').dataset.state='dirty';renderSettingsResult();}});
  form.addEventListener('submit',async event=>{
    event.preventDefault(); if(saving||!form.reportValidity())return;
    const body=Object.fromEntries(new FormData(form)), button=form.querySelector('[type="submit"]'), result=$('#settings-result');
    saving=true; button.disabled=true; result.dataset.state='pending';renderSettingsResult();clearError();
    const inputs=[...form.querySelectorAll('input')];inputs.forEach(input=>input.disabled=true);
    try { await api('/api/settings',{method:'PUT',body:JSON.stringify(body)});result.dataset.state='saved';renderSettingsResult(); }
    catch(error){result.dataset.state='error';renderSettingsResult();showError(error);}
    finally{saving=false;button.disabled=false;inputs.forEach(input=>input.disabled=false);}
  });
}
function renderLogs() {
  $('#log-table').innerHTML=logItems.filter(x=>!$('#log-level').value||x.level===$('#log-level').value).map(x=>`<tr><td>${dateText(x.created_at)}</td><td>${esc(x.level)}</td><td>${esc(message(x.source))}</td><td>${esc(message(x.event))}</td><td>${esc(message(x.message))}</td></tr>`).join('')||`<tr><td colspan="5" class="empty">${t('No matching events','暂无匹配事件')}</td></tr>`;
}
async function logs(){ const data=await api('/api/logs');logItems=data.items;renderLogs(); }
function renderSnapshotState() {
  if(!$('#snapshot-state'))return;
  $('#snapshot-state').textContent=refreshFailed?t('Refresh failed. Existing data is an older snapshot; refresh before assessing it.','刷新失败，已有数据是旧快照，请刷新后再判断'):lastRead?`${t('Page read at ','页面读取于 ')}${dateText(lastRead)} · ${t('Shanghai time','上海时间')}`:'';
  if(refreshFailed&&$('#system-pill')){$('#system-pill').textContent=t('Page refresh failed','页面刷新失败');$('#system-pill').className='pill waiting';}
}
async function refreshPage(run) {
  if(refreshing||!run)return;
  refreshing=true;
  const button=$('#refresh'); if(button)button.disabled=true;
  try { await run();clearError();lastRead=new Date();refreshFailed=false;renderSnapshotState(); }
  catch(error){ records.offset=records.appliedOffset;refreshFailed=true;showError(error);renderSnapshotState(); }
  finally { refreshing=false;if(button)button.disabled=false; }
}
function renderCurrentLanguage() {
  const page=document.body.dataset.page, data=pageData[page];
  if(page==='dashboard'&&data)renderDashboard(...data);
  else if(page==='opportunities'&&data)renderOpportunities(data);
  else if(page==='market'&&data)renderMarketDetail(data);
  else if(page==='paper-trades'&&data)renderPaperTrades(data,true);
  else if(page==='history'&&data)renderHistory(data,true);
  else if(page==='settings')renderSettingsResult();
  else if(page==='logs')renderLogs();
  if($('#clock'))$('#clock').textContent=dateText(new Date());
  renderSnapshotState();if(lastError)showError(lastError);
}
window.addEventListener('site-language-change',renderCurrentLanguage);
document.addEventListener('DOMContentLoaded',()=>{
  const clock=()=>{if($('#clock'))$('#clock').textContent=dateText(new Date());}; clock();setInterval(clock,1000);
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
