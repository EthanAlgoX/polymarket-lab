(() => {
  'use strict';
  const preferenceKey = 'polymarket.market-language';
  const cacheKey = 'polymarket.market-translations.deepseek-flash.market-zh-v2';
  const cache = new Map();
  const esc = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  let language = 'zh', requestRunning = false, scanTimer, pollTimer, persistTimer, providerAvailable = null;
  try {
    if (localStorage.getItem(preferenceKey) === 'en') language = 'en';
    const saved = JSON.parse(localStorage.getItem(cacheKey) || '[]');
    if (Array.isArray(saved)) saved.slice(-500).forEach(pair => {
      if (Array.isArray(pair) && pair.length === 2 && pair.every(text => typeof text === 'string' && text.length <= 20000)) cache.set(pair[0], {status:'ready', text:pair[1]});
    });
  } catch { /* Display and translation still work when browser storage is unavailable. */ }

  const sourceOf = element => {
    try { return decodeURIComponent(element.dataset.marketSource || ''); } catch { return element.dataset.marketSource || ''; }
  };
  const needsTranslation = source => /[A-Za-z]/.test(source);
  const displayed = source => language === 'zh' && cache.get(source)?.status === 'ready' ? cache.get(source).text : source;
  const splitText = source => {
    const parts = [];
    while (source.length > 18000) {
      let boundary = source.lastIndexOf('\n', 18000);
      if (boundary < 9000) boundary = source.lastIndexOf('. ', 18000);
      if (boundary < 9000) boundary = 18000;
      else boundary += 1;
      // Preserve complete Unicode characters and every original whitespace character.
      if (/[\uD800-\uDBFF]/.test(source.charAt(boundary - 1))) boundary -= 1;
      parts.push(source.slice(0, boundary));
      source = source.slice(boundary);
    }
    parts.push(source);
    return parts;
  };
  function html(value) {
    return splitText(String(value ?? '')).map(source => `<span class="market-text" data-market-text data-market-source="${esc(encodeURIComponent(source))}" title="${esc(source)}" lang="${language === 'zh' && cache.get(source)?.status === 'ready' ? 'zh-CN' : 'en'}" translate="no">${esc(displayed(source))}</span>`).join('');
  }
  function visibleElements() {
    return Array.from(document.querySelectorAll('[data-market-text]')).filter(element => {
      if (element.closest('[hidden]')) return false;
      const details = element.closest('details');
      return !details || details.open || !!element.closest('summary');
    });
  }
  function apply(element) {
    const source = sourceOf(element), entry = cache.get(source), text = displayed(source);
    if (element.textContent !== text) element.textContent = text;
    element.title = source;
    element.lang = language === 'zh' && (!needsTranslation(source) || entry?.status === 'ready') ? 'zh-CN' : 'en';
    element.dataset.translationState = language === 'en' || !needsTranslation(source) ? 'original' : entry?.status || 'pending';
  }
  function updateControls(elements = visibleElements()) {
    document.querySelectorAll('[data-market-language]').forEach(button => {
      const active = button.dataset.marketLanguage === language;
      button.setAttribute('aria-pressed', String(active));
      button.classList.toggle('active', active);
    });
    const sources = [...new Set(elements.map(sourceOf).filter(needsTranslation))];
    const errors = sources.filter(source => cache.get(source)?.status === 'error');
    const pending = sources.filter(source => !cache.has(source) || cache.get(source).status === 'pending');
    let message = sources.length ? '已显示中文' : '中文模式';
    if (language === 'en') message = '显示英文原文';
    else if (providerAvailable === false && (errors.length || pending.length)) message = '中文翻译未接通 · 暂显原文';
    else if (errors.length) message = pending.length ? `翻译中 · ${errors.length} 条暂显原文` : '部分翻译不可用 · 保留原文';
    else if (pending.length) message = providerAvailable === false ? '中文翻译准备中 · 暂显原文' : `正在翻译 · ${pending.length} 条待完成`;
    document.querySelectorAll('[data-market-language-status]').forEach(element => {
      if (element.textContent !== message) element.textContent = message;
      element.title = language === 'zh' && errors.length ? `${cache.get(errors[0])?.reason || '翻译暂时不可用'}。稍后点击中文或刷新数据重试。` : '';
    });
  }
  function persist() {
    // Keep long-running refresh sessions bounded without evicting visible or pending text.
    const visible = new Set(visibleElements().map(sourceOf));
    for (const [source, entry] of cache) {
      if (cache.size <= 10000) break;
      if (!visible.has(source) && entry.status !== 'pending') cache.delete(source);
    }
    clearTimeout(persistTimer);
    persistTimer = setTimeout(() => {
      let size = 0;
      const ready = [...cache].filter(([, entry]) => entry.status === 'ready').reverse().filter(([source, entry]) => {
        size += source.length + entry.text.length;
        return size <= 450000;
      }).slice(0, 400).map(([source, entry]) => [source, entry.text]).reverse();
      try { localStorage.setItem(cacheKey, JSON.stringify(ready)); } catch { /* The backend also caches completed translations. */ }
    }, 150);
  }
  function scheduleScan(delay = 60) {
    clearTimeout(scanTimer);
    scanTimer = setTimeout(scan, delay);
  }
  function armPoll(elements) {
    clearTimeout(pollTimer);
    if (language !== 'zh') return;
    const due = elements.map(sourceOf).map(source => cache.get(source)).filter(entry => entry?.status === 'pending').map(entry => entry.retryAt || Date.now());
    if (due.length) pollTimer = setTimeout(scan, Math.max(150, Math.min(...due) - Date.now()));
  }
  async function scan() {
    const elements = visibleElements();
    elements.forEach(apply);
    updateControls(elements);
    if (language !== 'zh') { clearTimeout(pollTimer); return; }
    if (requestRunning) return;
    const now = Date.now();
    const sources = [...new Set(elements.map(sourceOf).filter(needsTranslation))];
    const request = [];
    let characters = 0;
    for (const source of sources) {
      const entry = cache.get(source);
      if (entry?.status === 'ready' || entry?.status === 'error' || (entry?.retryAt || 0) > now) continue;
      if (entry?.pendingSince && now - entry.pendingSince > 600000) {
        cache.set(source, {status:'error', reason:'翻译等待超时', retryAt:now + 30000});
        continue;
      }
      if (request.length >= 80 || characters + source.length > 90000) break;
      request.push(source);
      characters += source.length;
      cache.set(source, {status:'pending', pendingSince:entry?.pendingSince || now, retryAt:now + 1100});
    }
    if (!request.length) { updateControls(elements); armPoll(elements); return; }
    requestRunning = true;
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 20000);
    try {
      const response = await fetch('/api/translations', {method:'POST', headers:{'Accept':'application/json','Content-Type':'application/json'}, body:JSON.stringify({texts:request}), signal:abort.signal});
      if (!response.ok) throw new Error(`翻译服务请求失败（${response.status}）`);
      const result = await response.json();
      providerAvailable = result.available;
      const items = new Map((Array.isArray(result.items) ? result.items : []).filter(item => item && request.includes(item.source)).map(item => [item.source, item]));
      request.forEach(source => {
        const item = items.get(source), previous = cache.get(source);
        if (item?.status === 'ready' && typeof item.text === 'string' && item.text.trim()) {
          cache.delete(source);
          cache.set(source, {status:'ready', text:item.text});
        } else if (item?.status === 'pending') {
          cache.set(source, {status:'pending', pendingSince:previous.pendingSince, retryAt:Date.now() + 1100});
        } else {
          cache.set(source, {status:'error', reason:item?.reason || '翻译服务未返回有效译文', retryAt:Date.now() + 30000});
        }
      });
      persist();
    } catch (error) {
      request.forEach(source => cache.set(source, {status:'error', reason:error.name === 'AbortError' ? '翻译服务响应超时' : error.message, retryAt:Date.now() + 30000}));
    } finally {
      clearTimeout(timeout);
      requestRunning = false;
      // Read the current language and current nodes again: a user may have switched
      // language or refreshed the market list while this response was in flight.
      scheduleScan(20);
    }
  }
  function retryFailed() {
    const now = Date.now();
    cache.forEach((entry, source) => { if (entry.status === 'error' && (entry.retryAt || 0) <= now) cache.delete(source); });
  }
  function setLanguage(value) {
    if (!['zh', 'en'].includes(value)) return;
    language = value;
    try { localStorage.setItem(preferenceKey, value); } catch { /* Preference remains active for this page. */ }
    retryFailed();
    // Restore even text in a collapsed rules section immediately on a language switch.
    document.querySelectorAll('[data-market-text]').forEach(apply);
    updateControls();
    scheduleScan(0);
  }
  window.MarketLanguage = {html, setLanguage, refresh:() => {retryFailed(); scheduleScan(0);}, getLanguage:() => language};
  document.addEventListener('DOMContentLoaded', () => {
    document.addEventListener('click', event => {
      const button = event.target.closest('[data-market-language]');
      if (button) setLanguage(button.dataset.marketLanguage);
      if (event.target.closest('#refresh')) { retryFailed(); scheduleScan(); }
    });
    document.addEventListener('toggle', event => { if (event.target.matches('details')) scheduleScan(); }, true);
    new MutationObserver(records => {
      if (records.some(record => record.type === 'attributes' || [...record.addedNodes].some(node => node.nodeType === 1 && (node.matches?.('[data-market-text]') || node.querySelector?.('[data-market-text]'))))) scheduleScan();
    }).observe(document.body, {childList:true, subtree:true, attributes:true, attributeFilter:['hidden']});
    document.addEventListener('visibilitychange', () => { if (!document.hidden) scheduleScan(); });
    window.addEventListener('storage', event => { if (event.key === preferenceKey && ['zh','en'].includes(event.newValue)) setLanguage(event.newValue); });
    scheduleScan(0);
  });
})();
