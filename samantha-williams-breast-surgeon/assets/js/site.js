/* Samantha Williams Breast Surgeon — site behaviour.
   The site works without this file; it only adds the mobile menu,
   cookie consent, analytics loading and enquiry-form handling. */
(function () {
  'use strict';

  var CONFIG = window.SITE_CONFIG || {};
  var GA_ID = CONFIG.gaMeasurementId || '';
  var FORM_ENDPOINT = CONFIG.formEndpoint || '';

  /* Nav border once the page has scrolled */
  var nav = document.getElementById('siteNav');
  if (nav) {
    var onScroll = function () {
      nav.classList.toggle('is-scrolled', window.scrollY > 8);
    };
    document.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* Mobile menu */
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

  /* Cookie consent and Google Analytics (loaded only after consent) */
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

  /* Enquiry form */
  var form = document.getElementById('enquiryForm');
  if (form) {
    var status = document.getElementById('formStatus');
    var setStatus = function (msg) { if (status) status.textContent = msg; };
    var endpointReady = FORM_ENDPOINT && !/REPLACE/i.test(FORM_ENDPOINT);

    if (endpointReady) form.setAttribute('action', FORM_ENDPOINT);

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var trap = form.querySelector('.form__honeypot input');
      if (trap && trap.value) return;
      if (!endpointReady) {
        setStatus('The enquiry form is not connected yet. Please call or email Tracy using the details on this page.');
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
          setStatus('Thank you. Your enquiry has been sent and Tracy will be in touch.');
        } else {
          setStatus('Sorry, the enquiry could not be sent. Please call or email instead.');
        }
      }).catch(function () {
        setStatus('Sorry, the enquiry could not be sent. Please call or email instead.');
      }).finally(function () { submitBtn.disabled = false; });
    });
  }
})();
