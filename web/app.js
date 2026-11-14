/* Capitol Flow — vanilla JS, no build step.
 * Data: data/app_data.json (fetch) → falls back to data/app_data.js (window.__CAPITOL_DATA__)
 * so the site works on GitHub Pages and when opened straight from disk (file://).
 */
(function () {
  'use strict';

  // ------------------------------------------------------------------ utils
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ESC[c]; }); }
  function safeUrl(u) { return /^https?:\/\//i.test(u || '') ? u : null; }

  var MO = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
  var DAY = 864e5;
  function pd(s) { var p = String(s).split('-'); return Date.UTC(+p[0], +p[1] - 1, +p[2]); }
  function validDate(s) { return /^\d{4}-\d{2}-\d{2}$/.test(s || ''); }
  function days(a, b) { return Math.round((pd(b) - pd(a)) / DAY); } // b - a
  function md(s) { var p = s.split('-'); return MO[+p[1] - 1] + ' ' + (+p[2]); }
  function mdy(s) { var p = s.split('-'); return MO[+p[1] - 1] + ' ' + (+p[2]) + ', ' + p[0]; }
  function ago(s) {
    var n = days(s, TODAY);
    return n <= 0 ? 'TODAY' : n === 1 ? '1D AGO' : n + 'D AGO';
  }

  function money(n) {
    n = +n || 0;
    if (n >= 1e6) { var v = n / 1e6; return '$' + (v >= 10 ? Math.round(v) : +v.toFixed(1)) + 'M'; }
    if (n >= 1e3) return '$' + Math.round(n / 1e3) + 'K';
    return '$' + Math.round(n);
  }
  function range(lo, hi) {
    if (!hi || lo === hi) return money(lo || hi);
    return money(lo) + '–' + money(hi);
  }
  function pct(x) { return (x >= 0 ? '▲ ' : '▼ ') + Math.abs(x * 100).toFixed(1) + '%'; }
  function px(n) { return n == null || isNaN(n) ? '—' : (+n).toFixed(2); }
  function stripHon(n) { return String(n || '').replace(/^Hon\.\s*/i, ''); }

  var OWNER = { Self: '', SP: 'Spouse', JT: 'Joint', DC: 'Child' };

  function assetName(t) {
    var s = String(t.asset_raw || '').replace(/\s*\[[^\]]*\]\s*/g, ' ');
    if (t.ticker) s = s.split('(' + t.ticker + ')').join(' ');
    return s.replace(/\s+/g, ' ').trim() || t.asset_raw || '';
  }

  // ------------------------------------------------------------------ state
  var D = null;          // the bundle
  var TODAY = '';        // bundle generation date (YYYY-MM-DD)
  var byId = new Map();
  var byTicker = new Map();
  var nameOf = new Map();
  var signalOf = new Map(); // trade id → max politicians in any cluster containing it
  var signals = [];
  var S = {
    feed: { dir: 'all', large: false, sig: false, q: '', limit: 30 },
    big: { sell: 6, buy: 6 },
    showAllSignals: false,
    tf: 'daily',
    chart: null,
    dashScroll: 0
  };

  // ------------------------------------------------------------------ data
  function loadScript(src) {
    return new Promise(function (res, rej) {
      var s = document.createElement('script');
      s.src = src; s.onload = res; s.onerror = function () { rej(new Error('Failed to load ' + src)); };
      document.head.appendChild(s);
    });
  }
  function loadData() {
    if (window.__CAPITOL_DATA__) return Promise.resolve(window.__CAPITOL_DATA__);
    var viaFetch = location.protocol === 'file:'
      ? Promise.reject(new Error('file://'))
      : fetch('data/app_data.json', { cache: 'no-cache' }).then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        });
    return viaFetch.catch(function () {
      return loadScript('data/app_data.js').then(function () {
        if (!window.__CAPITOL_DATA__) throw new Error('Inline data missing');
        return window.__CAPITOL_DATA__;
      });
    });
  }

  function index(d) {
    D = d;
    D.trades = D.trades || []; D.clusters = D.clusters || []; D.prices = D.prices || {}; D.news = D.news || {};
    TODAY = String(D.generated || new Date().toISOString()).slice(0, 10);

    D.trades.forEach(function (t) {
      byId.set(t.id, t);
      if (!t.ticker) return;
      if (!byTicker.has(t.ticker)) byTicker.set(t.ticker, []);
      byTicker.get(t.ticker).push(t);
      if (!nameOf.has(t.ticker)) nameOf.set(t.ticker, assetName(t));
    });
    byTicker.forEach(function (list) {
      list.sort(function (a, b) { return String(b.txn_date).localeCompare(String(a.txn_date)); });
    });

    // Cluster membership comes from each cluster's own trade list (authoritative).
    D.clusters.forEach(function (c) {
      (c.trades || []).forEach(function (id) {
        signalOf.set(id, Math.max(signalOf.get(id) || 0, c.n_politicians || 0));
      });
    });

    // One signal per ticker: the strongest window; remember how many windows fired.
    var groups = new Map();
    D.clusters.forEach(function (c) {
      if (!groups.has(c.ticker)) groups.set(c.ticker, []);
      groups.get(c.ticker).push(c);
    });
    var rank = function (a, b) {
      return (b.n_politicians - a.n_politicians) ||
        String(b.window_end).localeCompare(String(a.window_end)) ||
        (b.n_trades - a.n_trades);
    };
    signals = [];
    groups.forEach(function (list, tk) {
      list.sort(rank);
      var top = list[0];
      var lo = 0, hi = 0;
      (top.trades || []).forEach(function (id) {
        var t = byId.get(id); if (t) { lo += t.amount_low || 0; hi += t.amount_high || 0; }
      });
      signals.push(Object.assign({}, top, { windows: list.length, lo: lo, hi: hi }));
    });
    signals.sort(rank);
  }

  function hasPrices(tk) { var p = D.prices[tk]; return !!(p && p.daily && p.daily.length); }

  // Close on the first daily bar on/after a date → % move to latest close.
  function sinceTrade(tk, date) {
    var p = D.prices[tk]; if (!p || !p.daily || !p.daily.length || !validDate(date)) return null;
    var bars = p.daily, last = bars[bars.length - 1];
    for (var i = 0; i < bars.length; i++) {
      if (bars[i].t >= date) return bars[i].c ? last.c / bars[i].c - 1 : null;
    }
    return null;
  }

  // ------------------------------------------------------------------ pieces
  function dirLabel(t) {
    if (t.direction === 'sell') return '▼ SELL';
    if (t.direction === 'buy') return '▲ BUY';
    return '◆ ' + esc(String(t.txn_type_label || 'Other').toUpperCase());
  }

  function tradeRow(t, opt) {
    opt = opt || {};
    var dir = t.direction === 'sell' || t.direction === 'buy' ? t.direction : 'other';
    var cls = ['trade', dir];
    if (t.is_large) cls.push('large');
    if (t.is_very_large) cls.push('very-large');
    var date = validDate(t.txn_date) ? t.txn_date : null;
    var mo = date ? MO[+date.slice(5, 7) - 1] : '—';
    var dy = date ? +date.slice(8, 10) : '—';

    var tk;
    if (!t.ticker) {
      tk = '<span class="tk none" title="No exchange ticker — no chart available">No ticker</span>';
    } else {
      tk = '<button type="button" class="tk' + (hasPrices(t.ticker) ? '' : ' nochart') + '" data-tk="' + esc(t.ticker) +
        '" aria-label="Open ' + esc(t.ticker) + ' detail">' + esc(t.ticker) + '</button>';
    }

    var badges = '';
    if (t.is_very_large) badges += '<span class="badge vl" title="Upper bound ≥ $500,000">$500K+</span>';
    else if (t.is_large) badges += '<span class="badge lg" title="Upper bound ≥ $100,000">$100K+</span>';
    var sig = signalOf.get(t.id);
    if (sig && !opt.hideSignal) badges += '<span class="badge cl" title="Part of a multi-politician cluster">◆ SIGNAL ' + sig + 'P</span>';

    var who = [];
    who.push('<b>' + esc(stripHon(t.politician)) + '</b>');
    if (t.state_district) who.push(esc(t.state_district));
    if (OWNER[t.owner]) who.push(esc(OWNER[t.owner]));
    if (date && validDate(t.notification_date)) {
      var lag = days(date, t.notification_date);
      if (lag >= 0) who.push('filed +' + lag + 'd');
    }

    var since = '';
    if (opt.since && t.ticker && date) {
      var s = sinceTrade(t.ticker, date);
      if (s != null) since = '<div class="since ' + (s >= 0 ? 'buy-ink' : 'sell-ink') + '" title="Price change from close on trade date to latest close">' + pct(s) + ' since</div>';
    }
    var src = safeUrl(t.source_url);
    var amtText = range(t.amount_low, t.amount_high);

    return '<li class="' + cls.join(' ') + '">' +
      '<div class="t-date" title="' + (date ? mdy(date) : 'Date unknown') + '"><div class="mo">' + mo + '</div><div class="dy display">' + dy + '</div></div>' +
      '<div class="t-main">' +
        '<div class="t-line1"><span class="dir ' + dir + '">' + dirLabel(t) + '</span>' + tk + badges + '</div>' +
        '<div class="t-asset" title="' + esc(t.asset_raw) + '">' + esc(assetName(t)) + '</div>' +
        '<div class="t-who">' + who.join(' · ') + '</div>' +
      '</div>' +
      '<div class="t-amt"><div class="display" title="' + esc(t.amount_label) + '">' + amtText + '</div>' + since +
        (src ? '<a href="' + esc(src) + '" target="_blank" rel="noopener noreferrer" aria-label="Open the official filing PDF for this trade">FILING ↗</a>' : '') +
      '</div>' +
    '</li>';
  }

  function biasOf(s) {
    if (s.sells > s.buys) return { text: 'Net sell', cls: 'sell-ink' };
    if (s.buys > s.sells) return { text: 'Net buy', cls: 'buy-ink' };
    return { text: 'Split', cls: 'neutral' };
  }

  function splitBar(sells, buys) {
    var total = sells + buys || 1;
    var bar = '';
    if (sells) bar += '<i class="s" style="width:' + (sells / total * 100) + '%"></i>';
    if (buys) bar += '<i class="b" style="width:' + (buys / total * 100) + '%"></i>';
    return '<div><div class="split" role="img" aria-label="' + sells + ' sells, ' + buys + ' buys">' + bar + '</div>' +
      '<div class="split-labels"><span class="sell-ink">▼ ' + sells + ' SELL' + (sells === 1 ? '' : 'S') + '</span>' +
      '<span class="buy-ink">' + buys + ' BUY' + (buys === 1 ? '' : 'S') + ' ▲</span></div></div>';
  }

  function sigMeta(s) {
    return '<div class="sig-meta">' +
      '<div><div class="micro">Window</div><div class="v">' + md(s.window_start) + ' – ' + md(s.window_end) + '</div></div>' +
      '<div><div class="micro">Est. volume</div><div class="v">' + range(s.lo, s.hi) + '</div></div>' +
      '<div><div class="micro">Last trade</div><div class="v">' + ago(s.window_end) + '</div></div>' +
    '</div>';
  }

  function sigWho(s) {
    var more = s.windows > 1 ? ' <span>· ' + (s.windows - 1) + ' more window' + (s.windows > 2 ? 's' : '') + '</span>' : '';
    return '<div class="sig-who">' + s.politicians.map(function (p) { return '<b>' + esc(stripHon(p)) + '</b>'; }).join(', ') + more + '</div>';
  }

  function sigCard(s, i) {
    var b = biasOf(s);
    var href = '#/stock/' + encodeURIComponent(s.ticker);
    var label = s.ticker + ': ' + s.n_politicians + ' politicians, ' + s.sells + ' sells, ' + s.buys + ' buys. Open detail.';
    var name = esc(nameOf.get(s.ticker) || '');
    var count = '<div class="sig-count"><div class="display">' + s.n_politicians + '</div><div class="micro">Politicians</div></div>';
    var bias = '<span class="bias ' + b.cls + '">' + b.text + '</span>';
    if (i === 0) {
      return '<a class="sig lead" href="' + href + '" aria-label="Top signal. ' + esc(label) + '">' +
        '<div class="lead-left">' +
          '<div><span class="lead-tag">TOP SIGNAL</span></div>' +
          '<div><div class="sig-ticker display">' + esc(s.ticker) + '</div><div class="sig-name" style="margin-top:8px">' + name + '</div></div>' +
          sigWho(s) +
        '</div>' +
        '<div class="sig-top">' + count + bias + '</div>' +
        splitBar(s.sells, s.buys) +
        sigMeta(s) +
      '</a>';
    }
    return '<a class="sig" href="' + href + '" aria-label="' + esc(label) + '">' +
      '<div class="sig-top"><div class="sig-ticker display">' + esc(s.ticker) + '</div>' + count + '</div>' +
      '<div class="sig-name">' + name + '</div>' +
      '<div class="sig-top" style="align-items:center"><span class="micro">' + s.n_trades + ' trades</span>' + bias + '</div>' +
      splitBar(s.sells, s.buys) +
      sigMeta(s) +
      sigWho(s) +
    '</a>';
  }

  function sum(list, k) { return list.reduce(function (a, t) { return a + (t[k] || 0); }, 0); }

  // ------------------------------------------------------------------ dashboard
  function renderDashboard() {
    destroyChart();
    var T = D.trades;
    var sells = T.filter(function (t) { return t.direction === 'sell'; });
    var buys = T.filter(function (t) { return t.direction === 'buy'; });
    var large = T.filter(function (t) { return t.is_large; });
    var vlarge = T.filter(function (t) { return t.is_very_large; });
    var dates = T.map(function (t) { return t.txn_date; }).filter(validDate).sort();
    var span = dates.length ? md(dates[0]) + ' – ' + md(dates[dates.length - 1]) : '';

    var shownSignals = S.showAllSignals ? signals : signals.slice(0, 7);

    var html =
      '<section aria-labelledby="hero-h">' +
        '<h1 id="hero-h" class="hero-title display">Who’s selling. Who’s buying.</h1>' +
        '<p class="hero-lede">' + T.length + ' trades disclosed by members of the House, ' + esc(span) +
          '. A signal fires when two or more politicians trade the same stock within ' + (D.window_days || 14) + ' days.</p>' +
        '<div class="stats" role="list">' +
          '<div class="stat" role="listitem"><div class="micro"><span class="stat-dot" style="background:var(--sell)"></span>Sells</div><div class="display">' + sells.length + '</div><div class="sub">Est. ' + range(sum(sells, 'amount_low'), sum(sells, 'amount_high')) + '</div></div>' +
          '<div class="stat" role="listitem"><div class="micro"><span class="stat-dot" style="background:var(--buy)"></span>Buys</div><div class="display">' + buys.length + '</div><div class="sub">Est. ' + range(sum(buys, 'amount_low'), sum(buys, 'amount_high')) + '</div></div>' +
          '<div class="stat" role="listitem"><div class="micro">◆ Signals</div><div class="display">' + signals.length + '</div><div class="sub">' + D.clusters.length + ' cluster windows</div></div>' +
          '<div class="stat" role="listitem"><div class="micro">$100K+ trades</div><div class="display">' + large.length + '</div><div class="sub">' + vlarge.length + ' at $500K+</div></div>' +
        '</div>' +
      '</section>' +

      '<section class="block" id="signals" aria-labelledby="sig-h">' +
        '<div class="sec-head"><div><div class="micro">◆ Cluster signals</div><h2 id="sig-h" class="display">Same stock. Many hands.</h2></div>' +
        '<p>Two or more politicians trading one ticker inside a ' + (D.window_days || 14) + '-day window. Ranked by how many politicians moved, then recency.</p></div>' +
        (signals.length
          ? '<div class="signals">' + shownSignals.map(sigCard).join('') + '</div>' +
            (signals.length > 7 ? '<div class="sig-more"><button type="button" class="btn-ghost" data-action="toggle-signals">' +
              (S.showAllSignals ? 'Show top signals' : 'Show all ' + signals.length + ' signals') + '</button></div>' : '')
          : '<p class="empty">No multi-politician clusters in this window.</p>') +
      '</section>' +

      '<section class="block" id="big" aria-labelledby="big-h">' +
        '<div class="sec-head"><div><div class="micro">$100K and up</div><h2 id="big-h" class="display">Big money</h2></div>' +
        '<p>Every trade with a disclosed upper bound of $100,000 or more. Sells and buys side by side, newest first.</p></div>' +
        '<div class="duo">' + bigCol('sell', large) + bigCol('buy', large) + '</div>' +
      '</section>' +

      '<section class="block" id="feed" aria-labelledby="feed-h">' +
        '<div class="sec-head"><div><div class="micro">All disclosures</div><h2 id="feed-h" class="display">The feed</h2></div>' +
        '<p>Sales lead, newest first, then purchases. Tap a ticker for the chart, the trades and the news.</p></div>' +
        '<div class="controls">' +
          '<div class="seg" role="group" aria-label="Filter by direction">' +
            segBtn('all', 'All') + segBtn('sell', '▼ Sells') + segBtn('buy', '▲ Buys') +
          '</div>' +
          '<button type="button" class="chip" data-action="toggle-large" aria-pressed="' + S.feed.large + '">$100K+ only</button>' +
          '<button type="button" class="chip" data-action="toggle-sig" aria-pressed="' + S.feed.sig + '">◆ Signals only</button>' +
          '<div class="search-wrap"><label class="sr-only" for="q">Search politician, ticker or asset</label>' +
          '<input id="q" class="search" type="search" placeholder="Search politician, ticker, asset" autocomplete="off" value="' + esc(S.feed.q) + '"></div>' +
        '</div>' +
        '<div class="micro result-count" id="feed-count"></div>' +
        '<ul class="trades" id="feed-list"></ul>' +
        '<div style="margin-top:12px" id="feed-more"></div>' +
      '</section>';

    $('#app').innerHTML = html;
    renderFeed();
    document.title = 'Capitol Flow — Politician Trade Signals';
  }

  function segBtn(v, label) {
    return '<button type="button" data-action="dir" data-v="' + v + '" aria-pressed="' + (S.feed.dir === v) + '">' + label + '</button>';
  }

  function bigCol(dir, large) {
    var list = large.filter(function (t) { return t.direction === dir; })
      .sort(function (a, b) { return String(b.txn_date).localeCompare(String(a.txn_date)) || (b.amount_high - a.amount_high); });
    var n = S.big[dir];
    var head = '<div class="duo-head ' + dir + '-ink"><h3 class="display">' + (dir === 'sell' ? '▼ Sells' : '▲ Buys') +
      '</h3><span class="display">' + list.length + '</span></div>';
    var body = list.length
      ? '<ul class="trades">' + list.slice(0, n).map(function (t) { return tradeRow(t); }).join('') + '</ul>'
      : '<p class="empty">None in this window.</p>';
    var more = list.length > n
      ? '<div style="margin-top:8px"><button type="button" class="btn-ghost" data-action="big-more" data-v="' + dir + '">Show ' + Math.min(10, list.length - n) + ' more ' + (dir === 'sell' ? 'sells' : 'buys') + '</button></div>'
      : '';
    return '<div>' + head + body + more + '</div>';
  }

  function feedList() {
    var f = S.feed, q = f.q.trim().toLowerCase();
    return D.trades.filter(function (t) {
      if (f.dir !== 'all' && t.direction !== f.dir) return false;
      if (f.large && !t.is_large) return false;
      if (f.sig && !signalOf.has(t.id)) return false;
      if (q) {
        var hay = (t.politician + ' ' + (t.ticker || '') + ' ' + t.asset_raw + ' ' + (t.state_district || '')).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
  }

  function renderFeed() {
    var list = feedList();
    var shown = list.slice(0, S.feed.limit);
    $('#feed-list').innerHTML = shown.length ? shown.map(function (t) { return tradeRow(t); }).join('') : '<li class="empty">No trades match.</li>';
    $('#feed-count').textContent = 'Showing ' + shown.length + ' of ' + list.length + ' trades';
    $('#feed-more').innerHTML = list.length > shown.length
      ? '<button type="button" class="btn-ghost" data-action="feed-more">Show ' + Math.min(30, list.length - shown.length) + ' more</button>' : '';
    document.querySelectorAll('[data-action="dir"]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.v === S.feed.dir)); });
    document.querySelectorAll('[data-action="toggle-large"]').forEach(function (b) { b.setAttribute('aria-pressed', String(S.feed.large)); });
    document.querySelectorAll('[data-action="toggle-sig"]').forEach(function (b) { b.setAttribute('aria-pressed', String(S.feed.sig)); });
  }

  // ------------------------------------------------------------------ detail
  function renderDetail(tk) {
    destroyChart();
    var trades = byTicker.get(tk) || [];
    var p = D.prices[tk] || {};
    var daily = p.daily || [];
    if (!trades.length && !daily.length) {
      $('#app').innerHTML = '<button type="button" class="back" data-action="back">← BACK</button>' +
        '<p class="empty">No trades or prices found for ' + esc(tk) + '.</p>';
      return;
    }
    var sells = trades.filter(function (t) { return t.direction === 'sell'; });
    var buys = trades.filter(function (t) { return t.direction === 'buy'; });
    var pols = new Set(trades.map(function (t) { return t.politician; }));
    var sig = signals.find(function (s) { return s.ticker === tk; });

    var priceBlock = '';
    if (daily.length) {
      var last = daily[daily.length - 1], prev = daily[daily.length - 2];
      var chg = prev ? last.c - prev.c : 0, chgP = prev && prev.c ? chg / prev.c : 0;
      priceBlock = '<div class="d-price"><div class="micro">Last close · ' + esc(md(last.t)) + '</div>' +
        '<div class="display">$' + px(last.c) + '</div>' +
        (prev ? '<div class="chg ' + (chg >= 0 ? 'buy-ink' : 'sell-ink') + '">' + (chg >= 0 ? '+' : '−') + Math.abs(chg).toFixed(2) + ' (' + pct(chgP) + ') day</div>' : '') +
        '</div>';
    }

    var html =
      '<button type="button" class="back" data-action="back" aria-label="Back to dashboard">← ALL SIGNALS</button>' +
      '<section class="d-hero" aria-labelledby="d-h">' +
        '<div><div class="micro">' + (sig ? '◆ Signal · ' + sig.n_politicians + ' politicians in ' + (D.window_days || 14) + ' days' : 'Stock detail') + '</div>' +
          '<h1 id="d-h" class="d-ticker display">' + esc(tk) + '</h1>' +
          '<div class="d-name">' + esc(nameOf.get(tk) || '') + '</div></div>' +
        priceBlock +
      '</section>' +
      '<div class="stats d-stats" role="list">' +
        '<div class="stat" role="listitem"><div class="micro">Politicians</div><div class="display">' + pols.size + '</div></div>' +
        '<div class="stat" role="listitem"><div class="micro"><span class="stat-dot" style="background:var(--sell)"></span>Sells</div><div class="display">' + sells.length + '</div><div class="sub">Est. ' + range(sum(sells, 'amount_low'), sum(sells, 'amount_high')) + '</div></div>' +
        '<div class="stat" role="listitem"><div class="micro"><span class="stat-dot" style="background:var(--buy)"></span>Buys</div><div class="display">' + buys.length + '</div><div class="sub">Est. ' + range(sum(buys, 'amount_low'), sum(buys, 'amount_high')) + '</div></div>' +
        '<div class="stat" role="listitem"><div class="micro">Last trade</div><div class="display">' + (trades[0] && validDate(trades[0].txn_date) ? md(trades[0].txn_date) : '—') + '</div><div class="sub">' + (trades[0] && validDate(trades[0].txn_date) ? ago(trades[0].txn_date) : '') + '</div></div>' +
      '</div>' +

      '<section class="chart-card" aria-label="' + esc(tk) + ' candlestick chart with Bollinger Bands">' +
        '<div class="chart-bar">' +
          '<div class="seg" role="group" aria-label="Chart timeframe">' +
            '<button type="button" data-action="tf" data-v="daily" aria-pressed="' + (S.tf === 'daily') + '">Daily</button>' +
            '<button type="button" data-action="tf" data-v="hourly" aria-pressed="' + (S.tf === 'hourly') + '">Hourly</button>' +
          '</div>' +
          '<div class="readout" id="readout" aria-live="off"></div>' +
        '</div>' +
        '<div class="chart" id="chart"></div>' +
        '<div class="legend" aria-label="Chart legend">' +
          '<span><i class="sw-up"></i>Up candle (hollow)</span><span><i class="sw-dn"></i>Down candle (filled)</span>' +
          '<span><i class="sw-line"></i>Upper / lower band</span><span><i class="sw-line mid"></i>SMA 20</span>' +
          '<span><b class="sell-ink">▼S</b> politician sale</span><span><b class="buy-ink">▲B</b> politician buy</span>' +
        '</div>' +
        '<div class="chart-note" id="chart-note"></div>' +
        '<details class="table"><summary>VIEW PRICE DATA TABLE</summary><div class="scroll" id="chart-table"></div></details>' +
      '</section>' +

      '<div class="d-cols">' +
        '<section class="block" aria-labelledby="who-h"><div class="micro">Who traded ' + esc(tk) + '</div><h3 id="who-h" class="display">The trades</h3>' +
          (trades.length ? '<ul class="trades">' + trades.map(function (t) { return tradeRow(t, { since: true }); }).join('') + '</ul>' : '<p class="empty">No disclosed trades.</p>') +
        '</section>' +
        '<section class="block" aria-labelledby="news-h"><div class="micro">Around the trades</div><h3 id="news-h" class="display">The news</h3>' + newsBlock(tk, trades) + '</section>' +
      '</div>';

    $('#app').innerHTML = html;
    document.title = tk + ' — Capitol Flow';
    window.scrollTo(0, 0);
    mountChart(tk);
  }

  function newsBlock(tk, trades) {
    var items = (D.news[tk] || []).slice();
    if (!items.length) return '<p class="note">No headlines in this data bundle for ' + esc(tk) + '.</p>';
    var tdates = trades.filter(function (t) { return validDate(t.txn_date); });
    var anyDated = false;
    var rows = items.map(function (a, i) {
      var r = { a: a, i: i, near: null };
      if (validDate(a.date)) {
        anyDated = true;
        var best = null;
        tdates.forEach(function (t) {
          var d = days(t.txn_date, a.date);
          if (!best || Math.abs(d) < Math.abs(best.d)) best = { d: d, t: t };
        });
        if (best && Math.abs(best.d) <= 7) r.near = best;
        r.dist = best ? Math.abs(best.d) : 1e9;
      }
      return r;
    });
    rows.sort(function (x, y) {
      if (!!x.near !== !!y.near) return x.near ? -1 : 1;
      if (x.near && y.near) return x.dist - y.dist;
      var xd = validDate(x.a.date), yd = validDate(y.a.date);
      if (xd && yd) return y.a.date.localeCompare(x.a.date);
      if (xd !== yd) return xd ? -1 : 1;
      return x.i - y.i;
    });
    var note = anyDated
      ? '<p class="note">Headlines published within 7 days of a politician’s trade are flagged and listed first.</p>'
      : '<p class="note">This data refresh didn’t include publish dates, so headlines can’t be matched to trade dates yet. Showing the latest ' + esc(tk) + ' coverage.</p>';
    return note + '<ul class="news">' + rows.map(function (r) {
      var a = r.a, url = safeUrl(a.url);
      var meta = '<span class="micro">' + esc(a.publisher || 'Source') + '</span>' +
        '<span class="micro">' + (validDate(a.date) ? esc(mdy(a.date)) : 'Undated') + '</span>';
      if (r.near) {
        var d = r.near.d, t = r.near.t;
        var when = d === 0 ? 'Same day as' : Math.abs(d) + 'D ' + (d > 0 ? 'after' : 'before');
        meta = '<span class="near-tag">' + esc((when + ' ' + (t.direction === 'sell' ? 'sale' : t.direction === 'buy' ? 'buy' : 'trade') + ' · ' + stripHon(t.politician)).toUpperCase()) + '</span>' + meta;
      }
      var inner = '<div class="n-title">' + esc(a.title) + '</div><div class="n-meta">' + meta + '</div>';
      return '<li class="' + (r.near ? 'near' : '') + '">' +
        (url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + inner + '<span class="sr-only"> (opens in new tab)</span></a>' : '<a>' + inner + '</a>') +
        '</li>';
    }).join('') + '</ul>';
  }

  // ------------------------------------------------------------------ chart
  var etFmt = null;
  try {
    etFmt = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' });
  } catch (e) { etFmt = null; }
  // lightweight-charts renders UTCTimestamps as UTC; shift to US/Eastern wall-clock so bars read 9:30, 10:30…
  function toET(sec) {
    if (!etFmt) return sec;
    var p = {};
    etFmt.formatToParts(new Date(sec * 1000)).forEach(function (x) { p[x.type] = x.value; });
    return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second) / 1000;
  }
  function barDate(time) { return typeof time === 'string' ? time : new Date(time * 1000).toISOString().slice(0, 10); }
  function barLabel(time) {
    if (typeof time === 'string') return mdy(time);
    var iso = new Date(time * 1000).toISOString();
    return md(iso.slice(0, 10)) + ' ' + iso.slice(11, 16) + ' ET';
  }

  // Bollinger Bands — SMA(n) ± k·σ (population σ, the standard definition).
  function bollinger(closes, n, k) {
    n = n || 20; k = k || 2;
    var out = new Array(closes.length);
    for (var i = 0; i < closes.length; i++) {
      if (i < n - 1) { out[i] = null; continue; }
      var s = 0, j;
      for (j = i - n + 1; j <= i; j++) s += closes[j];
      var m = s / n, v = 0;
      for (j = i - n + 1; j <= i; j++) v += (closes[j] - m) * (closes[j] - m);
      var sd = Math.sqrt(v / n);
      out[i] = { mid: m, upper: m + k * sd, lower: m - k * sd };
    }
    return out;
  }

  function getBars(tk, tf) {
    var p = D.prices[tk] || {};
    var raw = (tf === 'hourly' ? p.hourly : p.daily) || [];
    var bars = [], lastT = null;
    raw.forEach(function (b) {
      if ([b.o, b.h, b.l, b.c].some(function (x) { return x == null || isNaN(x); })) return;
      var time = tf === 'hourly' ? toET(+b.t) : String(b.t);
      if (lastT !== null && !(time > lastT)) return; // strictly ascending, no dupes
      lastT = time;
      bars.push({ time: time, open: +b.o, high: +b.h, low: +b.l, close: +b.c });
    });
    return bars;
  }

  function tradeMarkers(trades, bars) {
    var dates = bars.map(function (b) { return barDate(b.time); });
    var agg = new Map(), outside = 0;
    trades.forEach(function (t) {
      if ((t.direction !== 'buy' && t.direction !== 'sell') || !validDate(t.txn_date)) return;
      var idx = -1;
      for (var i = 0; i < dates.length; i++) { if (dates[i] >= t.txn_date) { idx = i; break; } }
      if (idx === -1 || t.txn_date < dates[0] || days(t.txn_date, dates[idx]) > 4) { outside++; return; }
      var key = idx + ':' + t.direction;
      agg.set(key, { idx: idx, dir: t.direction, n: (agg.has(key) ? agg.get(key).n : 0) + 1 });
    });
    var markers = [];
    agg.forEach(function (m) {
      var sell = m.dir === 'sell';
      markers.push({
        time: bars[m.idx].time, position: sell ? 'aboveBar' : 'belowBar',
        color: sell ? '#FF5000' : '#00C805', shape: sell ? 'arrowDown' : 'arrowUp',
        text: (m.n > 1 ? m.n : '') + (sell ? 'S' : 'B'), _i: m.idx
      });
    });
    markers.sort(function (a, b) { return a._i - b._i; });
    markers.forEach(function (m) { delete m._i; });
    return { markers: markers, outside: outside };
  }

  function addSeries(chart, LW, type, opts) {
    if (typeof chart.addSeries === 'function' && LW[type + 'Series']) return chart.addSeries(LW[type + 'Series'], opts); // v5
    return chart['add' + type + 'Series'](opts); // v4
  }
  function setMarkers(LW, series, markers) {
    if (typeof LW.createSeriesMarkers === 'function') return LW.createSeriesMarkers(series, markers); // v5
    if (typeof series.setMarkers === 'function') series.setMarkers(markers); // v4
  }

  function destroyChart() {
    if (S.chart) { try { S.chart.remove(); } catch (e) { /* already gone */ } S.chart = null; }
  }

  function chartEmpty(el, title, msg) {
    el.innerHTML = '<div class="chart-empty"><div><span class="display">' + esc(title) + '</span>' + esc(msg) + '</div></div>';
  }

  function mountChart(tk) {
    destroyChart();
    var el = $('#chart'); if (!el) return;
    el.innerHTML = '';
    $('#readout').innerHTML = '';
    $('#chart-table').innerHTML = '';
    var tf = S.tf;
    var bars = getBars(tk, tf);
    var trades = byTicker.get(tk) || [];
    var noteEl = $('#chart-note');

    if (!bars.length) {
      chartEmpty(el, hasPrices(tk) ? 'No ' + tf + ' prices' : 'No price data', hasPrices(tk)
        ? 'This data bundle has no ' + tf + ' price history for ' + tk + '. The trades and news below still apply.'
        : 'No price history for ' + tk + '.');
      noteEl.textContent = '';
      return;
    }

    var bb = bollinger(bars.map(function (b) { return b.close; }), 20, 2);
    var mk = tradeMarkers(trades, bars);
    var notes = ['Bollinger Bands: 20-period SMA ± 2σ, computed in your browser from the ' + tf + ' closes.'];
    if (tf === 'hourly') notes.push('Hourly times are US Eastern.');
    if (mk.outside) notes.push(mk.outside + ' trade' + (mk.outside === 1 ? '' : 's') + ' fall outside this ' + tf + ' range' + (tf === 'hourly' ? ' — switch to Daily to see ' + (mk.outside === 1 ? 'it' : 'them') : '') + '.');
    noteEl.textContent = notes.join(' ');

    // Accessible table view (latest 30 bars).
    var rows = [];
    for (var i = bars.length - 1; i >= Math.max(0, bars.length - 30); i--) {
      var b = bars[i], x = bb[i];
      rows.push('<tr><td>' + esc(barLabel(b.time)) + '</td><td>' + px(b.open) + '</td><td>' + px(b.high) + '</td><td>' + px(b.low) + '</td><td>' + px(b.close) +
        '</td><td>' + (x ? px(x.upper) : '—') + '</td><td>' + (x ? px(x.mid) : '—') + '</td><td>' + (x ? px(x.lower) : '—') + '</td></tr>');
    }
    $('#chart-table').innerHTML = '<table><thead><tr><th scope="col">' + (tf === 'hourly' ? 'Time' : 'Date') + '</th><th scope="col">Open</th><th scope="col">High</th><th scope="col">Low</th><th scope="col">Close</th><th scope="col">BB upper</th><th scope="col">SMA 20</th><th scope="col">BB lower</th></tr></thead><tbody>' + rows.join('') + '</tbody></table>';

    var LW = window.LightweightCharts;
    if (!LW || typeof LW.createChart !== 'function') {
      chartEmpty(el, 'Chart offline', 'The charting library could not load. Open the price data table below.');
      return;
    }

    var chart = LW.createChart(el, {
      autoSize: true,
      layout: { background: { type: 'solid', color: '#151517' }, textColor: '#8E8E93', fontSize: 11,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif', attributionLogo: false },
      grid: { vertLines: { color: '#1C1C1F' }, horzLines: { color: '#1C1C1F' } },
      rightPriceScale: { borderColor: '#242427', scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { borderColor: '#242427', timeVisible: tf === 'hourly', secondsVisible: false, rightOffset: 4 },
      crosshair: { mode: 0,
        vertLine: { color: '#5A5A60', labelBackgroundColor: '#34343A' },
        horzLine: { color: '#5A5A60', labelBackgroundColor: '#34343A' } },
      handleScroll: { vertTouchDrag: false }
    });
    S.chart = chart;

    var line = { lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
    var upper = addSeries(chart, LW, 'Line', Object.assign({ color: '#8E8E93' }, line));
    var lower = addSeries(chart, LW, 'Line', Object.assign({ color: '#8E8E93' }, line));
    var mid = addSeries(chart, LW, 'Line', Object.assign({ color: '#C7C7CC', lineStyle: 2 }, line));
    var candles = addSeries(chart, LW, 'Candlestick', {
      upColor: 'rgba(0,0,0,0)', downColor: '#FF5000', borderVisible: true,
      borderUpColor: '#00C805', borderDownColor: '#FF5000', wickUpColor: '#00C805', wickDownColor: '#FF5000',
      priceLineColor: '#5A5A60'
    });
    candles.setData(bars);
    var pick = function (k) {
      var out = [];
      bars.forEach(function (b, i) { if (bb[i]) out.push({ time: b.time, value: bb[i][k] }); });
      return out;
    };
    upper.setData(pick('upper')); lower.setData(pick('lower')); mid.setData(pick('mid'));
    if (mk.markers.length) setMarkers(LW, candles, mk.markers);

    var idxOf = new Map(bars.map(function (b, i) { return [b.time, i]; }));
    var readout = $('#readout');
    var show = function (i) {
      var b = bars[i], x = bb[i], p = bars[i - 1];
      var ch = p ? b.close / p.close - 1 : null;
      readout.innerHTML = '<span><b>' + esc(barLabel(b.time)) + '</b></span>' +
        '<span>O <b>' + px(b.open) + '</b></span><span>H <b>' + px(b.high) + '</b></span>' +
        '<span>L <b>' + px(b.low) + '</b></span><span>C <b>' + px(b.close) + '</b></span>' +
        (ch != null ? '<span class="' + (ch >= 0 ? 'buy-ink' : 'sell-ink') + '">' + pct(ch) + '</span>' : '') +
        (x ? '<span>BB <b>' + px(x.upper) + '</b> / <b>' + px(x.mid) + '</b> / <b>' + px(x.lower) + '</b></span>' : '');
    };
    show(bars.length - 1);
    chart.subscribeCrosshairMove(function (param) {
      var i = param && param.time !== undefined ? idxOf.get(param.time) : undefined;
      show(i === undefined ? bars.length - 1 : i);
    });

    if (tf === 'hourly' && bars.length > 160) {
      chart.timeScale().setVisibleLogicalRange({ from: bars.length - 160, to: bars.length + 3 });
    } else {
      chart.timeScale().fitContent();
    }
  }

  // ------------------------------------------------------------------ routing & events
  function currentTicker() {
    var m = location.hash.match(/^#\/stock\/(.+)$/);
    return m ? decodeURIComponent(m[1]) : null;
  }
  var lastRoute = null;
  function route() {
    var tk = currentTicker();
    if (tk) {
      if (lastRoute === null || lastRoute === 'dash') S.dashScroll = window.scrollY;
      lastRoute = 'stock:' + tk;
      renderDetail(tk);
    } else {
      var wasDetail = lastRoute && lastRoute !== 'dash';
      lastRoute = 'dash';
      renderDashboard();
      if (wasDetail) window.scrollTo(0, S.dashScroll);
    }
  }

  function onClick(e) {
    var tkBtn = e.target.closest('[data-tk]');
    if (tkBtn) { location.hash = '#/stock/' + encodeURIComponent(tkBtn.dataset.tk); return; }
    var a = e.target.closest('[data-action]');
    if (!a) return;
    var act = a.dataset.action;
    if (act === 'back') { location.hash = '#/'; }
    else if (act === 'dir') { S.feed.dir = a.dataset.v; S.feed.limit = 30; renderFeed(); }
    else if (act === 'toggle-large') { S.feed.large = !S.feed.large; S.feed.limit = 30; renderFeed(); }
    else if (act === 'toggle-sig') { S.feed.sig = !S.feed.sig; S.feed.limit = 30; renderFeed(); }
    else if (act === 'feed-more') { S.feed.limit += 30; renderFeed(); }
    else if (act === 'big-more') { S.big[a.dataset.v] += 10; S.dashScroll = window.scrollY; renderDashboard(); window.scrollTo(0, S.dashScroll); }
    else if (act === 'toggle-signals') {
      S.showAllSignals = !S.showAllSignals; renderDashboard();
      if (!S.showAllSignals) { var el = $('#signals'); if (el) el.scrollIntoView(); }
    }
    else if (act === 'tf') {
      if (S.tf === a.dataset.v) return;
      S.tf = a.dataset.v;
      document.querySelectorAll('[data-action="tf"]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.v === S.tf)); });
      var tk = currentTicker(); if (tk) mountChart(tk);
    }
  }

  var qTimer = null;
  function onInput(e) {
    if (e.target.id !== 'q') return;
    clearTimeout(qTimer);
    var v = e.target.value;
    qTimer = setTimeout(function () { S.feed.q = v; S.feed.limit = 30; renderFeed(); }, 120);
  }

  function boot() {
    loadData().then(function (d) {
      index(d);
      var g = String(D.generated || '');
      $('#updated').innerHTML = g ? 'Updated <b>' + esc(md(g.slice(0, 10))) + '</b><span class="utc"> · ' + esc(g.slice(11, 16)) + ' UTC</span>' : '';
      $('#source-note').innerHTML = 'Source: ' + esc(D.source || 'Official disclosures') +
        '. Prices &amp; headlines are snapshots from the last data refresh. Charts by <a href="https://www.tradingview.com/lightweight-charts/" target="_blank" rel="noopener noreferrer">TradingView Lightweight Charts</a>.';
      var app = $('#app');
      app.addEventListener('click', onClick);
      app.addEventListener('input', onInput);
      window.addEventListener('hashchange', route);
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && currentTicker()) location.hash = '#/';
      });
      route();
    }).catch(function (err) {
      $('#app').innerHTML = '<div class="loading"><span class="display">Data unavailable</span><p class="note">' + esc(err && err.message) +
        '. Serve the site over HTTP (python3 -m http.server) or make sure web/data/app_data.js exists.</p></div>';
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
