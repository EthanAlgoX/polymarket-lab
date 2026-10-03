(() => {
  'use strict';
  let language = 'en';
  const messages = {
    "扫描参数必须是非负有限数值":"Scanner parameters must be finite and nonnegative",
    "每腿目标数量必须大于零且不超过 100000":"Target quantity per leg must be greater than zero and at most 100000",
    "扫描参数超过支持的范围":"Scanner parameters exceed the supported range",
    "保存的扫描参数未通过校验":"Saved scanner parameters failed validation",
    "市场不可交易":"Market is not tradable",
    "扫描参数无效":"Invalid scanner parameters",
    "计算字段无效":"Invalid calculation fields",
    "行情过期":"Stale quotes",
    "共同可成交数量不足":"Insufficient common executable quantity",
    "低于最低预计净利润":"Below minimum estimated net profit",
    "低于最低预计净收益率":"Below minimum estimated budget ROI",
    "有效机会":"Valid candidate",
    "服务重启, 等待新盘口核验":"Service restarted; waiting for fresh order book verification",
    "不是恰好两个结果的市场":"The market does not have exactly two outcomes",
    "无法识别 Yes/No 结果":"Cannot identify Yes/No outcomes",
    "结果 Token ID 缺失":"Outcome token IDs are missing",
    "市场当前不可扫描":"The market is not currently scannable",
    "市场标识缺失":"Market identifiers are missing",
    "市场字段无效":"Invalid market fields",
    "未命名市场":"Untitled market",
    "API configuration fields must be strings.":"API 配置字段必须是文本。",
    "API configuration is available only from the local computer.":"API 设置只能在原生本机服务中修改。Docker 用户请在 .env 配置密钥并重启容器。",
    "API configuration is unavailable in this test server.":"此测试服务未启用 API 配置。",
    "API configuration requires the configured HTTPS website origin.":"API 设置必须来自配置的 HTTPS 网站来源。",
    "API configuration requires a request from this website's origin.":"请从当前网站的配置页面提交 API 设置。",
    "Choose DeepSeek or an OpenAI-compatible provider.":"请选择 DeepSeek 或 OpenAI 兼容接口。",
    "Configure your LLM API in Settings before switching to Chinese.":"切换中文前，请在设置中配置自己的 LLM API。",
    "DeepSeek requires its official HTTPS API base URL.":"DeepSeek 必须使用官方 HTTPS API 基础地址。",
    "Enter a new API key when changing provider or API base URL.":"更换提供商或 API 地址时，请输入目标对应的新密钥。",
    "Enter a valid API key without whitespace, up to 2048 characters.":"请输入不含空白的有效 API 密钥，最多 2048 个字符。",
    "Enter a valid model ID, up to 160 characters.":"请输入有效模型 ID，最多 160 个字符。",
    "Enter the API base URL, without /chat/completions or /models.":"请输入 API 基础地址，不要包含 /chat/completions 或 /models。",
    "Only public market text already displayed by this application can be translated.":"只能翻译此应用已展示的公开市场文本。",
    "Provide provider, api_base, model and api_key as JSON fields.":"请提供 provider、api_base、model 和 api_key 这四个 JSON 字段。",
    "Send API configuration as JSON.":"请使用 JSON 格式提交 API 配置。",
    "The API configuration JSON is invalid.":"API 配置 JSON 格式无效。",
    "The API configuration request is too large.":"API 配置请求过大。",
    "The API host must resolve exclusively to public internet addresses.":"API 域名只能解析到公网地址，不能使用本地或私网地址。",
    "The local API configuration could not be removed.":"无法移除本地 API 配置，请检查文件权限。",
    "The local API configuration could not be saved.":"无法保存本地 API 配置，请检查文件权限。",
    "The local API configuration file is invalid.":"本地 API 配置文件无效。",
    "The local API configuration file must not be a symbolic link.":"本地 API 配置文件不能是符号链接。",
    "The translation API account has insufficient credit.":"翻译 API 账户余额不足，请检查账户余额。",
    "The translation API could not be reached. Try again later.":"无法连接翻译 API，请稍后重试。",
    "The translation API is rate limited. Try again later.":"翻译 API 已限流，请稍后重试。",
    "The translation API is temporarily unavailable.":"翻译 API 暂时不可用。",
    "The translation API rejected the credentials. Check the API key in Settings.":"翻译 API 拒绝了密钥，请在设置中检查 API 密钥。",
    "The translation queue is full. Try again later.":"翻译队列繁忙，请稍后重试。",
    "The translation response was incomplete. Try again later.":"翻译结果不完整，请稍后重试。",
    "Translation failed its integrity check. Retry or view the English original.":"译文未通过完整性检查，请重试或查看英文原文。",
    "Use a public HTTPS API base URL on port 443, without credentials or query parameters.":"请使用 443 端口的公网 HTTPS API 基础地址，不包含账号、密码或查询参数。",
    "Translation timed out":"翻译等待超时",
    "No valid translation was returned":"翻译服务未返回有效译文",
    "Translation unavailable":"翻译暂时不可用",
    "Request timed out. Refresh to try again.":"请求超时，请刷新后重试。",
    "Request timed out or was cancelled. Refresh to try again.":"请求超时或已取消，请刷新后重试。",
    "Cannot load API settings. Check the local server and reload this page.":"无法读取 API 设置。请检查本地服务器并重新加载页面。",
    "Invalid parameter":"参数无效",
    "manual":"手动记录",
    "automatic":"自动记录",
    "SUCCESS":"已保存",
    "ACTIVE":"有效",
    "EXPIRED":"已过期",
    '未检查':'Not checked', '未连接':'Disconnected', '已连接':'Connected', '正常':'Healthy', '异常':'Error',
    '市场不存在或尚未加载':'Market not found or not loaded yet', '模拟记录不存在':'Paper record not found', '历史信号不存在':'Historical signal not found',
    '市场尚未进入目录':'Market is not in the catalog yet', '公开盘口暂时无法读取; 请稍后重试':'Public order books are unavailable. Try again shortly.',
    '本次公开接口未返回该开盘市场; 可能已关闭, 暂停成本核验':'The public API no longer returns this open market. Cost verification is paused.',
    '市场已关闭或停止接受交易, 暂停成本核验':'The market is closed or no longer accepting orders. Cost verification is paused.',
    '市场标识或结果与 Token 映射已变化, 等待目录更新后核验':'Market identifiers or outcome-to-token mapping changed. Wait for a catalog refresh.',
    '市场费率或费率公式未核实':'Market fees or the fee formula are unverified', '未核实当前费率公式':'Current fee formula is unverified',
    '没有可追溯的实时订单簿计算结果':'No traceable calculation from live order books', '缺少用于该计算的独立 REST 两腿盘口快照':'Independent REST snapshots for both legs are missing',
    '当前快照过期或未通过全部机会门槛; 请刷新盘口':'The snapshot is stale or no longer passes all candidate thresholds. Refresh the books.',
    '参数更新; 等待新盘口':'Settings updated; waiting for new books', '市场更新; 等待新盘口':'Markets updated; waiting for new books',
    '市场元数据暂时无法核实':'Market metadata cannot currently be verified', '当前无可扫描市场':'No markets currently available to scan',
    '盘口获取或计算失败':'Order book retrieval or calculation failed', '盘口更新或未通过当前门槛':'Books updated or current thresholds not met',
    '公开市场已结算或不再满足门槛':'The public market settled or no longer meets thresholds',
    '读取':'Fetched', '可扫描':'Scannable', '跳过':'Skipped', '受限':'Restricted', '未受限':'Unrestricted', '检查失败':'Check failed', '错误':'Error',
    'Only displayed public market text can be translated.':'只能翻译已展示的公开市场文本。',
    'Configure an LLM API key in Settings to translate market text.':'请先在设置中配置自己的 LLM API 密钥。',
  };
  messages['API configuration is available only from the local computer. For Docker, configure the key in .env and restart the container.'] = 'API 设置只能在原生本机服务中修改。Docker 用户请在 .env 配置密钥并重启容器。';
  const enums = {manual:['Manual','手动记录'],automatic:['Automatic','自动记录'],SUCCESS:['Saved','已保存'],FAILED:['Failed','失败'],active:['Active','有效'],disappeared:['No longer eligible','不再符合门槛'],ACTIVE:['Active','有效'],EXPIRED:['Expired','已过期']};
  const t = (en, zh) => language === 'zh' ? (zh ?? en) : en;
  function message(value) {
    const text = String(value ?? '');
    if (enums[text]) return t(...enums[text]);
    if (language === 'zh') {
      if (messages[text] && /[\u4e00-\u9fff]/.test(messages[text])) return messages[text];
      const original = Object.entries(messages).find(([zh, en]) => en === text && /[\u4e00-\u9fff]/.test(zh));
      if (original) return original[0];
      return text.replace(/^Value error, /, '参数错误：').replace(/^Translation request failed \((\d+)\)$/, '翻译请求失败（$1）');
    }
    if (messages[text] && !/[\u4e00-\u9fff]/.test(messages[text])) return messages[text];
    let output = text;
    Object.keys(messages).filter(key => /[\u4e00-\u9fff]/.test(key)).sort((a,b) => b.length-a.length).forEach(key => { output = output.split(key).join(messages[key]); });
    return output;
  }
  function apply() {
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
    document.title = t('Polymarket Lab', 'Polymarket 研究台');
    document.querySelectorAll('[data-i18n-en]').forEach(element => {
      element.textContent = t(element.dataset.i18nEn, element.dataset.i18nZh);
    });
    ['placeholder', 'aria-label', 'content'].forEach(attribute => {
      document.querySelectorAll(`[data-i18n-${attribute}-en]`).forEach(element => {
        element.setAttribute(attribute, t(element.getAttribute(`data-i18n-${attribute}-en`), element.getAttribute(`data-i18n-${attribute}-zh`)));
      });
    });
  }
  function setLanguage(value) {
    const next = value === 'zh' ? 'zh' : 'en';
    const changed = next !== language;
    language = next;
    apply();
    if (changed) window.dispatchEvent(new CustomEvent('site-language-change', {detail:{language}}));
  }
  window.SiteLanguage = {t, message, setLanguage, getLanguage:() => language};
  document.addEventListener('DOMContentLoaded', apply);
})();
