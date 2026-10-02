/* Display-only research metrics. Original books and calculations remain unchanged. */
(() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number = (value, digits=2) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('zh-CN', {maximumFractionDigits:digits});
  const price = value => value == null || !Number.isFinite(Number(value)) ? '—' : number(Number(value) * 100, 3) + '¢';
  const quality = {normal:'双边盘口', crossed:'交叉盘口', 'one-sided':'单边盘口', unavailable:'缺少盘口', invalid:'盘口数据无效'};

  function html(analyses, labels) {
    if (!Array.isArray(analyses) || !analyses.length) return '';
    const rows = analyses.map((data, index) => {
      const label = MarketLanguage.html(labels?.[index] ?? `结果 ${index + 1}`);
      if (!data) return `<tr><th scope="row">${label}</th><td colspan="4">盘口暂不可用</td></tr>`;
      const status = quality[data.quality] || '状态未知';
      const freshness = data.stale ? ' · 快照过期或时间未知' : '';
      const imbalance = data.imbalance == null ? '—' : number(Number(data.imbalance) * 100, 1) + '%';
      return `<tr><th scope="row">${label}</th><td>${price(data.spread)}<small>${escape(status + freshness)}</small></td><td>${number(data.bid_depth_quantity)} / ${number(data.ask_depth_quantity)}<small>买盘 / 卖盘 · 股</small></td><td>${imbalance}</td><td>${price(data.microprice)}</td></tr>`;
    }).join('');
    return `<section class="book-quality" aria-label="盘口质量指标"><h3>盘口质量</h3><p>近价深度统计距各侧最优价 2¢ 内的挂单；首档失衡为买量与卖量之差除以总量。加权价描述当前盘口结构。</p><div class="table-wrap"><table><thead><tr><th>结果</th><th>买卖价差</th><th>近价深度</th><th>首档失衡</th><th>首档加权价</th></tr></thead><tbody>${rows}</tbody></table></div><p>这些指标用于比较价差和深度，不代表胜率或盈利信号。</p></section>`;
  }
  window.BookQuality = {html};
})();
