/* 用 jsdom 真实渲染 Vue 应用，校验模板与数据绑定（无浏览器环境备选方案） */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const BASE = 'http://127.0.0.1:5000';
const ROOT = path.resolve(__dirname, '..');
const role = process.argv[2] || 'doctor';
const targetPage = process.argv[3] || '';
const password = role === 'patient' ? 'patient123' : role === 'admin' ? 'admin123' : 'doctor123';
const guest = role === 'guest';

(async () => {
  let cookie = '';
  if (!guest) {
    const loginRes = await fetch(BASE + '/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: role, password }),
    });
    if (!loginRes.ok) throw new Error('login failed ' + loginRes.status);
    cookie = (loginRes.headers.getSetCookie ? loginRes.headers.getSetCookie() : [loginRes.headers.get('set-cookie')])
      .map((c) => c.split(';')[0]).join('; ');
  }

  const html = fs.readFileSync(path.join(ROOT, 'frontend/index.html'), 'utf8')
    .replace(/<script src="[^"]+"><\/script>/g, '');
  const virtualConsole = new VirtualConsole();
  const errors = [];
  virtualConsole.on('jsdomError', (e) => errors.push('[jsdom] ' + e.message));
  virtualConsole.on('error', (...a) => errors.push('[console.error] ' + a.join(' ')));
  virtualConsole.on('warn', (...a) => { const s = a.join(' '); if (!s.includes('Not implemented')) errors.push('[warn] ' + s); });

  const dom = new JSDOM(html, {
    url: BASE + '/',
    runScripts: 'outside-only',
    pretendToBeVisual: true,
    virtualConsole,
  });
  const { window } = dom;
  window.fetch = async (url, opt = {}) => {
    const full = String(url).startsWith('http') ? url : BASE + url;
    const headers = Object.assign({}, opt.headers || {}, { Cookie: cookie });
    return fetch(full, { ...opt, headers });
  };
  window.confirm = () => true;
  window.prompt = () => '测试记忆';

  const files = ['assets/vue.global.prod.js', 'js/api.js', 'js/store.js', 'js/charts.js',
    'js/pages.overview.js', 'js/pages.patients.js', 'js/pages.chat.js', 'js/pages.devices.js', 'js/pages.users.js', 'js/pages.kb.js',
    'js/pages.settings.js', 'js/pages.portal.js', 'js/pages.expert.js',
    'js/pages.experts_admin.js', 'js/app.js'];
  for (const f of files) {
    try {
      window.eval(fs.readFileSync(path.join(ROOT, 'frontend', f), 'utf8'));
    } catch (e) {
      errors.push(`[load ${f}] ${e.message}`);
    }
  }

  await new Promise((r) => setTimeout(r, 3000));
  if (guest && targetPage === 'register') {
    const tabs = window.document.querySelectorAll('.auth-switch button');
    if (tabs[1]) tabs[1].dispatchEvent(new window.Event('click'));
    await new Promise((r) => setTimeout(r, 600));
  }
  if (targetPage && targetPage.indexOf('theme:') === 0) {
    const tid = targetPage.split(':')[1];
    window.Theme.applyTheme(tid);
    const cs = window.document.documentElement.style;
    console.log('主题切换：', window.Store.theme, '·', window.document.documentElement.getAttribute('data-theme'),
      '· primary', cs.getPropertyValue('--primary').trim(),
      '· accent', cs.getPropertyValue('--accent').trim());
  }
  if (targetPage && window.ui && !guest) {
    const pageId = targetPage === 'patient-diet' ? 'patient'
      : targetPage === 'expert-consult' ? 'expert'
      : targetPage.startsWith('experts-form') ? 'experts'
      : targetPage === 'theme' ? 'overview' : targetPage;
    window.ui.go(pageId === 'settings-theme' ? 'settings' : pageId, pageId === 'patient' ? { id: 1 } : pageId === 'chat' ? { patient: 1 } : pageId === 'settings' ? { tab: 'iot' } : pageId === 'settings-theme' ? { tab: 'theme' } : {});
    await new Promise((r) => setTimeout(r, 2600));
    if (targetPage === 'patient-diet') {
      const tab = [...window.document.querySelectorAll('.tab')].find((b) => b.textContent.trim() === '饮食管理');
      if (tab) tab.dispatchEvent(new window.Event('click'));
      await new Promise((r) => setTimeout(r, 2200));
    }
    if (targetPage === 'theme') {
      const btn = window.document.querySelector('.theme-wrap .icon-btn');
      if (btn) btn.dispatchEvent(new window.Event('click'));
      await new Promise((r) => setTimeout(r, 500));
      console.log('弹层主题项：', window.document.querySelectorAll('.theme-pop .tp-item').length);
    }
    if (targetPage.startsWith('experts-form')) {
      if (targetPage === 'experts-form-team') {
        const tab = [...window.document.querySelectorAll('.adm-bar .tab')][1];
        if (tab) tab.dispatchEvent(new window.Event('click'));
        await new Promise((r) => setTimeout(r, 500));
      }
      const btn = window.document.querySelector('.adm-bar .btn');
      if (btn) btn.dispatchEvent(new window.Event('click'));
      await new Promise((r) => setTimeout(r, 1200));
    }
    if (targetPage === 'expert-consult') {
      const btn = window.document.querySelector('.expert-card .btn');
      if (btn) btn.dispatchEvent(new window.Event('click'));
      await new Promise((r) => setTimeout(r, 600));
      const start = [...window.document.querySelectorAll('.modal-foot .btn')].pop();
      if (start) start.dispatchEvent(new window.Event('click'));
      await new Promise((r) => setTimeout(r, 2600));
      const ta = window.document.querySelector('.chat-input textarea');
      if (ta) {
        ta.value = '最近血压早上偏高，需要调药吗？';
        ta.dispatchEvent(new window.Event('input'));
        const send = [...window.document.querySelectorAll('.chat-actions .btn')].pop();
        if (send) send.dispatchEvent(new window.Event('click'));
        await new Promise((r) => setTimeout(r, 9000));
      }
    }
  }

  const text = window.document.body.textContent.replace(/\s+/g, ' ').trim();
  const page = window.Store ? window.Store.page : '?';
  console.log(`role=${role} page=${page} chars=${text.length}`);
  console.log('可见文本：', text.slice(0, 420));
  console.log('模块命中：', ['今日重点关注','家庭监测活跃度','智能体与知识库','本次回答依据','知识库文档','检索测试','主题配色','我的管理计划','用药与建议','患者画像','设备台账','实时上报','MQTT 接入配置','报文规范','接入设备','设备监测','心率变异性','我的设备','把家里的设备接进来','接入新设备','接入指引','今日饮食','拍照上传','账号列表','新建账号','已停用','今日配餐方案','食物宜忌','病种饮食要点','最近饮食记录','专家数字人','专家团','发起会诊','患者档案摘要','专家管理','数字人能力配置中心','知识库绑定','外部工具','新建专家'].filter((k)=>text.includes(k)).join(' / '));
  console.log('KPI 命中：', ['在管患者', '高风险人群', '血压达标率', '待处理预警'].filter((k) => text.includes(k)).join(' / '));
  console.log('图表元素：', window.document.querySelectorAll('svg').length, '个 SVG');
  if (errors.length) {
    console.log('--- 错误 ---');
    errors.slice(0, 12).forEach((e) => console.log(e.slice(0, 300)));
    process.exitCode = 1;
  } else {
    console.log('无渲染错误');
  }
  dom.window.close();
})();
