'use strict';
const fs=require('node:fs'), path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'), handlers={};
function node(id) {
  return {id,attrs:{},events:{},hidden:false,inert:false,isConnected:true,
    setAttribute(key,value){this.attrs[key]=value;},
    addEventListener(type,fn){this.events[type]=fn;},
    focus(){document.activeElement=this;},
    getClientRects(){return [{}];}
  };
}
const brand=node('brand'),close=node('close'),last=node('logs'),links=[brand,last],items=[brand,close,last];
const rail=node('rail'),toggle=node('toggle'),shade=node('shade'),main=node('main'),topbar=node('topbar');
rail.querySelectorAll=selector=>selector==='a'?links:items;
rail.contains=element=>items.includes(element);
const media={matches:true,addEventListener(type,fn){this.changed=fn;}}, classes=new Set();
const document={activeElement:toggle,body:{classList:{toggle(name,value){value?classes.add(name):classes.delete(name);}}},
  querySelector(selector){return {'.site-rail':rail,'.site-content':main,'.site-topbar':topbar}[selector];},
  getElementById(id){return {'navigation-toggle':toggle,'navigation-close':close,'navigation-shade':shade}[id];},
  addEventListener(type,fn){handlers[type]=fn;}};
Object.defineProperty(topbar,'inert',{get(){return this._inert||false;},set(value){this._inert=value;if(value&&document.activeElement===toggle)document.activeElement=document.body;}});
vm.runInNewContext(fs.readFileSync(path.join(root,'app/static/js/site-navigation.js'),'utf8'),{document,window:{matchMedia:()=>media},requestAnimationFrame:fn=>fn()});
handlers.DOMContentLoaded();
toggle.events.click();
assert.equal(toggle.attrs['aria-expanded'],'true');
assert.equal(main.inert,true);assert.equal(topbar.inert,true);
assert.equal(shade.hidden,false);assert.equal(document.activeElement,close);
document.activeElement=last;
let prevented=false;
handlers.keydown({key:'Tab',shiftKey:false,preventDefault(){prevented=true;}});
assert.equal(prevented,true);assert.equal(document.activeElement,brand);
handlers.keydown({key:'Tab',shiftKey:true,preventDefault(){}});
assert.equal(document.activeElement,last);
handlers.keydown({key:'Escape',preventDefault(){}});
assert.equal(main.inert,false);assert.equal(topbar.inert,false);
assert.equal(document.activeElement,toggle);assert.equal(shade.hidden,true);
toggle.events.click();document.activeElement=document.body;
handlers.keydown({key:'Tab',shiftKey:false,preventDefault(){}});
assert.equal(document.activeElement,brand,'Lost native focus must return inside the open navigation');
handlers.keydown({key:'Escape',preventDefault(){}});
toggle.events.click();last.events.click();
assert.equal(classes.has('navigation-open'),false,'Navigating to a route must close mobile navigation');
toggle.events.click();media.matches=false;media.changed();
assert.equal(main.inert,false,'Changing to desktop must release the work surface');
toggle.events.click();assert.equal(classes.has('navigation-open'),false,'Desktop toggle must not open mobile navigation');
console.log('PASS mobile navigation focus containment, escape recovery, route close and desktop transition');
