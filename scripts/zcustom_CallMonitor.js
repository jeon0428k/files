/* utils.js - Call Monitor Utility (ES6 Proxy if available, else ES5 wrap fallback)
 * Usage (browser):
 *   <script src="utils.js"></script>
 *   CallMonitor.install({ logArgs: true });
 *   // ... do something ...
 *   CallMonitor.uninstall();
 */
(function (root) {
  'use strict';

  var DEFAULT_CFG = {
    enabled: true,
    prefix: '[CALL]',
    logArgs: false,
    trace: false,
    maxDepth: 8,             // ES5 recursion depth
    maxGlobals: 5000,        // window scan safety limit
    excludeGlobalName: /^(webkit|moz|ms|on|__|chrome|safari|google|webkitStorageInfo$)/i,
    excludeObjectName: /^(window|document|location|navigator|history|console|localStorage|sessionStorage|indexedDB)$/i,
    includeOnly: null         // RegExp or null. If set, only logs matching names.
  };

  function shallowCopy(dst, src) {
    var k;
    for (k in src) if (Object.prototype.hasOwnProperty.call(src, k)) dst[k] = src[k];
    return dst;
  }

  function safeConsoleTrace() {
    try { if (root.console && root.console.trace) root.console.trace(); } catch (e) {}
  }

  function now() {
    try { return Date.now ? Date.now() : +new Date(); } catch (e) { return +new Date(); }
  }

  function isProbablyDOM(obj) {
    try {
      if (!obj) return false;
      if (obj === root || obj === root.document) return true;
      if (typeof root.Node !== 'undefined' && obj instanceof root.Node) return true;
      if (obj.nodeType && typeof obj.nodeType === 'number') return true;
      if (root.document && (obj === root.document.documentElement || obj === root.document.body)) return true;
      return false;
    } catch (e) {
      return true;
    }
  }

  function canWriteProperty(obj, key) {
    try {
      var d = Object.getOwnPropertyDescriptor(obj, key);
      if (!d) return true;
      if (d.set) return true;
      return !!d.writable;
    } catch (e) {
      return false;
    }
  }

  function supportsProxyES6() {
    try {
      if (typeof root.Proxy !== 'function' || typeof root.Reflect !== 'object') return false;
      // Check ES6 syntax support
      /* eslint no-new-func: "off" */
      new Function('let a=1; const b=2; return (()=>a+b)();');
      return true;
    } catch (e) {
      return false;
    }
  }

  function makeLogger(state) {
    return function logCall(name, argsLike) {
      if (!state.cfg.enabled) return;

      if (state.cfg.includeOnly && !state.cfg.includeOnly.test(name)) return;

      try {
        if (state.cfg.logArgs) {
          var arr = [];
          if (argsLike && typeof argsLike.length === 'number') {
            for (var i = 0; i < argsLike.length; i++) arr.push(argsLike[i]);
          }
          root.console.log(state.cfg.prefix, name, arr);
        } else {
          root.console.log(state.cfg.prefix, name);
        }
        if (state.cfg.trace) safeConsoleTrace();
      } catch (e) {}
    };
  }

  function createState(cfg) {
    var state = {
      cfg: shallowCopy(shallowCopy({}, DEFAULT_CFG), cfg || {}),
      mode: null, // "es6" | "es5"
      installed: false,
      originals: {
        // patched function originals
        fetch: null,
        setTimeout: null,
        setInterval: null,
        addEventListener: null, // EventTarget.prototype.addEventListener
        xhrOpen: null,
        xhrSend: null
      },
      // ES5: restore wrappers
      wrapped: [], // { obj, key, original }
      // ES6: restore globals swapped with proxies
      proxiedGlobals: [], // { key, original }
      // ES6: proxy cache
      proxyCache: null,
      log: null,
      installTime: now()
    };
    state.log = makeLogger(state);
    return state;
  }

  function hookCommonEntrypoints(state) {
    // fetch
    try {
      if (typeof root.fetch === 'function') {
        if (!state.originals.fetch) state.originals.fetch = root.fetch;
        if (!root.fetch.__cm_hooked__) {
          var origFetch = state.originals.fetch;
          root.fetch = function () {
            state.log('fetch', arguments);
            return origFetch.apply(this, arguments);
          };
          root.fetch.__cm_hooked__ = true;
        }
      }
    } catch (e) {}

    // setTimeout
    try {
      if (typeof root.setTimeout === 'function') {
        if (!state.originals.setTimeout) state.originals.setTimeout = root.setTimeout;
        if (!root.setTimeout.__cm_hooked__) {
          var _st = state.originals.setTimeout;
          root.setTimeout = function (fn, t) {
            if (typeof fn === 'function') {
              var name = 'setTimeout -> ' + (fn.name || 'anonymous');
              return _st.call(this, function () {
                state.log(name, arguments);
                return fn.apply(this, arguments);
              }, t);
            }
            return _st.apply(this, arguments);
          };
          root.setTimeout.__cm_hooked__ = true;
        }
      }
    } catch (e) {}

    // setInterval
    try {
      if (typeof root.setInterval === 'function') {
        if (!state.originals.setInterval) state.originals.setInterval = root.setInterval;
        if (!root.setInterval.__cm_hooked__) {
          var _si = state.originals.setInterval;
          root.setInterval = function (fn, t) {
            if (typeof fn === 'function') {
              var name2 = 'setInterval -> ' + (fn.name || 'anonymous');
              return _si.call(this, function () {
                state.log(name2, arguments);
                return fn.apply(this, arguments);
              }, t);
            }
            return _si.apply(this, arguments);
          };
          root.setInterval.__cm_hooked__ = true;
        }
      }
    } catch (e) {}

    // addEventListener
    try {
      if (typeof root.EventTarget !== 'undefined' && root.EventTarget.prototype) {
        var proto = root.EventTarget.prototype;
        if (!state.originals.addEventListener) state.originals.addEventListener = proto.addEventListener;
        if (typeof proto.addEventListener === 'function' && !proto.addEventListener.__cm_hooked__) {
          var origAEL = state.originals.addEventListener;
          proto.addEventListener = function (type, listener, options) {
            if (typeof listener === 'function' && !listener.__cm_wrapped_listener__) {
              var lname = listener.name || 'anonymous';
              var wrapped = function () {
                state.log('event:' + type + ' -> ' + lname, arguments);
                return listener.apply(this, arguments);
              };
              wrapped.__cm_wrapped_listener__ = true;
              wrapped.__cm_original__ = listener;
              listener = wrapped;
            }
            return origAEL.call(this, type, listener, options);
          };
          proto.addEventListener.__cm_hooked__ = true;
        }
      }
    } catch (e) {}

    // XHR
    try {
      if (root.XMLHttpRequest && root.XMLHttpRequest.prototype) {
        var XHR = root.XMLHttpRequest;
        if (!state.originals.xhrOpen) state.originals.xhrOpen = XHR.prototype.open;
        if (!state.originals.xhrSend) state.originals.xhrSend = XHR.prototype.send;

        if (typeof XHR.prototype.open === 'function' && !XHR.prototype.open.__cm_hooked__) {
          var open = state.originals.xhrOpen;
          XHR.prototype.open = function (method, url) {
            try { this.__cm_m = method; this.__cm_u = url; } catch (e2) {}
            return open.apply(this, arguments);
          };
          XHR.prototype.open.__cm_hooked__ = true;
        }

        if (typeof XHR.prototype.send === 'function' && !XHR.prototype.send.__cm_hooked__) {
          var send = state.originals.xhrSend;
          XHR.prototype.send = function () {
            state.log('xhr:' + (this.__cm_m || '') + ' ' + (this.__cm_u || ''), arguments);
            return send.apply(this, arguments);
          };
          XHR.prototype.send.__cm_hooked__ = true;
        }
      }
    } catch (e) {}
  }

  // -----------------------------
  // ES6 mode (Proxy)
  // -----------------------------
  function installES6(state) {
    state.mode = 'es6';
    state.proxyCache = new WeakMap();

    function isSafeToProxy(obj) {
      if (!obj) return false;
      if (isProbablyDOM(obj)) return false;
      return true;
    }

    function proxify(target, path) {
      if (!target) return target;

      var t = target;
      var typ = typeof t;
      if (typ !== 'object' && typ !== 'function') return t;
      if (!isSafeToProxy(t)) return t;

      var cached = state.proxyCache.get(t);
      if (cached) return cached;

      var handler = {
        get: function (obj, prop, receiver) {
          var v;
          try { v = root.Reflect.get(obj, prop, receiver); }
          catch (e) { try { v = obj[prop]; } catch (e2) { return undefined; } }

          if (typeof v === 'function') {
            return function () {
              var name = path + '.' + String(prop);
              state.log(name, arguments);

              // this 보정: proxy->real object
              var thisArg = this;
              if (thisArg === receiver) thisArg = obj;

              return v.apply(thisArg, arguments);
            };
          }

          if (v && (typeof v === 'object' || typeof v === 'function')) {
            if (!isSafeToProxy(v)) return v;
            return proxify(v, path + '.' + String(prop));
          }

          return v;
        },
        apply: function (fn, thisArg, args) {
          state.log(path + '()', args);
          return root.Reflect.apply(fn, thisArg, args);
        }
      };

      var p = new root.Proxy(t, handler);
      try { p.__cm_monitored__ = true; } catch (e) {}
      state.proxyCache.set(t, p);
      return p;
    }

    hookCommonEntrypoints(state);

    // Proxy globals (best-effort)
    var count = 0;
    for (var k in root) {
      count++;
      if (count > state.cfg.maxGlobals) break;

      if (state.cfg.excludeGlobalName.test(k)) continue;
      if (state.cfg.excludeObjectName.test(k)) continue;

      var v;
      try { v = root[k]; } catch (e) { continue; }
      if (!v) continue;

      if (v === root || v === root.document) continue;
      if (isProbablyDOM(v)) continue;

      var t2 = typeof v;
      if (t2 !== 'object' && t2 !== 'function') continue;

      if (!canWriteProperty(root, k)) continue;

      try {
        var p2 = proxify(v, 'window.' + k);
        // record for uninstall
        state.proxiedGlobals.push({ key: k, original: v });
        root[k] = p2;
      } catch (e) {
        // some host objects can't be proxied
      }
    }

    state.installed = true;
  }

  // -----------------------------
  // ES5 mode (wrap)
  // -----------------------------
  function installES5(state) {
    state.mode = 'es5';

    function alreadyWrapped(fn) {
      return !!(fn && fn.__cm_wrapped__);
    }

    function wrapMethod(obj, key, path) {
      var fn;
      try { fn = obj[key]; } catch (e) { return; }
      if (typeof fn !== 'function') return;
      if (alreadyWrapped(fn)) return;
      if (!canWriteProperty(obj, key)) return;

      try {
        obj[key] = (function (name, orig) {
          function wrapped() {
            state.log(name, arguments);
            return orig.apply(this, arguments);
          }
          wrapped.__cm_wrapped__ = true;
          wrapped.__cm_original__ = orig;
          return wrapped;
        })(path + '.' + key, fn);

        state.wrapped.push({ obj: obj, key: key, original: fn });
      } catch (e) {}
    }

    // cycle detection
    var visited = [];
    function seen(obj) {
      for (var i = 0; i < visited.length; i++) if (visited[i] === obj) return true;
      visited.push(obj);
      return false;
    }

    function walk(obj, path, depth) {
      if (!obj) return;
      var typ = typeof obj;
      if (typ !== 'object' && typ !== 'function') return;

      if (depth > state.cfg.maxDepth) return;
      if (seen(obj)) return;
      if (isProbablyDOM(obj)) return;

      var k, v;
      for (k in obj) {
        try { v = obj[k]; } catch (e) { continue; }
        if (typeof v === 'function') wrapMethod(obj, k, path);
        else if (v && typeof v === 'object' && !isProbablyDOM(v)) walk(v, path + '.' + k, depth + 1);
      }
    }

    hookCommonEntrypoints(state);

    // walk global objects
    var count = 0;
    for (var g in root) {
      count++;
      if (count > state.cfg.maxGlobals) break;

      if (state.cfg.excludeGlobalName.test(g)) continue;
      if (state.cfg.excludeObjectName.test(g)) continue;

      var obj;
      try { obj = root[g]; } catch (e) { continue; }
      if (!obj) continue;

      if (obj === root || obj === root.document) continue;
      if (isProbablyDOM(obj)) continue;

      var t = typeof obj;
      if (t !== 'object' && t !== 'function') continue;

      walk(obj, 'window.' + g, 0);
    }

    state.installed = true;
  }

  function uninstall(state) {
    if (!state || !state.installed) return;

    // restore patched entrypoints
    try {
      if (state.originals.fetch) root.fetch = state.originals.fetch;
    } catch (e) {}

    try {
      if (state.originals.setTimeout) root.setTimeout = state.originals.setTimeout;
    } catch (e) {}

    try {
      if (state.originals.setInterval) root.setInterval = state.originals.setInterval;
    } catch (e) {}

    try {
      if (state.originals.addEventListener && typeof root.EventTarget !== 'undefined' && root.EventTarget.prototype) {
        root.EventTarget.prototype.addEventListener = state.originals.addEventListener;
      }
    } catch (e) {}

    try {
      if (root.XMLHttpRequest && root.XMLHttpRequest.prototype) {
        if (state.originals.xhrOpen) root.XMLHttpRequest.prototype.open = state.originals.xhrOpen;
        if (state.originals.xhrSend) root.XMLHttpRequest.prototype.send = state.originals.xhrSend;
      }
    } catch (e) {}

    // restore ES5 wrapped methods
    for (var i = 0; i < state.wrapped.length; i++) {
      var w = state.wrapped[i];
      try { w.obj[w.key] = w.original; } catch (e) {}
    }
    state.wrapped = [];

    // restore ES6 proxied globals
    for (var j = 0; j < state.proxiedGlobals.length; j++) {
      var p = state.proxiedGlobals[j];
      try { root[p.key] = p.original; } catch (e) {}
    }
    state.proxiedGlobals = [];

    state.installed = false;
  }

  // Public API
  var CallMonitor = (function () {
    var _state = null;

    function install(cfg) {
      if (_state && _state.installed) return _state.mode;
      _state = createState(cfg || {});

      if (supportsProxyES6()) {
        try { installES6(_state); }
        catch (e) { installES5(_state); }
      } else {
        installES5(_state);
      }

      try {
        root.console.log('[hook] installed:', _state.mode === 'es6' ? 'ES6 Proxy mode' : 'ES5 wrap mode');
      } catch (e) {}

      return _state.mode;
    }

    function uninstallPublic() {
      if (!_state) return;
      uninstall(_state);
      try { root.console.log('[hook] uninstalled'); } catch (e) {}
    }

    function config(newCfg) {
      if (!_state) _state = createState({});
      shallowCopy(_state.cfg, newCfg || {});
      return shallowCopy({}, _state.cfg);
    }

    function state() {
      return _state ? {
        installed: _state.installed,
        mode: _state.mode,
        installTime: _state.installTime
      } : { installed: false, mode: null, installTime: null };
    }

    return {
      install: install,
      uninstall: uninstallPublic,
      config: config,
      state: state
    };
  })();

  // Export
  root.CallMonitor = CallMonitor;

})(typeof window !== 'undefined' ? window : this);