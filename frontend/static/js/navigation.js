'use strict';

document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.querySelector('.sidebar, .page-sidebar');
  const toggles = [...document.querySelectorAll('.btn-sidebar-toggle')];
  const backdrop = document.getElementById('sidebar-backdrop');
  const mainContent = document.querySelector('main');

  if (!sidebar || !toggles.length) return;

  const isMobile = () => window.matchMedia('(max-width: 820px)').matches;
  const isOpen = () => isMobile()
    ? sidebar.classList.contains('mobile-open')
    : !sidebar.classList.contains('collapsed');

  const setOpen = open => {
    if (isMobile()) {
      sidebar.classList.toggle('mobile-open', open);
      backdrop?.classList.toggle('visible', open);
      document.body.classList.toggle('sidebar-open', open);
    } else {
      sidebar.classList.toggle('collapsed', !open);
      backdrop?.classList.remove('visible');
      document.body.classList.remove('sidebar-open');
    }
    sidebar.inert = false;
    toggles.forEach(toggle => toggle.setAttribute('aria-expanded', String(open)));
  };

  toggles.forEach(toggle => toggle.addEventListener('click', () => {
    const open = !isOpen();
    setOpen(open);
    if (!open && isMobile()) mainContent?.focus({ preventScroll: true });
  }));
  backdrop?.addEventListener('click', () => {
    setOpen(false);
    mainContent?.focus({ preventScroll: true });
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && isOpen()) {
      setOpen(false);
      if (isMobile()) mainContent?.focus({ preventScroll: true });
    }
  });

  window.addEventListener('resize', () => {
    if (isMobile()) {
      sidebar.classList.remove('collapsed');
      sidebar.classList.remove('mobile-open');
      backdrop?.classList.remove('visible');
      document.body.classList.remove('sidebar-open');
      sidebar.inert = false;
      toggles.forEach(toggle => toggle.setAttribute('aria-expanded', 'false'));
    } else {
      sidebar.classList.remove('mobile-open');
      backdrop?.classList.remove('visible');
      document.body.classList.remove('sidebar-open');
      sidebar.inert = false;
      toggles.forEach(toggle => toggle.setAttribute('aria-expanded', String(!sidebar.classList.contains('collapsed'))));
    }
  });

  sidebar.inert = false;
  toggles.forEach(toggle => toggle.setAttribute('aria-expanded', String(!isMobile())));
});