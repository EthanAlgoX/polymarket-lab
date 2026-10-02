document.addEventListener('DOMContentLoaded', () => {
  const nav = document.querySelector('.site-nav');
  if (!nav) return;
  let frame;
  const revealActive = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      if (!window.matchMedia('(max-width:760px)').matches) return;
      const active = nav.querySelector('[aria-current="page"]');
      if (!active) return;
      const bounds = nav.getBoundingClientRect(), item = active.getBoundingClientRect();
      if (item.left < bounds.left + 8) nav.scrollLeft -= bounds.left + 8 - item.left;
      else if (item.right > bounds.right - 8) nav.scrollLeft += item.right - bounds.right + 8;
    });
  };
  new MutationObserver(revealActive).observe(nav, {subtree:true, attributes:true, attributeFilter:['aria-current']});
  window.addEventListener('resize', revealActive);
  revealActive();
});
