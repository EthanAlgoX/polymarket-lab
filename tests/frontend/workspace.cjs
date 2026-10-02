'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const pending = () => { let resolve, reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject}; };
const escape = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function environment() {
  const nodes=new Map(), rows=[], events=new Map(), documentEvents=new Map(), timers=[];
  let language='en', alerts=0;
  const node=selector=>{
    if(!nodes.has(selector)){
      const element={textContent:'',innerHTML:'',hidden:false,disabled:false,value:'',dataset:{},attributes:{},listeners:{},disclosures:[],focus(){this.focused=true;},setAttribute(name,value){this.attributes[name]=value;},querySelector(){return null;},querySelectorAll(){return this.disclosures;},addEventListener(name,handler){this.listeners[name]=handler;}};
      element.classList={add(value){if(value==='hidden')element.hidden=true;},remove(value){if(value==='hidden')element.hidden=false;}};
      nodes.set(selector,element);
    }
    return nodes.get(selector);
  };
  const context={console,Promise,Map,Set,URL,URLSearchParams,AbortController,Date,Number,Math,JSON,String,setTimeout,clearTimeout,setInterval(fn,delay){timers.push({fn,delay});},clearInterval(){},
    document:{hidden:false,body:{dataset:{},style:{}},querySelector:node,querySelectorAll(selector){return selector.includes('tr[')?rows:[];},addEventListener(name,handler){documentEvents.set(name,handler);}},
    window:{addEventListener(name,handler){events.set(name,handler);},SiteLanguage:{getLanguage:()=>language,t:(en,zh)=>language==='zh'?zh:en,message:value=>String(value??'')}},
    MarketLanguage:{html:escape},BookQuality:{html:()=>''},MutationObserver:class {observe(){}},FormData:class extends Map {constructor(form){super(Object.entries(form.values));}},alert(){alerts++;},fetch(){throw new Error('Unexpected network');}};
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'app/static/js/app.js'),'utf8'),context);
  return {context,node,nodes,rows,timers,documentEvents,run:source=>vm.runInContext(source,context),language(value){language=value;events.get('site-language-change')?.();},get alerts(){return alerts;}};
}
async function scannerZeroAndSearch() {
  const env=environment();env.context.response={items:[],scanner_diagnostics:{selected_count:3,calculated_count:3,candidate_count:0,reason_counts:{FEE_UNKNOWN:1,STALE:2},thresholds:{minimum_net_profit:'0.1',minimum_net_roi:'0.01',minimum_executable_quantity:'1',max_quote_age_seconds:'15'},calculation_as_of:'2026-10-03T00:00:00Z'}};
  env.context.api=async()=>env.context.response;await env.run('opportunities()');
  assert.ok(env.node('#opportunity-table').innerHTML.includes('valid result'));
  assert.ok(env.node('#scanner-diagnostics').innerHTML.includes('Unknown fees'));
  assert.ok(env.node('#scanner-diagnostics').innerHTML.includes('15'));
  assert.ok(env.node('#scanner-diagnostics').innerHTML.includes('Limited sample, not the whole catalog'));
  env.rows.push({dataset:{marketSearch:'Bitcoin? '},textContent:'比特币',hidden:false},{dataset:{marketSearch:'Ethereum?'},textContent:'以太坊',hidden:false});
  env.node('#search').value='nonexistent';env.run('filterOpportunities()');
  assert.equal(env.node('#opportunity-search-empty').hidden,false);assert.equal(env.node('#opportunity-result-count').textContent,'0 of 2 candidates shown');
  env.node('#search').value='比特币';env.run('filterOpportunities()');assert.equal(env.rows[0].hidden,false);assert.equal(env.rows[1].hidden,true);assert.equal(env.node('#opportunity-search-empty').hidden,true);
}
async function saveFeedbackAndDuplicateGuard() {
  const env=environment(), request=pending();let calls=0;
  env.context.api=(url,options)=>{calls++;assert.equal(url,'/api/paper-trades');assert.equal(JSON.parse(options.body).market_id,'101');return request.promise;};
  env.context.button={dataset:{trade:'101'},disabled:false,textContent:''};
  const saving=env.run('recordTrade(button)');await env.run('recordTrade(button)');assert.equal(calls,1);
  request.resolve({id:42});await saving;assert.equal(env.alerts,0);assert.equal(env.node('#paper-feedback').hidden,false);
  assert.ok(env.node('#paper-feedback').innerHTML.includes('Paper record #42 saved'));assert.ok(env.node('#paper-feedback').innerHTML.includes('href="/paper-trades"'));
  env.language('zh');assert.ok(env.node('#paper-feedback').innerHTML.includes('观察记录 #42'));assert.equal(calls,1);
}
async function savedSnapshotRaceAndPrecision() {
  const env=environment(), requests=[];
  env.context.api=url=>{const request=pending();requests.push({url,...request});return request.promise;};
  const first=env.run("inspectRecord('paper','11')"), second=env.run("inspectRecord('history','12')");
  assert.equal(requests[0].url,'/api/paper-trades/11');assert.equal(requests[1].url,'/api/opportunities/history/12');
  requests[0].resolve({id:11,market_question:'Old result',details:{}});await first;
  assert.ok(!env.node('#record-inspection').innerHTML.includes('Old result'));
  requests[1].resolve({id:12,question:'Current <script> title',market_id:'id/?&',details:{status:'VALID',net_profit:'0.000000000000000000123',net_roi:'0.0000000000000000001',audit:{source:'public CLOB',as_of:'2026-10-03T00:00:00Z',market:{description:'Original <script> rules'},orderbooks:[{asset_id:'No-first',asks:[{price:'0.50000000000000001',size:'1'}]}]}}});await second;
  let html=env.node('#record-inspection').innerHTML;
  assert.ok(html.includes('0.000000000000000000123'));assert.ok(html.includes('0.50000000000000001'));assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('/#markets?inspect=id%2F%3F%26'));
  const disclosure={dataset:{disclosure:'saved-inputs'},open:true};env.node('#record-inspection').disclosures=[disclosure];
  env.language('zh');html=env.node('#record-inspection').innerHTML;assert.ok(html.includes('保存快照'));assert.ok(html.includes('0.000000000000000000123'));assert.equal(disclosure.open,true);assert.equal(requests.length,2);
  const third=env.run("inspectRecord('paper','13')");env.run('closeRecordInspection()');requests[2].resolve({id:13,market_question:'Late result',details:{}});await third;
  assert.equal(env.node('#record-inspection').hidden,true);assert.ok(!env.node('#record-inspection').innerHTML.includes('Late result'));
  const legacy=env.run("inspectRecord('paper','14')");requests[3].resolve({id:14,market_question:'Legacy',details:{status:'VALID'}});await legacy;
  assert.ok(env.node('#record-inspection').innerHTML.includes('此旧记录未保存来源订单簿'));
}
async function pausedLogsDiscardInFlightAndAllowManualRefresh() {
  const env=environment();env.context.document.body.dataset.page='logs';env.context.api=async()=>({items:[{level:'INFO',message:'Stable original'}]});await env.run('refreshPage(logs)');
  const oldRead=env.run('lastRead'), request=pending();let calls=0;
  env.context.api=()=>{calls++;return request.promise;};
  const refreshing=env.run('refreshPage(logs)');env.run('setLogsPaused(true)');request.resolve({items:[{level:'INFO',message:'Unwanted automatic update'}]});await refreshing;
  assert.ok(env.node('#log-table').innerHTML.includes('Stable original'));assert.ok(!env.node('#log-table').innerHTML.includes('Unwanted'));
  assert.equal(env.run('lastRead'),oldRead);await env.run('logs()');assert.equal(calls,1);
  env.context.api=async()=>({items:[{level:'ERROR',message:'Explicit refresh'}]});await env.run('refreshPage(()=>logs(true))');
  assert.ok(env.node('#log-table').innerHTML.includes('Explicit refresh'));assert.equal(env.run('logsPaused'),true);
  env.node('#log-level').value='INFO';env.run('renderLogs()');assert.ok(!env.node('#log-table').innerHTML.includes('Explicit refresh'));
  env.language('zh');assert.equal(env.node('#pause-logs').textContent,'恢复更新');assert.equal(env.node('#pause-logs').attributes['aria-pressed'],'true');
}
async function settingsDraftAndSaveProtectAgainstOldLoads() {
  const env=environment(), handlers={}, input={value:'',disabled:false}, button={disabled:false};
  const form={values:{default_quantity:'1'},elements:{default_quantity:input},reportValidity:()=>true,querySelector:()=>button,querySelectorAll:()=>[input],addEventListener(name,handler){handlers[name]=handler;}};env.nodes.set('#settings-form',form);
  const initial=pending();env.context.api=()=>initial.promise;const loading=env.run('settingsPage()');input.value='123.000001';handlers.input();initial.resolve({default_quantity:'100'});await loading;assert.equal(input.value,'123.000001');
  env.context.document.body.dataset.page='settings';env.language('zh');assert.equal(input.value,'123.000001');assert.equal(env.node('#settings-result').textContent,'有未保存的修改');
  env.context.api=async()=>({default_quantity:'100'});await env.run('settingsPage()');assert.equal(input.value,'123.000001');
  const oldLoad=pending();let puts=0;env.context.api=(url,options)=>{if(options?.method==='PUT'){puts++;return Promise.resolve({});}return oldLoad.promise;};
  const loadingAgain=env.run('settingsPage()');await handlers.submit({preventDefault(){}});assert.equal(puts,1);oldLoad.resolve({default_quantity:'9'});await loadingAgain;assert.equal(input.value,'123.000001');
}
async function monitorUsesSingleStatusPayload() {
  const env=environment(), calls=[];
  env.context.api=async url=>{calls.push(url);if(url==='/api/dashboard')return {paper_trade_count:2,estimated_paper_profit:'0.1',status:{gamma_status:'正常',clob_status:'正常',live_scanner_enabled:true,active_market_count:100,binary_market_count:80,subscribed_tokens:160,scanner_diagnostics:{selected_count:80,calculated_count:76,candidate_count:0}}};return {items:[]};};
  await env.run('dashboard()');assert.deepEqual(calls,['/api/dashboard','/api/markets?limit=8']);assert.equal(env.node('#binary-markets').textContent,'80');assert.equal(env.node('#calculated-markets').textContent,'76');assert.equal(env.node('#opportunity-count').textContent,'0');
  assert.ok(env.node('#market-preview').innerHTML.includes('Open connection logs'));
}
async function detailsRetainDisclosureAndYesNoMapping() {
  const env=environment(), rules={dataset:{disclosure:'rules'},open:true}, source={dataset:{disclosure:'rest-source'},open:true};
  env.node('#market-summary').disclosures=[rules];env.node('#calculation').disclosures=[source];
  env.context.market={market_id:'reversed',question:'Reversed source order',outcomes:['No','Yes'],token_ids:['no-token','yes-token'],yes_token_id:'yes-token',no_token_id:'no-token',is_candidate:true,calculation:{status:'VALID'},calculation_orderbooks:[{asset_id:'yes-token',asks:[{price:'0.2',size:'1'}]},{asset_id:'no-token',asks:[{price:'0.3',size:'1'}]}]};
  env.run('renderMarketDetail(market)');const html=env.node('#calculation').innerHTML;
  assert.ok(html.indexOf('<h3>Yes</h3>')<html.indexOf('yes-token'));assert.ok(html.indexOf('<h3>No</h3>')<html.indexOf('no-token'));assert.equal(rules.open,true);assert.equal(source.open,true);assert.ok(html.includes('data-trade="reversed"'));
  env.context.document.body.dataset.page='market';env.context.api=async()=>env.context.market;await env.run('marketDetail()');env.language('zh');assert.equal(source.open,true);
}
const cases={scannerZeroAndSearch,saveFeedbackAndDuplicateGuard,savedSnapshotRaceAndPrecision,pausedLogsDiscardInFlightAndAllowManualRefresh,settingsDraftAndSaveProtectAgainstOldLoads,monitorUsesSingleStatusPayload,detailsRetainDisclosureAndYesNoMapping};
(async()=>{const name=process.argv[2];assert.ok(cases[name],`Unknown case ${name}`);await cases[name]();})().catch(error=>{console.error(error);process.exitCode=1;});
