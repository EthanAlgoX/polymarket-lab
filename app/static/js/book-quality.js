/* Display-only research metrics. Original books and calculations remain unchanged. */
(() => {
  const t = (en, zh) => window.SiteLanguage ? window.SiteLanguage.t(en, zh) : en;
  const locale = () => window.SiteLanguage?.getLanguage() === 'zh' ? 'zh-CN' : 'en-US';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number = (value, digits=2) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString(locale(), {maximumFractionDigits:digits});
  const price = value => value == null || !Number.isFinite(Number(value)) ? '—' : number(Number(value) * 100, 3) + '¢';
  const quality = () => ({normal:t('Two-sided book','双边盘口'), crossed:t('Crossed book','交叉盘口'), 'one-sided':t('One-sided book','单边盘口'), unavailable:t('Book unavailable','缺少盘口'), invalid:t('Invalid book','盘口数据无效')});

  function html(analyses, labels) {
    if (!Array.isArray(analyses) || !analyses.length) return '';
    const rows = analyses.map((data, index) => {
      const label = labels?.[index] == null ? escape(t(`Outcome ${index + 1}`,`结果 ${index + 1}`)) : MarketLanguage.html(labels[index]);
      if (!data) return `<tr><th scope="row">${label}</th><td colspan="4">${t('Order book unavailable','盘口暂不可用')}</td></tr>`;
      const status = quality()[data.quality] || t('Unknown status','状态未知');
      const freshness = data.stale ? t(' · Stale or undated snapshot',' · 快照过期或时间未知') : '';
      const imbalance = data.imbalance == null ? '—' : number(Number(data.imbalance) * 100, 1) + '%';
      return `<tr><th scope="row">${label}</th><td>${price(data.spread)}<small>${escape(status + freshness)}</small></td><td>${number(data.bid_depth_quantity)} / ${number(data.ask_depth_quantity)}<small>${t('Bid / ask · shares','买盘 / 卖盘 · 股')}</small></td><td>${imbalance}</td><td>${price(data.microprice)}</td></tr>`;
    }).join('');
    return `<section class="book-quality" aria-label="${t('Order book quality metrics','盘口质量指标')}"><h3>${t('Order book quality','盘口质量')}</h3><p>${t('Near-price depth includes orders within 2¢ of each side’s best price. Top-level imbalance is bid size minus ask size, divided by their sum. Microprice describes the current book structure.','近价深度统计距各侧最优价 2¢ 内的挂单；首档失衡为买量与卖量之差除以总量。加权价描述当前盘口结构。')}</p><div class="table-wrap"><table><thead><tr><th>${t('Outcome','结果')}</th><th>${t('Spread','买卖价差')}</th><th>${t('Near-price depth','近价深度')}</th><th>${t('Top-level imbalance','首档失衡')}</th><th>${t('Microprice','首档加权价')}</th></tr></thead><tbody>${rows}</tbody></table></div><p>${t('These metrics compare spreads and depth; they do not estimate win probability or profitability.','这些指标用于比较价差和深度，不代表胜率或盈利信号。')}</p></section>`;
  }
  window.BookQuality = {html};
})();
