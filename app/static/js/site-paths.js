(() => {
  'use strict';
  const prefix = document.querySelector('meta[name="app-root-path"]')?.content?.replace(/\/+$/, '') || '';
  window.SitePaths = Object.freeze({
    root: prefix,
    url(path) {
      if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//')) return path;
      return prefix + path;
    },
  });
})();
