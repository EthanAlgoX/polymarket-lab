'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const later = () => { let resolve, reject;const promise = new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject}; };
const tick = () => new Promise(resolve=>setImmediate(resolve));
function environment(file) {
  const nodes=new Map(), rows=[], events=new Map();
  let currentLanguage='en';
  const node=selector=>{
    if(!nodes.has(selector))nodes.set(selector,{textContent:'',innerHTML:'',hidden:false,className:'',disabled:false,dataset:{},value:'',classList:{add(){this.hidden=true;},remove(){this.hidden=false;}},querySelector(){return null;},querySelectorAll(){return [];} });
    return nodes.get(selector);
  };
  const context={
    console,Promise,Map,Set,URL,URLSearchParams,AbortController,Date,Number,Math,JSON,String,
    setTimeout,clearTimeout,setInterval(){},clearInterval(){},
    document:{hidden:false,body:{dataset:{},style:{}},querySelector:node,querySelectorAll(selector){return selector.includes('tr[')?rows:[];},addEventListener(){}},
    window:{addEventListener(name,handler){if(!events.has(name))events.set(name,[]);events.get(name).push(handler);},scrollTo(){},SiteLanguage:{getLanguage:()=>currentLanguage,t:(en,zh)=>currentLanguage==='zh'?zh:en,message:value=>String(value??'')}},location:{hash:''},localStorage:{getItem(){return null;}},MutationObserver:class{observe(){}},
    MarketLanguage:{html:value=>String(value??'')},BookQuality:{html:()=>''},alert(){},fetch(){throw new Error('Unexpected network call');},
  };
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context,{filename:file});
  return {context,node,nodes,rows,events,language(value){currentLanguage=value;for(const handler of events.get('site-language-change')||[])handler();},run:source=>vm.runInContext(source,context)};
}
async function catalogRace() {
  const env=environment('app/static/js/research.js'), pending=[];
  env.context.api=()=>{const item=later();pending.push(item);return item.promise;};
  env.context.renderCatalog=data=>{env.node('#updated').textContent='revision '+data.revision;};
  const first=env.run('loadCatalog()'), second=env.run('loadCatalog()');
  pending[2].resolve({revision:2,filteredTotal:1});pending[3].resolve({});await second;
  pending[0].reject(new Error('Old failure'));pending[1].resolve({});await first;
  assert.equal(env.node('#updated').textContent,'revision 2');
  assert.equal(env.node('#banner').hidden,true);
}
async function detailQueuedParameters() {
  const env=environment('app/static/js/research.js'), pending=[], urls=[];
  env.context.api=url=>{urls.push(url);const item=later();pending.push(item);return item.promise;};
  env.run("state.selected='test';");
  const first=env.run('loadDetail()');
  env.run("state.quantity='200.0000000000000000001';state.extraCost='1e+3';state.detailSequence++;loadDetail();");
  pending[0].resolve({calculation:null,books:[],outcomes:[],asOf:'2026-10-03T00:00:00Z'});await first;await tick();
  assert.equal(urls.length,2);assert.ok(urls[1].includes('quantity=200.0000000000000000001'));assert.ok(urls[1].includes('extra_cost=1e%2B3'));
  pending[1].resolve({calculation:null,books:[null,null,null],outcomes:['Alpha','Beta','Charlie'],asOf:'2026-10-03T00:00:00Z'});await tick();
  assert.equal(env.run('loadingDetail'),false);
  assert.ok(env.node('#detail-live').innerHTML.includes('Charlie'));
  assert.ok(env.node('#detail-live').innerHTML.includes('3 outcomes'));
}
async function opportunitySearch() {
  const env=environment('app/static/js/app.js');
  env.node('#search').value='bitcoin';
  env.rows.push({dataset:{marketSearch:'Will Bitcoin rise?'},textContent:'比特币会上涨吗？',hidden:false},{dataset:{marketSearch:'Will Ethereum rise?'},textContent:'以太坊会上涨吗？',hidden:false});
  env.context.api=async()=>({items:[{market:{market_id:'btc',question:'Will Bitcoin rise?'},calculation:{}},{market:{market_id:'eth',question:'Will Ethereum rise?'},calculation:{}}]});
  await env.run('opportunities()');
  assert.equal(env.rows[0].hidden,false);assert.equal(env.rows[1].hidden,true);
  // Another automatic refresh must keep the current search.
  await env.run('opportunities()');assert.equal(env.rows[1].hidden,true);
}
async function refreshRecoveryAndPagination() {
  const env=environment('app/static/js/app.js'), response=later();let count=0;
  env.context.operation=()=>{count++;return response.promise;};
  env.run('records.offset=100;');
  const first=env.run('refreshPage(operation)');await env.run('refreshPage(operation)');assert.equal(count,1);
  response.reject(new Error('Offline'));await first;
  assert.equal(env.run('records.offset'),0);assert.ok(env.node('#snapshot-state').textContent.includes('older snapshot'));
  env.context.operation=async()=>{};await env.run('refreshPage(operation)');
  assert.equal(env.node('#error').classList.hidden,true);assert.equal(env.run('refreshing'),false);
  env.context.items=Array.from({length:101},()=>({}));
  assert.equal(env.run('recordPagination(items).length'),100);assert.equal(env.node('#record-next').disabled,false);
  env.context.items=[];env.run('recordPagination(items)');assert.equal(env.node('#record-next').disabled,true);
}
async function duplicateSimulation() {
  const env=environment('app/static/js/app.js'), response=later();let count=0;
  env.context.api=()=>{count++;return response.promise;};
  const button={dataset:{trade:'id'},disabled:false,textContent:''};env.context.button=button;
  const first=env.run('recordTrade(button)');await env.run('recordTrade(button)');
  assert.equal(count,1);assert.equal(button.disabled,true);
  response.resolve({id:1});await first;assert.equal(env.run('recording.size'),0);
}
async function translationChunks() {
  const env=environment('app/static/js/market-language.js');
  const source='Source rules 2026. 😀\n'.repeat(1600);
  const html=env.context.window.MarketLanguage.html(source);
  const parts=[...html.matchAll(/data-market-source="([^"]*)"/g)].map(match=>decodeURIComponent(match[1]));
  assert.equal(parts.join(''),source);assert.ok(parts.length>1);
  process.stdout.write(JSON.stringify(parts));
}
async function calculationSourcesAndInvalidState() {
  const env=environment('app/static/js/app.js');
  env.context.document.body.dataset.marketId='market';
  env.context.api=async()=>({question:'Public market?',calculation:{status:'INVALID_CALCULATION'},calculation_as_of:'2026-10-03T00:00:00Z',yes_orderbook:{asks:[{price:'0.99',size:'1'}]},calculation_orderbooks:[{asset_id:'rest-yes',timestamp:'100',asks:[{price:'0.25',size:'100'}]},null]});
  await env.run('marketDetail()');
  assert.ok(env.node('#calculation').innerHTML.includes('Values exceed calculation limits'));
  assert.ok(env.node('#calculation').innerHTML.includes('REST asks'));
  assert.ok(env.node('#calculation').innerHTML.includes('rest-yes'));
  assert.ok(env.node('#calculation').innerHTML.includes('0.25'));
  assert.ok(env.node('#yes-book').innerHTML.includes('0.99'));
  assert.ok(env.node('#calculation').innerHTML.includes('displayed books may have since changed'));
  for(const net_profit of ['-0.1','0.1']){
    env.context.api=async()=>({question:'Public market?',is_candidate:false,calculation:{status:'VALID',net_profit}});
    await env.run('marketDetail()');
    assert.ok(env.node('#calculation').innerHTML.includes('Book calculation valid · Below current candidate thresholds'));
  }
  env.context.api=async()=>({question:'Public market?',is_candidate:true,calculation:{status:'VALID',net_profit:'0.1'}});
  await env.run('marketDetail()');
  assert.ok(env.node('#calculation').innerHTML.includes('Book calculation valid · Meets current candidate thresholds'));
}
async function settingSaveIsSingleAndHonest() {
  const env=environment('app/static/js/app.js'), pending=later(), handlers={};let puts=0;
  let registrations=0;
  const button={disabled:false}, input={disabled:false,value:'1'};
  const form={values:{default_quantity:'1'},elements:{default_quantity:input},reportValidity:()=>true,querySelector:()=>button,querySelectorAll:()=>[input],addEventListener:(name,handler)=>{registrations++;handlers[name]=handler;}};
  env.nodes.set('#settings-form',form);
  env.context.FormData=class extends Map{constructor(value){super(Object.entries(value.values));}};
  env.context.api=(url,options)=>{if(options?.method==='PUT'){puts++;return pending.promise;}return Promise.resolve(form.values);};
  await env.run('settingsPage()');
  await env.run('settingsPage()');assert.equal(registrations,2);
  const first=handlers.submit({preventDefault(){}});await handlers.submit({preventDefault(){}});
  assert.equal(puts,1);assert.equal(button.disabled,true);assert.equal(input.disabled,true);
  pending.resolve({});await first;
  assert.equal(input.disabled,false);assert.ok(env.node('#settings-result').textContent.includes('next order book refresh'));
  handlers.input();assert.equal(env.node('#settings-result').textContent,'You have unsaved changes');
  env.context.document.body.dataset.page='settings';env.language('zh');
  assert.equal(env.node('#settings-result').textContent,'有未保存的修改');
  assert.equal(input.value,'1');assert.equal(registrations,2);
}
async function verifiedScannerMix() {
  const env=environment('app/static/js/research.js');
  assert.ok(env.run('coverageText({liveScannerEnabled:false})').includes('Local offline mode'));
  env.context.selection={selectedTotal:80,categoryCounts:{sports:40,other:40},verification:{sourceRevision:3,requestedTotal:80,verifiedTotal:8,categoryCounts:{sports:5,crypto:3},verifiedAt:'2026-10-03T00:00:00Z',failed:false}};
  const text=env.run('scannerMixText(selection)');
  assert.ok(text.includes('Actually scanning 8'));assert.ok(text.includes('Sports 5'));assert.ok(text.includes('Crypto 3'));assert.ok(!text.includes('Sports 40'));
  env.context.selection.verification.verifiedTotal=0;env.context.selection.verification.categoryCounts={};
  assert.ok(env.run('scannerMixText(selection)').includes('Actually scanning 0'));
  env.context.selection.verification.failed=true;
  assert.ok(env.run('scannerMixText(selection)').includes('verification failed; candidate assessment paused'));
  delete env.context.selection.verification;
  assert.ok(env.run('scannerMixText(selection)').includes('Catalog preselection 80'));
  assert.ok(env.run('scannerMixText(selection)').includes('Market metadata verification is still pending'));
}
async function unavailableMarketStopsDetail() {
  const env=environment('app/static/js/research.js');
  env.context.market={available:false,unavailableReason:'市场已关闭 <script>',calculation:{status:'VALID',net_profit:'100'},books:[],outcomes:[],asOf:'2026-10-03T00:00:00Z'};
  env.context.api=async()=>env.context.market;
  env.run("state.selected='test';");await env.run('loadDetail()');
  assert.ok(env.node('#detail-live').innerHTML.includes('Order book verification paused'));
  assert.ok(env.node('#detail-live').innerHTML.includes('市场已关闭 &lt;script&gt;'));
  assert.ok(!env.node('#detail-live').innerHTML.includes('Positive gap candidate'));
  assert.equal(env.node('#quantity').disabled,true);assert.equal(env.node('#extra-cost').disabled,true);
  env.context.market={available:true,calculation:null,books:[],outcomes:[],asOf:'2026-10-03T00:00:00Z'};
  await env.run('loadDetail()');assert.equal(env.node('#quantity').disabled,false);
}
async function bilingualContent() {
  const research=environment('app/static/js/research.js');
  vm.runInContext(fs.readFileSync(path.join(root,'app/static/js/research-copy.js'),'utf8'),research.context);
  research.context.publicResearchData=JSON.parse(fs.readFileSync(path.join(root,'app/research.json'),'utf8'));
  const copy=research.context.window.ResearchCopy;
  for(const strategy of research.context.publicResearchData.strategies.categoryResearch)assert.ok(copy.strategies[strategy.category]);
  for(const repo of research.context.publicResearchData.github.repos)assert.ok(copy.repos[repo.id]);
  research.run('researchData=publicResearchData;state.repoFilter="all";renderResearch();');
  for(const selector of ['#strategy-grid','#repo-grid'])assert.ok(!/[\u4e00-\u9fff]/u.test(research.node(selector).innerHTML),selector);
  assert.ok(research.node('#strategy-grid').innerHTML.includes('Weather'));
  const repoIds=[...research.node('#repo-grid').innerHTML.matchAll(/<h3>(.*?)<\/h3>/g)].map(item=>item[1]);
  research.language('zh');assert.ok(research.node('#strategy-grid').innerHTML.includes('天气'));
  assert.ok(research.node('#repo-grid').innerHTML.includes('已借鉴'));
  assert.deepEqual([...research.node('#repo-grid').innerHTML.matchAll(/<h3>(.*?)<\/h3>/g)].map(item=>item[1]),repoIds);
  research.language('en');assert.ok(!/[\u4e00-\u9fff]/u.test(research.node('#repo-grid').innerHTML));

  const detail=environment('app/static/js/research.js');
  const onChange=()=>{};
  const quantityInput={value:'199.999',onchange:onChange,disabled:false,focus(){this.focused=true;}};
  const costInput={value:'12.345',onchange:onChange,disabled:false};
  detail.nodes.set('#quantity',quantityInput);detail.nodes.set('#extra-cost',costInput);
  detail.context.document.activeElement=quantityInput;
  Object.defineProperty(detail.node('#detail-body'),'innerHTML',{set(value){this.contents=value;for(const selector of ['#quantity','#extra-cost'])detail.nodes.set(selector,{replaceWith(original){detail.nodes.set(selector,original);}});},get(){return this.contents||'';}});
  detail.context.publicDetail={available:true,question:'Source title',description:'Source rules',outcomes:[],books:[],calculation:null};
  detail.run('state.selected="test";currentDetail=publicDetail;');detail.language('zh');
  assert.equal(detail.node('#quantity'),quantityInput);assert.equal(detail.node('#extra-cost'),costInput);
  assert.equal(quantityInput.value,'199.999');assert.equal(costInput.value,'12.345');
  assert.equal(quantityInput.onchange,onChange);assert.equal(quantityInput.focused,true);
  assert.equal(detail.run('state.quantity'),100);assert.equal(detail.run('state.extraCost'),.05);
  detail.language('en');assert.equal(quantityInput.value,'199.999');assert.equal(costInput.value,'12.345');

  const app=environment('app/static/js/app.js');app.context.document.body.dataset.page='paper-trades';
  app.context.api=async()=>({items:Array.from({length:101},()=>({market_question:'Source market'}))});
  await app.run('paperTrades()');app.run('records.offset=100;');
  app.language('zh');assert.equal(app.run('records.offset'),100);assert.equal(app.run('records.appliedOffset'),0);
  assert.equal(app.node('#record-page').textContent,'第 1–100 条');
  app.language('en');assert.equal(app.node('#record-page').textContent,'Records 1–100');
  assert.ok(app.node('#paper-table').innerHTML.includes('Source market'));

  const books=environment('app/static/js/book-quality.js');
  const values=[{quality:'normal',spread:'0.02',bid_depth_quantity:'10',ask_depth_quantity:'12',imbalance:'0.1',microprice:'0.5'}];
  const englishBook=books.context.window.BookQuality.html(values);
  assert.ok(englishBook.includes('Order book quality'));assert.ok(!/[\u4e00-\u9fff]/u.test(englishBook));
  books.language('zh');const chineseBook=books.context.window.BookQuality.html(values);
  assert.ok(chineseBook.includes('盘口质量'));assert.ok(chineseBook.includes('结果 1'));
  assert.equal([...englishBook.matchAll(/<td>(.*?)<\/td>/g)].map(item=>item[1].split('<small>')[0]).join('|'),[...chineseBook.matchAll(/<td>(.*?)<\/td>/g)].map(item=>item[1].split('<small>')[0]).join('|'));
}
const tests={catalogRace,detailQueuedParameters,opportunitySearch,refreshRecoveryAndPagination,duplicateSimulation,calculationSourcesAndInvalidState,settingSaveIsSingleAndHonest,verifiedScannerMix,unavailableMarketStopsDetail,bilingualContent,translationChunks};
(async()=>{const name=process.argv[2];assert.ok(tests[name],`Unknown test ${name}`);await tests[name]();})().catch(error=>{console.error(error);process.exitCode=1;});
