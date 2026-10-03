(() => {
  'use strict';
  const localUrl = path => window.SitePaths ? window.SitePaths.url(path) : path;
  const preferenceKey = 'polymarket.site-language.v2';
  let cacheKey = null, configuration = null, configurationRequest = null, generation = 0, selection = 0;
  const cache = new Map();
  const esc = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const t = (en, zh) => window.SiteLanguage ? window.SiteLanguage.t(en, zh) : en;
  let language = 'en', requestRunning = false, scanTimer, pollTimer, persistTimer, providerAvailable = null;
  let savedLanguage = 'en';
  try { savedLanguage = localStorage.getItem(preferenceKey) === 'zh' ? 'zh' : 'en'; } catch { /* Storage is optional. */ }
  function changeConfiguration(next) {
    const nextKey = next.configured && next.revision ? 'polymarket.market-translations.market-zh-v3.' + next.revision : null;
    const changed = nextKey !== cacheKey;
    configuration = next;
    if (next.configured) { const notice = document.querySelector('#language-notice'); if (notice) notice.hidden = true; }
    window.dispatchEvent(new CustomEvent('llm-configuration-change', {detail:next}));
    try { localStorage.setItem('polymarket.llm-config.revision', String(next.revision || 'none')); } catch { /* Configuration synchronization is optional. */ }
    providerAvailable = next.configured === true;
    if (changed) {
      generation += 1;
      clearTimeout(persistTimer);
      cache.clear();
      cacheKey = nextKey;
      if (cacheKey) {
        try {
          const saved = JSON.parse(localStorage.getItem(cacheKey) || '[]');
          if (Array.isArray(saved)) saved.slice(-500).forEach(pair => {
            if (Array.isArray(pair) && pair.length === 2 && pair.every(text => typeof text === 'string' && text.length <= 20000)) cache.set(pair[0], {status:'ready', text:pair[1]});
          });
        } catch { /* Persistent backend translations remain available. */ }
      }
    }
    if (!providerAvailable && language === 'zh') applyLanguage('en');
    document.querySelectorAll('[data-market-text]').forEach(apply);
    updateControls();
    scheduleScan(0);
    return next;
  }
  async function loadConfiguration(force = false) {
    if (force && configurationRequest) {
      try { await configurationRequest; } catch { /* A new read follows the pending request. */ }
    }
    if (configurationRequest) return configurationRequest;
    const configurationGeneration = generation;
    configurationRequest = (async () => {
      const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 10000);
      try {
        const response = await fetch(localUrl('/api/llm/config'), {cache:'no-store', signal:controller.signal});
        if (!response.ok) throw new Error('Configuration unavailable');
        const result = await response.json();
        if (configurationGeneration !== generation && configuration) return configuration;
        if (typeof result.configured !== 'boolean') throw new Error('Invalid configuration');
        return changeConfiguration(result);
      } catch (error) {
        if (configurationGeneration !== generation && configuration) return configuration;
        throw error;
      } finally { clearTimeout(timeout); }
    })();
    try { return await configurationRequest; } finally { configurationRequest = null; }
  }
  function showConfigurationNotice(unavailable = false) {
    const notice = document.querySelector('#language-notice');
    if (!notice) return;
    notice.hidden = false;
    document.querySelector('#language-notice-title').textContent = unavailable ? 'Unable to check your LLM API configuration' : 'Configure an LLM API to use Chinese';
    document.querySelector('#language-notice-text').textContent = unavailable ? 'Check the local server connection, then try again. API settings are available in Settings.' : 'Add your own API key in Settings. English market data works without a key.';
  }

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
    let message = sources.length ? t('Chinese market text', '已显示中文') : t('Chinese interface', '中文模式');
    if (language === 'en') message = 'English · Original market text';
    else if (providerAvailable === false) message = t('Configure an LLM API first', '请先配置 LLM API');
    else if (errors.length) message = pending.length ? t(`Translating · ${errors.length} originals retained`, `翻译中 · ${errors.length} 条暂显原文`) : t('Some translations unavailable · Originals retained', '部分翻译不可用 · 保留原文');
    else if (pending.length) message = t(`Translating · ${pending.length} pending`, `正在翻译 · ${pending.length} 条待完成`);
    document.querySelectorAll('[data-market-language-status]').forEach(element => {
      if (element.textContent !== message) element.textContent = message;
      element.title = language === 'zh' && errors.length ? `${window.SiteLanguage?.message(cache.get(errors[0])?.reason || 'Translation unavailable') || 'Translation unavailable'} ${t('Click Chinese or Refresh to retry shortly.', '稍后点击中文或刷新数据重试。')}` : '';
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
      try { if (cacheKey && providerAvailable) localStorage.setItem(cacheKey, JSON.stringify(ready)); } catch { /* The backend also caches completed translations. */ }
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
    if (language !== 'zh' || !providerAvailable) { clearTimeout(pollTimer); return; }
    if (requestRunning) return;
    const now = Date.now();
    const sources = [...new Set(elements.map(sourceOf).filter(needsTranslation))];
    const request = [];
    let characters = 0;
    for (const source of sources) {
      const entry = cache.get(source);
      if (entry?.status === 'ready' || entry?.status === 'error' || (entry?.retryAt || 0) > now) continue;
      if (entry?.pendingSince && now - entry.pendingSince > 600000) {
        cache.set(source, {status:'error', reason:'Translation timed out', retryAt:now + 30000});
        continue;
      }
      if (request.length >= 80 || characters + source.length > 90000) break;
      request.push(source);
      characters += source.length;
      cache.set(source, {status:'pending', pendingSince:entry?.pendingSince || now, retryAt:now + 1100});
    }
    if (!request.length) { updateControls(elements); armPoll(elements); return; }
    requestRunning = true;
    const requestGeneration = generation;
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 20000);
    try {
      const response = await fetch(localUrl('/api/translations'), {method:'POST', headers:{'Accept':'application/json','Content-Type':'application/json'}, body:JSON.stringify({texts:request}), signal:abort.signal});
      if (!response.ok) throw new Error(`Translation request failed (${response.status})`);
      const result = await response.json();
      if (requestGeneration !== generation) return;
      if (result.available === false) {
        // A hot configuration update briefly pauses workers; confirm the key before
        // treating that pause as a missing configuration.
        const next = await loadConfiguration();
        if (!next.configured) showConfigurationNotice();
        return;
      }
      if (result.revision && result.revision !== configuration?.revision) { await loadConfiguration(); return; }
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
          cache.set(source, {status:'error', reason:item?.reason || 'No valid translation was returned', retryAt:Date.now() + 30000});
        }
      });
      persist();
    } catch (error) {
      if (requestGeneration !== generation) return;
      request.forEach(source => cache.set(source, {status:'error', reason:error.name === 'AbortError' ? 'Translation timed out' : error.message, retryAt:Date.now() + 30000}));
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
  function applyLanguage(value) {
    language = value === 'zh' ? 'zh' : 'en';
    try { localStorage.setItem(preferenceKey, language); } catch { /* Session-only preference. */ }
    window.SiteLanguage?.setLanguage(language);
    retryFailed();
    document.querySelectorAll('[data-market-text]').forEach(apply);
    updateControls();
    scheduleScan(0);
  }
  async function setLanguage(value) {
    const intent = ++selection;
    if (value !== 'zh') { applyLanguage('en'); return true; }
    try {
      const next = await loadConfiguration();
      if (intent !== selection) return false;
      if (!next.configured) { applyLanguage('en'); showConfigurationNotice(); return false; }
      const notice = document.querySelector('#language-notice');
      if (notice) notice.hidden = true;
      applyLanguage('zh');
      return true;
    } catch {
      if (intent !== selection) return false;
      providerAvailable = false;
      applyLanguage('en');
      showConfigurationNotice(true);
      return false;
    }
  }
  window.MarketLanguage = {html, setLanguage, refresh:() => scheduleScan(), getLanguage:() => language, getConfiguration:loadConfiguration, configurationChanged:changeConfiguration};

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
    document.addEventListener('visibilitychange', () => { if (!document.hidden) { scheduleScan(); if (language === 'zh' || document.querySelector('#llm-settings-form')) loadConfiguration().catch(() => {}); } });
    setInterval(() => { if ((language === 'zh' || document.querySelector('#llm-settings-form')) && !document.hidden) loadConfiguration().catch(() => {}); }, 30000);
    document.querySelector('#dismiss-language-notice')?.addEventListener('click', () => { document.querySelector('#language-notice').hidden = true; });
    window.addEventListener('storage', event => {
      if (event.key === preferenceKey && ['zh','en'].includes(event.newValue)) setLanguage(event.newValue);
      if (event.key === 'polymarket.llm-config.revision' && event.newValue !== configuration?.revision && (language === 'zh' || document.querySelector('#llm-settings-form'))) loadConfiguration().catch(() => {});
    });
    if (savedLanguage === 'zh') setLanguage('zh');
    else { updateControls(); scheduleScan(0); }
  });
})();
