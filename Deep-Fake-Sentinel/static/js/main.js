(function () {
  'use strict';

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function initNavigation() {
    var toggle = document.getElementById('navToggle');
    var mobileNav = document.getElementById('mobileNav');
    var header = document.getElementById('siteHeader');

    if (toggle && mobileNav) {
      toggle.addEventListener('click', function () {
        var isOpen = mobileNav.classList.toggle('is-open');
        toggle.setAttribute('aria-expanded', String(isOpen));
        toggle.textContent = isOpen ? '×' : '☰';
      });
      mobileNav.addEventListener('click', function (event) {
        if (event.target.closest('a')) {
          mobileNav.classList.remove('is-open');
          toggle.setAttribute('aria-expanded', 'false');
          toggle.textContent = '☰';
        }
      });
      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && mobileNav.classList.contains('is-open')) {
          mobileNav.classList.remove('is-open');
          toggle.setAttribute('aria-expanded', 'false');
          toggle.textContent = '☰';
          toggle.focus();
        }
      });
    }

    if (header) {
      var updateHeader = function () {
        header.classList.toggle('is-scrolled', window.scrollY > 24);
      };
      window.addEventListener('scroll', updateHeader, { passive: true });
      updateHeader();
    }
  }

  function initWorkspaceSidebar() {
    var toggle = document.getElementById('sidebarToggle');
    var sidebar = document.getElementById('workspaceSidebar');
    var overlay = document.getElementById('sidebarOverlay');
    if (!toggle || !sidebar) return;

    function setOpen(open) {
      sidebar.classList.toggle('is-open', open);
      if (overlay) overlay.classList.toggle('is-visible', open);
      toggle.setAttribute('aria-expanded', String(open));
    }

    toggle.addEventListener('click', function () {
      setOpen(!sidebar.classList.contains('is-open'));
    });

    if (overlay) {
      overlay.addEventListener('click', function () { setOpen(false); });
    }

    sidebar.addEventListener('click', function (event) {
      if (event.target.closest('a')) setOpen(false);
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && sidebar.classList.contains('is-open')) {
        setOpen(false);
        toggle.focus();
      }
    });
  }

  function initHeroAnimations() {
    var heroItems = document.querySelectorAll('[data-hero]');
    if (!heroItems.length) return;

    if (reducedMotion || !window.gsap) {
      heroItems.forEach(function (item) { item.style.opacity = '1'; });
      return;
    }

    var tl = window.gsap.timeline({ defaults: { ease: 'power3.out' } });
    tl.from(heroItems, { opacity: 0, y: 34, duration: 0.9, stagger: 0.1 });
    tl.from('.signal-frame', { opacity: 0, scale: 0.96, duration: 1.1 }, '-=0.75');
    tl.from('.hero__float-card', { opacity: 0, x: -24, duration: 0.8 }, '-=0.6');
    tl.to('.signal-frame', { boxShadow: '0 40px 90px rgba(0,0,0,0.55), 0 0 50px rgba(212,175,55,0.16)', duration: 2.4, repeat: -1, yoyo: true, ease: 'sine.inOut' });

    var bars = document.querySelectorAll('.waveform span');
    if (bars.length) {
      window.gsap.to(bars, {
        scaleY: function (index) { return 0.35 + ((index * 17) % 10) / 10; },
        duration: 0.8,
        stagger: { each: 0.07, from: 'center', repeat: -1, yoyo: true },
        ease: 'sine.inOut'
      });
    }
  }

  function initScrollReveals() {
    var items = document.querySelectorAll('[data-reveal]');
    if (!items.length) return;
    if (reducedMotion || !window.gsap || !window.ScrollTrigger) {
      items.forEach(function (item) { item.style.opacity = '1'; });
      return;
    }
    window.gsap.registerPlugin(window.ScrollTrigger);
    items.forEach(function (item) {
      window.gsap.from(item, {
        opacity: 0,
        y: 42,
        duration: 0.9,
        ease: 'power3.out',
        scrollTrigger: { trigger: item, start: 'top 88%', once: true }
      });
    });
  }

  function initScene() {
    var mount = document.getElementById('heroCanvasMount');
    if (!mount || !window.SentinelScene) return;
    var handle = window.SentinelScene.mount(mount, { particles: 90 });
    window.addEventListener('pagehide', function () {
      if (handle) handle.destroy();
    }, { once: true });
  }

  function syncHeroState() {
    var label = document.getElementById('heroStateLabel');
    if (!label || typeof fetch !== 'function') return;
    fetch('/api/analytics/dashboard/', { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
      .then(function (response) {
        if (!response.ok) throw new Error('Analytics service unavailable');
        return response.json();
      })
      .then(function (data) {
        var checkpoint = data && (data.checkpoint || data.model_checkpoint || (data.summary && data.summary.checkpoint));
        if (checkpoint === null || checkpoint === false) {
          label.textContent = 'Inconclusive — no trained checkpoint';
          return;
        }
        label.textContent = 'Service connected';
      })
      .catch(function () {
        label.textContent = 'Awaiting evidence';
      });
  }

  function initTransitions() {
    if (reducedMotion || !window.gsap) return;
    var overlay = document.createElement('div');
    overlay.setAttribute('aria-hidden', 'true');
    overlay.style.cssText = 'position:fixed;inset:0;z-index:300;pointer-events:none;opacity:0;background:radial-gradient(circle at 50% 50%, rgba(212,175,55,0.12), #04060b 72%)';
    document.body.appendChild(overlay);

    window.addEventListener('pageshow', function () {
      window.gsap.to(overlay, { opacity: 0, duration: 0.25 });
    });

    document.addEventListener('click', function (event) {
      var anchor = event.target.closest('a[href]');
      if (!anchor || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      var url = new URL(anchor.href, window.location.href);
      if (url.origin !== window.location.origin || anchor.target === '_blank' || anchor.hasAttribute('download')) return;
      if (url.pathname === window.location.pathname && url.hash) return;
      if (url.pathname === window.location.pathname && !url.search) return;
      window.gsap.to(overlay, { opacity: 1, duration: 0.18, ease: 'power2.in' });
    });
  }

  initNavigation();
  initWorkspaceSidebar();
  initHeroAnimations();
  initScrollReveals();
  initScene();
  syncHeroState();
  initTransitions();
})();
