(() => {
  'use strict';
  const localUrl = path => window.SitePaths ? window.SitePaths.url(path) : path;
  const t = (en, zh) => window.SiteLanguage ? window.SiteLanguage.t(en, zh) : en;
  let config = null, busy = false, result = null, dirty = false;
  const normalizedBase = value => { try { const url = new URL(value); return url.origin + url.pathname.replace(/\/+$/, ''); } catch { return value; } };
  const field = name => document.querySelector(`#llm-${name.replaceAll('_', '-')}`);
  function renderStatus() {
    const status = document.querySelector('#llm-config-status');
    if (!status) return;
    status.textContent = config ? (config.configured ? t('API configured', 'API 已配置') : t('No API key configured', '尚未配置 API 密钥')) : t('Checking configuration…', '正在检查配置…');
    status.className = `pill ${config?.configured ? 'ok' : 'waiting'}`;
    const sources = {environment:t('Using environment / .env', '使用环境变量 / .env'), local:t('Saved on this local backend', '已保存到本地后端'), none:t('English is available without a key', '英文模式无需密钥')};
    document.querySelector('#llm-config-source').textContent = config ? (sources[config.source] || '') : '';
    document.querySelector('#remove-llm-config').disabled = busy || config?.source !== 'local';
    const sameDestination = config?.configured && field('provider').value === config.provider && normalizedBase(field('api_base').value.trim()) === config.api_base;
    field('api_key').required = !sameDestination;
    field('api_key').placeholder = sameDestination ? t('Leave blank to keep the current key', '留空保留当前密钥') : t('Enter your API key', '输入自己的 API 密钥');
    const output = document.querySelector('#llm-settings-result');
    if (result) { output.textContent = typeof result.text === 'function' ? result.text() : (window.SiteLanguage?.message(result.text) || result.text); output.classList.toggle('is-error', result.error === true); }
  }
  function populate(next) {
    config = next;
    dirty = false;
    field('provider').value = next.provider || 'deepseek';
    field('api_base').value = next.api_base || 'https://api.deepseek.com';
    field('model').value = next.model || 'deepseek-flash';
    field('api_key').value = '';
    window.MarketLanguage.configurationChanged(next);
    renderStatus();
  }
  function setBusy(value) {
    busy = value;
    document.querySelector('#llm-settings-form').querySelectorAll('input, select, button').forEach(element => { element.disabled = value; });
    renderStatus();
  }
  async function mutate(method, body) {
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(localUrl('/api/llm/config'), {method, cache:'no-store', headers:{'Content-Type':'application/json'}, body:body ? JSON.stringify(body) : undefined, signal:controller.signal});
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? (payload.detail === 'API configuration is available only from the local computer.' ? 'API configuration is available only from the local computer. For Docker, configure the key in .env and restart the container.' : payload.detail) : t('Check the provider, URL, model, and API key fields.', '请检查提供商、地址、模型和密钥字段。'));
      // Read the active server configuration after the write. Another tab may have
      // committed a newer value while this mutation response was in flight.
      const current = await window.MarketLanguage.getConfiguration(true);
      return {current, superseded:current.revision !== payload.revision};
    } catch (error) {
      if (error.name === 'AbortError' || error instanceof TypeError) throw new Error(t('The local server did not respond. Reopen Settings to check whether the configuration was saved.', '本地服务器未响应。请重新打开设置，检查配置是否已保存。'));
      throw error;
    } finally { clearTimeout(timeout); }
  }
  document.addEventListener('DOMContentLoaded', async () => {
    const form = document.querySelector('#llm-settings-form');
    if (!form) return;
    window.addEventListener('site-language-change', renderStatus);
    form.addEventListener('input', () => { dirty = true; });
    form.addEventListener('change', () => { dirty = true; renderStatus(); });
    window.addEventListener('llm-configuration-change', event => {
      const changed = event.detail.revision !== config?.revision;
      config = event.detail;
      if (changed && !dirty && !busy) {
        field('provider').value = config.provider || 'deepseek';
        field('api_base').value = config.api_base || 'https://api.deepseek.com';
        field('model').value = config.model || 'deepseek-flash';
        field('api_key').value = '';
      }
      renderStatus();
    });
    field('provider').addEventListener('change', () => {
      const deepseek = field('provider').value === 'deepseek';
      field('api_base').value = deepseek ? 'https://api.deepseek.com' : '';
      field('model').value = deepseek ? 'deepseek-flash' : '';
      field('api_key').value = '';
      result = {text:() => t('Enter a key when changing provider or URL. Your saved configuration remains active until you save.', '更换提供商或地址时请输入密钥。保存前仍使用已有配置。')};
      renderStatus();
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (busy || !form.reportValidity()) return;
      const body = {provider:field('provider').value, api_base:field('api_base').value.trim(), model:field('model').value.trim(), api_key:field('api_key').value.trim()};
      setBusy(true);
      result = {text:() => t('Saving API settings…', '正在保存 API 设置…')}; renderStatus();
      try {
        const response = await mutate('PUT', body);
        populate(response.current);
        result = {text:() => response.superseded ? t('Settings saved, then changed by another tab. The current active configuration is shown above.', '设置已保存，随后被另一标签页修改。上方显示当前生效的配置。') : t('Saved and active. Choose Chinese to translate visible market text. Provider charges may apply.', '已保存并生效。选择中文即可翻译可见的市场文本，可能产生模型费用。')};
      }
      catch (error) { result = {text:error.message, error:true}; }
      finally { setBusy(false); }
    });
    document.querySelector('#remove-llm-config').addEventListener('click', async () => {
      if (busy || config?.source !== 'local') return;
      setBusy(true);
      try { const response = await mutate('DELETE'); populate(response.current); result = {text:() => response.superseded ? t('Saved settings were removed, then changed by another tab. The current active configuration is shown above.', '已移除保存设置，随后被另一标签页修改。上方显示当前生效的配置。') : config.configured ? t('Saved settings removed. The environment API configuration is now active.', '已移除网站保存的设置，现使用环境中的 API 配置。') : t('Saved settings removed. English is active; add an API key to use Chinese.', '已移除网站保存的设置。现在使用英文，配置密钥后可使用中文。')}; }
      catch (error) { result = {text:error.message, error:true}; }
      finally { setBusy(false); }
    });
    setBusy(true);
    try { populate(await window.MarketLanguage.getConfiguration()); }
    catch { result = {text:() => t('Cannot load API settings. Check the local server and reload this page.', '无法读取 API 设置。请检查本地服务器并重新加载页面。'), error:true}; }
    finally { setBusy(false); }
  });
})();
