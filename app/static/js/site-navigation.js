/* The only mobile navigation controller; page scripts own active-route state. */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelector('.skip-link')?.addEventListener('click', event => {
    const main=document.getElementById('main-content');
    if(!main)return;
    // Hash routes belong to research.js; skip navigation must retain that view.
    event.preventDefault();main.focus();main.scrollIntoView({block:'start'});
  });
  const rail=document.querySelector('.site-rail'), toggle=document.getElementById('navigation-toggle');
  const close=document.getElementById('navigation-close'), shade=document.getElementById('navigation-shade');
  if(!rail || !toggle || !close || !shade) return;
  const mobile=window.matchMedia('(max-width:760px)');
  let opened=false, previousFocus=null;
  const backgrounds=()=>[document.querySelector('.site-content'),document.querySelector('.site-topbar')].filter(Boolean);
  const setOpen=(value,restore=true)=>{
    const next=Boolean(value && mobile.matches);
    if(next===opened)return;
    opened=next;
    toggle.setAttribute('aria-expanded',String(opened));
    document.body.classList.toggle('navigation-open',opened);
    shade.hidden=!opened;
    if(opened)previousFocus=document.activeElement;
    backgrounds().forEach(element=>{element.inert=opened;});
    if(opened)requestAnimationFrame(()=>{if(opened)close.focus();});
    else if(restore && previousFocus?.isConnected)previousFocus.focus();
  };
  toggle.addEventListener('click',()=>setOpen(!opened));
  close.addEventListener('click',()=>setOpen(false));
  shade.addEventListener('click',()=>setOpen(false));
  rail.querySelectorAll('a').forEach(link=>link.addEventListener('click',()=>setOpen(false)));
  document.addEventListener('keydown',event=>{
    if(!opened)return;
    if(event.key==='Escape'){event.preventDefault();setOpen(false);return;}
    if(event.key!=='Tab')return;
    const items=[...rail.querySelectorAll('a[href],button:not([disabled])')].filter(element=>element.getClientRects().length);
    const first=items[0], last=items[items.length-1];
    if(!first)return;
    if(!rail.contains(document.activeElement)){event.preventDefault();first.focus();}
    else if(event.shiftKey && document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first.focus();}
  });
  mobile.addEventListener('change',()=>setOpen(false,false));
});
