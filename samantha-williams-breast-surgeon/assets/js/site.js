/* Samantha Williams Breast Surgeon — site behaviour
   All enhancements are progressive: the page is fully usable without this file. */
(function () {
  'use strict';

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- Site configuration (edit these) ---------- */
  var CONFIG = window.SITE_CONFIG || {};
  var GA_ID = CONFIG.gaMeasurementId || '';          // e.g. 'G-XXXXXXXXXX'
  var FORM_ENDPOINT = CONFIG.formEndpoint || '';      // e.g. 'https://formspree.io/f/abcdwxyz'

  /* ---------- Nav: scrolled state ---------- */
  var nav = document.getElementById('siteNav');
  if (nav) {
    var onScroll = function () {
      if (window.scrollY > 24) nav.classList.add('is-scrolled');
      else nav.classList.remove('is-scrolled');
    };
    document.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* ---------- Nav: mobile menu ---------- */
  var navToggle = document.getElementById('navToggle');
  var mobileMenu = document.getElementById('mobileMenu');
  if (navToggle && mobileMenu) {
    var closeMenu = function () {
      mobileMenu.classList.remove('is-open');
      navToggle.classList.remove('is-active');
      navToggle.setAttribute('aria-expanded', 'false');
    };
    navToggle.addEventListener('click', function () {
      var isOpen = mobileMenu.classList.toggle('is-open');
      navToggle.classList.toggle('is-active', isOpen);
      navToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });
    mobileMenu.querySelectorAll('a').forEach(function (a) { a.addEventListener('click', closeMenu); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeMenu(); });
  }

  /* ---------- Nav: highlight in-page section (home page) ---------- */
  var sectionLinks = document.querySelectorAll('.nav__link[data-section]');
  if (sectionLinks.length && 'IntersectionObserver' in window) {
    var linkFor = {};
    sectionLinks.forEach(function (link) { linkFor[link.getAttribute('data-section')] = link; });
    var sectionIo = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var link = linkFor[entry.target.id];
        if (link && entry.isIntersecting) {
          sectionLinks.forEach(function (l) { l.classList.remove('is-active'); });
          link.classList.add('is-active');
        }
      });
    }, { rootMargin: '-45% 0px -45% 0px' });
    Object.keys(linkFor).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) sectionIo.observe(el);
    });
  }

  /* ---------- Hero glow follows the cursor (mouse devices only) ---------- */
  var heroEl = document.querySelector('.hero');
  var glowEl = document.querySelector('.hero__glow');
  var canHover = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  if (heroEl && glowEl && canHover && !reduceMotion) {
    var defaultX = 50, defaultY = 30;
    var targetX = defaultX, targetY = defaultY, curX = defaultX, curY = defaultY;
    var clamp = function (v, min, max) { return Math.max(min, Math.min(max, v)); };
    heroEl.addEventListener('mousemove', function (e) {
      var rect = heroEl.getBoundingClientRect();
      targetX = clamp(((e.clientX - rect.left) / rect.width) * 100, 15, 85);
      targetY = clamp(((e.clientY - rect.top) / rect.height) * 100, 5, 65);
    });
    heroEl.addEventListener('mouseleave', function () { targetX = defaultX; targetY = defaultY; });
    var animateGlow = function () {
      curX += (targetX - curX) * 0.05;
      curY += (targetY - curY) * 0.05;
      glowEl.style.setProperty('--glow-x', curX.toFixed(2) + '%');
      glowEl.style.setProperty('--glow-y', curY.toFixed(2) + '%');
      requestAnimationFrame(animateGlow);
    };
    requestAnimationFrame(animateGlow);
  }

  /* ---------- Scroll reveal (content is visible by default; this only adds the fade) ---------- */
  var revealEls = document.querySelectorAll('.reveal');
  if (revealEls.length && 'IntersectionObserver' in window && !reduceMotion) {
    document.documentElement.classList.add('js-reveal');
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { entry.target.classList.add('is-visible'); io.unobserve(entry.target); }
      });
    }, { threshold: 0.15 });
    revealEls.forEach(function (el) { io.observe(el); });
  }

  /* ---------- Copy to clipboard ---------- */
  document.querySelectorAll('.copy-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var value = btn.getAttribute('data-copy');
      if (!(navigator.clipboard && navigator.clipboard.writeText)) return;
      navigator.clipboard.writeText(value).then(function () {
        btn.textContent = 'Copied';
        btn.classList.add('is-copied');
        setTimeout(function () { btn.textContent = 'Copy'; btn.classList.remove('is-copied'); }, 1600);
      });
    });
  });

  /* ---------- Testimonial carousel ---------- */
  var track = document.getElementById('testimonialTrack');
  if (track) {
    var cards = Array.prototype.slice.call(track.querySelectorAll('blockquote'));
    var dots = Array.prototype.slice.call(document.querySelectorAll('.carousel-dot'));
    var step = function () { return cards[0] ? cards[0].getBoundingClientRect().width + 24 : track.clientWidth; };

    document.querySelectorAll('.carousel-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var dir = parseInt(btn.getAttribute('data-dir'), 10);
        track.scrollBy({ left: dir * step(), behavior: reduceMotion ? 'auto' : 'smooth' });
      });
    });

    dots.forEach(function (dot) {
      dot.addEventListener('click', function () {
        var card = cards[parseInt(dot.getAttribute('data-index'), 10)];
        if (card) track.scrollTo({ left: card.offsetLeft, behavior: reduceMotion ? 'auto' : 'smooth' });
      });
    });

    track.setAttribute('tabindex', '0');
    track.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        e.preventDefault();
        track.scrollBy({ left: (e.key === 'ArrowRight' ? 1 : -1) * step(), behavior: reduceMotion ? 'auto' : 'smooth' });
      }
    });

    if ('IntersectionObserver' in window && dots.length) {
      var dotIo = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          var index = cards.indexOf(entry.target);
          if (index === -1 || !dots[index] || !entry.isIntersecting) return;
          dots.forEach(function (d) { d.classList.remove('is-active'); d.setAttribute('aria-selected', 'false'); });
          dots[index].classList.add('is-active');
          dots[index].setAttribute('aria-selected', 'true');
        });
      }, { root: track, threshold: 0.6 });
      cards.forEach(function (card) { dotIo.observe(card); });
    }
  }

  /* ---------- Cookie consent + Google Analytics (loads only after consent) ---------- */
  var CONSENT_KEY = 'swbs-cookie-consent';
  var banner = document.getElementById('cookieBanner');

  var readConsent = function () {
    try { return localStorage.getItem(CONSENT_KEY); } catch (e) { return null; }
  };
  var writeConsent = function (value) {
    try { localStorage.setItem(CONSENT_KEY, value); } catch (e) { /* storage unavailable */ }
  };

  var loadAnalytics = function () {
    if (!GA_ID || /^G-X+$/i.test(GA_ID) || window.__gaLoaded) return;
    window.__gaLoaded = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag('js', new Date());
    window.gtag('config', GA_ID, { anonymize_ip: true });
    var s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(GA_ID);
    document.head.appendChild(s);
  };

  if (banner) {
    var consent = readConsent();
    if (consent === 'accepted') {
      loadAnalytics();
    } else if (consent !== 'declined') {
      banner.classList.add('is-visible');
    }
    var acceptBtn = document.getElementById('cookieAccept');
    var declineBtn = document.getElementById('cookieDecline');
    if (acceptBtn) acceptBtn.addEventListener('click', function () {
      writeConsent('accepted'); banner.classList.remove('is-visible'); loadAnalytics();
    });
    if (declineBtn) declineBtn.addEventListener('click', function () {
      writeConsent('declined'); banner.classList.remove('is-visible');
    });
  }

  /* ---------- Enquiry form ---------- */
  var form = document.getElementById('enquiryForm');
  if (form) {
    var status = document.getElementById('formStatus');
    var setStatus = function (msg) { if (status) status.textContent = msg; };
    var endpointReady = FORM_ENDPOINT && !/REPLACE/i.test(FORM_ENDPOINT);

    if (endpointReady) form.setAttribute('action', FORM_ENDPOINT);

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (form.querySelector('.form__honeypot input').value) return; // bot
      if (!endpointReady) {
        setStatus('The enquiry form is not connected yet. Please call or email Tracy using the details alongside.');
        return;
      }
      var submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      setStatus('Sending…');
      fetch(FORM_ENDPOINT, {
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        body: new FormData(form)
      }).then(function (res) {
        if (res.ok) {
          form.reset();
          setStatus('Thank you. Your enquiry has been sent and Tracy will be in touch shortly.');
        } else {
          setStatus('Sorry, something went wrong sending your enquiry. Please call or email instead.');
        }
      }).catch(function () {
        setStatus('Sorry, something went wrong sending your enquiry. Please call or email instead.');
      }).finally(function () { submitBtn.disabled = false; });
    });
  }
})();
