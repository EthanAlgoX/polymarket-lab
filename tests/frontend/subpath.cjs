'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
function environment(prefix, script) {
  const nodes = new Map(), requests = [];
  const node = selector => {
    if (selector === 'meta[name="app-root-path"]') return {content:prefix};
    if (!nodes.has(selector)) nodes.set(selector, {innerHTML:'',textContent:'',hidden:false,dataset:{},querySelectorAll:()=>[],classList:{remove(){},add(){}},setAttribute(){}});
    return nodes.get(selector);
  };
  const context = {Promise, Map, Set, JSON, String, Date, Math, Number, URL, URLSearchParams, AbortController,
    setTimeout, clearTimeout, setInterval(){},clearInterval(){},
    localStorage:{getItem:()=>null,setItem(){}},
    CustomEvent:class {constructor(type,options){this.type=type;this.detail=options.detail;}},
    window:{addEventListener(){},dispatchEvent(){}},
    document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){},body:{dataset:{}}},
    MarketLanguage:{html:String},
    fetch:async (url,options)=>{requests.push({url,options});return {ok:true,json:async()=>({configured:false,revision:'none'})};},
  };
  vm.createContext(context);
  for (const name of ['site-paths.js',script]) vm.runInContext(fs.readFileSync(path.join(root,'app/static/js',name),'utf8'),context,{filename:name});
  return {context,node,requests,run:source=>vm.runInContext(source,context)};
}
async function main() {
  for (const prefix of ['', '/polymarket-lab']) {
    const workspace = environment(prefix,'app.js');
    assert.equal(workspace.context.window.SitePaths.url('/api/markets?q=a%26b'), prefix+'/api/markets?q=a%26b');
    assert.equal(workspace.context.window.SitePaths.url('/#markets?inspect=a%2Fb'), prefix+'/#markets?inspect=a%2Fb');
    assert.equal(workspace.context.window.SitePaths.url('https://polymarket.com/event/x'),'https://polymarket.com/event/x');
    assert.equal(workspace.context.window.SitePaths.url('#main-content'),'#main-content');
    await workspace.run("api('/api/paper-trades',{method:'POST',body:'{}'})");
    assert.equal(workspace.requests[0].url,prefix+'/api/paper-trades');
    assert.equal(workspace.requests[0].options.method,'POST');
    assert.equal(workspace.run("currentMarketLink('id/?&')"),prefix+'/#markets?inspect=id%2F%3F%26');
    workspace.run('savedPaperId=123;renderPaperFeedback()');
    assert.ok(workspace.node('#paper-feedback').innerHTML.includes('href="'+prefix+'/paper-trades"'));
    const research = environment(prefix,'research.js');
    await research.run("api('/api/inspect/101?quantity=10&extra_cost=0.05')");
    assert.equal(research.requests[0].url,prefix+'/api/inspect/101?quantity=10&extra_cost=0.05');
    const translation = environment(prefix,'market-language.js');
    await translation.context.window.MarketLanguage.getConfiguration();
    assert.equal(translation.requests[0].url,prefix+'/api/llm/config');
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
