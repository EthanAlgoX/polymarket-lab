'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const later = () => {let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
function environment(){
  const nodes=new Map(),events=new Map();let language='en';
  const node=selector=>{if(!nodes.has(selector))nodes.set(selector,{innerHTML:'',textContent:'',hidden:false,disabled:false,dataset:{},value:'',inert:false,attributes:{},setAttribute(key,value){this.attributes[key]=value;},focus(){this.focused=true;},querySelector(){return null;},querySelectorAll(){return [];}});return nodes.get(selector);};
  const location={hash:'#markets',pathname:'/',search:''};
  const context={console,Promise,URL,URLSearchParams,AbortController,Date,Number,Math,JSON,String,Map,Set,setTimeout,clearTimeout,setInterval(){},document:{hidden:false,activeElement:null,body:{style:{}},querySelector:node,querySelectorAll(){return [];},addEventListener(){}},location,
    window:{scrollTo(){},addEventListener(name,handler){events.set(name,handler);},history:{replaceState(_state,_title,url){location.hash='#'+url.split('#')[1];}},SiteLanguage:{getLanguage:()=>language,t:(en,zh)=>language==='zh'?zh:en,message:value=>String(value??'')}},
    MarketLanguage:{html:value=>String(value??'')},BookQuality:{html:()=>''},fetch(){throw new Error('Unexpected request');}};
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'app/static/js/research.js'),'utf8'),context);
  return {context,node,run:source=>vm.runInContext(source,context),language(value){language=value;events.get('site-language-change')?.();}};
}
function snapshot(revision=1){return {revision,total:81,filteredTotal:81,filteredVolume24h:1000,filteredLiquidity:2000,candidateCount:1,scannerCount:8,scannerRefreshSeconds:5,coverage:'capped',pages:100,categories:[{id:'sports',count:50,volume24h:500}],items:[],updatedAt:'2026-10-03T00:00:00Z'};}
async function appliedCatalogAndStatusIsolation(){
  const env=environment(),pending=[];env.context.api=url=>{const value=later();pending.push({url,...value});return value.promise;};
  const first=env.run('loadCatalog()');pending[0].resolve(snapshot());pending[1].resolve({gamma_status:'正常',clob_status:'正常'});await first;
  assert.equal(env.node('#page-info').textContent,'1–40 / 81');
  env.run('state.category="sports";state.offset=40;');const second=env.run('loadCatalog()');
  assert.equal(env.node('#market-surface').attributes['aria-busy'],'true');assert.equal(env.node('#next').disabled,true);
  env.language('zh');assert.ok(env.node('#result-count').textContent.includes('全部市场'));assert.equal(env.node('#page-info').textContent,'1–40 / 81');
  pending[2].reject(new Error('Catalog unavailable'));pending[3].resolve({});await second;
  assert.equal(env.node('#previous').disabled,true);assert.equal(env.node('#next').disabled,true);assert.ok(env.node('#catalog-loading').textContent.includes('先前结果'));
  env.language('en');assert.ok(env.node('#result-count').textContent.includes('All markets'));assert.equal(env.node('#page-info').textContent,'1–40 / 81');
  const retry=env.run('loadCatalog()');pending[4].resolve(snapshot(2));pending[5].reject(new Error('Monitor unavailable'));await retry;
  assert.ok(env.node('#result-count').textContent.includes('Sports'));assert.equal(env.node('#page-info').textContent,'41–80 / 81');
  assert.equal(env.node('#live-status').textContent,'Scanner status unavailable');assert.equal(env.node('#banner').hidden,true);assert.equal(env.node('#market-surface').attributes['aria-busy'],'false');
  assert.ok(env.node('#coverage').textContent.includes('Coverage capped'));assert.ok(env.node('#scan-scope').textContent.includes('Global'));
}
async function inspectDeepLinksAndFocus(){
  const env=environment();env.context.api=async()=>({available:false,question:'Closed market',unavailableReason:'Market closed',calculation:null,books:[],outcomes:[]});
  env.context.location.hash='#markets?inspect=expired%2Fid%20%26&filter=preserved';
  const route=env.run('routeFromHash(location.hash)');assert.equal(route.view,'markets');assert.equal(route.inspect,'expired/id &');
  env.run('applyRoute()');assert.equal(env.run('state.selected'),'expired/id &');
  for(const selector of ['.site-content','.site-rail','.site-topbar'])assert.equal(env.node(selector).inert,true);
  assert.equal(env.node('#close-drawer').focused,true);await Promise.resolve();await Promise.resolve();
  const sequence=env.run('state.detailSequence');env.run('applyRoute()');assert.equal(env.run('state.detailSequence'),sequence);
  env.run('closeDetail()');assert.equal(env.run('state.selected'),null);assert.equal(env.context.location.hash,'#markets?filter=preserved');
  for(const selector of ['.site-content','.site-rail','.site-topbar'])assert.equal(env.node(selector).inert,false);
  assert.equal(env.node('#drawer').hidden,true);assert.equal(env.node('#drawer-shade').hidden,true);
  env.context.location.hash='#strategies?inspect=ignored';assert.equal(env.run('routeFromHash(location.hash).inspect'),null);
}
async function honestPreviewAndInitialError(){
  const env=environment();env.context.market={available:true,minimumOrderSize:1,calculation:{status:'VALID',net_profit:'0.1'}};
  const html=env.run('calcHtml(market)');assert.ok(html.includes('Positive estimated gap'));assert.ok(html.includes('scanner thresholds still need checking'));assert.ok(!html.includes('Positive gap candidate'));
  env.context.api=async()=>{throw new Error('Unavailable');};await env.run('loadCatalog()');
  assert.ok(env.node('#market-rows').innerHTML.includes('Could not load the market directory'));assert.equal(env.node('#next').disabled,true);
  await env.run('loadResearch()');assert.ok(env.node('#repo-grid').innerHTML.includes('Retry loading references'));
  env.language('zh');assert.ok(env.node('#repo-grid').innerHTML.includes('重新加载参考资料'));
}
const tests={appliedCatalogAndStatusIsolation,inspectDeepLinksAndFocus,honestPreviewAndInitialError};
(async()=>{const name=process.argv[2];assert.ok(tests[name],`Unknown case ${name}`);await tests[name]();})().catch(error=>{console.error(error);process.exitCode=1;});
