(function () {
  'use strict';

  var TOKEN_KEY = 'dfs_access_token';
  var USER_KEY = 'dfs_user';
  var INCONCLUSIVE = 'Inconclusive — no trained checkpoint';
  var TERMINAL = ['completed', 'complete', 'done', 'failed', 'error', 'succeeded'];
  var ACTIVE = ['pending', 'processing', 'queued', 'running', 'in_progress', 'analyzing'];

  var $ = function (selector, root) { return (root || document).querySelector(selector); };
  var $$ = function (selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); };
  var page = document.body.dataset.page || '';
  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function esc(value) {
    return String(value === undefined || value === null ? '' : value).replace(/[&<>"']/g, function (char) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char];
    });
  }

  function has(source, key) {
    return Boolean(source) && typeof source === 'object' && Object.prototype.hasOwnProperty.call(source, key);
  }

  function first(source, keys) {
    if (!source || typeof source !== 'object') return undefined;
    for (var i = 0; i < keys.length; i += 1) {
      var value = source[keys[i]];
      if (value !== undefined && value !== null && value !== '') return value;
    }
    return undefined;
  }

  function text(value, fallback) {
    var result = first(value && value.value !== undefined ? value : {}, []) || value;
    if (result === undefined || result === null || result === '') return fallback === undefined ? '' : fallback;
    return String(result);
  }

  function listOf(payload, keys) {
    if (Array.isArray(payload)) return payload;
    if (!payload || typeof payload !== 'object') return [];
    var candidates = (keys || []).concat(['results', 'data', 'items', 'objects']);
    for (var i = 0; i < candidates.length; i += 1) {
      if (Array.isArray(payload[candidates[i]])) return payload[candidates[i]];
    }
    return [];
  }

  function recordOf(payload, keys) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return {};
    var candidates = (keys || []).concat(['data', 'result', 'detail', 'record']);
    for (var i = 0; i < candidates.length; i += 1) {
      var value = payload[candidates[i]];
      if (value && typeof value === 'object' && !Array.isArray(value)) return value;
    }
    return payload;
  }

  function idOf(item) {
    return first(item, ['id', 'pk', 'uuid', 'media_id', 'case_id', 'report_id']);
  }

  function nameOf(item) {
    return text(first(item, ['original_name', 'file_name', 'filename', 'name', 'title', 'label']), 'Untitled artifact');
  }

  function typeOf(item) {
    return text(first(item, ['media_type', 'type', 'file_type', 'modality', 'kind']), 'unknown');
  }

  function statusOf(item) {
    return text(first(item, ['status', 'analysis_status', 'state', 'processing_status']), 'unknown').toLowerCase();
  }

  function statusClass(status) {
    var value = String(status || '').toLowerCase();
    if (['completed', 'complete', 'success', 'succeeded', 'verified', 'authentic'].indexOf(value) !== -1) return 'badge--success';
    if (['failed', 'error', 'fake', 'manipulated', 'critical'].indexOf(value) !== -1) return 'badge--danger';
    if (['pending', 'queued', 'processing', 'running', 'warning', 'review'].indexOf(value) !== -1) return 'badge--warning';
    if (['in_progress', 'analyzing', 'open', 'normal'].indexOf(value) !== -1) return 'badge--info';
    return '';
  }

  function dateText(value) {
    if (!value) return '—';
    var date = new Date(value);
    if (isNaN(date.getTime())) return String(value);
    return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  }

  function truncate(value, length) {
    var str = String(value || '');
    return str.length > length ? str.slice(0, length - 1) + '…' : str;
  }

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY);
  }

  function storeToken(token, remember) {
    var store = remember ? localStorage : sessionStorage;
    store.setItem(TOKEN_KEY, token);
    try { store.setItem(USER_KEY, JSON.stringify({})); } catch (error) { return; }
  }

  function storeUser(user, remember) {
    var store = remember ? localStorage : sessionStorage;
    try { store.setItem(USER_KEY, JSON.stringify(user || {})); } catch (error) { return; }
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    sessionStorage.removeItem(USER_KEY);
  }

  function csrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function errorText(payload, status) {
    if (typeof payload === 'string') return payload;
    if (!payload || typeof payload !== 'object') return 'Request failed (' + status + ').';
    var message = first(payload, ['detail', 'error', 'message', 'error_message']);
    if (message) return typeof message === 'string' ? message : JSON.stringify(message);
    var fieldMessages = [];
    Object.keys(payload).forEach(function (key) {
      var value = payload[key];
      if (Array.isArray(value)) fieldMessages.push(key + ': ' + value.join(', '));
      else if (value && typeof value === 'object') fieldMessages.push(key + ': ' + JSON.stringify(value));
      else if (typeof value === 'string' && key !== 'status') fieldMessages.push(key + ': ' + value);
    });
    return fieldMessages.length ? fieldMessages.join(' · ') : 'Request failed (' + status + ').';
  }

  function api(path, options) {
    var opts = options || {};
    var method = (opts.method || 'GET').toUpperCase();
    var url = path.indexOf('/api/') === 0 ? path : '/api/' + path.replace(/^\//, '');
    var headers = { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
    Object.keys(opts.headers || {}).forEach(function (key) { headers[key] = opts.headers[key]; });
    var body = opts.body;
    if (body !== undefined && body !== null && !(body instanceof FormData) && typeof body !== 'string') {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(body);
    }
    if (getToken()) headers.Authorization = 'Token ' + getToken();
    if (method !== 'GET' && method !== 'HEAD' && csrfToken()) headers['X-CSRFToken'] = csrfToken();
    return fetch(url, { method: method, headers: headers, body: body, credentials: 'same-origin' }).then(function (response) {
      var parsed = response.headers.get('content-type') && response.headers.get('content-type').indexOf('json') !== -1
        ? response.json().catch(function () { return null; })
        : Promise.resolve(null);
      return parsed.then(function (payload) {
        if (!response.ok) {
          var error = new Error(errorText(payload, response.status));
          error.status = response.status;
          error.payload = payload;
          throw error;
        }
        return payload === null ? {} : payload;
      });
    }).catch(function (error) {
      if (error instanceof TypeError) throw new Error('Network unreachable. Check the API service.');
      throw error;
    });
  }

  function reportDownloadPath(report, payload) {
    var id = first(report, ['id', 'report_id']) || first(payload, ['id', 'report_id']);
    if (id === undefined || id === null || id === '') return '';
    return '/api/reports/' + encodeURIComponent(id) + '/download/';
  }

  function downloadReportFile(url, filename) {
    var headers = { Accept: 'application/pdf', 'X-Requested-With': 'XMLHttpRequest' };
    if (getToken()) headers.Authorization = 'Token ' + getToken();
    if (csrfToken()) headers['X-CSRFToken'] = csrfToken();
    return fetch(url, { headers: headers, credentials: 'same-origin' }).then(function (response) {
      var contentType = response.headers.get('content-type') || '';
      var parsing = contentType.indexOf('json') !== -1
        ? response.json().catch(function () { return null; })
        : Promise.resolve(null);
      return parsing.then(function (payload) {
        if (!response.ok) {
          var error = new Error(errorText(payload, response.status));
          error.status = response.status;
          throw error;
        }
        return response.blob();
      });
    }).then(function (blob) {
      if (!window.URL || !window.URL.createObjectURL) throw new Error('Browser download is not supported.');
      var objectUrl = window.URL.createObjectURL(blob);
      var link = document.createElement('a');
      link.href = objectUrl;
      link.download = filename || 'report.pdf';
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(function () { window.URL.revokeObjectURL(objectUrl); }, 1000);
    }).catch(function (error) {
      if (error instanceof TypeError) throw new Error('Network unreachable. Check the API service.');
      throw error;
    });
  }

  function initReportDownloads() {
    document.addEventListener('click', function (event) {
      var link = event.target.closest('a[data-report-download]');
      if (!link) return;
      event.preventDefault();
      var url = link.getAttribute('href');
      if (!url || url === '#') {
        toast('Report download is not available yet.', 'error');
        return;
      }
      downloadReportFile(url, link.dataset.reportName || 'report.pdf')
        .catch(function (error) { toast('Download failed: ' + error.message, 'error'); });
    });
  }

  function setVisible(element, visible) {
    if (element) element.classList.toggle('is-hidden', !visible);
  }

  function region(prefix, state, content) {
    ['Loading', 'Empty', 'Error'].forEach(function (suffix) {
      setVisible(document.getElementById(prefix + suffix), state === suffix.toLowerCase());
    });
    if (content) setVisible(content, state === 'content');
  }

  function toast(message, kind) {
    var regionElement = document.getElementById('toastRegion');
    if (!regionElement) return;
    var item = document.createElement('div');
    item.className = 'toast' + (kind ? ' toast--' + kind : '');
    item.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    item.textContent = message;
    regionElement.appendChild(item);
    if (window.gsap && !reducedMotion) window.gsap.from(item, { opacity: 0, y: 12, duration: 0.3 });
    window.setTimeout(function () {
      if (window.gsap && !reducedMotion) window.gsap.to(item, { opacity: 0, duration: 0.3, onComplete: function () { item.remove(); } });
      else item.remove();
    }, 4200);
  }

  function showAlert(element, message, success) {
    if (!element) return;
    element.textContent = message || '';
    element.classList.toggle('is-visible', Boolean(message));
    element.classList.toggle('form-alert--success', Boolean(success));
  }

  function clearFieldErrors(form) {
    $$('.field__error', form).forEach(function (element) { element.textContent = ''; });
  }

  function applyFieldErrors(form, payload) {
    if (!payload || typeof payload !== 'object') return;
    Object.keys(payload).forEach(function (key) {
      var target = document.getElementById('error_' + key);
      if (!target) return;
      var value = payload[key];
      target.textContent = Array.isArray(value) ? value.join(' ') : String(value);
    });
  }

  function buttonBusy(button, busy, label) {
    if (!button) return;
    if (!button.dataset.originalLabel) button.dataset.originalLabel = button.textContent;
    button.disabled = busy;
    button.textContent = busy ? (label || 'Working…') : button.dataset.originalLabel;
  }

  function roleDestination(user) {
    var role = text(first(user || {}, ['role', 'user_role', 'user_type', 'type', 'group']), '').toLowerCase();
    if (role.indexOf('investigator') !== -1 || role.indexOf('supervisor') !== -1 || role.indexOf('admin') !== -1) return '/investigations/';
    return '/dashboard/';
  }

  function initAuthForms() {
    var loginForm = document.getElementById('loginForm');
    var registerForm = document.getElementById('registerForm');

    if (loginForm) {
      loginForm.addEventListener('submit', function (event) {
        event.preventDefault();
        var alertElement = document.getElementById('authAlert');
        var submit = document.getElementById('loginSubmit');
        var identifier = $('#loginUsername', loginForm).value.trim();
        var password = $('#loginPassword', loginForm).value;
        var remember = $('#loginRemember', loginForm).checked;
        clearFieldErrors(loginForm);
        showAlert(alertElement, '');
        if (!identifier || !password) {
          showAlert(alertElement, 'Enter your username and password.');
          return;
        }
        var payload = { username: identifier, password: password };
        if (identifier.indexOf('@') !== -1) payload.email = identifier;
        buttonBusy(submit, true, 'Authenticating…');
        api('/api/auth/login/', { method: 'POST', body: payload })
          .then(function (data) {
            var token = first(data, ['token', 'access', 'access_token', 'key', 'jwt']);
            if (token) storeToken(token, remember);
            var user = recordOf(data, ['user', 'profile']);
            return api('/api/auth/me/').then(function (me) {
              var merged = Object.keys(user).length ? Object.assign({}, me, user) : me;
              storeUser(merged, remember);
              return merged;
            }).catch(function () {
              storeUser(user, remember);
              return user;
            });
          })
          .then(function (user) {
            window.location.assign(roleDestination(user));
          })
          .catch(function (error) {
            if (error.payload && typeof error.payload === 'object') applyFieldErrors(loginForm, error.payload);
            showAlert(alertElement, error.message);
          })
          .finally(function () { buttonBusy(submit, false); });
      });
    }

    if (registerForm) {
      registerForm.addEventListener('submit', function (event) {
        event.preventDefault();
        var alertElement = document.getElementById('authAlert');
        var submit = document.getElementById('registerSubmit');
        var username = $('#registerUsername', registerForm).value.trim();
        var email = $('#registerEmail', registerForm).value.trim();
        var password = $('#registerPassword', registerForm).value;
        var confirm = $('#registerConfirm', registerForm).value;
        var role = $('#registerRole', registerForm).value;
        clearFieldErrors(registerForm);
        showAlert(alertElement, '');
        if (password !== confirm) {
          $('#error_confirm_password').textContent = 'Passwords do not match.';
          return;
        }
        if (password.length < 8) {
          $('#error_password').textContent = 'Use at least 8 characters.';
          return;
        }
        var payload = { username: username, email: email, password: password, password2: confirm, confirm_password: confirm, role: role };
        buttonBusy(submit, true, 'Creating account…');
        api('/api/auth/register/', { method: 'POST', body: payload })
          .then(function (data) {
            var token = first(data, ['token', 'access', 'access_token', 'key', 'jwt']);
            if (!token) {
              showAlert(alertElement, 'Account created. Sign in with your new credentials.', true);
              registerForm.reset();
              return null;
            }
            storeToken(token, true);
            return api('/api/auth/me/').then(function (me) {
              storeUser(me, true);
              window.location.assign(roleDestination(me));
              return null;
            }).catch(function () {
              window.location.assign('/dashboard/');
              return null;
            });
          })
          .catch(function (error) {
            if (error.payload && typeof error.payload === 'object') applyFieldErrors(registerForm, error.payload);
            showAlert(alertElement, error.message);
          })
          .finally(function () { buttonBusy(submit, false); });
      });
    }
  }

  function initSessionUI() {
    var logout = document.getElementById('logoutBtn');
    if (logout) {
      logout.addEventListener('click', function () {
        buttonBusy(logout, true, 'Signing out…');
        api('/api/auth/logout/', { method: 'POST' })
          .catch(function (error) {
            if (error.status !== 401 && error.status !== 404) toast('Logout request failed; local session cleared.', 'error');
          })
          .finally(function () {
            clearSession();
            window.location.assign('/');
          });
      });
    }

    if (!getToken()) return;
    api('/api/auth/me/')
      .then(function (data) {
        var user = recordOf(data, ['user', 'profile']);
        var label = text(first(user, ['display_name', 'full_name', 'username', 'email', 'name']), 'Authenticated user');
        var role = text(first(user, ['role', 'user_role', 'group']), '');
        var initials = label.slice(0, 2).toUpperCase();
        var labelElement = document.getElementById('userLabel');
        var initialsElement = document.getElementById('userInitials');
        if (labelElement) labelElement.textContent = role ? label + ' · ' + role : label;
        if (initialsElement) initialsElement.textContent = initials;
        storeUser(user, Boolean(localStorage.getItem(TOKEN_KEY)));
      })
      .catch(function (error) {
        if (error.status === 401) clearSession();
      });
  }

  function initTopbarSearch() {
    var form = document.getElementById('topbarSearchForm');
    if (!form) return;
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var value = $('#topbarSearch', form).value.trim();
      window.location.assign('/media/' + (value ? '?search=' + encodeURIComponent(value) : ''));
    });
  }

  var dashState = {
    media: [],
    selectedId: null,
    charts: {},
    pollTimer: null,
    attempts: {}
  };

  function setStat(key, value, note) {
    var valueElement = $('[data-stat-value="' + key + '"]');
    var noteElement = $('[data-stat-note="' + key + '"]');
    if (valueElement) valueElement.textContent = value === undefined || value === null ? '—' : String(value);
    if (noteElement) noteElement.textContent = note || 'Live API data';
  }

  function loadAnalytics() {
    return api('/api/analytics/dashboard/')
      .then(function (payload) {
        var source = recordOf(payload, ['summary', 'stats', 'metrics', 'counts', 'analytics']);
        var note = text(first(payload, ['period', 'generated_at', 'updated_at']), 'Live API data');
        setStat('total_media', first(source, ['total_media', 'media_count', 'total_media_count', 'total']), note);
        setStat('analyses', first(source, ['analyses', 'total_analyses', 'analysis_count', 'completed_analyses']), note);
        setStat('open_cases', first(source, ['open_investigations', 'open_cases', 'active_cases']), note);
        setStat('reports', first(source, ['reports', 'total_reports', 'report_count']), note);
        renderCharts(payload);
      })
      .catch(function (error) {
        ['total_media', 'analyses', 'open_cases', 'reports'].forEach(function (key) { setStat(key, '—', 'Unavailable'); });
        renderCharts(null);
        toast('Analytics unavailable: ' + error.message, 'error');
      });
  }

  function pairsFrom(series) {
    var pairs = [];
    if (Array.isArray(series)) {
      series.forEach(function (item) {
        if (Array.isArray(item) && item.length >= 2) {
          pairs.push({ label: String(item[0]), value: Number(item[1]) || 0 });
          return;
        }
        if (item && typeof item === 'object') {
          var label = first(item, ['label', 'status', 'name', 'key', 'date', 'day', 'bucket']);
          var value = first(item, ['count', 'value', 'total', 'amount']);
          if (label !== undefined && value !== undefined) pairs.push({ label: String(label), value: Number(value) || 0 });
        }
      });
    } else if (series && typeof series === 'object') {
      Object.keys(series).forEach(function (key) {
        var value = series[key];
        pairs.push({ label: key, value: typeof value === 'number' ? value : (value && Number(first(value, ['count', 'value'])) ? Number(first(value, ['count', 'value'])) : 0) });
      });
    }
    return pairs;
  }

  function statusPairs(media) {
    var counts = {};
    media.forEach(function (item) {
      var key = statusOf(item);
      counts[key] = (counts[key] || 0) + 1;
    });
    return Object.keys(counts).map(function (key) { return { label: key, value: counts[key] }; });
  }

  function chartOptions(kind) {
    var base = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#c9d2df', boxWidth: 12, font: { family: 'Plus Jakarta Sans', size: 10 } } },
        tooltip: { backgroundColor: '#0b1730', borderColor: 'rgba(212,175,55,0.35)', borderWidth: 1, titleColor: '#f3dfa0', bodyColor: '#f6f8fc' }
      }
    };
    if (kind === 'line') {
      base.scales = {
        x: { ticks: { color: '#8b98ae', font: { size: 10 } }, grid: { color: 'rgba(201,210,223,0.06)' } },
        y: { beginAtZero: true, ticks: { color: '#8b98ae', precision: 0, font: { size: 10 } }, grid: { color: 'rgba(201,210,223,0.08)' } }
      };
    }
    return base;
  }

  function renderChart(canvas, emptyId, key, config, hasData) {
    var empty = document.getElementById(emptyId);
    setVisible(canvas, hasData);
    setVisible(empty, !hasData);
    if (!hasData || typeof Chart === 'undefined') {
      if (dashState.charts[key]) {
        dashState.charts[key].destroy();
        delete dashState.charts[key];
      }
      if (empty && typeof Chart === 'undefined') empty.querySelector('p').textContent = 'Chart library unavailable.';
      return;
    }
    if (dashState.charts[key]) dashState.charts[key].destroy();
    dashState.charts[key] = new Chart(canvas, config);
  }

  function renderCharts(payload) {
    if (page !== 'dashboard') return;
    var statusCanvas = document.getElementById('statusChart');
    var trendCanvas = document.getElementById('trendChart');
    if (!statusCanvas || !trendCanvas) return;
    var source = recordOf(payload, ['charts', 'analytics']) || {};
    var distribution = first(source, ['status_distribution', 'media_statuses', 'status_counts', 'verdict_distribution', 'distribution']);
    var pairs = pairsFrom(distribution);
    if (!pairs.length && dashState.media.length) pairs = statusPairs(dashState.media);
    renderChart(statusCanvas, 'statusChartEmpty', 'status', {
      type: 'doughnut',
      data: {
        labels: pairs.map(function (pair) { return pair.label; }),
        datasets: [{ data: pairs.map(function (pair) { return pair.value; }), backgroundColor: ['#d4af37', '#7fb8f0', '#5fd6a4', '#e8b85c', '#ee7b7b', '#8b98ae'], borderColor: '#080c15', borderWidth: 2 }]
      },
      options: chartOptions('doughnut')
    }, pairs.length > 0);

    var series = first(source, ['trend', 'volume', 'analyses_over_time', 'daily', 'timeseries']);
    var trendPairs = pairsFrom(series);
    renderChart(trendCanvas, 'trendChartEmpty', 'trend', {
      type: 'line',
      data: {
        labels: trendPairs.map(function (pair) { return pair.label; }),
        datasets: [{ label: 'Analyses', data: trendPairs.map(function (pair) { return pair.value; }), borderColor: '#d4af37', backgroundColor: 'rgba(212,175,55,0.12)', fill: true, tension: 0.35, pointRadius: 3, pointBackgroundColor: '#f3dfa0' }]
      },
      options: chartOptions('line')
    }, trendPairs.length > 0);
  }

  function renderMediaTable() {
    var body = document.getElementById('mediaTableBody');
    if (!body) return;
    var list = dashState.media;
    region('media', list.length ? 'content' : 'empty', document.getElementById('mediaTableWrap'));
    var caption = document.getElementById('libraryCaption');
    if (caption) caption.textContent = list.length + ' artifact(s) returned by /api/media/';
    body.innerHTML = list.map(function (item) {
      var id = idOf(item);
      var status = statusOf(item);
      return '<tr data-id="' + esc(id) + '">' +
        '<td><span class="data-table__name">' + esc(nameOf(item)) + '</span><span class="data-table__sub">#' + esc(id) + ' · ' + esc(typeOf(item)) + '</span></td>' +
        '<td><span class="badge ' + statusClass(status) + '" data-cell-status>' + esc(status) + '</span></td>' +
        '<td><div class="row-actions">' +
        '<button class="btn btn--ghost btn--sm" type="button" data-action="select">Analyze</button>' +
        '<button class="btn btn--quiet btn--sm" type="button" data-action="status">Status</button>' +
        '<button class="btn btn--quiet btn--sm" type="button" data-action="reprocess">Reprocess</button>' +
        '</div></td></tr>';
    }).join('');
  }

  function loadMedia(search) {
    region('media', 'loading', document.getElementById('mediaTableWrap'));
    var params = new URLSearchParams();
    if (search) params.set('search', search);
    return api('/api/media/' + (params.toString() ? '?' + params.toString() : ''))
      .then(function (payload) {
        dashState.media = listOf(payload, ['media', 'results']);
        renderMediaTable();
        renderCharts(null);
        var requested = new URLSearchParams(window.location.search).get('media');
        if (requested && !dashState.selectedId) selectMedia(requested);
        return dashState.media;
      })
      .catch(function (error) {
        var detail = document.getElementById('mediaErrorDetail');
        if (detail) detail.textContent = error.message;
        region('media', 'error', document.getElementById('mediaTableWrap'));
        throw error;
      });
  }

  function updateRowStatus(id, status) {
    var row = $('tr[data-id="' + String(id).replace(/"/g, '\\"') + '"]');
    if (!row) return;
    var cell = $('[data-cell-status]', row);
    if (!cell) return;
    cell.textContent = status;
    cell.className = 'badge ' + statusClass(status);
  }

  function refreshStatus(id, announce) {
    return api('/api/media/' + encodeURIComponent(id) + '/status/')
      .then(function (payload) {
        var data = recordOf(payload, ['status', 'data', 'result']);
        var status = statusOf(Object.keys(data).length ? data : payload);
        updateRowStatus(id, status);
        var mediaItem = dashState.media.filter(function (item) { return String(idOf(item)) === String(id); })[0];
        if (mediaItem) mediaItem.status = status;
        if (String(dashState.selectedId) === String(id) && TERMINAL.indexOf(status) !== -1) loadAnalysis(id);
        if (announce) toast('Status: ' + status, 'success');
        return data;
      })
      .catch(function (error) {
        if (announce) toast(error.message, 'error');
      });
  }

  function startPolling() {
    if (dashState.pollTimer) return;
    dashState.pollTimer = window.setInterval(function () {
      if (document.hidden) return;
      dashState.media.filter(function (item) {
        return ACTIVE.indexOf(statusOf(item)) !== -1;
      }).slice(0, 12).forEach(function (item) {
        var id = idOf(item);
        dashState.attempts[id] = (dashState.attempts[id] || 0) + 1;
        if (dashState.attempts[id] > 60) return;
        refreshStatus(id, false);
      });
    }, 6000);
  }

  function reprocessMedia(id) {
    buttonBusy($('#reprocessBtn'), true, 'Reprocessing…');
    return api('/api/media/' + encodeURIComponent(id) + '/reprocess/', { method: 'POST', body: {} })
      .then(function () {
        toast('Reprocessing requested for this artifact.', 'success');
        return refreshStatus(id, false);
      })
      .catch(function (error) { toast(error.message, 'error'); })
      .finally(function () { buttonBusy($('#reprocessBtn'), false); });
  }

  function isUntrained(data) {
    if (!data || typeof data !== 'object') return false;
    if (data.checkpoint === null || data.model_checkpoint === null) return true;
    if (data.model_trained === false || data.trained === false || data.has_checkpoint === false || data.untrained === true) return true;
    var label = text(first(data, ['status', 'state', 'verdict', 'result', 'conclusion']), '').toLowerCase();
    return label.indexOf('untrained') !== -1 || label.indexOf('no checkpoint') !== -1;
  }

  function verdictOf(data) {
    if (isUntrained(data)) return INCONCLUSIVE;
    return text(first(data, ['verdict', 'result', 'prediction', 'conclusion', 'classification', 'label']), '');
  }

  function confidenceOf(data) {
    if (!data || isUntrained(data)) return null;
    var value = first(data, ['confidence', 'confidence_score', 'probability', 'score']);
    var number = Number(value);
    if (!isFinite(number)) return null;
    if (number > 0 && number <= 1) number = number * 100;
    if (number < 0 || number > 100) return null;
    return number;
  }

  function valuesOf(data, keys) {
    return listOf(first(data, keys), ['signals', 'items', 'results', 'findings', 'frames']);
  }

  function renderSignalList(signals) {
    var list = document.getElementById('signalList');
    var empty = document.getElementById('signalEmpty');
    setVisible(empty, signals.length === 0);
    if (!list) return;
    list.innerHTML = signals.map(function (signal) {
      if (typeof signal !== 'object' || signal === null) return '<li><div class="signal-list__head"><span>' + esc(signal) + '</span></div></li>';
      var label = text(first(signal, ['label', 'name', 'title', 'type', 'signal']), 'Unnamed signal');
      var value = first(signal, ['value', 'score', 'severity', 'confidence']);
      var detail = text(first(signal, ['description', 'detail', 'reason', 'note']), '');
      return '<li><div class="signal-list__head"><span>' + esc(label) + '</span><span>' + esc(value === undefined ? '' : value) + '</span></div>' +
        (detail ? '<p>' + esc(detail) + '</p>' : '') + '</li>';
    }).join('');
  }

  function renderTimeline(events) {
    var list = document.getElementById('forensicTimeline');
    var empty = document.getElementById('timelineEmpty');
    setVisible(empty, events.length === 0);
    if (!list) return;
    list.innerHTML = events.map(function (event) {
      if (typeof event !== 'object' || event === null) return '<li><strong>' + esc(event) + '</strong></li>';
      var title = text(first(event, ['title', 'label', 'event', 'name', 'action']), 'Forensic event');
      var time = first(event, ['timestamp', 'time', 'date', 'frame_time']);
      var detail = text(first(event, ['description', 'detail', 'note']), '');
      return '<li>' + (time ? '<time>' + esc(dateText(time)) + '</time>' : '') + '<strong>' + esc(title) + '</strong>' + (detail ? '<p>' + esc(detail) + '</p>' : '') + '</li>';
    }).join('');
  }

  function renderFrames(frames) {
    var grid = document.getElementById('frameGrid');
    var suspicious = document.getElementById('suspiciousFrames');
    var empty = document.getElementById('framesEmpty');
    var suspiciousEmpty = document.getElementById('suspiciousEmpty');
    setVisible(empty, frames.length === 0);
    setVisible(suspiciousEmpty, frames.length === 0);
    var markup = frames.map(function (frame) {
      var label = text(first(frame, ['label', 'name', 'frame_id', 'id', 'timestamp', 'time']), 'Frame');
      var flag = text(first(frame, ['reason', 'flag', 'score', 'severity', 'status']), 'flagged');
      var flagged = frame && (frame.flagged === true || frame.suspicious === true || statusClass(String(flag).toLowerCase()) === 'badge--danger');
      return '<article class="frame-card">' +
        '<img src="/static/images/forensic-frame.svg" alt="Forensic frame placeholder for ' + esc(label) + '">' +
        '<div class="frame-card__meta"><span>' + esc(label) + '</span><span>' + esc(flagged ? flag || 'flagged' : flag) + '</span></div>' +
        '</article>';
    }).join('');
    if (grid) grid.innerHTML = markup;
    if (suspicious) suspicious.innerHTML = markup;
  }

  function renderMetadata(data) {
    var list = document.getElementById('metadataList');
    if (!list) return;
    var entries = Object.keys(data || {}).filter(function (key) {
      return data[key] !== null && typeof data[key] !== 'object';
    }).slice(0, 14);
    list.innerHTML = entries.length ? entries.map(function (key) {
      return '<div><dt>' + esc(key.replace(/_/g, ' ')) + '</dt><dd>' + esc(data[key]) + '</dd></div>';
    }).join('') : '<div><dt>Records</dt><dd>None returned</dd></div>';
  }

  function renderIntegrity(data) {
    var container = document.getElementById('integrityList');
    if (!container) return;
    var checks = valuesOf(data, ['checks', 'results', 'evidence', 'records', 'items']);
    if (!checks.length && data && typeof data === 'object') {
      checks = Object.keys(data).filter(function (key) { return data[key] !== null && typeof data[key] !== 'object'; }).map(function (key) {
        return { label: key, value: data[key] };
      });
    }
    container.innerHTML = checks.map(function (check) {
      if (typeof check !== 'object' || check === null) return '<div class="evidence-item"><div class="evidence-item__head">' + esc(check) + '</div></div>';
      var label = text(first(check, ['label', 'name', 'check', 'type']), 'Integrity check');
      var value = first(check, ['value', 'result', 'status', 'verified']);
      var detail = text(first(check, ['detail', 'description', 'note']), '');
      return '<div class="evidence-item"><div class="evidence-item__head"><span>' + esc(label) + '</span><span class="badge ' + statusClass(String(value).toLowerCase()) + '">' + esc(value === undefined ? '—' : value) + '</span></div>' + (detail ? '<p>' + esc(detail) + '</p>' : '') + '</div>';
    }).join('');
    setVisible(document.getElementById('evidenceEmpty'), checks.length === 0);
  }

  function renderExplanations(data) {
    var container = document.getElementById('explanationList');
    if (!container) return;
    var items = valuesOf(data, ['explanations', 'reasons', 'highlights', 'items']);
    if (!items.length && data && typeof data === 'object') {
      items = Object.keys(data).filter(function (key) { return data[key] && typeof data[key] !== 'object'; }).map(function (key) {
        return { label: key, detail: data[key] };
      });
    }
    container.innerHTML = items.map(function (item) {
      if (typeof item !== 'object' || item === null) return '<div class="explain-item"><p>' + esc(item) + '</p></div>';
      var title = text(first(item, ['title', 'label', 'factor', 'name']), 'Explanation');
      var detail = text(first(item, ['description', 'detail', 'reason', 'text', 'value']), '');
      return '<div class="explain-item"><strong>' + esc(title) + '</strong><p>' + esc(detail) + '</p></div>';
    }).join('');
    setVisible(document.getElementById('explanationsEmpty'), items.length === 0);
  }

  function renderModality(elementId, noteId, result, fallback) {
    var element = document.getElementById(elementId);
    var note = document.getElementById(noteId);
    if (!element) return;
    if (!result || !result.ok) {
      element.textContent = result && result.error && result.error.status === 404 ? 'Not applicable' : 'Unavailable';
      if (note) note.textContent = result && result.error ? result.error.message.slice(0, 70) : fallback;
      return;
    }
    var value = recordOf(result.value, ['analysis', 'data', 'result']);
    var verdict = verdictOf(Object.keys(value).length ? value : result.value) || 'No verdict reported';
    element.textContent = verdict === INCONCLUSIVE ? 'Inconclusive' : truncate(verdict, 48);
    element.classList.toggle('is-inconclusive', verdict === INCONCLUSIVE);
    if (note) note.textContent = text(first(value, ['status', 'state']), fallback);
  }

  function settle(endpoint) {
    return api(endpoint).then(function (value) { return { ok: true, value: value }; }).catch(function (error) {
      return { ok: false, error: error, status: error.status };
    });
  }

  function loadAnalysis(id) {
    dashState.selectedId = id;
    region('result', 'loading');
    var generate = document.getElementById('generateReportBtn');
    var refresh = document.getElementById('refreshStatusBtn');
    var reprocess = document.getElementById('reprocessBtn');
    if (generate) generate.disabled = true;
    if (refresh) refresh.disabled = false;
    if (reprocess) reprocess.disabled = false;
    setVisible(document.getElementById('reportDownloadLink'), false);

    var endpoints = {
      image: '/api/analyses/image/' + encodeURIComponent(id) + '/',
      video: '/api/analyses/video/' + encodeURIComponent(id) + '/',
      audio: '/api/analyses/audio/' + encodeURIComponent(id) + '/',
      forensics: '/api/forensics/' + encodeURIComponent(id) + '/',
      metadata: '/api/metadata/' + encodeURIComponent(id) + '/',
      integrity: '/api/integrity/' + encodeURIComponent(id) + '/',
      explanations: '/api/explanations/' + encodeURIComponent(id) + '/'
    };

    Promise.all([
      settle('/api/media/' + encodeURIComponent(id) + '/status/'),
      settle(endpoints.image),
      settle(endpoints.video),
      settle(endpoints.audio),
      settle(endpoints.forensics),
      settle(endpoints.metadata),
      settle(endpoints.integrity),
      settle(endpoints.explanations)
    ]).then(function (results) {
      var statusResult = results[0];
      var successes = results.filter(function (result) { return result.ok; }).length;
      if (successes === 0) {
        var detail = document.getElementById('resultErrorDetail');
        if (detail) detail.textContent = statusResult.error ? statusResult.error.message : 'All analysis endpoints failed.';
        region('result', 'error');
        return;
      }
      var statusData = statusResult.ok ? recordOf(statusResult.value, ['status', 'data', 'result']) : {};
      var status = statusOf(Object.keys(statusData).length ? statusData : {});
      var imageResult = results[1];
      var videoResult = results[2];
      var audioResult = results[3];
      var forensicResult = results[4];
      var metadataResult = results[5];
      var integrityResult = results[6];
      var explanationResult = results[7];

      var forensicData = forensicResult.ok ? recordOf(forensicResult.value, ['analysis', 'data', 'result']) : {};
      var candidates = [imageResult, videoResult, audioResult, forensicResult].filter(function (result) { return result.ok; });
      var untrained = candidates.some(function (result) {
        var data = recordOf(result.value, ['analysis', 'data', 'result']);
        return isUntrained(Object.keys(data).length ? data : result.value);
      });
      var verdict = '';
      candidates.forEach(function (result) {
        if (verdict) return;
        var data = recordOf(result.value, ['analysis', 'data', 'result']);
        verdict = verdictOf(Object.keys(data).length ? data : result.value);
      });
      if (untrained || isUntrained(statusData)) verdict = INCONCLUSIVE;
      if (!verdict && ACTIVE.indexOf(status) !== -1) verdict = 'Analysis in progress';
      if (!verdict) verdict = 'No conclusion reported';

      var verdictElement = document.getElementById('resultVerdict');
      if (verdictElement) {
        verdictElement.textContent = verdict;
        verdictElement.classList.toggle('is-inconclusive', verdict === INCONCLUSIVE);
      }
      var statusBadge = document.getElementById('resultStatus');
      if (statusBadge) {
        statusBadge.textContent = status;
        statusBadge.className = 'status-badge ' + statusClass(status).replace('badge--', 'status-badge--');
      }
      var media = dashState.media.filter(function (item) { return String(idOf(item)) === String(id); })[0] || {};
      var mediaName = document.getElementById('resultMediaName');
      if (mediaName) mediaName.textContent = nameOf(media);
      var timestamp = document.getElementById('resultTimestamp');
      if (timestamp) timestamp.textContent = dateText(first(statusData, ['updated_at', 'created_at', 'completed_at']));
      var caption = document.getElementById('resultCaption');
      if (caption) caption.textContent = 'Analysis for ' + nameOf(media) + ' · artifact #' + id;

      var confidence = null;
      candidates.forEach(function (result) {
        if (confidence !== null) return;
        var data = recordOf(result.value, ['analysis', 'data', 'result']);
        confidence = confidenceOf(Object.keys(data).length ? data : result.value);
      });
      var confidenceValue = document.getElementById('confidenceValue');
      var confidenceBar = document.getElementById('confidenceBar');
      if (confidenceValue) confidenceValue.textContent = confidence === null ? 'Not reported' : confidence.toFixed(1) + '%';
      if (confidenceBar) confidenceBar.style.width = confidence === null ? '0%' : confidence + '%';

      renderModality('analysisImage', 'analysisImageNote', imageResult, 'Image channel');
      renderModality('analysisVideo', 'analysisVideoNote', videoResult, 'Video channel');
      renderModality('analysisAudio', 'analysisAudioNote', audioResult, 'Audio channel');
      renderSignalList(valuesOf(forensicData, ['signals', 'findings', 'indicators']));
      renderTimeline(valuesOf(forensicData, ['timeline', 'events', 'activity']));
      renderFrames(valuesOf(forensicData, ['suspicious_frames', 'flagged_frames', 'frames']));
      var metadataData = metadataResult.ok ? recordOf(metadataResult.value, ['metadata', 'data', 'result']) : {};
      renderMetadata(metadataData);
      var integrityData = integrityResult.ok ? recordOf(integrityResult.value, ['integrity', 'data', 'result']) : {};
      renderIntegrity(integrityData);
      var explanationData = explanationResult.ok ? recordOf(explanationResult.value, ['explanations', 'data', 'result']) : {};
      renderExplanations(explanationData);

      region('result', 'content', document.getElementById('resultContent'));
      if (generate) generate.disabled = false;
      var reportStatus = document.getElementById('reportStatus');
      if (reportStatus) reportStatus.textContent = 'Ready to generate a report for artifact #' + id + '.';
      if (window.gsap && !reducedMotion) window.gsap.from('#resultContent', { opacity: 0, y: 16, duration: 0.45 });
    }).catch(function (error) {
      var detail = document.getElementById('resultErrorDetail');
      if (detail) detail.textContent = error.message;
      region('result', 'error');
    });
  }

  function generateReport(id) {
    var button = $('#generateReportBtn');
    var status = $('#reportStatus');
    if (!id) return;
    buttonBusy(button, true, 'Generating…');
    api('/api/reports/generate/' + encodeURIComponent(id) + '/', { method: 'POST' })
      .then(function (payload) {
        var report = recordOf(payload, ['report', 'data', 'result']);
        var reportId = first(report, ['report_id', 'id']) || first(payload, ['report_id', 'id']);
        var url = reportDownloadPath(report, payload);
        var link = document.getElementById('reportDownloadLink');
        if (url && link) {
          link.href = url;
          link.dataset.reportName = 'report-' + String(reportId) + '.pdf';
          link.textContent = 'Download PDF report ↗';
          setVisible(link, true);
        } else {
          setVisible(link, false);
        }
        if (status) status.textContent = reportId
          ? 'PDF report ' + reportId + ' generated.'
          : 'PDF report generated. Open the report registry to download it.';
        toast('PDF report generated.', 'success');
      })
      .catch(function (error) {
        if (status) status.textContent = error.message;
        toast(error.message, 'error');
      })
      .finally(function () { buttonBusy(button, false); });
  }

  function initResultTabs() {
    var tabs = $$('.tab[data-tab]');
    if (!tabs.length) return;
    tabs.forEach(function (tab, index) {
      tab.addEventListener('click', function () {
        tabs.forEach(function (item) { item.setAttribute('aria-selected', 'false'); });
        tab.setAttribute('aria-selected', 'true');
        $$('.tab-panel').forEach(function (panel) { setVisible(panel, panel.id === 'panel-' + tab.dataset.tab); });
      });
      tab.addEventListener('keydown', function (event) {
        if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
        var offset = event.key === 'ArrowRight' ? 1 : -1;
        var next = tabs[(index + offset + tabs.length) % tabs.length];
        next.focus();
        next.click();
      });
    });
  }

  function initUpload() {
    var drop = document.getElementById('dropZone');
    var input = document.getElementById('fileInput');
    var browse = document.getElementById('browseBtn');
    var queue = document.getElementById('uploadQueue');
    if (!drop || !input || !browse || !queue) return;

    browse.addEventListener('click', function () { input.click(); });
    input.addEventListener('change', function () {
      handleFiles(input.files);
      input.value = '';
    });
    ['dragenter', 'dragover'].forEach(function (eventName) {
      drop.addEventListener(eventName, function (event) {
        event.preventDefault();
        drop.classList.add('is-dragging');
      });
    });
    ['dragleave', 'drop'].forEach(function (eventName) {
      drop.addEventListener(eventName, function (event) {
        event.preventDefault();
        drop.classList.remove('is-dragging');
      });
    });
    drop.addEventListener('drop', function (event) {
      handleFiles(event.dataTransfer && event.dataTransfer.files);
    });
    var clear = document.getElementById('clearUploadQueue');
    if (clear) clear.addEventListener('click', function () {
      queue.innerHTML = '';
      toast('Upload queue cleared.');
    });

    function handleFiles(files) {
      if (!files || !files.length) return;
      Array.prototype.slice.call(files).forEach(function (file) {
        var row = document.createElement('div');
        row.className = 'progress-row';
        row.innerHTML = '<div class="progress-row__head"><span>' + esc(file.name) + '</span><span data-progress-label>0%</span></div><div class="progress"><div class="progress__bar"></div></div><div class="muted" data-progress-note style="font-size:.7rem">Queued locally</div>';
        queue.appendChild(row);
        uploadFile(file, row);
      });
    }

    function uploadFile(file, row) {
      var label = $('[data-progress-label]', row);
      var bar = $('.progress__bar', row);
      var note = $('[data-progress-note]', row);
      var formData = new FormData();
      formData.append('file', file, file.name);
      if (file.type) formData.append('media_type', file.type.split('/')[0]);
      var xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/media/');
      xhr.setRequestHeader('Accept', 'application/json');
      if (getToken()) xhr.setRequestHeader('Authorization', 'Token ' + getToken());
      if (csrfToken()) xhr.setRequestHeader('X-CSRFToken', csrfToken());
      xhr.upload.addEventListener('progress', function (event) {
        if (!event.lengthComputable) return;
        var percent = Math.round((event.loaded / event.total) * 100);
        if (label) label.textContent = percent + '%';
        if (bar) bar.style.width = percent + '%';
        if (note) note.textContent = 'Uploading…';
      });
      xhr.addEventListener('load', function () {
        var payload = null;
        try { payload = JSON.parse(xhr.responseText); } catch (error) { payload = null; }
        if (xhr.status < 200 || xhr.status >= 300) {
          if (note) note.textContent = errorText(payload, xhr.status);
          if (label) label.textContent = 'Failed';
          toast(file.name + ': ' + errorText(payload, xhr.status), 'error');
          return;
        }
        if (label) label.textContent = '100%';
        if (bar) bar.style.width = '100%';
        if (note) note.textContent = 'Uploaded · queued for analysis';
        var id = idOf(payload || {});
        if (id) {
          refreshStatus(id, false);
          loadAnalysis(id);
        }
        loadMedia().catch(function () {});
        toast(file.name + ' uploaded.', 'success');
      });
      xhr.addEventListener('error', function () {
        if (note) note.textContent = 'Network unreachable';
        if (label) label.textContent = 'Failed';
        toast('Upload failed: network unreachable.', 'error');
      });
      xhr.send(formData);
    }
  }

  function loadCasesPreview() {
    return api('/api/investigations/')
      .then(function (payload) {
        var list = listOf(payload, ['investigations', 'cases']).filter(function (item) {
          return ['closed', 'resolved'].indexOf(statusOf(item)) === -1;
        }).slice(0, 4);
        region('case', list.length ? 'content' : 'empty', document.getElementById('caseList'));
        var container = document.getElementById('caseList');
        if (!container) return;
        container.innerHTML = list.map(function (item) {
          var id = idOf(item);
          return '<article class="investigation-card"><h3>' + esc(nameOf(item)) + '</h3>' +
            '<div class="investigation-card__meta"><span class="badge ' + statusClass(statusOf(item)) + '">' + esc(statusOf(item)) + '</span>' +
            '<span>' + esc(text(first(item, ['assignee', 'assigned_to', 'owner']), 'Unassigned')) + '</span></div>' +
            '<a class="btn btn--quiet btn--sm" href="/investigations/' + encodeURIComponent(id) + '/">Open case →</a></article>';
        }).join('');
      })
      .catch(function () { region('case', 'error', document.getElementById('caseList')); });
  }

  function bindDashboardActions() {
    var mediaBody = document.getElementById('mediaTableBody');
    if (mediaBody) {
      mediaBody.addEventListener('click', function (event) {
        var button = event.target.closest('button[data-action]');
        if (!button) return;
        var row = button.closest('tr[data-id]');
        if (!row) return;
        var id = row.dataset.id;
        if (button.dataset.action === 'select') loadAnalysis(id);
        if (button.dataset.action === 'status') refreshStatus(id, true);
        if (button.dataset.action === 'reprocess') reprocessMedia(id);
      });
    }
    var refresh = $('#refreshDashboardBtn');
    if (refresh) refresh.addEventListener('click', function () {
      loadAnalytics();
      loadMedia();
      loadCasesPreview();
      toast('Workspace refreshed.');
    });
    var refreshMedia = $('#refreshMediaBtn');
    if (refreshMedia) refreshMedia.addEventListener('click', function () { loadMedia().catch(function () {}); });
    var refreshCharts = $('#refreshChartsBtn');
    if (refreshCharts) refreshCharts.addEventListener('click', function () { loadAnalytics(); });
    var refreshStatusBtn = $('#refreshStatusBtn');
    if (refreshStatusBtn) refreshStatusBtn.addEventListener('click', function () {
      if (dashState.selectedId) refreshStatus(dashState.selectedId, true);
    });
    var reprocessBtn = $('#reprocessBtn');
    if (reprocessBtn) reprocessBtn.addEventListener('click', function () {
      if (dashState.selectedId) reprocessMedia(dashState.selectedId);
    });
    var generate = $('#generateReportBtn');
    if (generate) generate.addEventListener('click', function () { generateReport(dashState.selectedId); });
  }

  function initDashboard() {
    if (page !== 'dashboard') return;
    initResultTabs();
    initUpload();
    bindDashboardActions();
    region('result', 'empty');
    if (window.SentinelScene && document.getElementById('forensicCanvasMount')) {
      var handle = window.SentinelScene.mount(document.getElementById('forensicCanvasMount'), { particles: 80 });
      window.addEventListener('pagehide', function () { if (handle) handle.destroy(); }, { once: true });
    }
    loadMedia().catch(function () {});
    loadAnalytics();
    loadCasesPreview();
    startPolling();
  }

  function initInvestigationsList() {
    if (page !== 'investigations') return;
    var form = document.getElementById('caseFilters');
    var newForm = document.getElementById('newCaseForm');
    var panel = document.getElementById('newCaseFormPanel');
    var toggle = $('#openCaseFormBtn');
    var cancel = $('#cancelCaseForm');
    var refresh = $('#refreshCasesBtn');

    function toggleForm(force) {
      var open = typeof force === 'boolean' ? force : panel.classList.contains('is-hidden');
      setVisible(panel, open);
      if (toggle) toggle.setAttribute('aria-expanded', String(open));
    }

    if (toggle) toggle.addEventListener('click', function () { toggleForm(); });
    if (cancel) cancel.addEventListener('click', function () { toggleForm(false); });
    if (refresh) refresh.addEventListener('click', function () { loadCases(); });
    if (form) {
      form.addEventListener('submit', function (event) { event.preventDefault(); loadCases(); });
      var clear = $('#clearCaseFilters');
      if (clear) clear.addEventListener('click', function () { form.reset(); loadCases(); });
    }

    function loadCases() {
      region('caseList', 'loading', document.getElementById('caseCards'));
      var params = new URLSearchParams(new FormData(form || document.createElement('form')));
      return api('/api/investigations/' + (params.toString() ? '?' + params.toString() : ''))
        .then(function (payload) {
          var list = listOf(payload, ['investigations', 'cases']);
          region('caseList', list.length ? 'content' : 'empty', document.getElementById('caseCards'));
          var container = document.getElementById('caseCards');
          if (container) {
            container.innerHTML = list.map(function (item) {
              var id = idOf(item);
              var assignee = text(first(item, ['assignee', 'assigned_to', 'owner']), 'Unassigned');
              var evidenceCount = listOf(first(item, ['media', 'evidence', 'attachments']), ['items']).length;
              return '<article class="investigation-card"><h3>' + esc(nameOf(item)) + '</h3>' +
                '<div class="investigation-card__meta"><span class="badge ' + statusClass(statusOf(item)) + '">' + esc(statusOf(item)) + '</span>' +
                '<span>' + esc(assignee) + '</span><span>' + esc(text(first(item, ['priority']), 'normal')) + '</span>' +
                '<span>' + evidenceCount + ' evidence</span></div>' +
                '<p>' + esc(truncate(text(first(item, ['description', 'summary']), 'No description provided.'), 140)) + '</p>' +
                '<a class="btn btn--outline btn--sm" href="/investigations/' + encodeURIComponent(id) + '/">Open case →</a></article>';
            }).join('');
          }
          var count = document.getElementById('caseCount');
          if (count) count.textContent = list.length + ' investigation(s) returned by API';
        })
        .catch(function (error) {
          var detail = document.getElementById('caseListErrorDetail');
          if (detail) detail.textContent = error.message;
          region('caseList', 'error', document.getElementById('caseCards'));
        });
    }

    if (newForm) {
      newForm.addEventListener('submit', function (event) {
        event.preventDefault();
        clearFieldErrors(newForm);
        showAlert(document.getElementById('caseFormAlert'), '');
        var payload = {
          title: $('#caseTitleInput', newForm).value.trim(),
          description: $('#caseDescription', newForm).value.trim(),
          assigned_to: $('#caseAssignee', newForm).value.trim(),
          priority: $('#casePriority', newForm).value.toUpperCase()
        };
        if (!payload.title) {
          $('#error_title').textContent = 'A case title is required.';
          return;
        }
        var submit = $('button[type="submit"]', newForm);
        buttonBusy(submit, true, 'Creating…');
        api('/api/investigations/', { method: 'POST', body: payload })
          .then(function () {
            showAlert(document.getElementById('caseFormAlert'), 'Investigation created.', true);
            newForm.reset();
            toggleForm(false);
            loadCases();
            toast('Investigation created.', 'success');
          })
          .catch(function (error) {
            if (error.payload) applyFieldErrors(newForm, error.payload);
            showAlert(document.getElementById('caseFormAlert'), error.message);
          })
          .finally(function () { buttonBusy(submit, false); });
      });
    }
    loadCases();
  }

  function initInvestigationDetail() {
    if (page !== 'investigation-detail') return;
    var root = document.getElementById('investigationDetail');
    var pathParts = window.location.pathname.split('/').filter(Boolean);
    var id = (root && root.dataset.investigationId) || pathParts[1] || '';
    if (!id) {
      region('timeline', 'error');
      return;
    }

    function renderCase(payload) {
      var data = recordOf(payload, ['investigation', 'case', 'data', 'result']);
      var title = text(first(data, ['title', 'name', 'case_title']), 'Case #' + id);
      var status = statusOf(Object.keys(data).length ? data : payload);
      var assignee = text(first(data, ['assignee', 'assigned_to', 'owner']), 'Unassigned');
      var priority = text(first(data, ['priority']), 'normal');
      var description = text(first(data, ['description', 'summary']), 'No description recorded.');
      var evidence = listOf(first(data, ['media', 'media_evidence', 'evidence', 'artifacts', 'attachments']), ['items']);

      $('#caseDetailTitle').textContent = title;
      $('#caseDetailSubtitle').textContent = truncate(description, 180);
      $('#caseDetailStatus').textContent = status;
      $('#caseDetailAssignee').textContent = truncate(assignee, 14);
      $('#caseDetailPriority').textContent = priority;
      $('#caseDetailEvidenceCount').textContent = String(evidence.length);
      $('#caseDetailDescription').textContent = description;
      $('#caseDetailId').textContent = String(first(data, ['case_number', 'reference', 'id']) || id);
      $('#caseDetailCreated').textContent = dateText(first(data, ['created_at', 'date_created', 'opened_at']));
      $('#caseDetailUpdated').textContent = dateText(first(data, ['updated_at', 'modified_at']));
      var badge = $('#caseDetailBadge');
      if (badge) {
        badge.textContent = status;
        badge.className = 'status-badge ' + statusClass(status).replace('badge--', 'status-badge--');
      }

      region('evidence', evidence.length ? 'content' : 'empty', document.getElementById('detailEvidenceList'));
      var container = document.getElementById('detailEvidenceList');
      if (container) {
        container.innerHTML = evidence.map(function (item) {
          var mediaId = typeof item === 'object' && item !== null ? idOf(item) : item;
          var label = typeof item === 'object' && item !== null ? nameOf(item) : String(item);
          var mediaStatus = typeof item === 'object' && item !== null ? statusOf(item) : 'linked';
          return '<div class="evidence-item"><div class="evidence-item__head"><span>' + esc(label) + '</span><span class="badge ' + statusClass(mediaStatus) + '">' + esc(mediaStatus) + '</span></div>' +
            '<p>Media #' + esc(mediaId) + '</p><a class="btn btn--quiet btn--sm" href="/dashboard/?media=' + encodeURIComponent(mediaId) + '">Inspect analysis →</a></div>';
        }).join('');
      }

      var observations = listOf(first(data, ['observations', 'notes', 'comments']), ['items']);
      renderObservations(observations);
      var access = listOf(first(data, ['access_history', 'access_log', 'accesses']), ['items']);
      renderAccess(access);
    }

    function loadCase() {
      return api('/api/investigations/' + encodeURIComponent(id) + '/')
        .then(function (payload) { renderCase(payload); })
        .catch(function (error) {
          var subtitle = $('#caseDetailSubtitle');
          if (subtitle) subtitle.textContent = 'Case API unavailable: ' + error.message;
          region('evidence', 'error', document.getElementById('detailEvidenceList'));
        });
    }

    function renderObservations(items) {
      var list = document.getElementById('observationList');
      var empty = document.getElementById('observationEmpty');
      setVisible(empty, items.length === 0);
      if (!list) return;
      list.innerHTML = items.map(function (item) {
        if (typeof item !== 'object' || item === null) return '<li><p>' + esc(item) + '</p></li>';
        var author = text(first(item, ['author_username', 'username', 'created_by_username', 'reviewer_username', 'author', 'user', 'created_by', 'reviewer']), 'Analyst');
        var note = text(first(item, ['note', 'observation', 'comment', 'text', 'body']), '');
        var time = first(item, ['created_at', 'timestamp', 'date']);
        return '<li><strong>' + esc(author) + (time ? ' · ' + esc(dateText(time)) : '') + '</strong><p>' + esc(note) + '</p></li>';
      }).join('');
    }

    function renderAccess(items) {
      var list = document.getElementById('accessHistory');
      var empty = document.getElementById('accessEmpty');
      setVisible(empty, items.length === 0);
      if (!list) return;
      list.innerHTML = items.map(function (item) {
        if (typeof item !== 'object' || item === null) return '<li><strong>' + esc(item) + '</strong></li>';
        var actor = text(first(item, ['username', 'actor_username', 'author_username', 'user_username', 'user', 'actor', 'email']), 'Unknown user');
        var action = text(first(item, ['action', 'event', 'description']), 'Accessed case');
        var time = first(item, ['timestamp', 'created_at', 'date']);
        return '<li>' + (time ? '<time>' + esc(dateText(time)) + '</time>' : '') + '<strong>' + esc(actor) + '</strong><p>' + esc(action) + '</p></li>';
      }).join('');
    }

    function loadTimeline() {
      region('timeline', 'loading', document.getElementById('caseTimeline'));
      return api('/api/investigations/' + encodeURIComponent(id) + '/timeline/')
        .then(function (payload) {
          var items = listOf(payload, ['timeline', 'events', 'results', 'activity']);
          region('timeline', items.length ? 'content' : 'empty', document.getElementById('caseTimeline'));
          var list = document.getElementById('caseTimeline');
          if (!list) return;
          list.innerHTML = items.map(function (item) {
            if (typeof item !== 'object' || item === null) return '<li><strong>' + esc(item) + '</strong></li>';
            var title = text(first(item, ['title', 'action', 'event', 'label']), 'Case event');
            var time = first(item, ['timestamp', 'created_at', 'date', 'time']);
            var detail = text(first(item, ['description', 'detail', 'note']), '');
            return '<li>' + (time ? '<time>' + esc(dateText(time)) + '</time>' : '') + '<strong>' + esc(title) + '</strong>' + (detail ? '<p>' + esc(detail) + '</p>' : '') + '</li>';
          }).join('');
        })
        .catch(function (error) {
          var detail = $('#timelineErrorDetail');
          if (detail) detail.textContent = error.message;
          region('timeline', 'error', document.getElementById('caseTimeline'));
        });
    }

    var refreshCase = $('#refreshCaseBtn');
    if (refreshCase) refreshCase.addEventListener('click', function () { loadCase(); toast('Case record refreshed.'); });
    var refreshTimeline = $('#refreshTimelineBtn');
    if (refreshTimeline) refreshTimeline.addEventListener('click', function () { loadTimeline(); });
    var refreshObservations = $('#refreshObservationsBtn');
    if (refreshObservations) refreshObservations.addEventListener('click', function () { loadCase(); });

    var observationForm = document.getElementById('observationForm');
    if (observationForm) {
      observationForm.addEventListener('submit', function (event) {
        event.preventDefault();
        clearFieldErrors(observationForm);
        var note = $('#observationText', observationForm).value.trim();
        if (!note) {
          $('#error_note').textContent = 'Write an observation first.';
          return;
        }
        var payload = {
          note: note,
          observation: note,
          comment: note,
          author: $('#observationAuthor', observationForm).value.trim()
        };
        var submit = $('#observationSubmit');
        buttonBusy(submit, true, 'Saving…');
        api('/api/investigations/' + encodeURIComponent(id) + '/observations/', { method: 'POST', body: payload })
          .then(function () {
            showAlert(document.getElementById('observationAlert'), 'Observation added.', true);
            observationForm.reset();
            loadCase();
            loadTimeline();
            toast('Observation recorded.', 'success');
          })
          .catch(function (error) {
            if (error.payload) applyFieldErrors(observationForm, error.payload);
            showAlert(document.getElementById('observationAlert'), error.message);
          })
          .finally(function () { buttonBusy(submit, false); });
      });
    }
    loadCase();
    loadTimeline();
  }

  function initReportsList() {
    if (page !== 'reports') return;
    var form = document.getElementById('reportFilters');
    var refresh = $('#refreshReportsBtn');
    if (refresh) refresh.addEventListener('click', function () { loadReports(); });
    if (form) {
      form.addEventListener('submit', function (event) { event.preventDefault(); loadReports(); });
      var clear = $('#clearReportFilters');
      if (clear) clear.addEventListener('click', function () { form.reset(); loadReports(); });
    }

    function loadReports() {
      region('report', 'loading', document.getElementById('reportTableWrap'));
      var params = new URLSearchParams(new FormData(form || document.createElement('form')));
      return api('/api/reports/' + (params.toString() ? '?' + params.toString() : ''))
        .then(function (payload) {
          var list = listOf(payload, ['reports', 'results']);
          region('report', list.length ? 'content' : 'empty', document.getElementById('reportTableWrap'));
          var body = document.getElementById('reportTableBody');
          if (body) {
            body.innerHTML = list.map(function (item) {
              var id = idOf(item);
              var reportId = text(first(item, ['report_id', 'id']), String(id || ''));
              var url = reportDownloadPath(item, item);
              var action = url
                ? '<a class="btn btn--outline btn--sm" href="' + esc(url) + '" data-report-download data-report-name="report-' + esc(reportId) + '.pdf">Download PDF</a>'
                : '<span class="muted">Unavailable</span>';
              return '<tr><td><span class="data-table__name">Report ' + esc(reportId) + '</span><span class="data-table__sub">' + esc(text(first(item, ['media_name', 'media', 'title']), 'Evidence report')) + '</span></td>' +
                '<td>PDF</td>' +
                '<td>' + esc(dateText(first(item, ['created_at', 'generated_at']))) + '</td>' +
                '<td>' + action + '</td></tr>';
            }).join('');
          }
          var summary = $('#reportSummary');
          if (summary) summary.textContent = list.length + ' report(s) returned by API';
        })
        .catch(function (error) {
          var detail = $('#reportErrorDetail');
          if (detail) detail.textContent = error.message;
          region('report', 'error', document.getElementById('reportTableWrap'));
        });
    }
    loadReports();
  }

  function initMediaList() {
    if (page !== 'media') return;
    var form = document.getElementById('mediaFilters');
    var refresh = $('#refreshMediaLibraryBtn');
    var query = new URLSearchParams(window.location.search);
    if (form) {
      ['search', 'status', 'media_type'].forEach(function (key) {
        var field = form.elements[key];
        if (field && query.has(key)) field.value = query.get(key);
      });
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        var params = new URLSearchParams(new FormData(form));
        window.history.replaceState(null, '', '/media/' + (params.toString() ? '?' + params.toString() : ''));
        loadMediaLibrary();
      });
      var clear = $('#clearMediaFilters');
      if (clear) clear.addEventListener('click', function () {
        form.reset();
        window.history.replaceState(null, '', '/media/');
        loadMediaLibrary();
      });
    }
    if (refresh) refresh.addEventListener('click', function () { loadMediaLibrary(); });

    function updateRow(id, payload) {
      var row = $('tr[data-media-id="' + String(id).replace(/"/g, '\\"') + '"]');
      if (!row) return;
      var data = recordOf(payload, ['status', 'data', 'result']);
      var status = statusOf(Object.keys(data).length ? data : payload);
      var cell = $('[data-library-status]', row);
      if (cell) {
        cell.textContent = status;
        cell.className = 'badge ' + statusClass(status);
      }
      return status;
    }

    function loadMediaLibrary() {
      region('mediaLibrary', 'loading', document.getElementById('mediaLibraryWrap'));
      var params = new URLSearchParams(new FormData(form || document.createElement('form')));
      return api('/api/media/' + (params.toString() ? '?' + params.toString() : ''))
        .then(function (payload) {
          var list = listOf(payload, ['media', 'results']);
          region('mediaLibrary', list.length ? 'content' : 'empty', document.getElementById('mediaLibraryWrap'));
          var body = document.getElementById('mediaLibraryBody');
          if (body) {
            body.innerHTML = list.map(function (item) {
              var id = idOf(item);
              var status = statusOf(item);
              return '<tr data-media-id="' + esc(id) + '"><td><span class="data-table__name">' + esc(nameOf(item)) + '</span><span class="data-table__sub">#' + esc(id) + '</span></td>' +
                '<td>' + esc(typeOf(item)) + '</td><td><span class="badge ' + statusClass(status) + '" data-library-status>' + esc(status) + '</span></td>' +
                '<td>' + esc(dateText(first(item, ['created_at', 'uploaded_at', 'timestamp']))) + '</td>' +
                '<td><div class="row-actions"><a class="btn btn--ghost btn--sm" href="/dashboard/?media=' + encodeURIComponent(id) + '">Analyze</a>' +
                '<button class="btn btn--quiet btn--sm" type="button" data-action="status">Status</button>' +
                '<button class="btn btn--quiet btn--sm" type="button" data-action="reprocess">Reprocess</button>' +
                '<button class="btn btn--outline btn--sm" type="button" data-action="report">Report</button>' +
                '<span data-report-slot></span></div></td></tr>';
            }).join('');
          }
          var summary = $('#mediaLibrarySummary');
          if (summary) summary.textContent = list.length + ' artifact(s) returned by API';
        })
        .catch(function (error) {
          var detail = $('#mediaLibraryErrorDetail');
          if (detail) detail.textContent = error.message;
          region('mediaLibrary', 'error', document.getElementById('mediaLibraryWrap'));
        });
    }

    var body = document.getElementById('mediaLibraryBody');
    if (body) {
      body.addEventListener('click', function (event) {
        var button = event.target.closest('button[data-action]');
        if (!button) return;
        var row = button.closest('tr[data-media-id]');
        if (!row) return;
        var id = row.dataset.mediaId;
        if (button.dataset.action === 'status') {
          buttonBusy(button, true, 'Checking…');
          api('/api/media/' + encodeURIComponent(id) + '/status/')
            .then(function (payload) { toast('Status: ' + (updateRow(id, payload) || 'unknown'), 'success'); })
            .catch(function (error) { toast(error.message, 'error'); })
            .finally(function () { buttonBusy(button, false); });
        }
        if (button.dataset.action === 'reprocess') {
          buttonBusy(button, true, 'Queuing…');
          api('/api/media/' + encodeURIComponent(id) + '/reprocess/', { method: 'POST', body: {} })
            .then(function () { toast('Reprocessing requested for #' + id, 'success'); })
            .catch(function (error) { toast(error.message, 'error'); })
            .finally(function () { buttonBusy(button, false); });
        }
        if (button.dataset.action === 'report') {
          buttonBusy(button, true, 'Generating…');
          api('/api/reports/generate/' + encodeURIComponent(id) + '/', { method: 'POST' })
            .then(function (payload) {
              var report = recordOf(payload, ['report', 'data', 'result']);
              var url = reportDownloadPath(report, payload);
              var slot = $('[data-report-slot]', row);
              if (slot && url) {
                slot.innerHTML = '<a class="btn btn--quiet btn--sm" href="' + esc(url) + '" data-report-download data-report-name="report-' + esc(String(first(report, ['report_id', 'id']) || 'latest')) + '.pdf">Download PDF ↗</a>';
              } else if (slot) {
                slot.textContent = 'Report generated';
              }
              toast('PDF report generated for #' + id, 'success');
            })
            .catch(function (error) { toast(error.message, 'error'); })
            .finally(function () { buttonBusy(button, false); });
        }
      });
    }
    loadMediaLibrary();
  }

  initAuthForms();
  initSessionUI();
  initReportDownloads();
  initTopbarSearch();
  initDashboard();
  initInvestigationsList();
  initInvestigationDetail();
  initReportsList();
  initMediaList();
})();
