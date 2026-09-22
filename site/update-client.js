/* Optional companion for strategy_platform_server.py. Static previews remain usable. */
(() => {
  const toast = document.querySelector('#update-toast');
  if (!toast) return;
  const message = toast.querySelector('[data-update-message]');
  let previousRun = '';
  let refreshedFor = sessionStorage.getItem('strategy-update-refreshed') || '';
  const show = (value, state = 'working') => { message.textContent = value; toast.dataset.state = state; toast.hidden = false; };
  const hide = () => { toast.hidden = true; };
  const check = async () => {
    try {
      const response = await fetch('./api/update-status', { cache: 'no-store' });
      if (!response.ok) return;
      const status = await response.json();
      const run = `${status.updatedAt || ''}|${status.lastResult || ''}`;
      if (status.inProgress) show(status.message || '正在同步策略日表');
      else if (status.lastResult === 'updated' && run && run !== refreshedFor) {
        show('策略底稿已更新，正在刷新页面', 'updated');
        sessionStorage.setItem('strategy-update-refreshed', run);
        refreshedFor = run;
        window.setTimeout(() => window.location.reload(), 1350);
      } else if (status.lastResult === 'failed' && run !== previousRun) {
        show(status.message || '日表更新失败，将自动重试', 'failed');
        window.setTimeout(hide, 6000);
      } else if (!status.inProgress) hide();
      previousRun = run;
    } catch {
      // The static prototype can be hosted without the local update service.
    }
  };
  check();
  window.setInterval(check, 5000);
})();
