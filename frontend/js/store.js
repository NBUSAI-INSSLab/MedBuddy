/* 全局状态与主题 */
(function () {
  const { reactive } = Vue;

  const THEMES = [
    { id: 'orange', name: '橙色', desc: '温暖醒目',
      primary: '#ea580c', dark: '#c2410c', light: '#ffedd5', accent: '#9a3412' },
    { id: 'orangeblue', name: '橙蓝', desc: '橙主蓝辅 · 双色',
      primary: '#ea580c', dark: '#c2410c', light: '#ffedd5',
      accent: '#1d4ed8', accentLight: '#dbeafe', dual: true },
    { id: 'blue', name: '蓝色', desc: '沉稳专业',
      primary: '#2563eb', dark: '#1d4ed8', light: '#dbeafe', accent: '#1e3a8a' },
    { id: 'green', name: '绿色', desc: '医疗清新',
      primary: '#16a34a', dark: '#15803d', light: '#dcfce7', accent: '#14532d' },
    { id: 'graphite', name: '黑灰', desc: '极简克制',
      primary: '#334155', dark: '#0f172a', light: '#e2e8f0', accent: '#09090b' },
  ];

  const LEGACY = { mint: 'green', ocean: 'blue', amber: 'orange', violet: 'blue', sunset: 'orange' };

  const Store = reactive({
    ready: false,
    user: null,
    page: 'overview',
    params: {},
    theme: 'green',
    themes: THEMES,
    alerts: 0,
    toasts: [],
    draftPatient: null,
  });

  function hexToRgb(hex) {
    const h = hex.replace('#', '');
    const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function applyTheme(id) {
    const key = LEGACY[id] || id;
    const t = THEMES.find((x) => x.id === key) || THEMES[3];
    const rgb = hexToRgb(t.primary);
    const ar = hexToRgb(t.accent || t.dark);
    const root = document.documentElement.style;
    root.setProperty('--primary', t.primary);
    root.setProperty('--primary-dark', t.dark);
    root.setProperty('--primary-light', t.light);
    root.setProperty('--primary-rgb', rgb.join(','));
    root.setProperty('--primary-50', `rgba(${rgb.join(',')},.055)`);
    root.setProperty('--accent', t.accent || t.dark);
    root.setProperty('--accent-rgb', ar.join(','));
    root.setProperty('--accent-soft', t.accentLight || `rgba(${ar.join(',')},.12)`);
    document.documentElement.setAttribute('data-theme', t.id);
    Store.theme = t.id;
    try { localStorage.setItem('mb-theme', t.id); } catch (e) {}
  }

  function setCustomTheme(hex) {
    if (!/^#[0-9a-fA-F]{6}$/.test(hex)) return;
    const rgb = hexToRgb(hex);
    const dark = `rgb(${rgb.map((c) => Math.round(c * 0.78)).join(',')})`;
    const light = `rgba(${rgb.join(',')},.16)`;
    const root = document.documentElement.style;
    root.setProperty('--primary', hex);
    root.setProperty('--primary-dark', dark);
    root.setProperty('--primary-light', light);
    root.setProperty('--primary-rgb', rgb.join(','));
    root.setProperty('--primary-50', `rgba(${rgb.join(',')},.055)`);
    root.setProperty('--accent', dark);
    root.setProperty('--accent-rgb', rgb.map((c) => Math.round(c * 0.78)).join(','));
    root.setProperty('--accent-soft', light);
    document.documentElement.setAttribute('data-theme', 'custom');
    Store.theme = 'custom';
    try { localStorage.setItem('mb-theme', 'custom'); localStorage.setItem('mb-custom', hex); } catch (e) {}
  }

  function toast(msg, type = 'ok') {
    const id = Date.now() + Math.random();
    Store.toasts.push({ id, msg, type });
    setTimeout(() => {
      const i = Store.toasts.findIndex((t) => t.id === id);
      if (i >= 0) Store.toasts.splice(i, 1);
    }, 3200);
  }

  function go(page, params) {
    Store.page = page;
    Store.params = params || {};
    const content = document.querySelector('.content');
    if (content) content.scrollTop = 0;
  }

  const RISK = {
    critical: { cn: '极高危', cls: 'risk-critical' },
    high: { cn: '高危', cls: 'risk-high' },
    medium: { cn: '中危', cls: 'risk-medium' },
    low: { cn: '低危', cls: 'risk-low' },
  };

  const METRIC = {
    sbp: { name: '收缩压', unit: 'mmHg' }, dbp: { name: '舒张压', unit: 'mmHg' },
    glucose: { name: '血糖', unit: 'mmol/L' }, hba1c: { name: '糖化血红蛋白', unit: '%' },
    weight: { name: '体重', unit: 'kg' }, heart_rate: { name: '静息心率', unit: '次/分' },
    spo2: { name: '血氧饱和度', unit: '%' }, ldl: { name: '低密度脂蛋白', unit: 'mmol/L' },
    egfr: { name: 'eGFR', unit: 'mL/min' }, uric_acid: { name: '尿酸', unit: 'μmol/L' },
    steps: { name: '日步数', unit: '步' },
    temp: { name: '体温', unit: '℃' }, hrv: { name: '心率变异性', unit: 'ms' },
    resp_rate: { name: '呼吸频率', unit: '次/分' },
  };

  window.Store = Store;
  window.Theme = { applyTheme, setCustomTheme, THEMES };
  window.ui = { toast, go, RISK, METRIC };

  const saved = (() => { try { return localStorage.getItem('mb-theme'); } catch (e) { return null; } })();
  if (saved === 'custom') {
    const hex = (() => { try { return localStorage.getItem('mb-custom'); } catch (e) { return null; } })();
    if (hex) setCustomTheme(hex);
  } else {
    applyTheme(saved || 'green');
  }
})();
