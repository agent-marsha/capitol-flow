/* Capitol Flow — vanilla JS, no build step.
 * Data: data/app_data.json (fetch) → falls back to data/app_data.js (window.__CAPITOL_DATA__)
 * so the site works on GitHub Pages and when opened straight from disk (file://).
 * Optional: data/fundamentals.json → data/fundamentals.js (window.__CAPITOL_FUNDAMENTALS__)
 * powers "The basics" on each stock page. If it is missing the section is simply omitted.
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
  var F = null;          // fundamentals by ticker (null until loaded; {} if unavailable)
  var O = null;          // options positioning by ticker (null until loaded; {} if unavailable)
  var TODAY = '';        // bundle generation date (YYYY-MM-DD)
  var byId = new Map();
  var byTicker = new Map();
  var nameOf = new Map();
  var signalOf = new Map(); // trade id → max politicians in any cluster containing it
  var signals = [];
  var S = {
    feed: { dir: 'all', large: false, sig: false, stocks: true, q: '', limit: 30 },
    big: { sell: 6, buy: 6 },
    bigAll: false,
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

  // Fundamentals are optional: any failure resolves to {} and never blocks the page.
  function loadFundamentals() {
    if (window.__CAPITOL_FUNDAMENTALS__) return Promise.resolve(window.__CAPITOL_FUNDAMENTALS__);
    var viaFetch = location.protocol === 'file:'
      ? Promise.reject(new Error('file://'))
      : fetch('data/fundamentals.json', { cache: 'no-cache' }).then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        });
    return viaFetch.catch(function () {
      return loadScript('data/fundamentals.js').then(function () { return window.__CAPITOL_FUNDAMENTALS__; });
    }).then(function (f) {
      return f && typeof f === 'object' && !Array.isArray(f) ? f : {};
    }).catch(function () { return {}; });
  }

  // Options are optional too: same fetch → inline-script → {} fallback chain.
  function loadOptions() {
    if (window.__CAPITOL_OPTIONS__) return Promise.resolve(window.__CAPITOL_OPTIONS__);
    var viaFetch = location.protocol === 'file:'
      ? Promise.reject(new Error('file://'))
      : fetch('data/options.json', { cache: 'no-cache' }).then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        });
    return viaFetch.catch(function () {
      return loadScript('data/options.js').then(function () { return window.__CAPITOL_OPTIONS__; });
    }).then(function (o) {
      return o && typeof o === 'object' && !Array.isArray(o) ? o : {};
    }).catch(function () { return {}; });
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
    // The Big money columns list STOCKS only. Bonds, funds, CDs and similar have no
    // ticker, so they cannot be charted or looked up — they are excluded there.
    var largeTk = large.filter(function (t) { return t.ticker; });
    var dates = T.map(function (t) { return t.txn_date; }).filter(validDate).sort();
    var span = dates.length ? md(dates[0]) + ' – ' + md(dates[dates.length - 1]) : '';

    var shownSignals = S.showAllSignals ? signals : signals.slice(0, 7);

    var html =
      '<section aria-labelledby="hero-h">' +
        '<h1 id="hero-h" class="hero-title display">Who’s selling. Who’s buying.</h1>' +
        '<p class="hero-lede">' + T.length + ' trades disclosed by members of Congress, ' + esc(span) +
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
        '<p>Stock trades with a disclosed upper bound of $100,000 or more — bonds, funds and similar instruments are left out, since they can\'t be charted. Sells and buys side by side, newest first.</p></div>' +
        '<div class="duo">' + bigCol('sell', largeTk) + bigCol('buy', largeTk) + '</div>' +
        bigChartShell(large) +
      '</section>' +

      '<section class="block" id="feed" aria-labelledby="feed-h">' +
        '<div class="sec-head"><div><div class="micro">All disclosures</div><h2 id="feed-h" class="display">The feed</h2></div>' +
        '<p>Stock trades, sales first. Tap a ticker for the chart, the trades and the news. Turn off "Stocks only" to include bonds and funds.</p></div>' +
        '<div class="controls">' +
          '<div class="seg" role="group" aria-label="Filter by direction">' +
            segBtn('all', 'All') + segBtn('sell', '▼ Sells') + segBtn('buy', '▲ Buys') +
          '</div>' +
          '<button type="button" class="chip" data-action="toggle-large" aria-pressed="' + S.feed.large + '">$100K+ only</button>' +
          '<button type="button" class="chip" data-action="toggle-sig" aria-pressed="' + S.feed.sig + '">◆ Signals only</button>' +
          '<button type="button" class="chip" data-action="toggle-stocks" aria-pressed="' + S.feed.stocks + '">Stocks only</button>' +
          '<div class="search-wrap"><label class="sr-only" for="q">Search politician, ticker or asset</label>' +
          '<input id="q" class="search" type="search" placeholder="Search politician, ticker, asset" autocomplete="off" value="' + esc(S.feed.q) + '"></div>' +
        '</div>' +
        '<div class="micro result-count" id="feed-count"></div>' +
        '<ul class="trades" id="feed-list"></ul>' +
        '<div style="margin-top:12px" id="feed-more"></div>' +
      '</section>';

    $('#app').innerHTML = html;
    renderBigChart();
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

  // ---- "Where the big money went": one bar per stock, scaled to the largest estimated total.
  var BM_TOP = 15;
  function bigMoneyRows() {
    var rows = Array.isArray(D.big_money) ? D.big_money : [];
    return rows.filter(function (r) { return r && r.ticker && (+r.total_est || 0) > 0; });
  }
  function plural(n, w) { return n + ' ' + w + (n === 1 ? '' : 's'); }

  function bigChartShell(large) {
    var rows = bigMoneyRows();
    if (!rows.length) return '';
    var buyEst = sum(rows, 'buy_est'), sellEst = sum(rows, 'sell_est');
    var lgBuys = large.filter(function (t) { return t.direction === 'buy'; });
    var lgBuysNoTk = lgBuys.filter(function (t) { return !t.ticker; }).length;
    var note = sellEst > buyEst && lgBuys.length && lgBuysNoTk * 2 > lgBuys.length
      ? '<p class="bm-note">Most large buys by politicians are bonds and funds, not single stocks (' + lgBuysNoTk + ' of ' + lgBuys.length +
        ' here have no ticker), so this chart is mostly sales.</p>'
      : '';
    return '<div class="bm" aria-labelledby="bm-h">' +
      '<div class="bm-head"><div><div class="micro">By stock · estimated</div><h3 id="bm-h" class="display">Where the big money went</h3></div>' +
        '<p>Estimated dollars from trades of $100,000 or more. Sells and buys, by stock.</p></div>' +
      '<div class="bm-legend" aria-hidden="true"><span></span><span class="bm-keys"><span><i class="sw b"></i>▲ Buys</span><span><i class="sw s"></i>▼ Sells</span></span>' +
        '<span class="bm-legend-tot">Est. total</span></div>' +
      '<p class="sr-only">Bar chart of ' + rows.length + ' stocks ranked by estimated dollar volume. Each row is a link that states the estimated total and the buy and sell split.</p>' +
      '<ol class="bm-rows" id="bm-rows"></ol>' +
      '<div class="bm-more" id="bm-more"></div>' +
      '<p class="bm-caveat"><b>All figures are estimates.</b> Disclosures only report dollar ranges (e.g. $500,001 – $1,000,000), so each trade is counted at the midpoint of its range.</p>' +
      note +
    '</div>';
  }

  function bigChartRow(r, max) {
    var b = Math.max(0, +r.buy_est || 0), s = Math.max(0, +r.sell_est || 0), tot = +r.total_est || (b + s);
    var nb = +r.n_buy || 0, ns = +r.n_sell || 0;
    var w = Math.max(1.5, tot / max * 100);
    var segs = '';
    if (b) segs += '<i class="b" style="width:' + (b / (b + s) * 100) + '%"></i>';
    if (s) segs += '<i class="s" style="width:' + (s / (b + s) * 100) + '%"></i>';
    var label = r.ticker + ': estimated ' + money(tot) + ' total. ' +
      (b ? 'Buys about ' + money(b) + ' (' + plural(nb, 'trade') + ')' : 'No large buys') + ', ' +
      (s ? 'sells about ' + money(s) + ' (' + plural(ns, 'trade') + ')' : 'no large sells') + '. Open detail.';
    return '<li><a class="bm-row" href="#/stock/' + encodeURIComponent(r.ticker) + '" aria-label="' + esc(label) + '">' +
      '<div class="bm-tk"><div class="display">' + esc(r.ticker) + '</div>' +
        '<div class="bm-meta" aria-hidden="true">' + plural(nb, 'buy') + ' · ' + plural(ns, 'sell') + '</div></div>' +
      '<div class="bm-track" aria-hidden="true"><div class="bm-bar" data-w="' + w.toFixed(2) + '">' + segs + '</div></div>' +
      '<div class="bm-v display" aria-hidden="true">' + money(tot) + '</div>' +
    '</a></li>';
  }

  function renderBigChart() {
    var list = $('#bm-rows'); if (!list) return;
    var rows = bigMoneyRows();
    var max = rows.reduce(function (m, r) { return Math.max(m, +r.total_est || 0); }, 0) || 1;
    var shown = S.bigAll ? rows : rows.slice(0, BM_TOP);
    var start = list.children.length; // only animate newly added rows
    list.insertAdjacentHTML('beforeend', shown.slice(start).map(function (r) { return bigChartRow(r, max); }).join(''));
    $('#bm-more').innerHTML = rows.length > BM_TOP
      ? '<button type="button" class="btn-ghost" data-action="bm-all" aria-expanded="' + !!S.bigAll + '">' +
          (S.bigAll ? 'Show top ' + BM_TOP : 'Show all ' + rows.length + ' stocks') + '</button>'
      : '';
    var bars = list.querySelectorAll('.bm-bar[data-w]');
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        bars.forEach(function (el) { el.style.width = el.dataset.w + '%'; el.removeAttribute('data-w'); });
      });
    });
  }

  function feedList() {
    var f = S.feed, q = f.q.trim().toLowerCase();
    return D.trades.filter(function (t) {
      if (f.dir !== 'all' && t.direction !== f.dir) return false;
      if (f.large && !t.is_large) return false;
      if (f.sig && !signalOf.has(t.id)) return false;
      // bonds, funds and CDs carry no ticker — no chart, no stock signal
      if (f.stocks && !t.ticker) return false;
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
    document.querySelectorAll('[data-action="toggle-stocks"]').forEach(function (b) { b.setAttribute('aria-pressed', String(S.feed.stocks)); });
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
        '<div id="opt-slot" class="opt-slot" data-opt-tk="' + esc(tk) + '"></div>' +
        '<section class="block d-news" aria-labelledby="news-h"><div class="micro">Around the trades</div><h3 id="news-h" class="display">The news</h3>' + newsBlock(tk, trades) + '</section>' +
      '</div>' +
      '<div id="fund-slot" data-fund-tk="' + esc(tk) + '"></div>';

    $('#app').innerHTML = html;
    document.title = tk + ' — Capitol Flow';
    window.scrollTo(0, 0);
    mountChart(tk);
    fillOptions();
    fillFundamentals();
  }

  // ------------------------------------------------------------------ options ("Options")
  // Same contract as fillFundamentals: a no-op until data lands, then fills the slot.
  function fillOptions() {
    var slot = $('#opt-slot');
    if (!slot || O === null) return;
    var html = '';
    try { html = optionsBlock(slot.getAttribute('data-opt-tk')); } catch (e) { html = ''; }
    slot.innerHTML = html;
  }

  function optCount(n) {
    n = +n || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
    if (n >= 1e4) return (n / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
    return Math.round(n).toLocaleString('en-US');
  }
  function optStrike(n) { return '$' + (+n % 1 ? (+n).toFixed(2).replace(/0$/, '') : String(+n)); }

  // The price of one contract: last trade if there is one, else the bid/ask midpoint.
  function optPrice(c) {
    if (fnum(c.price) && c.price > 0) return { v: c.price, lab: 'last' };
    if (fnum(c.bid) && fnum(c.ask) && c.ask > 0) return { v: (c.bid + c.ask) / 2, lab: 'mid' };
    return null;
  }

  function optRows(list) {
    return (Array.isArray(list) ? list : []).filter(function (c) {
      return c && fnum(c.strike) && fnum(c.oi) && c.oi >= 0;
    }).sort(function (a, b) { return a.strike - b.strike; });
  }

  var MONTH = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  // Short contract date: "DEC 18", or "DEC 18 '26" when it isn't this year.
  function optDate(s) {
    if (!validDate(s)) return '';
    var y = String(TODAY || new Date().toISOString()).slice(0, 4);
    return md(s) + (s.slice(0, 4) !== y ? " '" + s.slice(2, 4) : '');
  }
  function optDateLong(s) {
    var p = s.split('-'), y = String(TODAY || new Date().toISOString()).slice(0, 4);
    return MONTH[+p[1] - 1] + ' ' + (+p[2]) + (p[0] !== y ? ', ' + p[0] : '');
  }

  function optRow(c, side, max, tk) {
    var kind = side === 'call' ? 'call' : 'put';
    var w = max > 0 ? Math.max(2, Math.round(c.oi / max * 100)) : 0;
    var pr = optPrice(c);
    var prTxt = pr ? '$' + pr.v.toFixed(2) : '—';
    var expiry = validDate(c.expiry) ? c.expiry : null;
    var phrase = optStrike(c.strike) + ' ' + kind + (expiry ? ' expiring ' + optDateLong(expiry) : '') + ', open interest ' + Math.round(c.oi).toLocaleString('en-US') +
      (pr ? ', price ' + prTxt : '');
    var extra = [];
    if (fnum(c.volume)) extra.push('Vol ' + optCount(c.volume));
    if (fnum(c.iv)) extra.push('IV ' + c.iv.toFixed(0) + '%');
    var url = safeUrl(c.tv_url);
    var exp = validDate(expiry) ? ' expiring ' + mdy(expiry) : '';
    var link = url
      ? '<a class="opt-link" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer" aria-label="' +
          esc('Open the ' + tk + ' ' + optStrike(c.strike) + ' ' + kind + exp + ' (' + (c.symbol || '') + ') on TradingView, new tab') +
        '">TradingView ↗</a>'
      : '';
    return '<li class="opt-row ' + kind + '">' +
      '<span class="sr-only">' + esc(phrase) + '.</span>' +
      '<div class="opt-l1" aria-hidden="true">' +
        '<span class="opt-k display">' + esc(optStrike(c.strike)) + '</span>' +
        '<span class="opt-track"><i style="width:' + w + '%"></i></span>' +
        '<span class="opt-oi display" title="' + esc(Math.round(c.oi).toLocaleString('en-US')) + ' open contracts">' + esc(optCount(c.oi)) + '</span>' +
      '</div>' +
      '<div class="opt-l2">' +
        (expiry ? '<span class="opt-exp" aria-hidden="true" title="Expires ' + esc(mdy(expiry)) + '"><span class="opt-lab">Exp</span><b>' + esc(optDate(expiry)) + '</b></span>' : '') +
        '<span class="opt-px" aria-hidden="true"><span class="opt-lab">' + (pr ? pr.lab : 'price') + '</span><b>' + esc(prTxt) + '</b></span>' +
        (extra.length ? '<span class="opt-extra" aria-hidden="true">' + esc(extra.join(' · ')) + '</span>' : '') +
        link +
      '</div>' +
    '</li>';
  }

  function optCol(side, list, tk) {
    var isCall = side === 'call';
    var max = list.reduce(function (m, c) { return Math.max(m, c.oi); }, 0);
    var id = 'opt-' + side + '-h';
    return '<div class="opt-col ' + side + '" role="group" aria-labelledby="' + id + '">' +
      '<div class="opt-col-head ' + (isCall ? 'buy-ink' : 'sell-ink') + '">' +
        '<h4 id="' + id + '" class="display">' + (isCall ? 'Calls' : 'Puts') + '</h4>' +
        '<span class="micro">' + (isCall ? 'Bets it goes up' : 'Bets it goes down') + '</span>' +
      '</div>' +
      '<div class="opt-legend micro" aria-hidden="true"><span>Strike</span><span>Open interest</span></div>' +
      (list.length
        ? '<ul class="opt-rows">' + list.map(function (c) { return optRow(c, side, max, tk); }).join('') + '</ul>'
        : '<p class="empty">No open ' + (isCall ? 'calls' : 'puts') + ' listed.</p>') +
    '</div>';
  }

  function optionsBlock(tk) {
    var o = O && Object.prototype.hasOwnProperty.call(O, tk) ? O[tk] : null;
    if (!o || typeof o !== 'object') return '';
    var calls = optRows(o.top_calls), puts = optRows(o.top_puts);
    if (!calls.length && !puts.length) return '';
    var exp = validDate(o.expiry) ? o.expiry : null;
    var dte = fnum(o.dte) ? Math.round(o.dte) : (exp && D.generated ? days(String(D.generated).slice(0, 10), exp) : null);
    var cOI = fnum(o.call_oi) ? o.call_oi : sum(calls, 'oi');
    var pOI = fnum(o.put_oi) ? o.put_oi : sum(puts, 'oi');
    var pc = fnum(o.pc_ratio) ? o.pc_ratio : (cOI ? pOI / cOI : null);
    var pcRead = pc == null ? '' : pc > 1.2 ? 'More puts than calls' : pc < 0.8 ? 'More calls than puts' : 'Roughly balanced';
    var expTxt = exp ? md(exp) : '—';
    var dteTxt = dte != null ? (dte <= 0 ? 'Expires today' : plural(dte, 'day') + ' to go') : '';
    var total = cOI + pOI;
    var cons = (Array.isArray(o.expiries_considered) ? o.expiries_considered : []).filter(validDate).sort();
    var range = cons.length ? (cons.length > 1 && cons[0] !== cons[cons.length - 1]
      ? optDate(cons[0]) + ' – ' + optDate(cons[cons.length - 1]) : optDate(cons[0])) : '';

    return '<section class="block opt" aria-labelledby="opt-h">' +
      '<div class="micro">Market positioning</div><h3 id="opt-h" class="display">Options</h3>' +
      '<p class="note">Where traders have placed their bets on ' + esc(tk) + ', by strike price.</p>' +
      '<div class="opt-strip" role="list">' +
        '<div class="opt-stat" role="listitem"><div class="micro">Most active expiry</div><div class="display">' + esc(exp ? optDate(exp) : expTxt) + '</div>' + (dteTxt ? '<div class="sub">' + dteTxt + '</div>' : '') + '</div>' +
        '<div class="opt-stat" role="listitem"><div class="micro">Call vs put OI</div>' +
          '<div class="display"><span class="buy-ink">' + esc(optCount(cOI)) + '</span><span class="opt-vs">/</span><span class="sell-ink">' + esc(optCount(pOI)) + '</span></div>' +
          (total > 0 ? '<div class="split opt-split" aria-hidden="true"><i class="b" style="width:' + (cOI / total * 100).toFixed(1) + '%"></i><i class="s" style="width:' + (pOI / total * 100).toFixed(1) + '%"></i></div>' : '') +
          '<span class="sr-only">' + Math.round(cOI).toLocaleString('en-US') + ' call contracts open, ' + Math.round(pOI).toLocaleString('en-US') + ' put contracts open.</span>' +
        '</div>' +
        '<div class="opt-stat" role="listitem"><div class="micro">Put/call ratio</div><div class="display">' + (pc == null ? '—' : pc.toFixed(2)) + '</div>' +
          (pcRead ? '<div class="sub">' + pcRead + '</div>' : '') + '</div>' +
      '</div>' +
      '<p class="opt-explain">Open interest is how many contracts are still open at each strike. Big piles often act like walls — prices tend to stall there.' +
        (fnum(o.underlying) ? ' <span class="opt-under">' + esc(tk) + ' is at <b>$' + px(o.underlying) + '</b>.</span>' : '') + '</p>' +
      (range ? '<p class="opt-range">Totals cover the next few expirations (' + esc(range) + '). Each row shows its own expiration.</p>' : '') +
      '<div class="opt-cols">' + optCol('call', calls, tk) + optCol('put', puts, tk) + '</div>' +
      '<p class="opt-foot">Open interest per strike is summed across those expirations. Price is for one contract on the row\'s expiration, quoted per share (one contract covers 100 shares). Snapshot from the last data refresh.</p>' +
    '</section>';
  }

  // ------------------------------------------------------------------ fundamentals ("The basics")
  // Fills the slot for whichever ticker the slot was rendered for. Safe to call any time:
  // before the data arrives it does nothing; once it arrives it is called again.
  function fillFundamentals() {
    var slot = $('#fund-slot');
    if (!slot || F === null) return;
    var tk = slot.getAttribute('data-fund-tk');
    var f = Object.prototype.hasOwnProperty.call(F, tk) ? F[tk] : null;
    var cards = f && Array.isArray(f.cards) ? f.cards : [];
    var html = '';
    try {
      var ordered = orderCards(cards);
      var lead = ordered.filter(isStatCard).map(fundCard).filter(Boolean);
      var rest = ordered.filter(function (c) { return !isStatCard(c); }).map(fundCard).filter(Boolean);
      // The valuation pair leads, as its own group, ahead of the rest of the cards.
      if (lead.length) {
        html += '<div class="fund-lead" role="group" aria-labelledby="fund-lead-h">' +
          '<div id="fund-lead-h" class="micro fund-tag">Valuation</div>' +
          '<div class="fund-grid fund-grid-lead">' + lead.join('') + '</div></div>';
      }
      if (rest.length) html += '<div class="fund-grid">' + rest.join('') + '</div>';
    } catch (e) { html = ''; }
    if (!html) { slot.innerHTML = ''; return; }
    var name = f.name || nameOf.get(tk) || tk;
    var cik = /^\d+$/.test(f.cik || '') ? f.cik : null;
    var src = cik
      ? '<a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&amp;CIK=' + cik + '&amp;type=10-K" target="_blank" rel="noopener noreferrer">official yearly reports to the SEC ↗</a>'
      : 'official yearly reports to the SEC';
    slot.innerHTML = '<section class="block fund" aria-labelledby="fund-h">' +
      '<div class="micro">In plain English</div><h3 id="fund-h" class="display">The basics</h3>' +
      '<p class="note">' + esc(name) + '’s numbers, from its ' + src + ' (10-K).</p>' +
      html + '</section>';
  }

  // A stat card with something to show. Only these lead the section.
  function isStatCard(c) {
    return !!(c && c.chart && c.chart.type === 'stat' && c.chart.value != null && String(c.chart.value).trim());
  }

  // Stat cards first (by rank ascending; unranked after ranked), everything else after
  // in its original relative order. Stable: ties fall back to the original index.
  function orderCards(cards) {
    var rk = function (c) { return c && fnum(c.rank) ? c.rank : Infinity; };
    return cards.map(function (c, i) { return { c: c, i: i }; }).sort(function (a, b) {
      var sa = isStatCard(a.c), sb = isStatCard(b.c);
      if (sa !== sb) return sa ? -1 : 1;
      if (sa) {
        var d = rk(a.c) - rk(b.c);
        if (d && !isNaN(d)) return d;
      }
      return a.i - b.i;
    }).map(function (o) { return o.c; });
  }

  function fnum(n) { return typeof n === 'number' && isFinite(n); }

  // $478.8B, $132.2B, $73M, −$1.4B
  function bigMoney(n) {
    var a = Math.abs(n), s = n < 0 ? '−$' : '$', v, u;
    if (a >= 1e12) { v = a / 1e12; u = 'T'; }
    else if (a >= 1e9) { v = a / 1e9; u = 'B'; }
    else if (a >= 1e6) { v = a / 1e6; u = 'M'; }
    else if (a >= 1e3) { v = a / 1e3; u = 'K'; }
    else return s + Math.round(a);
    return s + (v >= 100 && u !== 'B' && u !== 'T' ? Math.round(v) : v.toFixed(1)) + u;
  }
  function fmtVal(y, unit) {
    if (unit === 'pct') return (+y).toFixed(1) + '%';
    return bigMoney(y);
  }

  function fundCard(c) {
    if (!c || !c.text) return '';
    var head = '<div class="micro fund-head"><span class="fund-emoji" aria-hidden="true">' + esc(c.emoji || '') + '</span>' + esc(c.headline || '') + '</div>';
    if (isStatCard(c)) {
      // The figure is the headline: it sits right under the card title, ahead of the words.
      return '<article class="fund-card fund-card-stat">' + head + vizStat(c.chart) +
        '<p class="fund-text">' + esc(c.text) + '</p></article>';
    }
    var viz = '';
    var ch = c.chart && typeof c.chart === 'object' ? c.chart : {};
    var pts = (Array.isArray(ch.points) ? ch.points : []).filter(function (p) { return p && p.x != null && fnum(p.y); });
    // Unknown or missing chart types fall through with no viz: the card's text still renders.
    if (pts.length) {
      try {
        if (ch.type === 'bars') viz = vizBars(pts, ch);
        else if (ch.type === 'bars2') viz = vizBars2(pts, ch, c.id);
        else if (ch.type === 'split') viz = vizSplit(pts, ch);
      } catch (e) { viz = ''; }
    }
    return '<article class="fund-card">' +
      head +
      '<p class="fund-text">' + esc(c.text) + '</p>' +
      (viz ? '<div class="fund-viz">' + (ch.label ? '<div class="micro fund-label">' + esc(ch.label) + '</div>' : '') + viz + '</div>' : '') +
    '</article>';
  }

  // stat: one big figure. Label above, value, sub below — read as one idea.
  function vizStat(ch) {
    var label = ch.label ? String(ch.label) : '';
    var value = String(ch.value).trim();
    var sub = ch.sub ? String(ch.sub) : '';
    var aria = (label ? label + ': ' : '') + value + (sub ? ' ' + sub : '');
    return '<div class="fund-stat" role="img" aria-label="' + esc(aria) + '">' +
      (label ? '<div class="micro fund-label" aria-hidden="true">' + esc(label) + '</div>' : '') +
      '<div class="display fstat-v" aria-hidden="true">' + esc(value) + '</div>' +
      (sub ? '<div class="fstat-sub" aria-hidden="true">' + esc(sub) + '</div>' : '') +
    '</div>';
  }

  var BARS_MAX = 6;   // most recent years; keeps value labels legible at 390px
  var BARS_H = 96;    // plot height in px

  function vizBars(pts, ch) {
    pts = pts.slice(-BARS_MAX);
    var maxP = 0, maxN = 0;
    pts.forEach(function (p) { if (p.y > maxP) maxP = p.y; if (-p.y > maxN) maxN = -p.y; });
    var span = maxP + maxN || 1;
    var hp = Math.round(BARS_H * maxP / span), hn = BARS_H - hp;
    if (!maxN) { hp = BARS_H; hn = 0; }
    var cols = pts.map(function (p) {
      var h = Math.max(2, Math.round(BARS_H * Math.abs(p.y) / span));
      var v = '<span class="fb-v">' + esc(fmtVal(p.y, ch.unit)) + '</span>';
      var pos = p.y >= 0
        ? v + '<i class="fb-bar" style="height:' + h + 'px"></i>'
        : '';
      var neg = p.y < 0
        ? '<i class="fb-bar neg" style="height:' + h + 'px"></i>' + v
        : '';
      return '<li class="fb-col">' +
        '<div class="fb-pos" style="height:' + (hp + 18) + 'px">' + pos + '</div>' +
        (maxN ? '<div class="fb-neg" style="height:' + (hn + 18) + 'px">' + neg + '</div>' : '') +
        '<span class="fb-x">' + esc(p.x) + '</span></li>';
    }).join('');
    var aria = pts.map(function (p) { return p.x + ': ' + fmtVal(p.y, ch.unit); }).join(', ');
    return '<ul class="fbars' + (maxN ? ' has-neg' : '') + '" role="img" aria-label="' + esc((ch.label || 'Each year') + '. ' + aria) + '">' + cols + '</ul>';
  }

  // Which bars are "good" / "bad" for a comparison. Only labels we understand get a colour.
  var GOOD_X = { 'owns': 1, 'in the bank': 1 };
  var BAD_X = { 'owes': 1 };
  var NET_X = { 'really left': 1 };
  var CLEAR = 0.10; // a gap under 10% of the larger side counts as a tie

  function vizBars2(pts, ch) {
    var key = function (p) { return String(p.x).trim().toLowerCase(); };
    var good = pts.find(function (p) { return GOOD_X[key(p)]; });
    var bad = pts.find(function (p) { return BAD_X[key(p)]; });
    var verdict = 0; // 1 good wins, -1 bad wins, 0 unclear
    if (good && bad && good.y >= 0 && bad.y >= 0) {
      var big = Math.max(good.y, bad.y);
      if (big > 0 && Math.abs(good.y - bad.y) / big >= CLEAR) verdict = good.y > bad.y ? 1 : -1;
    }
    var max = 0;
    pts.forEach(function (p) { if (Math.abs(p.y) > max) max = Math.abs(p.y); });
    max = max || 1;
    var rows = pts.map(function (p) {
      var k = key(p), cls = '';
      if (GOOD_X[k] && verdict === 1) cls = 'good';
      else if (BAD_X[k] && verdict !== 0) cls = 'bad';
      else if (NET_X[k] && Math.abs(p.y) / max >= CLEAR) cls = p.y > 0 && verdict === 1 ? 'good' : p.y < 0 ? 'bad' : '';
      var w = Math.abs(p.y) / max * 100;
      return '<li class="f2-row ' + cls + '">' +
        '<span class="f2-x">' + esc(p.x) + '</span>' +
        '<span class="f2-track"><i style="width:' + Math.max(w, p.y ? 1 : 0).toFixed(2) + '%"' + (p.y < 0 ? ' class="neg"' : '') + '></i></span>' +
        '<span class="f2-v">' + esc(fmtVal(p.y, ch.unit)) + '</span></li>';
    }).join('');
    var aria = pts.map(function (p) { return p.x + ': ' + fmtVal(p.y, ch.unit); }).join(', ');
    return '<ul class="fbars2" role="img" aria-label="' + esc((ch.label || 'Comparison') + '. ' + aria) + '">' + rows + '</ul>';
  }

  function vizSplit(pts, ch) {
    pts = pts.slice(0, 2);
    var vals = pts.map(function (p) { return Math.max(0, p.y); });
    var total = vals.reduce(function (a, b) { return a + b; }, 0);
    if (!total) return '';
    var segs = pts.map(function (p, i) {
      var w = vals[i] / total * 100;
      return w > 0 ? '<i class="fs-' + i + '" style="width:' + w.toFixed(2) + '%"></i>' : '';
    }).join('');
    var labels = pts.map(function (p, i) {
      return '<div class="fs-lab fs-lab-' + i + '"><span class="display">' + esc((vals[i] / total * 100).toFixed(1)) + '%</span><span class="micro">' + esc(p.x) + '</span></div>';
    }).join('');
    var aria = pts.map(function (p, i) { return p.x + ': ' + (vals[i] / total * 100).toFixed(1) + '%'; }).join(', ');
    return '<div role="img" aria-label="' + esc((ch.label || 'Split') + '. ' + aria) + '">' +
      '<div class="fsplit">' + segs + '</div><div class="fs-labels">' + labels + '</div></div>';
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
    else if (act === 'toggle-stocks') { S.feed.stocks = !S.feed.stocks; S.feed.limit = 30; renderFeed(); }
    else if (act === 'feed-more') { S.feed.limit += 30; renderFeed(); }
    else if (act === 'big-more') { S.big[a.dataset.v] += 10; S.dashScroll = window.scrollY; renderDashboard(); window.scrollTo(0, S.dashScroll); }
    else if (act === 'bm-all') {
      S.bigAll = !S.bigAll;
      if (!S.bigAll) {
        var ol = $('#bm-rows');
        while (ol && ol.children.length > BM_TOP) ol.removeChild(ol.lastElementChild);
      }
      renderBigChart();
      var mb = $('#bm-more button'); if (mb) mb.focus();
    }
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
    // In parallel with the main bundle; fills the section in whenever it lands.
    loadFundamentals().then(function (f) {
      F = f;
      try { fillFundamentals(); } catch (e) { /* never break the page */ }
    });
    loadOptions().then(function (o) {
      O = o;
      try { fillOptions(); } catch (e) { /* never break the page */ }
    });
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
