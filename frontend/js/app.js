/* 应用外壳、登录与导航 */
(function () {
  const { createApp, ref, computed, onMounted } = Vue;

  const PAGE_META = {
    overview: { title: '首页概览', crumb: '首页', icon: 'grid' },
    patients: { title: '患者管理', crumb: '患者', icon: 'users' },
    patient: { title: '患者全景档案', crumb: '患者 / 全景', icon: 'users' },
    chat: { title: '智能助手', crumb: '智能助手', icon: 'chat' },
    expert: { title: '专家会诊', crumb: '专家会诊', icon: 'stethoscope' },
    kb: { title: '医疗知识', crumb: '医疗知识', icon: 'book' },
    devices: { title: '我的设备', crumb: '设备', icon: 'cpu' },
    users: { title: '用户管理', crumb: '账号', icon: 'usercheck' },
    experts: { title: '专家管理', crumb: '专家', icon: 'stethoscope' },
    settings: { title: '平台配置', crumb: '配置', icon: 'sliders' },
    portal: { title: '我的健康', crumb: '患者端', icon: 'heart' },
  };

  const NAV = {
    doctor: ['overview', 'patients', 'chat'],
    patient: ['portal', 'expert'],
    admin: ['overview', 'kb', 'users', 'experts', 'settings'],
  };

  const NAV_LABEL = {
    overview: '首页概览', patients: '患者管理', chat: '智能助手',
    kb: '医疗知识', settings: '平台配置', portal: '我的健康', devices: '我的设备',
    users: '用户管理', expert: '专家会诊', experts: '专家管理',
  };

  const Login = {
    emits: ['done'],
    setup(props, { emit }) {
      const mode = ref('login');
      const username = ref('doctor');
      const password = ref('doctor123');
      const loading = ref(false);
      const error = ref('');
      const showPwd = ref(false);
      const form = ref({ name: '', phone: '', username: '', password: '', confirm: '', gender: '女', city: '' });
      const demos = [
        { u: 'doctor', p: 'doctor123', label: '医生 · 江先亮' },
        { u: 'patient', p: 'patient123', label: '患者 · 陈建国' },
        { u: 'admin', p: 'admin123', label: '管理员' },
      ];
      function switchMode(m) {
        if (m === mode.value) return;
        mode.value = m;
        error.value = '';
      }
      async function submit() {
        if (!username.value || !password.value) { error.value = '请输入账号与密码'; return; }
        loading.value = true; error.value = '';
        try {
          const d = await API.post('/api/auth/login', { username: username.value, password: password.value });
          emit('done', d);
        } catch (e) { error.value = e.message; }
        finally { loading.value = false; }
      }
      function useDemo(d) { username.value = d.u; password.value = d.p; submit(); }
      async function register() {
        const f = form.value;
        error.value = '';
        if (f.name.trim().length < 2) { error.value = '请填写真实姓名'; return; }
        if (!/^1[3-9]\d{9}$/.test(f.phone.trim())) { error.value = '请填写正确的 11 位手机号'; return; }
        if (!/^[A-Za-z][A-Za-z0-9_]{2,19}$/.test(f.username.trim())) { error.value = '账号需以字母开头，3–20 位字母、数字或下划线'; return; }
        if ((f.password || '').length < 6) { error.value = '密码至少 6 位'; return; }
        if (f.password !== f.confirm) { error.value = '两次输入的密码不一致'; return; }
        loading.value = true;
        try {
          const d = await API.post('/api/auth/register', {
            name: f.name.trim(), phone: f.phone.trim(), username: f.username.trim(),
            password: f.password, gender: f.gender, city: f.city.trim(),
          });
          emit('done', d);
        } catch (e) { error.value = e.message; }
        finally { loading.value = false; }
      }
      return { mode, username, password, loading, error, demos, form, submit, useDemo, register, switchMode, showPwd };
    },
    template: `
      <div class="login-wrap">
        <div class="login-art">
          <div class="login-brand">
            <svg class="mark" viewBox="0 0 48 48" fill="none">
              <rect width="48" height="48" rx="13" fill="rgba(255,255,255,.14)" stroke="rgba(255,255,255,.35)"/>
              <path d="M9 26h6.5l3-8 5 16 4-10.5 2.5 4.5H39" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <div>
              <div class="name">慢病智管</div>
              <div class="sub">社区慢病管理平台</div>
            </div>
          </div>
          <div class="login-copy">
            <h1>让每一位居民<br>都有一个懂自己的智能助手</h1>
            <p>以患者全景档案为底座，融合本地知识库与开源大模型，把指南变成贴合个人情况、可执行、可追溯的日常建议。历史数据越完整，服务越精准。</p>
            <div class="login-points">
              <div class="login-point"><b>12</b><span>在管居民示例</span></div>
              <div class="login-point"><b>76</b><span>本地指南片段</span></div>
              <div class="login-point"><b>7</b><span>安全门禁规则</span></div>
            </div>
          </div>
          <div style="position:relative;z-index:2;font-size:11.5px;opacity:.7">
            数据本地存储 · 支持私有化部署 · 不替代临床诊断
          </div>
        </div>
        <div class="login-form-side">
          <div class="login-box" :class="{tall: mode==='register'}">
            <div class="auth-switch">
              <span class="auth-switch-thumb" :class="{right: mode==='register'}"></span>
              <button :class="{active: mode==='login'}" @click="switchMode('login')">
                <mb-icon name="logout" :size="14"/> 账号登录
              </button>
              <button :class="{active: mode==='register'}" @click="switchMode('register')">
                <mb-icon name="usercheck" :size="14"/> 用户注册
              </button>
            </div>

            <transition name="auth-fade" mode="out-in">
              <div class="auth-panel" :key="mode">
                <h2>{{ mode === 'login' ? '欢迎回来' : '创建用户账号' }}</h2>
                <div class="hint">{{ mode === 'login'
                  ? '使用演示账号可直接体验完整流程'
                  : '注册后自动关联或建立健康档案，并与智能助手、设备数据打通' }}</div>

                <template v-if="mode === 'login'">
                  <div class="field">
                    <label>账号</label>
                    <div class="input-ico">
                      <span class="ii"><mb-icon name="users" :size="15"/></span>
                      <input class="input" v-model="username" placeholder="请输入账号" @keyup.enter="submit">
                    </div>
                  </div>
                  <div class="field">
                    <label>密码</label>
                    <div class="input-ico">
                      <span class="ii"><mb-icon name="shield" :size="15"/></span>
                      <input class="input" :type="showPwd ? 'text' : 'password'" v-model="password"
                             placeholder="请输入密码" @keyup.enter="submit">
                      <button class="input-eye" type="button" @click="showPwd = !showPwd">
                        {{ showPwd ? '隐藏' : '显示' }}
                      </button>
                    </div>
                  </div>
                  <div class="login-error" v-if="error">{{ error }}</div>
                  <button class="btn login-btn" :disabled="loading" @click="submit">
                    {{ loading ? '登录中…' : '登录' }}
                    <mb-icon v-if="!loading" name="arrow" :size="15"/>
                  </button>
                  <div class="demo-accounts">
                    <div class="cap">演示账号快速登录</div>
                    <div class="demo-chips">
                      <button class="demo-chip" v-for="d in demos" :key="d.u" @click="useDemo(d)">
                        <span class="demo-dot" :class="d.u"></span>{{ d.label }}
                      </button>
                    </div>
                  </div>
                </template>

                <template v-else>
                  <div class="auth-section">基本信息</div>
                  <div class="auth-grid">
                    <div class="field">
                      <label>姓名</label>
                      <input class="input" v-model="form.name" placeholder="身份证姓名">
                    </div>
                    <div class="field">
                      <label>手机号</label>
                      <input class="input num" v-model="form.phone" maxlength="11" placeholder="用于匹配健康档案">
                    </div>
                  </div>
                  <div class="auth-section">账号设置</div>
                  <div class="field">
                    <label>登录账号</label>
                    <input class="input" v-model="form.username" placeholder="字母开头，3–20 位">
                    <div class="field-help">已有档案时，姓名与手机号一致会自动关联既往记录</div>
                  </div>
                  <div class="auth-grid">
                    <div class="field">
                      <label>密码</label>
                      <input class="input" type="password" v-model="form.password" placeholder="至少 6 位">
                    </div>
                    <div class="field">
                      <label>确认密码</label>
                      <input class="input" type="password" v-model="form.confirm" placeholder="再次输入">
                    </div>
                  </div>
                  <div class="auth-section">健康档案</div>
                  <div class="auth-grid">
                    <div class="field">
                      <label>性别</label>
                      <select class="select" v-model="form.gender">
                        <option value="女">女</option>
                        <option value="男">男</option>
                      </select>
                    </div>
                    <div class="field">
                      <label>所在城市<span class="opt">（选填）</span></label>
                      <input class="input" v-model="form.city" placeholder="如 宁波">
                    </div>
                  </div>
                  <div class="login-error" v-if="error">{{ error }}</div>
                  <button class="btn login-btn" :disabled="loading" @click="register">
                    {{ loading ? '提交中…' : '注册并进入' }}
                    <mb-icon v-if="!loading" name="arrow" :size="15"/>
                  </button>
                  <div class="login-note">
                    <mb-icon name="shield" :size="13"/>
                    <span>注册即表示同意平台仅将数据用于本人健康管理，不替代临床诊断。</span>
                  </div>
                </template>
              </div>
            </transition>
          </div>
        </div>
      </div>`,
  };

  const App = {
    components: { Login },
    setup() {
      const booted = ref(false);
      const q = ref('');
      const themeOpen = ref(false);
      const customHex = ref('#0f766e');

      const nav = computed(() => NAV[Store.user ? Store.user.role : 'doctor'] || NAV.doctor);
      const pageComp = computed(() => (window.Pages[Store.page] || window.Pages.overview));
      const pageKey = computed(() => Store.page + ':' + JSON.stringify(Store.params));
      const meta = computed(() => PAGE_META[Store.page] || PAGE_META.overview);
      const today = computed(() => {
        const d = new Date();
        const w = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()];
        return `${d.getMonth() + 1}月${d.getDate()}日 周${w}`;
      });
      const initials = computed(() => (Store.user ? Store.user.name.slice(-2) : ''));

      function go(page, params) { ui.go(page, params); }

      async function boot() {
        try {
          const u = await API.get('/api/auth/me');
          Store.user = u;
          if (!localStorage.getItem('mb-theme') && u.theme) Theme.applyTheme(u.theme);
          go(u.role === 'patient' ? 'portal' : 'overview');
        } catch (e) {
          Store.user = null;
        } finally {
          booted.value = true;
          Store.ready = true;
        }
      }
      onMounted(boot);

      function onLogin(u) {
        Store.user = u;
        if (!localStorage.getItem('mb-theme') && u.theme) Theme.applyTheme(u.theme);
        go(u.role === 'patient' ? 'portal' : 'overview');
        ui.toast(u.message || ('欢迎回来，' + u.name));
      }
      async function logout() {
        try { await API.post('/api/auth/logout', {}); } catch (e) {}
        Store.user = null;
        Store.page = 'overview';
      }
      function search() {
        if (!q.value.trim()) return;
        go('patients', { q: q.value.trim() });
      }
      function navBadge(key) {
        return key === 'patients' && Store.alerts > 0 ? Store.alerts : 0;
      }
      function navLabel(key) { return NAV_LABEL[key] || key; }

      function pickTheme(t) {
        Theme.applyTheme(t.id);
        themeOpen.value = false;
        API.put('/api/auth/theme', { theme: t.id }).catch(() => {});
      }
      function applyCustom() {
        if (!/^#[0-9a-fA-F]{6}$/.test(customHex.value)) return ui.toast('请输入完整的十六进制色值', 'err');
        Theme.setCustomTheme(customHex.value);
        themeOpen.value = false;
        API.put('/api/auth/theme', { theme: 'custom' }).catch(() => {});
      }
      function openUserCard() {
        if (nav.value.includes('settings')) go('settings');
        else themeOpen.value = true;
      }

      return { Store, booted, nav, pageComp, pageKey, meta, today, initials, q,
               themeOpen, customHex, pickTheme, applyCustom, openUserCard,
               go, onLogin, logout, search, navBadge, navLabel };
    },
    template: `
      <div v-if="!booted" class="boot">
        <div class="boot-logo"></div>
        <div class="boot-text">正在加载慢病智管…</div>
      </div>
      <login v-else-if="!Store.user" @done="onLogin"/>
      <div v-else class="shell">
        <aside class="sidebar">
          <div class="brand">
            <svg class="mark" viewBox="0 0 48 48" fill="none">
              <defs>
                <linearGradient id="brandGrad" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stop-color="var(--primary)"/>
                  <stop offset="100%" stop-color="var(--accent)"/>
                </linearGradient>
              </defs>
              <rect width="48" height="48" rx="13" fill="url(#brandGrad)"/>
              <path d="M9 26h6.5l3-8 5 16 4-10.5 2.5 4.5H39" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="36" cy="12" r="3.2" fill="rgba(255,255,255,.55)"/>
            </svg>
            <div>
              <div class="brand-name">慢病智管</div>
              <div class="brand-sub">社区慢病管理平台</div>
            </div>
          </div>

          <nav class="nav">
            <button v-for="k in nav" :key="k" class="nav-item"
                    :class="{ active: Store.page === k || (k === 'patients' && Store.page === 'patient') }"
                    @click="go(k)">
              <span class="nav-icon"><mb-icon :name="({portal:'heart',patients:'users',chat:'chat',expert:'stethoscope',experts:'stethoscope',kb:'book',settings:'sliders',devices:'cpu',users:'usercheck'})[k] || 'grid'" :size="17"/></span>
              {{ navLabel(k) }}
              <span class="nav-badge" v-if="navBadge(k)">{{ navBadge(k) }}</span>
            </button>
          </nav>

          <div class="side-foot">
            <div class="agent-mini">
              <div class="row1"><span class="dot"></span>智能体运行中</div>
              <div class="row2">知识库 · 患者画像 · 长期记忆</div>
            </div>
            <div class="user-card" @click="openUserCard">
              <div class="avatar" :style="{background:'var(--primary)'}">{{ initials }}</div>
              <div style="min-width:0">
                <div class="user-name">{{ Store.user.name }}</div>
                <div class="user-role">{{ Store.user.role === 'doctor' ? '签约医生' : Store.user.role === 'patient' ? '签约居民' : '系统管理员' }}</div>
              </div>
              <button class="user-exit" title="退出登录" @click.stop="logout"><mb-icon name="logout" :size="15"/></button>
            </div>
          </div>
        </aside>

        <div class="main">
          <header class="topbar">
            <div>
              <div class="crumb">慢病智管 / {{ meta.crumb }}</div>
              <h1>{{ meta.title }}</h1>
            </div>
            <div class="topbar-right">
              <div class="top-search" v-if="Store.user.role !== 'patient'">
                <span class="si"><mb-icon name="search" :size="14"/></span>
                <input v-model="q" placeholder="搜索患者姓名" @keyup.enter="search">
              </div>
              <span class="small faint nowrap" style="margin:0 4px">{{ today }}</span>
              <button class="icon-btn" title="预警" @click="go(Store.user.role === 'patient' ? 'portal' : 'patients', {risk:'high'})">
                <mb-icon name="bell" :size="16"/>
              </button>
              <div class="theme-wrap">
                <button class="icon-btn" :class="{ on: themeOpen }" title="主题配色" @click="themeOpen = !themeOpen">
                  <mb-icon name="sparkles" :size="16"/>
                </button>
                <div class="tp-mask" v-if="themeOpen" @click="themeOpen = false"></div>
                <div class="theme-pop" v-if="themeOpen">
                  <div class="tp-head"><b>主题配色</b><span>切换后自动保存</span></div>
                  <button class="tp-item" v-for="t in Store.themes" :key="t.id"
                          :class="{ active: Store.theme === t.id }" @click="pickTheme(t)">
                    <span class="tp-dot" :style="{ background: t.primary }"></span>
                    <span class="tp-name">{{ t.name }}<small>{{ t.desc }}</small></span>
                    <mb-icon v-if="Store.theme === t.id" name="check" :size="14"/>
                  </button>
                  <div class="tp-custom">
                    <label>自定义主色</label>
                    <input type="color" v-model="customHex">
                    <button class="btn sm ghost" @click="applyCustom">应用</button>
                  </div>
                </div>
              </div>
            </div>
          </header>
          <main class="content">
            <component :is="pageComp" :key="pageKey"/>
          </main>
        </div>

        <div class="toast-wrap">
          <div v-for="t in Store.toasts" :key="t.id" class="toast" :class="t.type">{{ t.msg }}</div>
        </div>
      </div>`,
  };

  const app = createApp(App);
  app.component('mb-icon', Mb.Icon);
  app.mount('#app');
})();
