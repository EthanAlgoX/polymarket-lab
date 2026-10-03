const localUrl = path => window.SitePaths ? window.SitePaths.url(path) : path;
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
let refreshing = false, settingsBound = false, settingsDirty = false, settingsSaving = false, logItems = [], logsPaused = false, lastRead = null, lastError = null, refreshFailed = false, savedPaperId = null;
let logUpdateRevision = 0, thresholdRevision = 0;
const recordInspection = {kind:null, id:null, sequence:0, loading:false, payload:null, error:null};
const currentMarketLink = id => localUrl(`/#markets?inspect=${encodeURIComponent(id)}`);

function requestMessage(detail, fallback) {
  if (typeof detail === 'string') return message(detail);
  if (Array.isArray(detail)) return detail.map(item => `${(item.loc || []).filter(x => x !== 'body').join('.')}: ${message(item.msg || t('Invalid parameter','参数无效'))}`).join('; ');
  return fallback;
}
async function api(path, options={}) {
  const abort = new AbortController(), timeout = setTimeout(() => abort.abort(), 25000);
  try {
    const response = await fetch(localUrl(path), {headers:{Accept:'application/json','Content-Type':'application/json'}, ...options, signal:abort.signal});
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
  const diagnostics=s.scanner_diagnostics;
  if(diagnostics){$('#binary-markets').textContent=num(diagnostics.selected_count,0);$('#calculated-markets').textContent=num(diagnostics.calculated_count,0);$('#opportunity-count').textContent=num(diagnostics.candidate_count,0);}
  else $('#calculated-markets').textContent='—';
  $('#scanner-scope').textContent=t('Sample coverage is limited; the catalog is broader.','扫描覆盖有限，市场目录范围更广。');
  const healthy=s.gamma_status==='正常'&&s.clob_status==='正常';
  $('#system-pill').textContent=s.live_scanner_enabled===false?t('Local offline mode','本地离线模式'):healthy?t('Public API connections responding','公开 API 连接正常响应'):t('Public data connections not ready','公开数据链路未就绪'); $('#system-pill').className=`pill ${healthy&&s.live_scanner_enabled!==false?'ok':'waiting'}`;
  $('#last-update').textContent=`${t('REST books received: ','REST 盘口接收于：')}${dateText(s.last_orderbook_refresh)}`;
  $('#connections').innerHTML=[['Gamma API',s.gamma_status],['CLOB API',s.clob_status],['Market WebSocket',s.websocket_status],[t('Region status','地区状态'),s.geoblock_status]].map(x=>`<div class="connection"><b>${esc(x[0])}</b><span>${esc(message(x[1]))}</span></div>`).join('');
  $('#runtime').innerHTML=`<dt>${t('Started at','启动时间')}</dt><dd>${dateText(s.started_at)}</dd><dt>${t('Metadata received','元数据接收时间')}</dt><dd>${dateText(s.last_market_refresh)}</dd><dt>${t('Last WebSocket message','最近 WebSocket 消息')}</dt><dd>${dateText(s.last_websocket_message)}</dd><dt>${t('WebSocket messages','WebSocket 消息')}</dt><dd>${num(s.websocket_messages,0)}</dd><dt>${t('Latest error','最近错误')}</dt><dd>${esc(s.recent_error?message(s.recent_error):t('None','无'))}</dd>`;
  const h=s.public_http||{};
  $('#http-metrics').innerHTML=`<span>${t('Public API requests','公开 API 请求')} <b>${num(h.calls,0)}</b></span><span>${t('Retries','实际重试')} <b>${num(h.retries,0)}</b></span><span>${t('Rate-limit responses','限流响应')} <b>${num(h.rate_limited,0)}</b></span><span>${t('Last wait','最近等待')} <b>${num(h.last_retry_delay,2)} ${t('s','秒')}</b></span>`;
  $('#market-preview').innerHTML=markets.items.length?markets.items.map(m=>`<tr><td><a href="${localUrl(`/markets/${encodeURIComponent(m.market_id)}`)}">${marketText(m.question)}</a></td><td>${num(m.liquidity,2)}</td><td>${num(m.volume,2)}</td><td>${m.fee_rate!=null?`${num(Number(m.fee_rate)*100,2)}%`:m.fees_enabled===false?t('No fee','无费用'):m.fee_reason?t('Unknown fees','手续费未知'):t('Unverified','待核验')}</td><td>${esc(calculationStatus()[m.calculation?.status]||t('Awaiting order book','等待订单簿'))}</td></tr>`).join(''):`<tr><td colspan="5" class="empty"><strong>${t('No scanner sample available','暂无扫描样本')}</strong><p>${t('Check connections and collection logs. The market catalog can still be explored independently.','请检查连接与采集日志，仍可独立浏览市场目录。')}</p><a href="${localUrl('/logs')}">${t('Open connection logs','打开连接日志')}</a></td></tr>`;
}
async function dashboard() {
  const [data,markets] = await Promise.all([api('/api/dashboard'), api('/api/markets?limit=8')]);
  const values=[data,markets,data.status];
  pageData.dashboard=values;renderDashboard(...values);
}
function rejectionReasons() {
  return {...calculationStatus(),
    AWAITING_CALCULATION:t('Awaiting calculation','等待计算'), METADATA_UNVERIFIED:t('Metadata unverified','元数据未核验'),
    BOOKS_UNAVAILABLE:t('Books unavailable','盘口不可用'), QUOTE_TIME_UNKNOWN:t('Unknown source timestamp','来源时间戳未知'),
    BELOW_QUANTITY:t('Below minimum common quantity','低于共同数量门槛'), BELOW_NET_PROFIT:t('Below net-edge threshold','低于净差额门槛'), BELOW_NET_ROI:t('Below ROI threshold','低于收益率门槛'),
    MARKET_RESOLVED:t('Market resolved','市场已结算'), MARKET_UNAVAILABLE:t('Market unavailable','市场不可用'),
    INVALID_PARAMETERS:t('Invalid parameters','参数无效'), NO_LIQUIDITY:t('No common liquidity','没有共同流动性'), PARTIAL_NOT_ALLOWED:t('Partial quantity not allowed','不允许部分数量'),
  };
}
function renderScannerDiagnostics(diagnostics) {
  const target=$('#scanner-diagnostics');if(!target)return;
  if(!diagnostics){target.innerHTML=`<p class="muted">${t('Sample diagnostics are unavailable. Check the runtime monitor before assessing candidates.','样本诊断不可用，请先查看运行监控。')} <a href="${localUrl('/monitor')}">${t('Open monitor','打开运行监控')}</a></p>`;return;}
  const d=diagnostics, thresholds=d.thresholds||{}, reasons=rejectionReasons();
  target.innerHTML=`<div class="panel-head"><h2>${t('Sample eligibility','样本候选条件')}</h2><a href="${localUrl('/monitor')}">${t('Runtime monitor','运行监控')}</a></div><ol class="scanner-pipeline"><li><strong>${num(d.selected_count,0)}</strong><span>${t('Selected Yes/No markets','选定 Yes/No 市场')}</span></li><li><strong>${num(d.calculated_count,0)}</strong><span>${t('With calculations','已有计算')}</span></li><li><strong>${num(d.candidate_count,0)}</strong><span>${t('Eligible candidates','符合条件的候选')}</span></li></ol><p class="muted">${t('Limited sample, not the whole catalog. REST batch received: ','有限样本，并非全部市场目录。REST 批次接收于：')}${dateText(d.calculation_as_of)}</p><div class="diagnostic-reasons">${Object.entries(d.reason_counts||{}).filter(([,count])=>count>0).map(([code,count])=>`<span><b>${num(count,0)}</b> ${esc(reasons[code]||code)}</span>`).join('')||`<span>${t('No selected markets excluded in this check.','此次检查未排除选定市场。')}</span>`}</div><dl class="scanner-thresholds"><dt>${t('Min. net edge','最低净差额')}</dt><dd>${esc(thresholds.minimum_net_profit??'—')} pUSD</dd><dt>${t('Min. ROI','最低收益率')}</dt><dd>${pct(thresholds.minimum_net_roi)}</dd><dt>${t('Min. common shares','最低共同股数')}</dt><dd>${esc(thresholds.minimum_executable_quantity??'—')}</dd><dt>${t('Max. quote age','报价最长有效时间')}</dt><dd>${esc(thresholds.max_quote_age_seconds??'—')} ${t('s','秒')}</dd></dl>`;
}
function filterOpportunities() {
  const query=($('#search')?.value || '').trim().toLowerCase();
  const rows=[...document.querySelectorAll('#opportunity-table tr[data-market-search]')];let visible=0;
  rows.forEach(row => {
    row.hidden=!!query&&!`${row.dataset.marketSearch} ${row.textContent}`.toLowerCase().includes(query);
    if(!row.hidden)visible++;
  });
  if($('#opportunity-search-empty'))$('#opportunity-search-empty').hidden=rows.length===0||visible>0;
  if($('#opportunity-result-count'))$('#opportunity-result-count').textContent=t(`${visible} of ${rows.length} candidates shown`,`${rows.length} 个候选中显示 ${visible} 个`);
}
function renderOpportunities(data) {
  const body=$('#opportunity-table');
  body.innerHTML=data.items.length?data.items.map(({market:m,calculation:c})=>`<tr data-market-search="${esc(m.question)}"><td>${marketText(m.question)}</td><td>${num(c.yes_average_price,6)}</td><td>${num(c.no_average_price,6)}</td><td>${num(c.executable_quantity,4)}</td><td>${num(c.total_cost,6)}</td><td>${num(c.estimated_fees,6)}</td><td class="${Number(c.net_profit)>=0?'positive':'negative'}">${num(c.net_profit,6)}</td><td>${pct(c.net_roi)}</td><td><div class="row-actions"><a class="button small ghost" href="${localUrl(`/markets/${encodeURIComponent(m.market_id)}`)}">${t('Inspect','核验')}</a><button class="button small" data-trade="${esc(m.market_id)}" ${recording.has(m.market_id)?'disabled':''}>${recording.has(m.market_id)?t('Saving…','正在保存…'):t('Save paper record','保存观察记录')}</button></div></td></tr>`).join(''):`<tr><td colspan="9" class="empty"><strong>${t('No eligible candidates in this sample','本轮样本没有符合条件的候选')}</strong><p>${t('This is a valid result. Review exclusion reasons above, inspect market depth, or adjust your assumptions. Lower thresholds do not remove fees or stale quotes.','这是正常结果。可查看上方排除原因、核验市场深度或调整假设。降低门槛不会消除费用或过期报价。')}</p><a href="${localUrl('/#markets')}">${t('Explore open markets','浏览开放市场')}</a></td></tr>`;
  renderScannerDiagnostics(data.scanner_diagnostics);
  filterOpportunities();
}
async function opportunities() { const data=await api('/api/opportunities');pageData.opportunities=data;renderOpportunities(data); }
async function recordTrade(button) {
  const id=button.dataset.trade;
  if(recording.has(id))return;
  recording.add(id); button.disabled=true; button.textContent=t('Saving…','正在保存…'); clearError();
  savedPaperId=null;renderPaperFeedback();
  try { const result=await api('/api/paper-trades',{method:'POST',body:JSON.stringify({market_id:id})}); savedPaperId=result.id;renderPaperFeedback(); }
  catch(error){showError(error);}
  finally { recording.delete(id); document.querySelectorAll('[data-trade]').forEach(node=>{if(node.dataset.trade===id){node.disabled=false;node.textContent=t('Save paper record','保存观察记录');}}); }
}
function renderPaperFeedback() {
  const output=$('#paper-feedback');if(!output)return;
  if(savedPaperId==null){output.classList.add('hidden');return;}
  output.innerHTML=`<span>${t(`Paper record #${savedPaperId} saved. No orders were submitted.`,`已保存观察记录 #${savedPaperId}，没有提交订单。`)}</span> <a href="${localUrl('/paper-trades')}">${t('View paper records','查看观察记录')}</a>`;output.classList.remove('hidden');
}
function renderMarketDetail(m) {
  const disclosureState=captureDisclosures('#market-summary'), calculationDisclosures=captureDisclosures('#calculation');
  $('#market-summary').innerHTML=`<h2>${marketText(m.question)}</h2><p class="muted">${t('Selected scanner market · Official public Polymarket APIs','选定扫描市场 · Polymarket 官方公开 API')}</p><details class="audit-section" data-disclosure="rules"><summary>${t('Settlement rules','结算规则')}</summary><p class="muted">${m.description?marketText(m.description):t('No description available','暂无描述')}</p></details><details class="audit-section" data-disclosure="identifiers"><summary>${t('Settlement & token identifiers','结算与 Token 标识')}</summary><dl><dt>Condition ID</dt><dd><code>${esc(m.condition_id)}</code></dd><dt>Yes Token</dt><dd><code>${esc(m.yes_token_id)}</code></dd><dt>No Token</dt><dd><code>${esc(m.no_token_id)}</code></dd></dl></details>`;
  $('#book-analytics').innerHTML=BookQuality.html(m.book_analytics,['Yes','No']); $('#yes-book').innerHTML=bookTable(m.yes_orderbook); $('#no-book').innerHTML=bookTable(m.no_orderbook);
  const c=m.calculation;
  $('#calculation').innerHTML=c?`<p class="${c.status==='VALID'?'muted':'negative'}">${esc(calculationStatus()[c.status]||t('Unknown calculation status; assessment paused','计算状态未知，暂停判断'))} · ${c.status!=='VALID'?t('Candidate assessment paused','暂停候选评估'):m.is_candidate===true?t('Meets current candidate thresholds','通过当前候选门槛'):t('Below current candidate thresholds','未通过当前候选门槛')}</p><p class="muted">${t('Calculated at ','计算于 ')}${dateText(m.calculation_as_of)}${t(' · REST order book snapshot; displayed books may have since changed through WebSocket updates.',' · REST 订单簿快照；页面展示盘口可能已由 WebSocket 更新。')}</p><dl><dt>${t('Target shares per leg','每腿目标股数')}</dt><dd>${num(c.target_quantity)}</dd><dt>${t('Common executable shares','共同可执行股数')}</dt><dd>${num(c.executable_quantity)}</dd><dt>${t('Purchase cost / pUSD','买入成本 / pUSD')}</dt><dd>${num(c.total_cost,6)}</dd><dt>${t('Settlement value / pUSD','结算价值 / pUSD')}</dt><dd>${num(c.settlement_value,6)}</dd><dt>${t('Gross edge / pUSD','毛差额 / pUSD')}</dt><dd>${num(c.gross_profit,6)}</dd><dt>${t('Estimated fees / pUSD','估算费用 / pUSD')}</dt><dd>${c.estimated_fees==null?t('Unknown fees','手续费未知'):num(c.estimated_fees,6)}</dd><dt>${t('Slippage buffer / pUSD','滑点缓冲 / pUSD')}</dt><dd>${num(c.slippage_buffer,6)}</dd><dt>${t('Safety buffer / pUSD','安全缓冲 / pUSD')}</dt><dd>${num(c.safety_buffer,6)}</dd><dt>${t('Other costs / pUSD','其他成本 / pUSD')}</dt><dd>${num(c.extra_cost,6)}</dd><dt>${t('Estimated net edge / pUSD','估算净差额 / pUSD')}</dt><dd class="${Number(c.net_profit)>=0?'positive':'negative'}">${num(c.net_profit,6)}</dd><dt>${t('Budget ROI','预算收益率')}</dt><dd>${pct(c.net_roi)}</dd></dl>${m.is_candidate===true&&c.status==='VALID'&&m.market_id?`<div class="form-actions"><button class="button" data-trade="${esc(m.market_id)}" ${recording.has(m.market_id)?'disabled':''}>${recording.has(m.market_id)?t('Saving…','正在保存…'):t('Save paper record','保存观察记录')}</button></div>`:''}`:`<div class="empty">${t('No traceable order book calculation available','尚无可追溯的订单簿计算')}</div>`;
  if(c&&Array.isArray(m.calculation_orderbooks))$('#calculation').innerHTML+=`<details class="calculation-source" data-disclosure="rest-source"><summary>${t('Show REST asks used in this calculation','查看此次计算使用的 REST 卖盘')}</summary>${m.calculation_orderbooks.map((book,index)=>`<h3>${marketText(index===0?'Yes':'No')}</h3><p class="muted">Token <code>${esc(book?.asset_id||t('Unknown','未知'))}</code> · ${t('Timestamp','时间戳')} ${esc(book?.timestamp||t('Unknown','未知'))}</p>${bookTable(book)}`).join('')}</details>`;
  restoreDisclosures('#market-summary',disclosureState);restoreDisclosures('#calculation',calculationDisclosures);
}
async function marketDetail() { const m=await api(`/api/markets/${encodeURIComponent(document.body.dataset.marketId)}`);pageData.market=m;renderMarketDetail(m); }
function captureDisclosures(selector) {
  return new Map([...($(selector)?.querySelectorAll('details[data-disclosure]')||[])].map(node=>[node.dataset.disclosure,node.open]));
}
function restoreDisclosures(selector,state) {
  $(selector)?.querySelectorAll('details[data-disclosure]').forEach(node=>{if(state.has(node.dataset.disclosure))node.open=state.get(node.dataset.disclosure);});
}
function snapshotActions(kind, id, marketId) {
  return `<div class="row-actions"><button type="button" class="button small ghost" data-record-kind="${kind}" data-record-id="${esc(id)}">${t('View snapshot','查看快照')}</button>${marketId?`<a class="record-current-link" href="${currentMarketLink(marketId)}">${t('Inspect current market','检查当前市场')}</a>`:''}</div>`;
}
function renderRecordInspection() {
  const target=$('#record-inspection');if(!target||recordInspection.id==null)return;
  const disclosures=captureDisclosures('#record-inspection');
  const state=recordInspection, close=`<button class="button small ghost" type="button" data-close-record>${t('Close snapshot','关闭快照')}</button>`;
  target.classList.remove('hidden');
  const header=`<div class="panel-head"><h2>${t('Saved snapshot','保存快照')} #${esc(state.id)}</h2>${close}</div>`;
  if(state.loading){target.innerHTML=`${header}<p role="status">${t('Loading saved inputs…','正在读取保存的输入…')}</p>`;return;}
  if(state.error){target.innerHTML=`${header}<p class="negative" role="alert">${t('Cannot load this saved snapshot: ','无法读取此保存快照：')}${esc(message(state.error.message))}</p><button class="button ghost" type="button" data-record-kind="${state.kind}" data-record-id="${esc(state.id)}">${t('Retry snapshot','重新读取快照')}</button>`;return;}
  const payload=state.payload;if(!payload)return;
  const d=payload.details||{}, audit=d.audit, title=payload.market_question||payload.question||'', amount=value=>value==null?t('Unknown','未知'):esc(value);
  const fields=[
    [t('Calculation status','计算状态'),esc(calculationStatus()[d.status]||message(d.status)||t('Unknown','未知'))],
    [t('Target shares per leg','每腿目标股数'),amount(d.target_quantity)],
    [t('Common shares','共同股数'),amount(d.executable_quantity)],
    [t('Purchase cost / pUSD','买入成本 / pUSD'),amount(d.total_cost)],
    [t('Estimated fees / pUSD','估算费用 / pUSD'),amount(d.estimated_fees)],
    [t('Slippage buffer / pUSD','滑点缓冲 / pUSD'),amount(d.slippage_buffer)],
    [t('Safety buffer / pUSD','安全缓冲 / pUSD'),amount(d.safety_buffer)],
    [t('Other costs / pUSD','其他成本 / pUSD'),amount(d.extra_cost)],
    [t('Net edge / pUSD','净差额 / pUSD'),amount(d.net_profit)],
    [t('Budget ROI / decimal','预算收益率 / 小数'),amount(d.net_roi)],
  ];
  target.innerHTML=`${header}<h3>${marketText(title)}</h3><p class="muted">${t('Historical inputs only. The figures below are one saved calculation, not current quotes or the independent historical maxima.','以下仅为一份保存计算的历史输入，不代表当前报价，也不代表各项独立历史最大值。')}</p><dl class="audit-grid">${fields.map(([label,value])=>`<dt>${label}</dt><dd>${value}</dd>`).join('')}</dl>${audit?`<p class="muted">${t('Source: ','来源：')}${esc(audit.source||t('Not recorded','未记录'))} · ${t('Received at: ','接收时间：')}${dateText(audit.as_of)}</p><details class="audit-section" data-disclosure="saved-inputs"><summary>${t('Saved rules, parameters & source order books','保存的规则、参数与来源订单簿')}</summary><pre class="audit-json">${esc(JSON.stringify(audit,null,2))}</pre></details>`:`<p class="notice">${t('This older record has no saved source order books. Its calculation cannot be independently reconstructed from this record.','此旧记录未保存来源订单簿，无法仅根据该记录独立复算。')}</p>`}<details class="audit-section" data-disclosure="saved-calculation"><summary>${t('Original calculation JSON','原始计算 JSON')}</summary><pre class="audit-json">${esc(JSON.stringify(d,null,2))}</pre></details>${payload.disappeared_reason||payload.failure_reason?`<p class="muted">${t('Recorded reason: ','记录原因：')}${esc(message(payload.disappeared_reason||payload.failure_reason))}</p>`:''}${payload.market_id?`<div class="page-actions"><a href="${currentMarketLink(payload.market_id)}">${t('Inspect current market separately','另行检查当前市场')}</a></div>`:''}`;
  restoreDisclosures('#record-inspection',disclosures);
}
async function inspectRecord(kind,id) {
  if(!['paper','history'].includes(kind)||!/^\d+$/.test(String(id)))return;
  const sequence=++recordInspection.sequence;
  Object.assign(recordInspection,{kind,id,loading:true,payload:null,error:null});renderRecordInspection();
  $('#record-inspection')?.focus?.();
  try {
    const payload=await api(kind==='paper'?`/api/paper-trades/${encodeURIComponent(id)}`:`/api/opportunities/history/${encodeURIComponent(id)}`);
    if(sequence!==recordInspection.sequence)return;
    recordInspection.payload=payload;
  } catch(error){if(sequence!==recordInspection.sequence)return;recordInspection.error=error;}
  finally {if(sequence===recordInspection.sequence){recordInspection.loading=false;renderRecordInspection();}}
}
function closeRecordInspection() {
  const {kind,id}=recordInspection;
  recordInspection.sequence++;Object.assign(recordInspection,{kind:null,id:null,loading:false,payload:null,error:null});$('#record-inspection')?.classList.add('hidden');
  if(kind&&id!=null)document.querySelector(`[data-record-kind="${kind}"][data-record-id="${id}"]`)?.focus?.();
}
function recordPagination(items, languageOnly=false) {
  const offset=languageOnly?records.appliedOffset:records.offset;
  if(!languageOnly)records.appliedOffset=offset;
  $('#record-page').textContent=items.length?t(`Records ${offset+1}–${offset+Math.min(items.length,records.limit)}`,`第 ${offset+1}–${offset+Math.min(items.length,records.limit)} 条`):t('No records on this page','当前页暂无记录');
  $('#record-previous').disabled=offset===0; $('#record-next').disabled=items.length<=records.limit;
  return items.slice(0,records.limit);
}
function renderPaperTrades(data, languageOnly=false) {
  const items=recordPagination(data.items,languageOnly);
  $('#paper-table').innerHTML=items.length?items.map(x=>`<tr><td>${dateText(x.created_at)}</td><td>${marketText(x.market_question)}${snapshotActions('paper',x.id,x.market_id)}</td><td>${num(x.target_quantity)}</td><td>${num(x.executable_quantity)}</td><td>${num(x.total_cost,6)}</td><td>${num(x.net_profit,6)}</td><td>${esc(message(x.status))}</td><td>${esc(message(x.trigger_type))}</td></tr>`).join(''):`<tr><td colspan="8" class="empty"><strong>${t('No paper observations saved','尚未保存模拟观察记录')}</strong><p>${t('Inspect an eligible scanner candidate, then save its cost estimate and source books for review.','核验符合条件的扫描候选后，可保存成本估算及来源盘口以供回看。')}</p><a href="${localUrl('/opportunities')}">${t('Open book scanner','打开盘口扫描')}</a></td></tr>`;
}
async function paperTrades() { const data=await api(`/api/paper-trades?limit=${records.limit+1}&offset=${records.offset}`);pageData['paper-trades']=data;renderPaperTrades(data); }
function renderHistory(data, languageOnly=false) {
  const items=recordPagination(data.items,languageOnly);
  $('#history-table').innerHTML=items.length?items.map(x=>`<tr><td>${marketText(x.question)}${snapshotActions('history',x.id,x.market_id)}</td><td>${dateText(x.first_seen)}</td><td>${dateText(x.last_seen)}</td><td>${num(x.max_net_profit,6)}</td><td>${pct(x.max_net_roi)}</td><td>${num(x.max_quantity)}</td><td>${esc(message(x.status))}${x.disappeared_reason?`<small class="muted">${esc(message(x.disappeared_reason))}</small>`:''}</td></tr>`).join(''):`<tr><td colspan="7" class="empty"><strong>${t('No eligible signals recorded yet','尚无符合条件的历史信号')}</strong><p>${t('The scanner saves passing snapshots automatically. Review the current sample and exclusion reasons to understand coverage.','扫描器自动保存通过条件的快照。可查看当前样本与排除原因，了解覆盖范围。')}</p><a href="${localUrl('/opportunities')}">${t('Review scanner coverage','查看扫描范围')}</a></td></tr>`;
}
async function history() { const data=await api(`/api/opportunities/history?limit=${records.limit+1}&offset=${records.offset}`);pageData.history=data;renderHistory(data); }
function renderSettingsResult() {
  const result=$('#settings-result');if(!result)return;
  const copy={dirty:t('You have unsaved changes','有未保存的修改'),pending:t('Saving…','正在保存…'),saved:t('Saved. New parameters apply at the next order book refresh.','已保存，下一轮盘口刷新采用新参数'),error:t('Save failed. Try again.','保存失败，请重试')};
  if(copy[result.dataset.state])result.textContent=copy[result.dataset.state];
}
async function settingsPage() {
  const form=$('#settings-form');
  if(!settingsBound){
    settingsBound=true;
    form.addEventListener('input',()=>{if(!settingsSaving){thresholdRevision++;settingsDirty=true;$('#settings-result').dataset.state='dirty';renderSettingsResult();}});
    form.addEventListener('submit',async event=>{
      event.preventDefault(); if(settingsSaving||!form.reportValidity())return;
      const body=Object.fromEntries(new FormData(form)), button=form.querySelector('[type="submit"]'), result=$('#settings-result');
      thresholdRevision++;settingsSaving=true; button.disabled=true; result.dataset.state='pending';renderSettingsResult();clearError();
      const inputs=[...form.querySelectorAll('input')];inputs.forEach(input=>input.disabled=true);
      try { await api('/api/settings',{method:'PUT',body:JSON.stringify(body)});settingsDirty=false;result.dataset.state='saved';renderSettingsResult(); }
      catch(error){result.dataset.state='error';renderSettingsResult();showError(error);}
      finally{thresholdRevision++;settingsSaving=false;button.disabled=false;inputs.forEach(input=>input.disabled=false);}
    });
  }
  const revision=thresholdRevision, values=await api('/api/settings');
  if(settingsDirty||settingsSaving||revision!==thresholdRevision)return;
  Object.entries(values).forEach(([key,value])=>{if(form.elements[key])form.elements[key].value=value;});
}
function renderLogUpdateState() {
  const button=$('#pause-logs');if(!button)return;
  button.textContent=logsPaused?t('Resume updates','恢复更新'):t('Pause updates','暂停更新');
  button.setAttribute?.('aria-pressed',String(logsPaused));
  if($('#log-update-state'))$('#log-update-state').textContent=logsPaused?t('Updates paused · Manual refresh remains available','更新已暂停 · 仍可手动刷新'):t('Updates every 5 seconds','每 5 秒更新');
}
function setLogsPaused(value) {
  logsPaused=value;logUpdateRevision++;renderLogUpdateState();
}
function renderLogs() {
  $('#log-table').innerHTML=logItems.filter(x=>!$('#log-level').value||x.level===$('#log-level').value).map(x=>`<tr><td>${dateText(x.created_at)}</td><td><span class="log-level ${x.level==='ERROR'?'negative':x.level==='WARNING'?'warning':'muted'}">${esc(x.level)}</span></td><td>${esc(message(x.source))}</td><td>${esc(message(x.event))}</td><td>${esc(message(x.message))}</td></tr>`).join('')||`<tr><td colspan="5" class="empty">${t('No matching events in the latest 100. Change the level filter or refresh the snapshot.','最近 100 条记录中没有匹配事件，可调整级别筛选或刷新快照。')}</td></tr>`;
  renderLogUpdateState();
}
async function logs(manual=false){
  if(logsPaused&&!manual)return false;
  const revision=logUpdateRevision, data=await api('/api/logs');
  if(!manual&&(logsPaused||revision!==logUpdateRevision))return false;
  logItems=data.items;renderLogs();
}
function renderSnapshotState() {
  if(!$('#snapshot-state'))return;
  $('#snapshot-state').textContent=refreshFailed?t('Refresh failed. Existing data is an older snapshot; refresh before assessing it.','刷新失败，已有数据是旧快照，请刷新后再判断'):lastRead?`${t('Local view refreshed: ','本地视图刷新于：')}${dateText(lastRead)} · ${t('Shanghai time; source freshness is assessed separately.','上海时间，来源时效另行核验。')}`:'';
  if(refreshFailed&&$('#system-pill')){$('#system-pill').textContent=t('Page refresh failed','页面刷新失败');$('#system-pill').className='pill waiting';}
}
async function refreshPage(run) {
  if(refreshing||!run)return;
  refreshing=true;
  const button=$('#refresh'); if(button)button.disabled=true;
  try { const applied=await run();if(applied===false)return;clearError();lastRead=new Date();refreshFailed=false;renderSnapshotState(); }
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
  renderRecordInspection();renderPaperFeedback();
  renderSnapshotState();if(lastError)showError(lastError);
}
window.addEventListener('site-language-change',renderCurrentLanguage);
document.addEventListener('DOMContentLoaded',()=>{
  const routes={dashboard,opportunities,market:marketDetail,'paper-trades':paperTrades,history,settings:settingsPage,logs}, run=routes[document.body.dataset.page];
  if(run)refreshPage(run);
  if(['dashboard','opportunities','market','logs'].includes(document.body.dataset.page))setInterval(()=>{if(!document.hidden)refreshPage(run);},5000);
  $('#refresh')?.addEventListener('click',()=>refreshPage(document.body.dataset.page==='logs'?()=>logs(true):run));
  $('#search')?.addEventListener('input',filterOpportunities);
  $('#clear-search')?.addEventListener('click',()=>{$('#search').value='';filterOpportunities();$('#search').focus();});
  document.addEventListener('click',event=>{
    const trade=event.target.closest('[data-trade]');if(trade){recordTrade(trade);return;}
    const record=event.target.closest('[data-record-kind]');if(record){inspectRecord(record.dataset.recordKind,record.dataset.recordId);return;}
    if(event.target.closest('[data-close-record]'))closeRecordInspection();
  });
  if($('#opportunity-table'))new MutationObserver(filterOpportunities).observe($('#opportunity-table'),{childList:true,subtree:true,characterData:true});
  $('#log-level')?.addEventListener('change',renderLogs);
  $('#pause-logs')?.addEventListener('click',()=>{setLogsPaused(!logsPaused);if(!logsPaused)refreshPage(run);});
  $('#record-previous')?.addEventListener('click',()=>{if(refreshing)return;records.offset=Math.max(0,records.offset-records.limit);refreshPage(run);});
  $('#record-next')?.addEventListener('click',()=>{if(refreshing)return;records.offset+=records.limit;refreshPage(run);});
});
