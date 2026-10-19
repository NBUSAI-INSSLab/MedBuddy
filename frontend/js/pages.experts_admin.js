/* 专家管理（管理员）：数字人专家与专家团的人设、知识库、技能与 MCP 工具配置 */
(function () {
  const { ref, computed, onMounted } = Vue;
  const Pages = (window.Pages = window.Pages || {});

  const COLORS = [
    ['#b91c1c', '#f97316'], ['#7c3aed', '#2563eb'], ['#0d9488', '#22c55e'],
    ['#0369a1', '#0ea5e9'], ['#4338ca', '#8b5cf6'], ['#b45309', '#f59e0b'],
    ['#0f766e', '#14b8a6'], ['#be123c', '#fb7185'],
  ];

  function splitTags(text) {
    return (text || '').split(/[,，、;；\n]/).map((x) => x.trim()).filter(Boolean);
  }
  function splitLines(text) {
    return (text || '').split(/\n/).map((x) => x.trim()).filter(Boolean);
  }

  function blankExpert() {
    return {
      name: '', title: '', dept: '', org: '社区卫生服务中心', role_key: 'gp',
      years: 10, cases: '', tags: '', intro: '', style: '', greeting: '', questions: '',
      color: '#0f766e', color2: '#14b8a6', skills: [], kb_doc_ids: [], mcp_tools: [],
      status: 'active',
    };
  }
  function blankTeam() {
    return {
      name: '', desc: '', scenario: '', tags: '', member_ids: [], skills: [],
      kb_doc_ids: [], mcp_tools: [], status: 'active',
    };
  }

  Pages.experts = {
    components: { MbIcon: Mb.Icon },
    setup() {
      const data = ref(null);
      const loading = ref(true);
      const saving = ref(false);
      const busy = ref(false);
      const tab = ref('expert');
      const q = ref('');
      const kbQuery = ref('');
      const showForm = ref(false);
      const kind = ref('expert');
      const editing = ref(null);
      const form = ref(blankExpert());
      const customTool = ref({ name: '', desc: '' });
      const showCustomTool = ref(false);

      const catalog = computed(() => (data.value ? data.value.catalog : { skills: [], mcp: [], roles: [], kb: [] }));
      const stats = computed(() => (data.value ? data.value.stats : {}));
      const experts = computed(() => (data.value ? data.value.experts : []));
      const teams = computed(() => (data.value ? data.value.teams : []));

      function match(text) {
        const key = q.value.trim().toLowerCase();
        return !key || (text || '').toLowerCase().includes(key);
      }
      const filteredExperts = computed(() => experts.value.filter((e) =>
        match(e.name) || match(e.dept) || match(e.title) || e.tags.some((t) => match(t))));
      const filteredTeams = computed(() => teams.value.filter((t) =>
        match(t.name) || match(t.desc) || t.tags.some((x) => match(x))));
      const filteredKb = computed(() => {
        const key = kbQuery.value.trim().toLowerCase();
        return (catalog.value.kb || []).filter((d) =>
          !key || d.title.toLowerCase().includes(key) || (d.category || '').toLowerCase().includes(key));
      });
      const roleName = (key) => {
        const r = (catalog.value.roles || []).find((x) => x.key === key);
        return r ? r.name : '全科医学';
      };

      async function load(silent) {
        if (!silent) loading.value = true;
        try {
          data.value = await API.get('/api/admin/experts');
        } catch (e) {
          ui.toast(e.message, 'err');
        } finally {
          loading.value = false;
        }
      }
      onMounted(() => load(true));

      function openCreate() {
        kind.value = tab.value === 'team' ? 'team' : 'expert';
        editing.value = null;
        form.value = kind.value === 'team' ? blankTeam() : blankExpert();
        kbQuery.value = '';
        showCustomTool.value = false;
        customTool.value = { name: '', desc: '' };
        showForm.value = true;
      }
      function openEditExpert(e) {
        kind.value = 'expert';
        editing.value = e;
        form.value = {
          name: e.name, title: e.title, dept: e.dept, org: e.org, role_key: e.role_key,
          years: e.years, cases: e.cases, tags: e.tags.join('、'), intro: e.intro,
          style: e.style, greeting: e.greeting, questions: e.questions.join('\n'),
          color: e.color, color2: e.color2, skills: e.skills.map((s) => s.key),
          kb_doc_ids: [...e.kb_doc_ids], mcp_tools: e.mcp_tools.map((t) => ({ ...t })),
          status: e.status,
        };
        kbQuery.value = '';
        showCustomTool.value = false;
        customTool.value = { name: '', desc: '' };
        showForm.value = true;
      }
      function openEditTeam(t) {
        kind.value = 'team';
        editing.value = t;
        form.value = {
          name: t.name, desc: t.desc, scenario: t.scenario, tags: t.tags.join('、'),
          member_ids: [...t.member_ids], skills: t.skills.map((s) => s.key),
          kb_doc_ids: [...t.kb_doc_ids], mcp_tools: t.mcp_tools.map((x) => ({ ...x })),
          status: t.status,
        };
        kbQuery.value = '';
        showCustomTool.value = false;
        customTool.value = { name: '', desc: '' };
        showForm.value = true;
      }

      function hasSkill(key) { return form.value.skills.includes(key); }
      function toggleSkill(key) {
        const i = form.value.skills.indexOf(key);
        if (i >= 0) form.value.skills.splice(i, 1);
        else form.value.skills.push(key);
      }
      function hasKb(id) { return form.value.kb_doc_ids.includes(id); }
      function toggleKb(id) {
        const i = form.value.kb_doc_ids.indexOf(id);
        if (i >= 0) form.value.kb_doc_ids.splice(i, 1);
        else form.value.kb_doc_ids.push(id);
      }
      function hasTool(key) { return form.value.mcp_tools.some((t) => t.key === key); }
      function toggleTool(t) {
        const i = form.value.mcp_tools.findIndex((x) => x.key === t.key);
        if (i >= 0) form.value.mcp_tools.splice(i, 1);
        else form.value.mcp_tools.push({ key: t.key, name: t.name, desc: t.desc, builtin: !!t.builtin });
      }
      function addCustomTool() {
        const name = customTool.value.name.trim();
        if (!name) return ui.toast('请填写工具名称', 'err');
        form.value.mcp_tools.push({
          key: 'custom_' + Date.now().toString(36),
          name, desc: customTool.value.desc.trim(), builtin: false, custom: true,
        });
        customTool.value = { name: '', desc: '' };
        showCustomTool.value = false;
        ui.toast('已添加自定义工具');
      }
      function hasMember(code) { return form.value.member_ids.includes(code); }
      function toggleMember(code) {
        const i = form.value.member_ids.indexOf(code);
        if (i >= 0) form.value.member_ids.splice(i, 1);
        else form.value.member_ids.push(code);
      }
      function memberOrder(code) { return form.value.member_ids.indexOf(code) + 1; }
      const customTools = computed(() => form.value.mcp_tools.filter((x) => x.custom));
      const chosenMembers = computed(() => form.value.member_ids
        .map((code) => experts.value.find((e) => e.code === code))
        .filter(Boolean));
      function pickColor(pair) {
        form.value.color = pair[0];
        form.value.color2 = pair[1];
      }
      function orbStyle(x) {
        return { background: `linear-gradient(135deg, ${x.color || '#334155'}, ${x.color2 || '#64748b'})` };
      }

      async function save() {
        const f = form.value;
        if (f.name.trim().length < 2) return ui.toast('请填写名称（至少 2 个字）', 'err');
        if (kind.value === 'team' && !f.member_ids.length) return ui.toast('请至少选择一位专家作为成员', 'err');
        saving.value = true;
        try {
          if (kind.value === 'team') {
            const payload = {
              name: f.name.trim(), desc: f.desc.trim(), scenario: f.scenario.trim(),
              tags: splitTags(f.tags), member_ids: f.member_ids, skills: f.skills,
              kb_doc_ids: f.kb_doc_ids, mcp_tools: f.mcp_tools, status: f.status,
            };
            if (editing.value) await API.put('/api/admin/expert-teams/' + editing.value.db_id, payload);
            else await API.post('/api/admin/expert-teams', payload);
          } else {
            const payload = {
              name: f.name.trim(), title: f.title.trim(), dept: f.dept.trim(), org: f.org.trim(),
              role_key: f.role_key, years: f.years, cases: f.cases.trim(),
              tags: splitTags(f.tags), intro: f.intro.trim(), style: f.style.trim(),
              greeting: f.greeting.trim(), questions: splitLines(f.questions),
              color: f.color, color2: f.color2, skills: f.skills,
              kb_doc_ids: f.kb_doc_ids, mcp_tools: f.mcp_tools, status: f.status,
            };
            if (editing.value) await API.put('/api/admin/experts/' + editing.value.db_id, payload);
            else await API.post('/api/admin/experts', payload);
          }
          ui.toast(editing.value ? '配置已保存' : (kind.value === 'team' ? '专家团已创建' : '专家已创建'));
          showForm.value = false;
          await load(true);
        } catch (e) {
          ui.toast(e.message, 'err');
        } finally {
          saving.value = false;
        }
      }

      async function toggleStatus(item) {
        const isTeam = !item.role_key;
        busy.value = true;
        try {
          const base = isTeam ? '/api/admin/expert-teams/' : '/api/admin/experts/';
          const r = await API.post(base + item.db_id + '/status', {});
          ui.toast(r.status === 'active' ? '已上线' : '已停用，患者端不再展示');
          await load(true);
        } catch (e) { ui.toast(e.message, 'err'); }
        finally { busy.value = false; }
      }

      async function remove(item) {
        const isTeam = !item.role_key;
        if (!window.confirm('删除「' + item.name + '」？该操作不可恢复。')) return;
        try {
          await API.del((isTeam ? '/api/admin/expert-teams/' : '/api/admin/experts/') + item.db_id);
          ui.toast('已删除');
          await load(true);
        } catch (e) { ui.toast(e.message, 'err'); }
      }

      return {
        data, loading, saving, busy, tab, q, kbQuery, showForm, kind, editing, form,
        customTool, showCustomTool, catalog, stats, experts, teams, filteredExperts,
        filteredTeams, filteredKb, roleName, COLORS,
        load, openCreate, openEditExpert, openEditTeam, hasSkill, toggleSkill, hasKb,
        toggleKb, hasTool, toggleTool, addCustomTool, hasMember, toggleMember, memberOrder,
        chosenMembers, customTools, pickColor, orbStyle, save, toggleStatus, remove,
      };
    },
    template: `
      <div>
        <div v-if="loading" class="empty">正在加载专家配置…</div>
        <div v-else-if="data">
          <div class="adm-hero">
            <div class="adm-hero-copy">
              <div class="expert-kicker"><span class="live-dot"></span> 数字人能力配置中心</div>
              <h2>专家管理</h2>
              <p>为每位数字人设定专科人设、绑定专属知识库、勾选可执行技能，并授权外部工具（MCP）。配置立即对患者端「专家会诊」生效。</p>
              <div class="adm-hero-tags">
                <span><b>{{ stats.experts }}</b> 位专家</span>
                <span><b>{{ stats.teams }}</b> 个专家团</span>
                <span><b>{{ stats.kb_bound }}</b> 篇知识库已绑定</span>
                <span><b>{{ stats.sessions }}</b> 次会诊</span>
              </div>
            </div>
            <div class="adm-hero-orb"></div>
          </div>

          <div class="adm-bar mt14">
            <div class="tabs" style="border:none;flex:1">
              <button class="tab" :class="{active: tab==='expert'}" @click="tab='expert'">
                专家 <span class="tcount">{{ experts.length }}</span>
              </button>
              <button class="tab" :class="{active: tab==='team'}" @click="tab='team'">
                专家团 <span class="tcount">{{ teams.length }}</span>
              </button>
            </div>
            <div class="top-search" style="width:220px">
              <span class="si"><mb-icon name="search" :size="14"/></span>
              <input v-model="q" placeholder="搜索名称、科室或标签">
            </div>
            <button class="btn" @click="openCreate">
              <mb-icon name="plus" :size="14"/> {{ tab==='team' ? '新建专家团' : '新建专家' }}
            </button>
          </div>

          <!-- 专家 -->
          <div v-if="tab==='expert'">
            <div class="ea-grid mt14">
              <div class="ea-card" v-for="e in filteredExperts" :key="e.code" :class="{paused: e.status!=='active'}">
                <div class="ea-top">
                  <div class="expert-orb" :style="orbStyle(e)"><span>{{ e.initials }}</span></div>
                  <div class="grow" style="min-width:0">
                    <div class="ea-name">{{ e.name }}
                      <span class="tag" :class="e.status==='active' ? 'ok' : 'soft'">{{ e.status==='active' ? '在线' : '已停用' }}</span>
                    </div>
                    <div class="expert-title">{{ e.title }}</div>
                    <div class="expert-org">{{ e.org }} · 从业 {{ e.years }} 年</div>
                  </div>
                </div>
                <div class="expert-tags">
                  <span class="tag soft" v-for="t in e.tags" :key="t">{{ t }}</span>
                </div>
                <p class="expert-intro">{{ e.intro || '尚未填写人设介绍' }}</p>
                <div class="ea-caps">
                  <div class="ea-cap">
                    <span class="ea-cap-k"><mb-icon name="database" :size="12"/> 知识库</span>
                    <span class="ea-cap-v">{{ e.kb_docs.length }} 篇</span>
                  </div>
                  <div class="ea-cap">
                    <span class="ea-cap-k"><mb-icon name="sparkles" :size="12"/> 技能</span>
                    <span class="ea-cap-v">{{ e.skills.length }} 项</span>
                  </div>
                  <div class="ea-cap">
                    <span class="ea-cap-k"><mb-icon name="cpu" :size="12"/> MCP</span>
                    <span class="ea-cap-v">{{ e.tools.length }} 个</span>
                  </div>
                  <div class="ea-cap">
                    <span class="ea-cap-k"><mb-icon name="stethoscope" :size="12"/> 会诊</span>
                    <span class="ea-cap-v">{{ e.sessions }} 次</span>
                  </div>
                </div>
                <div class="ea-chips">
                  <span class="chip skill" v-for="s in e.skills.slice(0,4)" :key="s.key">{{ s.name }}</span>
                  <span class="chip more" v-if="e.skills.length>4">+{{ e.skills.length - 4 }}</span>
                </div>
                <div class="ea-chips">
                  <span class="chip tool" v-for="t in e.tools.slice(0,3)" :key="t.key">
                    <mb-icon name="cpu" :size="10"/> {{ t.name }}
                  </span>
                  <span class="chip more" v-if="e.tools.length>3">+{{ e.tools.length - 3 }}</span>
                  <span class="chip none" v-if="!e.tools.length">未授权外部工具</span>
                </div>
                <div class="ea-foot">
                  <button class="btn sm ghost" @click="openEditExpert(e)"><mb-icon name="edit" :size="12"/> 配置</button>
                  <button class="btn sm ghost" @click="toggleStatus(e)" :disabled="busy">
                    {{ e.status==='active' ? '停用' : '上线' }}
                  </button>
                  <button class="msg-tool" style="margin-left:auto" @click="remove(e)"><mb-icon name="trash" :size="12"/></button>
                </div>
              </div>
            </div>
            <div class="empty" v-if="!filteredExperts.length">没有匹配的专家，换个关键词或新建一位。</div>
          </div>

          <!-- 专家团 -->
          <div v-else>
            <div class="ea-grid mt14">
              <div class="ea-card" v-for="t in filteredTeams" :key="t.code" :class="{paused: t.status!=='active'}">
                <div class="ea-top">
                  <div class="team-orbs big">
                    <span v-for="m in t.members.slice(0,3)" :key="m.id" :style="orbStyle(m)">{{ m.initials }}</span>
                  </div>
                  <div class="grow" style="min-width:0">
                    <div class="ea-name">{{ t.name }}
                      <span class="tag" :class="t.status==='active' ? 'ok' : 'soft'">{{ t.status==='active' ? '在线' : '已停用' }}</span>
                    </div>
                    <div class="expert-title">{{ t.members.length }} 位专家 · 依次会诊</div>
                    <div class="expert-org">{{ t.members.map((m) => m.name).join(' · ') }}</div>
                  </div>
                </div>
                <p class="expert-intro">{{ t.desc || '尚未填写团队说明' }}</p>
                <div class="ea-caps">
                  <div class="ea-cap"><span class="ea-cap-k"><mb-icon name="database" :size="12"/> 知识库</span><span class="ea-cap-v">{{ t.kb_docs.length }} 篇</span></div>
                  <div class="ea-cap"><span class="ea-cap-k"><mb-icon name="sparkles" :size="12"/> 技能</span><span class="ea-cap-v">{{ t.skills.length }} 项</span></div>
                  <div class="ea-cap"><span class="ea-cap-k"><mb-icon name="cpu" :size="12"/> MCP</span><span class="ea-cap-v">{{ t.tools.length }} 个</span></div>
                  <div class="ea-cap"><span class="ea-cap-k"><mb-icon name="stethoscope" :size="12"/> 会诊</span><span class="ea-cap-v">{{ t.sessions }} 次</span></div>
                </div>
                <div class="ea-chips">
                  <span class="chip skill" v-for="s in t.skills.slice(0,4)" :key="s.key">{{ s.name }}</span>
                  <span class="chip more" v-if="t.skills.length>4">+{{ t.skills.length - 4 }}</span>
                </div>
                <div class="ea-chips">
                  <span class="chip tool" v-for="x in t.tools.slice(0,3)" :key="x.key"><mb-icon name="cpu" :size="10"/> {{ x.name }}</span>
                  <span class="chip more" v-if="t.tools.length>3">+{{ t.tools.length - 3 }}</span>
                  <span class="chip none" v-if="!t.tools.length">未授权外部工具</span>
                </div>
                <div class="ea-foot">
                  <button class="btn sm ghost" @click="openEditTeam(t)"><mb-icon name="edit" :size="12"/> 配置</button>
                  <button class="btn sm ghost" @click="toggleStatus(t)" :disabled="busy">{{ t.status==='active' ? '停用' : '上线' }}</button>
                  <button class="msg-tool" style="margin-left:auto" @click="remove(t)"><mb-icon name="trash" :size="12"/></button>
                </div>
              </div>
            </div>
            <div class="empty" v-if="!filteredTeams.length">还没有专家团。选 2–4 位专家组成多学科团队，患者即可一次召唤。</div>
          </div>

          <!-- 配置弹窗 -->
          <div class="mask" v-if="showForm" @click.self="showForm = false">
            <div class="modal wide">
              <div class="modal-head">
                <h3>{{ (editing ? '编辑' : '新建') + (kind==='team' ? '专家团' : '专家数字人') }}</h3>
                <span class="tiny faint" style="margin-left:8px">{{ kind==='team' ? '成员按顺序依次发言' : '配置对患者端即时生效' }}</span>
                <button class="icon-btn" style="margin-left:auto" @click="showForm = false"><mb-icon name="close" :size="15"/></button>
              </div>
              <div class="modal-body">
                <!-- 基本信息 -->
                <div class="form-sec">基本信息</div>
                <div class="grid g2" style="gap:12px">
                  <div class="field" style="margin-top:0">
                    <label>{{ kind==='team' ? '团队名称' : '姓名' }}</label>
                    <input class="input" v-model="form.name" :placeholder="kind==='team' ? '如 老年综合评估专家团' : '如 陈志远'">
                  </div>
                  <div class="field" style="margin-top:0" v-if="kind==='expert'">
                    <label>科室</label>
                    <input class="input" v-model="form.dept" placeholder="如 心血管内科">
                  </div>
                  <div class="field" style="margin-top:0" v-else>
                    <label>擅长标签<span class="opt">（逗号分隔）</span></label>
                    <input class="input" v-model="form.tags" placeholder="如 难治性高血压、限盐落地">
                  </div>
                </div>

                <template v-if="kind==='expert'">
                  <div class="grid g2" style="gap:12px;margin-top:12px">
                    <div class="field" style="margin-top:0">
                      <label>职称</label>
                      <input class="input" v-model="form.title" placeholder="如 主任医师 · 心血管内科">
                    </div>
                    <div class="field" style="margin-top:0">
                      <label>所属机构</label>
                      <input class="input" v-model="form.org" placeholder="如 市第一人民医院">
                    </div>
                  </div>
                  <div class="grid g3" style="gap:12px;margin-top:12px">
                    <div class="field" style="margin-top:0">
                      <label>专科模板<span class="opt">（决定离线作答侧重）</span></label>
                      <select class="select" v-model="form.role_key">
                        <option v-for="r in catalog.roles" :key="r.key" :value="r.key">{{ r.name }}</option>
                      </select>
                    </div>
                    <div class="field" style="margin-top:0">
                      <label>从业年限</label>
                      <input class="input num" type="number" min="0" max="60" v-model.number="form.years">
                    </div>
                    <div class="field" style="margin-top:0">
                      <label>年接诊量<span class="opt">（选填）</span></label>
                      <input class="input" v-model="form.cases" placeholder="如 3200+">
                    </div>
                  </div>
                  <div class="field">
                    <label>擅长标签<span class="opt">（逗号分隔，最多 8 个）</span></label>
                    <input class="input" v-model="form.tags" placeholder="高血压、冠心病、血压波动">
                  </div>
                  <div class="field">
                    <label>一句话介绍</label>
                    <textarea class="input" rows="2" v-model="form.intro" placeholder="擅长什么、习惯怎么判断问题"></textarea>
                  </div>
                  <div class="grid g2" style="gap:12px">
                    <div class="field" style="margin-top:0">
                      <label>沟通风格</label>
                      <input class="input" v-model="form.style" placeholder="如 先看数据再下结论，说话稳">
                    </div>
                    <div class="field" style="margin-top:0">
                      <label>头像主色</label>
                      <div class="color-row">
                        <button v-for="p in COLORS" :key="p[0]" class="color-dot"
                                :class="{active: form.color===p[0]}" :style="{background: 'linear-gradient(135deg,' + p[0] + ',' + p[1] + ')'}"
                                @click="pickColor(p)"></button>
                      </div>
                    </div>
                  </div>
                  <div class="field">
                    <label>开场白<span class="opt">（会诊开始时自动发送）</span></label>
                    <textarea class="input" rows="2" v-model="form.greeting" placeholder="我是……，已经看过您的档案，我们直接说重点。"></textarea>
                  </div>
                  <div class="field">
                    <label>建议问题<span class="opt">（每行一条，最多 5 条）</span></label>
                    <textarea class="input" rows="3" v-model="form.questions" placeholder="我的血压为什么忽高忽低？&#10;最近有点胸闷，需要马上就医吗？"></textarea>
                  </div>
                </template>

                <template v-else>
                  <div class="field">
                    <label>团队说明</label>
                    <textarea class="input" rows="2" v-model="form.desc" placeholder="什么情况下召唤这个团队，各位专家如何分工"></textarea>
                  </div>
                  <div class="field">
                    <label>适用场景</label>
                    <input class="input" v-model="form.scenario" placeholder="如 适合血压反复不达标、晨峰明显的患者">
                  </div>
                  <div class="form-sec">团队成员<span class="opt">（按点击顺序依次发言）</span></div>
                  <div class="member-pick">
                    <button class="member-chip" v-for="e in experts" :key="e.code"
                            :class="{active: hasMember(e.code)}" @click="toggleMember(e.code)">
                      <span class="mc-orb" :style="orbStyle(e)">{{ e.initials }}</span>
                      <span class="mc-name">{{ e.name }}<small>{{ e.dept }}</small></span>
                      <span class="mc-order" v-if="hasMember(e.code)">{{ memberOrder(e.code) }}</span>
                    </button>
                  </div>
                  <div class="tiny faint" style="margin-top:6px" v-if="chosenMembers.length">
                    发言顺序：{{ chosenMembers.map((m) => m.name).join(' → ') }}
                  </div>
                </template>

                <!-- 知识库 -->
                <div class="form-sec">知识库绑定<span class="opt">（不选则使用全库检索）</span></div>
                <div class="kb-picker">
                  <div class="kb-pick-head">
                    <div class="top-search" style="width:240px">
                      <span class="si"><mb-icon name="search" :size="13"/></span>
                      <input v-model="kbQuery" placeholder="搜索文档标题或分类">
                    </div>
                    <span class="tiny faint">已选 {{ form.kb_doc_ids.length }} 篇 · 会诊时只在这些文档内检索证据</span>
                  </div>
                  <div class="kb-pick-list">
                    <button class="kb-pick" v-for="d in filteredKb" :key="d.id"
                            :class="{active: hasKb(d.id)}" @click="toggleKb(d.id)">
                      <span class="kbp-check"><mb-icon v-if="hasKb(d.id)" name="check" :size="11"/></span>
                      <span class="kbp-title">{{ d.title }}</span>
                      <span class="tag soft">{{ d.category }}</span>
                    </button>
                    <div class="tiny faint" v-if="!filteredKb.length" style="padding:8px">没有匹配的文档</div>
                  </div>
                </div>

                <!-- 技能 -->
                <div class="form-sec">技能<span class="opt">（可执行的专业动作，会写入会诊提示词）</span></div>
                <div class="skill-grid">
                  <button class="skill-card" v-for="s in catalog.skills" :key="s.key"
                          :class="{active: hasSkill(s.key)}" @click="toggleSkill(s.key)">
                    <span class="sk-ico"><mb-icon :name="s.icon" :size="13"/></span>
                    <span class="sk-txt"><b>{{ s.name }}</b><small>{{ s.desc }}</small></span>
                    <mb-icon v-if="hasSkill(s.key)" name="check" :size="13"/>
                  </button>
                </div>

                <!-- MCP -->
                <div class="form-sec">外部工具（MCP）<span class="opt">（授权后可调用的数据与系统能力）</span></div>
                <div class="mcp-list">
                  <button class="mcp-row" v-for="m in catalog.mcp" :key="m.key"
                          :class="{active: hasTool(m.key)}" @click="toggleTool(m)">
                    <span class="mcp-check"><mb-icon v-if="hasTool(m.key)" name="check" :size="11"/></span>
                    <span class="mcp-main"><b>{{ m.name }}</b><small>{{ m.desc }}</small></span>
                    <span class="tag" :class="m.builtin ? 'primary' : 'soft'">{{ m.builtin ? '内置' : '外部服务' }}</span>
                  </button>
                  <div class="mcp-row custom" v-for="t in customTools" :key="t.key">
                    <span class="mcp-check on"><mb-icon name="check" :size="11"/></span>
                    <span class="mcp-main"><b>{{ t.name }}</b><small>{{ t.desc || '管理员自定义工具' }}</small></span>
                    <span class="tag amber">自定义</span>
                    <button class="msg-tool" @click="toggleTool(t)"><mb-icon name="close" :size="11"/></button>
                  </div>
                </div>
                <div class="custom-tool" v-if="showCustomTool">
                  <input class="input" v-model="customTool.name" placeholder="工具名称，如 跌倒风险问卷">
                  <input class="input" v-model="customTool.desc" placeholder="用途说明，如 调用老年跌倒评估量表">
                  <button class="btn sm" @click="addCustomTool">添加</button>
                  <button class="btn sm ghost" @click="showCustomTool = false">取消</button>
                </div>
                <button class="btn sm ghost mt10" v-else @click="showCustomTool = true">
                  <mb-icon name="plus" :size="12"/> 添加自定义 MCP 工具
                </button>

                <div class="form-sec">上线状态</div>
                <label class="switch" style="margin-bottom:4px">
                  <input type="checkbox" :checked="form.status === 'active'"
                         @change="form.status = $event.target.checked ? 'active' : 'paused'">
                  <i></i>
                  <span>{{ form.status === 'active' ? '已上线，患者可召唤' : '已停用，患者端不展示' }}</span>
                </label>
              </div>
              <div class="modal-foot">
                <button class="btn ghost" @click="showForm = false">取消</button>
                <button class="btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存配置' }}</button>
              </div>
            </div>
          </div>
        </div>
      </div>`,
  };
})();
