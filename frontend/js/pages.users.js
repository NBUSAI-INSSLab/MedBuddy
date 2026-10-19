/* 用户管理：账号查询、新建、编辑、重置密码、启停与删除 */
(function () {
  const { ref, computed, onMounted } = Vue;
  const Pages = (window.Pages = window.Pages || {});

  Pages.users = {
    components: { MbIcon: Mb.Icon },
    setup() {
      const data = ref(null);
      const options = ref([]);
      const loading = ref(true);
      const saving = ref(false);
      const q = ref(Store.params.q || '');
      const role = ref(Store.params.role || '');
      const status = ref('');
      const showForm = ref(false);
      const editing = ref(null);
      const form = ref(blank());
      const pwdTarget = ref(null);
      const pwdValue = ref('');
      const pwdResult = ref(null);
      const busy = ref(false);

      const me = computed(() => Store.user || {});
      const isAdmin = computed(() => me.value.role === 'admin');
      const items = computed(() => (data.value ? data.value.items : []));
      const stats = computed(() => (data.value ? data.value.stats : {}));
      const roleMeta = computed(() => (data.value ? data.value.role_meta : {}));

      function blank() {
        return { username: '', display_name: '', role: 'patient', title: '签约居民',
                 phone: '', patient_id: '', password: '', status: 'active' };
      }

      async function load(silent) {
        if (!silent) loading.value = true;
        try {
          const qs = new URLSearchParams();
          if (q.value.trim()) qs.set('q', q.value.trim());
          if (role.value) qs.set('role', role.value);
          if (status.value) qs.set('status', status.value);
          data.value = await API.get('/api/users' + (qs.toString() ? '?' + qs : ''));
        } catch (e) {
          if (!silent) ui.toast(e.message, 'err');
        } finally {
          loading.value = false;
        }
      }
      async function loadOptions() {
        try { options.value = await API.get('/api/users/options'); } catch (e) {}
      }
      onMounted(async () => { await Promise.all([load(), loadOptions()]); });

      function openCreate() {
        editing.value = null;
        form.value = blank();
        if (!isAdmin.value) form.value.role = 'patient';
        showForm.value = true;
      }
      function openEdit(u) {
        editing.value = u;
        form.value = {
          username: u.username, display_name: u.display_name, role: u.role,
          title: u.title, phone: u.phone, patient_id: u.patient_id || '',
          password: '', status: u.status,
        };
        showForm.value = true;
      }
      const roleChoices = computed(() => {
        if (isAdmin.value) return ['admin', 'doctor', 'patient'];
        return ['patient'];
      });
      const patientOptions = computed(() => {
        const self = editing.value ? editing.value.patient_id : null;
        return options.value.filter((p) => !p.bound_user || p.id === self);
      });
      function onRoleChange() {
        if (form.value.role !== 'patient') form.value.patient_id = '';
      }
      async function save() {
        if (!form.value.display_name.trim()) return ui.toast('请填写姓名', 'err');
        if (!editing.value && !form.value.username.trim()) return ui.toast('请填写登录账号', 'err');
        if (!editing.value && (form.value.password || '').length < 6) {
          return ui.toast('初始密码至少 6 位', 'err');
        }
        if (form.value.role === 'patient' && !form.value.patient_id) {
          return ui.toast('患者账号需要绑定一份健康档案', 'err');
        }
        saving.value = true;
        try {
          const payload = {
            display_name: form.value.display_name.trim(), role: form.value.role,
            title: form.value.title.trim(), phone: form.value.phone.trim(),
            patient_id: form.value.patient_id ? Number(form.value.patient_id) : null,
            status: form.value.status,
          };
          if (form.value.password) payload.password = form.value.password;
          if (editing.value) {
            await API.put('/api/users/' + editing.value.id, payload);
            ui.toast('账号已更新');
          } else {
            payload.username = form.value.username.trim();
            await API.post('/api/users', payload);
            ui.toast('账号已创建');
          }
          showForm.value = false;
          await Promise.all([load(true), loadOptions()]);
        } catch (e) { ui.toast(e.message, 'err'); }
        finally { saving.value = false; }
      }

      async function toggle(u) {
        busy.value = true;
        try {
          const r = await API.post('/api/users/' + u.id + '/status', {});
          ui.toast(r.status === 'active' ? '账号已启用' : '账号已停用');
          await load(true);
        } catch (e) { ui.toast(e.message, 'err'); }
        finally { busy.value = false; }
      }

      function openPwd(u) { pwdTarget.value = u; pwdValue.value = ''; pwdResult.value = null; }
      async function submitPwd() {
        if (pwdValue.value && pwdValue.value.length < 6) return ui.toast('密码至少 6 位', 'err');
        busy.value = true;
        try {
          const r = await API.post('/api/users/' + pwdTarget.value.id + '/password',
            { password: pwdValue.value });
          pwdResult.value = r;
          pwdValue.value = '';
          ui.toast('密码已重置');
        } catch (e) { ui.toast(e.message, 'err'); }
        finally { busy.value = false; }
      }

      async function remove(u) {
        if (!window.confirm('删除账号「' + u.display_name + '（' + u.username + '）」？其患者档案与历史数据会保留。')) return;
        try {
          await API.del('/api/users/' + u.id);
          ui.toast('账号已删除');
          await Promise.all([load(true), loadOptions()]);
        } catch (e) { ui.toast(e.message, 'err'); }
      }

      const themeName = (id) => {
        const t = Store.themes.find((x) => x.id === id);
        return t ? t.name : '默认';
      };
      const themeColor = (id) => {
        const t = Store.themes.find((x) => x.id === id);
        return t ? t.primary : 'var(--faint)';
      };
      function ago(t) {
        if (!t) return '从未登录';
        const d = new Date(t.replace(/-/g, '/'));
        const s = Math.floor((Date.now() - d.getTime()) / 1000);
        if (s < 60) return '刚刚';
        if (s < 3600) return Math.floor(s / 60) + ' 分钟前';
        if (s < 86400) return Math.floor(s / 3600) + ' 小时前';
        return Math.floor(s / 86400) + ' 天前';
      }
      const roleCls = { admin: 'red', doctor: 'primary', patient: 'soft' };
      function canManage(u) { return u.manageable; }
      function openPatient(u) { if (u.patient_id) ui.go('patient', { id: u.patient_id }); }

      return { data, loading, saving, busy, q, role, status, items, stats, roleMeta,
               showForm, editing, form, roleChoices, patientOptions, onRoleChange,
               pwdTarget, pwdValue, pwdResult, me, isAdmin,
               load, openCreate, openEdit, save, toggle, openPwd, submitPwd, remove,
               themeName, themeColor, ago, roleCls, canManage, openPatient };
    },
    template: `
      <div>
        <div v-if="loading" class="empty">正在加载账号数据…</div>
        <div v-else>
          <div class="grid g4">
            <div class="card kpi">
              <div class="kpi-top"><span class="kpi-ico"><mb-icon name="usercheck" :size="15"/></span>账号总数</div>
              <div class="kpi-val num">{{ stats.total }}<small>个</small></div>
              <div class="kpi-foot">已绑定健康档案 {{ stats.bound }} 个</div>
            </div>
            <div class="card kpi">
              <div class="kpi-top"><span class="kpi-ico" style="background:#eff6ff;color:#2563eb"><mb-icon name="shield" :size="15"/></span>医护 / 管理</div>
              <div class="kpi-val num">{{ stats.doctor + stats.admin }}<small>个</small></div>
              <div class="kpi-foot">医生 {{ stats.doctor }} · 管理员 {{ stats.admin }}</div>
            </div>
            <div class="card kpi">
              <div class="kpi-top"><span class="kpi-ico" style="background:#fff7ed;color:#ea580c"><mb-icon name="heart" :size="15"/></span>居民账号</div>
              <div class="kpi-val num">{{ stats.patient }}<small>个</small></div>
              <div class="kpi-foot">可查看本人档案并使用智能助手</div>
            </div>
            <div class="card kpi">
              <div class="kpi-top"><span class="kpi-ico" style="background:#f1f5f9;color:#64748b"><mb-icon name="alert" :size="15"/></span>已停用</div>
              <div class="kpi-val num">{{ stats.disabled }}<small>个</small></div>
              <div class="kpi-foot">停用后无法登录，数据保留</div>
            </div>
          </div>

          <div class="card flush mt14">
            <div class="card-head" style="padding-bottom:12px;flex-wrap:wrap;gap:10px">
              <h3>账号列表</h3>
              <span class="sub">{{ isAdmin ? '管理员可管理全部账号' : '医生可管理居民账号' }}</span>
              <div class="right" style="gap:8px">
                <div class="top-search" style="width:190px">
                  <span class="si"><mb-icon name="search" :size="13"/></span>
                  <input v-model="q" placeholder="账号 / 姓名" @keyup.enter="load()">
                </div>
                <select class="select" style="width:104px;padding:7px 9px;font-size:12px" v-model="role" @change="load()">
                  <option value="">全部角色</option>
                  <option value="admin">管理员</option>
                  <option value="doctor">医生</option>
                  <option value="patient">患者</option>
                </select>
                <select class="select" style="width:104px;padding:7px 9px;font-size:12px" v-model="status" @change="load()">
                  <option value="">全部状态</option>
                  <option value="active">启用</option>
                  <option value="disabled">停用</option>
                </select>
                <button class="btn sm" @click="openCreate"><mb-icon name="plus" :size="13"/> 新建账号</button>
              </div>
            </div>
            <table class="table">
              <thead>
                <tr>
                  <th>账号 / 姓名</th><th style="width:96px">角色</th><th style="width:150px">关联档案</th>
                  <th style="width:126px">联系方式</th><th style="width:86px">主题</th>
                  <th style="width:88px">状态</th><th style="width:104px">最近登录</th>
                  <th style="width:166px">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="u in items" :key="u.id" :class="{'row-off': u.status !== 'active'}">
                  <td>
                    <div class="row" style="gap:8px">
                      <span class="u-ava" :style="{background: u.role === 'admin' ? '#334155' : (u.role === 'doctor' ? 'var(--primary)' : '#0ea5e9')}">{{ u.display_name.slice(-2) }}</span>
                      <div style="min-width:0">
                        <div class="bold small">{{ u.display_name }}
                          <span v-if="u.is_self" class="tag soft" style="margin-left:4px">本人</span>
                        </div>
                        <div class="tiny faint num">{{ u.username }}</div>
                      </div>
                    </div>
                  </td>
                  <td><span class="tag" :class="roleCls[u.role]">{{ u.role_cn }}</span></td>
                  <td>
                    <div v-if="u.patient_name" class="row" style="gap:5px;cursor:pointer" @click="openPatient(u)">
                      <span class="small">{{ u.patient_name }}</span>
                      <mb-icon name="arrow" :size="11" style="color:var(--faint)"/>
                    </div>
                    <span v-else class="tiny faint">{{ u.role === 'patient' ? '未绑定' : '—' }}</span>
                  </td>
                  <td class="small num">{{ u.phone || '—' }}</td>
                  <td>
                    <span class="row" style="gap:5px">
                      <i class="theme-mini" :style="{background: themeColor(u.theme)}"></i>
                      <span class="tiny">{{ themeName(u.theme) }}</span>
                    </span>
                  </td>
                  <td>
                    <span class="dev-state" :class="u.status === 'active' ? 'ok' : 'off'">
                      <i></i>{{ u.status === 'active' ? '启用' : '停用' }}
                    </span>
                  </td>
                  <td class="tiny faint">{{ ago(u.last_login_at) }}</td>
                  <td>
                    <div v-if="canManage(u)" class="row" style="gap:5px;flex-wrap:wrap">
                      <button class="btn sm ghost" @click="openEdit(u)">编辑</button>
                      <button class="btn sm ghost" @click="openPwd(u)">密码</button>
                      <button v-if="!u.is_self" class="btn sm ghost" :disabled="busy" @click="toggle(u)">
                        {{ u.status === 'active' ? '停用' : '启用' }}
                      </button>
                      <button v-if="!u.is_self" class="msg-tool" title="删除" @click="remove(u)">
                        <mb-icon name="trash" :size="13"/>
                      </button>
                      <span v-else class="tiny faint">当前登录</span>
                    </div>
                    <span v-else class="tiny faint">只读</span>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-if="!items.length" class="empty">没有符合条件的账号</div>
            <div class="table-note">
              <mb-icon name="shield" :size="13"/>
              <span>密码与账号信息保存在本地 SQLite；停用账号会立即失去登录权限，历史数据不做删除。</span>
            </div>
          </div>
        </div>

        <div v-if="showForm" class="mask" @click.self="showForm = false">
          <div class="modal" style="max-width:560px">
            <div class="modal-head">
              <h3>{{ editing ? '编辑账号' : '新建账号' }}</h3>
              <button class="icon-btn" style="margin-left:auto" @click="showForm = false"><mb-icon name="close" :size="15"/></button>
            </div>
            <div class="modal-body">
              <div class="grid g2" style="gap:12px">
                <div class="form-col">
                  <label>登录账号</label>
                  <input class="input" v-model="form.username" :disabled="!!editing" placeholder="字母开头，3–20 位">
                </div>
                <div class="form-col">
                  <label>姓名</label>
                  <input class="input" v-model="form.display_name" placeholder="真实姓名">
                </div>
              </div>
              <div class="grid g2" style="gap:12px;margin-top:12px">
                <div class="form-col">
                  <label>角色</label>
                  <select class="select" v-model="form.role" :disabled="!!editing && editing.is_self" @change="onRoleChange">
                    <option v-for="r in roleChoices" :key="r" :value="r">{{ roleMeta[r] || r }}</option>
                  </select>
                  <div class="field-help">{{ roleMeta[form.role] }}</div>
                </div>
                <div class="form-col">
                  <label>职称 / 备注</label>
                  <input class="input" v-model="form.title" placeholder="如 社区慢病管理医师">
                </div>
              </div>
              <div class="grid g2" style="gap:12px;margin-top:12px">
                <div class="form-col">
                  <label>手机号</label>
                  <input class="input num" v-model="form.phone" maxlength="11" placeholder="11 位手机号">
                </div>
                <div class="form-col">
                  <label>账号状态</label>
                  <select class="select" v-model="form.status" :disabled="editing && editing.is_self">
                    <option value="active">启用</option>
                    <option value="disabled">停用</option>
                  </select>
                </div>
              </div>
              <div class="form-col" style="margin-top:12px" v-if="form.role === 'patient'">
                <label>绑定健康档案</label>
                <select class="select" v-model="form.patient_id">
                  <option value="">请选择档案</option>
                  <option v-for="p in patientOptions" :key="p.id" :value="p.id">
                    #{{ p.id }} {{ p.name }} · {{ p.gender || '—' }} · {{ p.phone || '无电话' }}
                  </option>
                </select>
                <div class="field-help">一份档案只能绑定一个居民账号，已被占用的档案不会出现在列表中。</div>
              </div>
              <div class="form-col" style="margin-top:12px">
                <label>{{ editing ? '重置密码（留空则不修改）' : '初始密码' }}</label>
                <input class="input" type="text" v-model="form.password" autocomplete="new-password"
                       :placeholder="editing ? '不修改请留空' : '至少 6 位'">
              </div>
            </div>
            <div class="modal-foot">
              <button class="btn ghost" @click="showForm = false">取消</button>
              <button class="btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : (editing ? '保存修改' : '创建账号') }}</button>
            </div>
          </div>
        </div>

        <div v-if="pwdTarget" class="mask" @click.self="pwdTarget = null">
          <div class="modal" style="max-width:430px">
            <div class="modal-head">
              <h3>重置密码 · {{ pwdTarget.display_name }}</h3>
              <button class="icon-btn" style="margin-left:auto" @click="pwdTarget = null"><mb-icon name="close" :size="15"/></button>
            </div>
            <div class="modal-body">
              <div class="form-col">
                <label>新密码</label>
                <input class="input" v-model="pwdValue" placeholder="至少 6 位，留空由系统生成">
              </div>
              <div v-if="pwdResult" class="pwd-box">
                <div class="tiny faint">新密码（请转告本人，仅本次显示）</div>
                <div class="pwd-val num">{{ pwdResult.password }}</div>
              </div>
              <div class="field-help" style="margin-top:10px">
                账号：{{ pwdTarget.username }} · 重置后原密码立即失效，本人登录后可在平台配置中修改主题等偏好。
              </div>
            </div>
            <div class="modal-foot">
              <button class="btn ghost" @click="pwdTarget = null">关闭</button>
              <button class="btn" :disabled="busy" @click="submitPwd">{{ busy ? '处理中…' : '重置密码' }}</button>
            </div>
          </div>
        </div>
      </div>`,
  };
})();
