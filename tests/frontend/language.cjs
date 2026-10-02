'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const tick = () => new Promise(resolve => setImmediate(resolve));
function environment(storage = {}) {
  const handlers = {}, nodes = new Map(), values = new Map(Object.entries(storage)), calls = [], timers = new Set();
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, {hidden:true, textContent:'', dataset:{}, setAttribute(){}, addEventListener(){}, classList:{toggle(){}}, title:''});
    return nodes.get(selector);
  };
  const labels = [{dataset:{i18nEn:'Settings',i18nZh:'设置'},textContent:'Settings'}];
  const attributeNode = {attrs:{'data-i18n-placeholder-en':'Search original text','data-i18n-placeholder-zh':'搜索原文'},getAttribute(key){return this.attrs[key];},setAttribute(key,value){this.attrs[key]=value;}};
  const context = {
    console, Promise, Map, Set, JSON, String, Date, Math, AbortController, CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},
    setTimeout(fn,ms){const timer=setTimeout(fn,ms);timers.add(timer);return timer;}, clearTimeout,
    setInterval(){}, MutationObserver:class{observe(){}},
    localStorage:{getItem:key=>values.get(key) || null,setItem:(key,value)=>values.set(key,value)},
    document:{hidden:false,documentElement:{lang:'en'},body:{},querySelector:node,querySelectorAll(selector){if(selector==='[data-i18n-en]')return labels;if(selector==='[data-i18n-placeholder-en]')return [attributeNode];return [];},addEventListener(type,fn){(handlers[type] ??= []).push(fn);}},
    window:{dispatchEvent(){},addEventListener(){}},
    fetch:async url=>{calls.push(url);return {ok:true,json:async()=>({configured:false,revision:'none'})};},
  };
  vm.createContext(context);
  for (const filename of ['site-language.js','market-language.js']) vm.runInContext(fs.readFileSync(path.join(root,'app/static/js',filename),'utf8'),context,{filename});
  return {context,values,calls,node,labels,attributeNode,start:async()=>{for(const fn of handlers.DOMContentLoaded || []) await fn();await tick();},close:()=>{for(const timer of timers)clearTimeout(timer);}};
}
async function main() {
  let env = environment({'polymarket.market-language':'zh'});
  await env.start();
  assert.equal(env.context.window.MarketLanguage.getLanguage(),'en');
  assert.equal(env.context.document.documentElement.lang,'en');
  assert.equal(env.context.window.SiteLanguage.message('Value error, 扫描参数必须是非负有限数值'), 'Value error, Scanner parameters must be finite and nonnegative');
  assert.equal(env.calls.length,0,'English startup must not call the LLM or config API');
  assert.equal(await env.context.window.MarketLanguage.setLanguage('zh'),false);
  assert.equal(env.context.window.MarketLanguage.getLanguage(),'en');
  assert.equal(env.node('#language-notice').hidden,false);
  assert.deepEqual(env.calls,['/api/llm/config']);
  env.close();

  env=environment({'polymarket.site-language.v2':'zh','polymarket.market-translations.market-zh-v3.old':JSON.stringify([['Will Bitcoin rise?','比特币会上涨吗？']])});
  await env.start();
  assert.equal(env.context.window.MarketLanguage.getLanguage(),'en','A saved Chinese preference cannot bypass a missing key');
  assert.ok(env.context.window.MarketLanguage.html('Will Bitcoin rise?').includes('Will Bitcoin rise?'));
  env.context.fetch=async()=>{throw new Error('Offline');};
  assert.equal(await env.context.window.MarketLanguage.setLanguage('zh'),false);
  assert.equal(env.context.window.MarketLanguage.getLanguage(),'en');
  env.close();

  env=environment({'polymarket.market-translations.market-zh-v3.a':JSON.stringify([['Will Bitcoin rise?','比特币会上涨吗？']])});
  env.context.fetch=async()=>({ok:true,json:async()=>({configured:true,revision:'a',provider:'deepseek'})});
  await env.start();
  assert.equal(await env.context.window.MarketLanguage.setLanguage('zh'),true);
  assert.equal(env.context.document.documentElement.lang,'zh-CN');
  assert.equal(env.labels[0].textContent,'设置');
  assert.equal(env.context.window.SiteLanguage.message('The translation API account has insufficient credit.'), '翻译 API 账户余额不足，请检查账户余额。');
  assert.equal(env.attributeNode.attrs.placeholder,'搜索原文');
  assert.ok(env.context.window.MarketLanguage.html('Will Bitcoin rise?').includes('比特币会上涨吗？'));
  env.context.window.MarketLanguage.configurationChanged({configured:true,revision:'b'});
  assert.ok(env.context.window.MarketLanguage.html('Will Bitcoin rise?').includes('>Will Bitcoin rise?</span>'),'Changing model/provider must not reuse another configuration cache');
  env.context.window.MarketLanguage.configurationChanged({configured:false,revision:'none'});
  assert.equal(env.context.window.MarketLanguage.getLanguage(),'en');
  assert.equal(env.labels[0].textContent,'Settings');
  assert.equal(env.values.get('polymarket.site-language.v2'),'en');
  env.close();

  env=environment();let resolve;
  env.context.fetch=()=>new Promise(done=>{resolve=done;});
  const chinese=env.context.window.MarketLanguage.setLanguage('zh');
  await env.context.window.MarketLanguage.setLanguage('en');
  resolve({ok:true,json:async()=>({configured:true,revision:'a'})});await chinese;
  assert.equal(env.context.window.MarketLanguage.getLanguage(),'en','A late config response must not override a newer language choice');
  env.close();
  env=environment();let resolveConfiguration;
  env.context.fetch=()=>new Promise(done=>{resolveConfiguration=done;});
  const oldGet=env.context.window.MarketLanguage.getConfiguration();
  env.context.window.MarketLanguage.configurationChanged({configured:true,revision:'new'});
  resolveConfiguration({ok:true,json:async()=>({configured:false,revision:'old'})});
  assert.equal((await oldGet).revision,'new','An old GET cannot overwrite a newly saved API configuration');
  env.close();

  env=environment();let rejectConfiguration;
  env.context.window.MarketLanguage.configurationChanged({configured:true,revision:'old'});
  env.context.fetch=()=>new Promise((done,reject)=>{rejectConfiguration=reject;});
  const failedGet=env.context.window.MarketLanguage.getConfiguration();
  env.context.window.MarketLanguage.configurationChanged({configured:false,revision:'removed'});
  rejectConfiguration(new Error('Stale network failure'));
  assert.equal((await failedGet).configured,false,'An old request failure cannot replace a successful removal');
  env.close();
  console.log('English defaults, API gate, locale labels, cache isolation, and language race checks passed');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
