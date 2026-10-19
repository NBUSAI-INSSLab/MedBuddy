/* 患者管理 + 患者全景 */
(function () {
  const { ref, computed, onMounted, watch } = Vue;
  const Pages = (window.Pages = window.Pages || {});

  Pages.patients = {
    components: { MbIcon: Mb.Icon },
    setup() {
      const list = ref([]);
      const total = ref(0);
      const loading = ref(true);
      const q = ref(Store.params.q || '');
      const risk = ref(Store.params.risk || '');
      const disease = ref('');
      const page = ref(1);
      const size = 12;
      const diseases = ['高血压', '2型糖尿病', '冠心病', '慢性肾脏病', '慢阻肺', '血脂异常'];

      async function load() {
        loading.value = true;
        try {
          const params = new URLSearchParams({ page: page.value, size });
          if (q.value) params.set('q', q.value);
          if (risk.value) params.set('risk', risk.value);
          if (disease.value) params.set('disease', disease.value);
          const d = await API.get('/api/patients?' + params.toString());
          list.value = d.items;
          total.value = d.total;
        } catch (e) {
          ui.toast(e.message, 'err');
        } finally {
          loading.value = false;
        }
      }
      onMounted(load);
      watch([risk, disease], () => { page.value = 1; load(); });
      let timer = null;
      watch(q, () => { clearTimeout(timer); timer = setTimeout(() => { page.value = 1; load(); }, 260); });
      watch(page, load);

      const pages = computed(() => Math.max(1, Math.ceil(total.value / size)));
      function open(id) { ui.go('patient', { id }); }
      function chat(id) { ui.go('chat', { patient: id }); }
      function lastMetric(p) {
        if (p.conditions.some((c) => c.includes('糖尿病'))) return '血糖管理';
        return '血压管理';
      }
      return { list, total, loading, q, risk, disease, diseases, page, pages, open, chat };
    },
    template: `
      <div>
        <div class="filters">
          <div class="search-box">
            <mb-icon name="search" :size="15"/>
            <input class="input" v-model="q" placeholder="搜索姓名、电话或社区">
          </div>
          <select class="select" v-model="risk">
            <option value="">全部风险</option>
            <option value="critical">极高危</option>
            <option value="high">高危</option>
            <option value="medium">中危</option>
            <option value="low">低危</option>
          </select>
          <select class="select" v-model="disease">
            <option value="">全部病种</option>
            <option v-for="d in diseases" :key="d" :value="d">{{ d }}</option>
          </select>
          <span class="small faint" style="margin-left:auto">共 {{ total }} 位在管患者</span>
          <button class="btn ghost sm" @click="load"><mb-icon name="activity" :size="13"/> 刷新</button>
        </div>

        <div class="card flush">
          <table class="table">
            <thead>
              <tr>
                <th style="width:190px">患者</th>
                <th>在管诊断</th>
                <th style="width:150px">风险分层</th>
                <th style="width:130px">最近指标</th>
                <th style="width:110px">管理时长</th>
                <th style="width:100px">预警</th>
                <th style="width:150px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in list" :key="p.id" class="clickable" @click="open(p.id)">
                <td>
                  <div class="name-cell">
                    <div class="avatar" :style="{background:p.avatar_color}">{{ p.name.slice(-2) }}</div>
                    <div style="min-width:0">
                      <div class="nm">{{ p.name }}</div>
                      <div class="meta">{{ p.age }}岁{{ p.gender }} · {{ p.city.replace('宁波市','') }}</div>
                    </div>
                  </div>
                </td>
                <td>
                  <div style="display:flex;gap:4px;flex-wrap:wrap">
                    <span class="tag soft" v-for="c in p.conditions" :key="c">{{ c }}</span>
                    <span v-if="!p.conditions.length" class="faint small">—</span>
                  </div>
                </td>
                <td>
                  <div class="row" style="gap:7px">
                    <span class="tag" :class="'risk-' + p.risk_level">{{ p.risk_label }}</span>
                    <span class="small num faint">{{ p.risk_score }}</span>
                  </div>
                  <div class="progress" style="margin-top:5px;height:4px">
                    <i :style="{width: p.risk_score + '%', background: p.risk_level === 'critical' ? '#b91c1c' : p.risk_level === 'high' ? '#ea580c' : p.risk_level === 'medium' ? '#d97706' : '#059669'}"></i>
                  </div>
                </td>
                <td class="small">
                  <div v-if="p.latest_bp" class="num" style="font-weight:600">{{ p.latest_bp.sbp.toFixed(0) }}<span v-if="p.latest_bp.dbp">/{{ p.latest_bp.dbp.toFixed(0) }}</span><span class="tiny faint"> mmHg</span></div>
                  <div v-if="p.latest_glucose" class="num" :style="{fontWeight: p.latest_bp ? 400 : 600, color: p.latest_bp ? 'var(--muted)' : 'inherit'}">
                    {{ p.latest_glucose.value.toFixed(1) }}<span class="tiny faint"> mmol/L {{ p.latest_glucose.note }}</span>
                  </div>
                  <div v-if="!p.latest_bp && !p.latest_glucose" class="faint">暂无记录</div>
                </td>
                <td class="small num">{{ p.managed_days }} 天</td>
                <td>
                  <span v-if="p.open_alerts" class="tag red">{{ p.open_alerts }} 条</span>
                  <span v-else class="tag soft">无</span>
                </td>
                <td>
                  <div class="row" style="gap:6px">
                    <button class="btn sm ghost" @click.stop="open(p.id)">档案</button>
                    <button class="btn sm soft" @click.stop="chat(p.id)">AI</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="loading" class="empty">正在加载患者列表…</div>
          <div v-else-if="!list.length" class="empty">没有符合条件的患者</div>
        </div>

        <div class="between mt14">
          <span class="small faint">第 {{ page }} / {{ pages }} 页</span>
          <div class="row">
            <button class="btn sm ghost" :disabled="page<=1" @click="page--">上一页</button>
            <button class="btn sm ghost" :disabled="page>=pages" @click="page++">下一页</button>
          </div>
        </div>
      </div>`,
  };

  Pages.patient = {
    components: { MbIcon: Mb.Icon, MbLine: Mb.LineChart, MbRing: Mb.Ring, MbBars: Mb.Bars },
    setup() {
      const id = Store.params.id;
      const data = ref(null);
      const loading = ref(true);
      const tab = ref('overview');
      const metric = ref('bp');
      const showMetric = ref(false);
      const form = ref({ metric_type: 'sbp', value: '', note: '', measured_at: '' });
      const saving = ref(false);
      const dietData = ref(null);
      const dietLoading = ref(false);
      const showDietLog = ref(false);
      const savingDiet = ref(false);
      const dietForm = ref({ log_date: todayStr(), meal: 'breakfast', foods: '', calories: '', sodium: '', note: '' });
      const photoView = ref(null);

      function todayStr() {
        const d = new Date();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${d.getFullYear()}-${m}-${day}`;
      }

      async function load() {
        loading.value = true;
        try {
          data.value = await API.get('/api/patients/' + id);
          if (!data.value.series.sbp) metric.value = data.value.series.glucose ? 'glucose' : (Object.keys(data.value.series)[0] || 'bp');
        } catch (e) {
          ui.toast(e.message, 'err');
        } finally {
          loading.value = false;
        }
      }
      async function loadDiet() {
        dietLoading.value = true;
        try {
          dietData.value = await API.get('/api/patients/' + id + '/diet');
        } catch (e) {
          ui.toast(e.message, 'err');
        } finally {
          dietLoading.value = false;
        }
      }
      onMounted(() => { load(); loadDiet(); });

      const s = computed(() => (data.value ? data.value.series : {}));
      const bpPoints = computed(() => (s.value.sbp || []).map((r) => ({ label: r.measured_at, value: r.value })));
      const bpPoints2 = computed(() => (s.value.dbp || []).map((r) => ({ label: r.measured_at, value: r.value })));
      const glucosePoints = computed(() => (s.value.glucose || []).map((r) => ({ label: r.measured_at, value: r.value })));
      const weightPoints = computed(() => (s.value.weight || []).map((r) => ({ label: r.measured_at, value: r.value })));
      const hba1cPoints = computed(() => (s.value.hba1c || []).map((r) => ({ label: r.measured_at, value: r.value })));
      const pointsOf = (k) => (s.value[k] || []).map((r) => ({ label: r.measured_at, value: r.value }));

      const VITALS = [
        { key: 'hr', metric: 'heart_rate', name: '心率', unit: '次/分', digits: 0 },
        { key: 'spo2', metric: 'spo2', name: '血氧', unit: '%', digits: 0 },
        { key: 'temp', metric: 'temp', name: '体温', unit: '℃', digits: 1 },
        { key: 'hrv', metric: 'hrv', name: 'HRV', unit: 'ms', digits: 0 },
        { key: 'resp_rate', metric: 'resp_rate', name: '呼吸', unit: '次/分', digits: 0 },
      ];
      const vitals = computed(() => {
        if (!data.value) return [];
        const f = data.value.features;
        return VITALS.map((v) => {
          const x = f[v.key];
          if (!x) return null;
          return {
            ...v,
            text: Number(x.latest).toFixed(v.digits),
            avg7: x.avg7 != null ? Number(x.avg7).toFixed(v.digits) : null,
            at: x.at,
            device: x.source === 'device',
            device_sn: x.device_sn,
          };
        }).filter(Boolean);
      });

      const chart = computed(() => {
        if (!data.value) return {};
        if (metric.value === 'bp') {
          return { points: bpPoints.value, points2: bpPoints2.value, name: '收缩压', name2: '舒张压',
                   unit: 'mmHg', target: Number((data.value.features.bp_target || '140/90').split('/')[0]),
                   targetLabel: '收缩压目标 ' + (data.value.features.bp_target || '140/90'), decimals: 0 };
        }
        if (metric.value === 'glucose') {
          return { points: glucosePoints.value, points2: [], name: '血糖', unit: 'mmol/L',
                   target: 7.0, targetLabel: '空腹目标 7.0', decimals: 1 };
        }
        if (metric.value === 'weight') {
          return { points: weightPoints.value, points2: [], name: '体重', unit: 'kg', decimals: 1 };
        }
        if (metric.value === 'hba1c') {
          return { points: hba1cPoints.value, points2: [], name: '糖化血红蛋白', unit: '%',
                   target: 7.0, targetLabel: '目标 <7.0%', decimals: 1 };
        }
        if (metric.value === 'heart_rate') {
          return { points: pointsOf('heart_rate'), points2: [], name: '心率', unit: '次/分',
                   target: 100, targetLabel: '静息心率参考上限 100', decimals: 0 };
        }
        if (metric.value === 'spo2') {
          return { points: pointsOf('spo2'), points2: [], name: '血氧饱和度', unit: '%',
                   target: 94, targetLabel: '目标 ≥94%', decimals: 0 };
        }
        if (metric.value === 'temp') {
          return { points: pointsOf('temp'), points2: [], name: '体温', unit: '℃',
                   target: 37.3, targetLabel: '发热阈值 37.3℃', decimals: 1 };
        }
        if (metric.value === 'hrv') {
          return { points: pointsOf('hrv'), points2: [], name: '心率变异性', unit: 'ms', decimals: 0 };
        }
        const m = ui.METRIC[metric.value] || { name: '指标', unit: '' };
        return { points: pointsOf(metric.value), points2: [], name: m.name, unit: m.unit, decimals: 1 };
      });

      const tabs = [
        { id: 'overview', label: '健康概览' },
        { id: 'trend', label: '指标趋势' },
        { id: 'meds', label: '用药与计划' },
        { id: 'alerts', label: '预警记录' },
        { id: 'diet', label: '饮食管理' },
        { id: 'memory', label: '长期记忆' },
      ];

      const dietPlan = computed(() => (dietData.value ? dietData.value.plan : null));
      const dietSummary = computed(() => (dietData.value ? dietData.value.summary : null));

      function openDietLog(meal) {
        dietForm.value = { log_date: todayStr(), meal: meal || 'breakfast',
                           foods: '', calories: '', sodium: '', note: '' };
        showDietLog.value = true;
      }
      async function addDietLog() {
        const f = dietForm.value;
        if (!f.foods.trim()) return ui.toast('请填写吃了什么', 'err');
        savingDiet.value = true;
        try {
          const d = await API.post('/api/patients/' + id + '/diet/logs', {
            log_date: f.log_date, meal: f.meal, foods: f.foods.trim(),
            calories: f.calories === '' ? null : Number(f.calories),
            sodium: f.sodium === '' ? null : Number(f.sodium),
            note: f.note,
          });
          ui.toast(d.estimated
            ? `已记录，自动估算 ${d.calories || 0} kcal / 钠 ${d.sodium || 0} mg`
            : '饮食记录已保存');
          showDietLog.value = false;
          await loadDiet();
        } catch (e) {
          ui.toast(e.message, 'err');
        } finally {
          savingDiet.value = false;
        }
      }
      async function delDietLog(l) {
        if (!window.confirm('删除这条饮食记录？')) return;
        try {
          await API.del('/api/patients/' + id + '/diet/logs/' + l.id);
          ui.toast('记录已删除');
          await loadDiet();
        } catch (e) { ui.toast(e.message, 'err'); }
      }

      async function addMetric() {
        if (!form.value.value) return ui.toast('请输入数值', 'err');
        saving.value = true;
        try {
          await API.post('/api/patients/' + id + '/metrics', {
            metric_type: form.value.metric_type,
            value: Number(form.value.value),
            note: form.value.note,
            measured_at: form.value.measured_at || undefined,
          });
          ui.toast('指标已记录，风险分层已更新');
          showMetric.value = false;
          form.value = { metric_type: 'sbp', value: '', note: '', measured_at: '' };
          await load();
        } catch (e) {
          ui.toast(e.message, 'err');
        } finally {
          saving.value = false;
        }
      }
      async function handleAlert(a) {
        try {
          await API.post('/api/patients/' + id + '/alerts/' + a.id + '/handle', { note: '医生已确认' });
          ui.toast('预警已标记处理');
          await load();
        } catch (e) { ui.toast(e.message, 'err'); }
      }
      async function addMemory() {
        const content = window.prompt('记录一条患者长期记忆（如偏好、困难、目标）');
        if (!content) return;
        try {
          await API.post('/api/patients/' + id + '/memories', { content, kind: 'fact' });
          ui.toast('已写入长期记忆');
          await load();
        } catch (e) { ui.toast(e.message, 'err'); }
      }
      async function delMemory(m) {
        if (!window.confirm('删除这条记忆？')) return;
        await API.del('/api/patients/' + id + '/memories/' + m.id);
        await load();
      }
      async function adoptPlan() {
        const fp = data.value.followup_plan;
        try {
          await API.post('/api/patients/' + id + '/plan', { title: fp.title, goals: fp.goals });
          ui.toast('已采纳智能体随访方案');
          await load();
        } catch (e) { ui.toast(e.message, 'err'); }
      }
      function chat() { ui.go('chat', { patient: id }); }
      function back() { ui.go('patients'); }

      return { data, loading, tab, tabs, metric, chart, showMetric, form, saving, vitals,
               dietData, dietLoading, dietPlan, dietSummary, showDietLog, dietForm, savingDiet,
               openDietLog, addDietLog, delDietLog, loadDiet, photoView,
               addMetric, handleAlert, addMemory, delMemory, adoptPlan, chat, back, load };
    },
    template: `
      <div>
        <div v-if="loading" class="empty">正在加载患者全景…</div>
        <div v-else-if="data">
          <div class="row" style="margin-bottom:12px">
            <button class="btn sm ghost" @click="back">← 返回患者列表</button>
            <span class="faint tiny">患者 ID #{{ data.profile.id }}</span>
          </div>

          <div class="card">
            <div class="patient-hero">
              <div class="big-avatar" :style="{background:data.profile.avatar_color}">{{ data.profile.name.slice(-2) }}</div>
              <div class="grow" style="min-width:0">
                <div class="row" style="gap:10px;flex-wrap:wrap">
                  <h2>{{ data.profile.name }}</h2>
                  <span class="tag" :class="'risk-' + data.risk.level">{{ data.risk.label }}</span>
                  <span class="tag soft">风险分 {{ data.risk.score }}</span>
                  <span class="tag primary">在管 {{ data.features.managed_days }} 天</span>
                </div>
                <div class="meta">
                  <span>{{ data.age }} 岁 · {{ data.patient.gender }}</span>
                  <span>{{ data.patient.city }}</span>
                  <span>{{ data.patient.occupation }}</span>
                  <span>{{ data.profile.phone }}</span>
                  <span v-if="data.patient.allergies">过敏：{{ data.patient.allergies }}</span>
                </div>
                <div class="row" style="margin-top:8px;gap:6px;flex-wrap:wrap">
                  <span class="tag soft" v-for="c in data.conditions" :key="c.id">{{ c.name }} · {{ c.severity }}</span>
                </div>
              </div>
              <div class="maturity-ring">
                <mb-ring :value="data.maturity.score" :size="68" :thickness="7"/>
                <div class="maturity-txt">
                  <b>{{ data.maturity.score }}<span style="font-size:11px;font-weight:400"> /100</span></b>
                  <span>个性化成熟度 · {{ data.maturity.stage }}</span>
                </div>
              </div>
              <div style="display:flex;flex-direction:column;gap:7px">
                <button class="btn" @click="chat"><mb-icon name="sparkles" :size="15"/> 智能助手</button>
                <button class="btn ghost" @click="showMetric = true"><mb-icon name="plus" :size="14"/> 录入指标</button>
              </div>
            </div>
            <div class="tabs" style="padding:0 14px">
              <button class="tab" v-for="t in tabs" :key="t.id" :class="{active: tab===t.id}" @click="tab=t.id">{{ t.label }}</button>
            </div>
            <div class="card-body">
              <!-- 概览 -->
              <div v-if="tab==='overview'">
                <div class="tip-card" style="margin-bottom:14px">
                  <mb-icon name="brain" :size="17"/>
                  <div>{{ data.narrative }}</div>
                </div>
                <div class="vital-grid" v-if="vitals.length">
                  <div class="vital-card" v-for="v in vitals" :key="v.key">
                    <div class="vital-top">
                      <span>{{ v.name }}</span>
                      <span class="tag" :class="v.device ? 'primary' : 'soft'">{{ v.device ? '设备' : '手工' }}</span>
                    </div>
                    <div class="vital-val num">{{ v.text }}<small>{{ v.unit }}</small></div>
                    <div class="vital-meta">
                      <span v-if="v.avg7 !== null">7 日均 {{ v.avg7 }}</span>
                      <span class="faint">{{ v.at ? v.at.slice(5,16) : '—' }}</span>
                    </div>
                  </div>
                </div>
                <div class="grid g-2-1">
                  <div>
                    <div class="side-cap">基础档案</div>
                    <div class="info-grid" style="margin-bottom:16px">
                      <div class="info-item"><div class="k">身高 / 体重</div><div class="v">{{ data.patient.height_cm }} cm / {{ data.patient.weight_kg }} kg</div></div>
                      <div class="info-item"><div class="k">血型</div><div class="v">{{ data.patient.blood_type || '—' }}</div></div>
                      <div class="info-item"><div class="k">吸烟</div><div class="v">{{ data.patient.smoking || '—' }}</div></div>
                      <div class="info-item"><div class="k">饮酒</div><div class="v">{{ data.patient.drinking || '—' }}</div></div>
                      <div class="info-item"><div class="k">运动</div><div class="v">{{ data.patient.exercise || '—' }}</div></div>
                      <div class="info-item"><div class="k">口味</div><div class="v">{{ data.patient.salt_intake || '—' }}</div></div>
                      <div class="info-item"><div class="k">睡眠</div><div class="v">{{ data.patient.sleep_quality || '—' }}</div></div>
                      <div class="info-item"><div class="k">家族史</div><div class="v">{{ data.patient.family_history || '—' }}</div></div>
                      <div class="info-item"><div class="k">用药依从性</div><div class="v">{{ data.features.med_adherence }}%</div></div>
                    </div>
                    <div class="side-cap">风险归因</div>
                    <div v-for="r in data.risk.reasons" :key="r" class="row" style="align-items:flex-start;margin-bottom:5px">
                      <span style="color:#ea580c;margin-top:3px"><mb-icon name="alert" :size="13"/></span>
                      <span class="small" style="color:var(--text-2)">{{ r }}</span>
                    </div>
                    <div v-if="!data.risk.reasons.length" class="small faint">各项指标控制良好，暂无突出风险因素。</div>
                  </div>
                  <div>
                    <div class="side-cap">关键指标</div>
                    <div class="metric-row" v-if="data.features.bp_latest">
                      <span class="metric-name">血压</span>
                      <span class="metric-val num">{{ data.features.bp_latest.sbp.toFixed(0) }}/{{ data.features.bp_latest.dbp.toFixed(0) }}</span>
                      <span class="metric-unit">mmHg</span>
                      <span class="metric-delta" :class="data.features.bp_control_rate > 50 ? 'trend-up' : 'trend-down'">达标 {{ data.features.bp_control_rate }}%</span>
                    </div>
                    <div class="metric-row" v-if="data.features.glucose_latest">
                      <span class="metric-name">血糖</span>
                      <span class="metric-val num">{{ data.features.glucose_latest.value.toFixed(1) }}</span>
                      <span class="metric-unit">mmol/L</span>
                      <span class="metric-delta">{{ data.features.glucose_latest.note }}</span>
                    </div>
                    <div class="metric-row" v-if="data.features.hba1c">
                      <span class="metric-name">糖化血红蛋白</span>
                      <span class="metric-val num">{{ data.features.hba1c.toFixed(1) }}</span>
                      <span class="metric-unit">%</span>
                      <span class="metric-delta" :class="data.features.hba1c >= 7 ? 'trend-down' : 'trend-up'">{{ data.features.hba1c >= 7 ? '未达标' : '达标' }}</span>
                    </div>
                    <div class="metric-row" v-if="data.features.ldl">
                      <span class="metric-name">低密度脂蛋白</span>
                      <span class="metric-val num">{{ data.features.ldl.toFixed(2) }}</span>
                      <span class="metric-unit">mmol/L</span>
                    </div>
                    <div class="metric-row" v-if="data.features.egfr">
                      <span class="metric-name">eGFR</span>
                      <span class="metric-val num">{{ data.features.egfr.toFixed(0) }}</span>
                      <span class="metric-unit">mL/min</span>
                    </div>
                    <div class="metric-row" v-if="data.features.spo2_latest">
                      <span class="metric-name">血氧</span>
                      <span class="metric-val num">{{ data.features.spo2_latest.toFixed(0) }}</span>
                      <span class="metric-unit">%</span>
                    </div>
                    <div class="metric-row">
                      <span class="metric-name">近30天记录</span>
                      <span class="metric-val num">{{ data.features.metric_count }}</span>
                      <span class="metric-unit">条</span>
                      <span class="metric-delta faint">覆盖 {{ data.features.record_density }}% 天数</span>
                    </div>
                    <div class="side-cap mt14">接入设备</div>
                    <div v-for="d in data.devices" :key="d.id" class="dev-mini">
                      <span class="dev-mini-dot" :class="d.status === 'online' ? 'ok' : 'off'"></span>
                      <span class="small">{{ d.name }}</span>
                      <span class="tiny faint num grow" style="text-align:right">{{ d.device_sn }}</span>
                      <span class="tiny faint nowrap">电量 {{ d.battery != null ? d.battery + '%' : '—' }}</span>
                    </div>
                    <div v-if="!data.devices || !data.devices.length" class="small faint" style="margin-bottom:8px">暂无绑定设备</div>
                    <div class="side-cap mt14">待处理预警</div>
                    <div v-for="a in data.alerts.slice(0,3)" :key="a.id" class="alert-item">
                      <div class="alert-dot" :class="a.level"></div>
                      <div><div class="alert-title">{{ a.title }}</div><div class="alert-desc">{{ a.detail }}</div></div>
                    </div>
                    <div v-if="!data.alerts.length" class="small faint">暂无待处理预警</div>
                  </div>
                </div>
              </div>

              <!-- 趋势 -->
              <div v-if="tab==='trend'">
                <div class="row" style="margin-bottom:10px;flex-wrap:wrap">
                  <button class="btn sm" :class="metric==='bp' ? '' : 'ghost'" @click="metric='bp'">血压</button>
                  <button class="btn sm" :class="metric==='glucose' ? '' : 'ghost'" @click="metric='glucose'" v-if="data.series.glucose">血糖</button>
                  <button class="btn sm" :class="metric==='heart_rate' ? '' : 'ghost'" @click="metric='heart_rate'" v-if="data.series.heart_rate">心率</button>
                  <button class="btn sm" :class="metric==='spo2' ? '' : 'ghost'" @click="metric='spo2'" v-if="data.series.spo2">血氧</button>
                  <button class="btn sm" :class="metric==='temp' ? '' : 'ghost'" @click="metric='temp'" v-if="data.series.temp">体温</button>
                  <button class="btn sm" :class="metric==='hrv' ? '' : 'ghost'" @click="metric='hrv'" v-if="data.series.hrv">HRV</button>
                  <button class="btn sm" :class="metric==='hba1c' ? '' : 'ghost'" @click="metric='hba1c'" v-if="data.series.hba1c">糖化血红蛋白</button>
                  <button class="btn sm" :class="metric==='weight' ? '' : 'ghost'" @click="metric='weight'" v-if="data.series.weight">体重</button>
                  <span class="small faint" style="margin-left:auto">目标区间由病种与年龄自动确定</span>
                </div>
                <mb-line :points="chart.points" :points2="chart.points2" :name="chart.name"
                         :name2="chart.name2" :unit="chart.unit" :target="chart.target"
                         :target-label="chart.targetLabel" :decimals="chart.decimals" :height="250"/>
                <div class="legend mt14">
                  <span><i :style="{background:'var(--primary)'}"></i>{{ chart.name }}</span>
                  <span v-if="chart.name2"><i :style="{background:'#94a3b8'}"></i>{{ chart.name2 }}</span>
                  <span v-if="chart.target"><i style="background:#f59e0b"></i>控制目标</span>
                </div>
              </div>

              <!-- 用药与计划 -->
              <div v-if="tab==='meds'" class="grid g2">
                <div>
                  <div class="side-cap">在用药物（{{ data.medications.length }}）</div>
                  <div class="med-item" v-for="m in data.medications" :key="m.id">
                    <div class="med-ico"><mb-icon name="pill" :size="15"/></div>
                    <div class="grow" style="min-width:0">
                      <div class="med-name">{{ m.drug_name }}</div>
                      <div class="med-spec">{{ m.dosage }} · {{ m.frequency }} · {{ m.timing }}</div>
                      <div class="med-spec" v-if="m.notes">{{ m.notes }}</div>
                    </div>
                    <div style="text-align:right">
                      <div class="tiny faint">依从性</div>
                      <div class="small num" :style="{color: m.adherence >= .8 ? '#059669' : '#ea580c', fontWeight:700}">{{ Math.round(m.adherence*100) }}%</div>
                    </div>
                  </div>
                  <div v-if="!data.medications.length" class="empty">暂无长期用药</div>
                </div>
                <div>
                  <div class="side-cap">管理计划</div>
                  <div v-if="data.plan" class="card" style="padding:13px;box-shadow:none;background:#fbfdfd">
                    <div class="bold small">{{ data.plan.title }}</div>
                    <div class="tiny faint" style="margin:4px 0 8px">下次随访 {{ data.plan.next_visit }} · 依从性 {{ Math.round((data.plan.adherence||0)*100) }}%</div>
                    <div class="row" style="align-items:flex-start;margin-bottom:5px" v-for="g in data.plan.goals" :key="g">
                      <span style="color:var(--primary);margin-top:2px"><mb-icon name="check" :size="13"/></span>
                      <span class="small">{{ g }}</span>
                    </div>
                  </div>
                  <div class="side-cap mt14">智能体建议方案</div>
                  <div class="tip-card" style="flex-direction:column;gap:6px">
                    <div class="bold small">{{ data.followup_plan.title }} · {{ data.followup_plan.cadence }}</div>
                    <div class="small" v-for="g in data.followup_plan.goals" :key="g">· {{ g }}</div>
                    <button class="btn sm soft mt14" style="align-self:flex-start" @click="adoptPlan">采纳为管理计划</button>
                  </div>
                </div>
              </div>

              <!-- 预警 -->
              <div v-if="tab==='alerts'">
                <div v-for="a in data.alerts" :key="a.id" class="alert-item">
                  <div class="alert-dot" :class="a.level"></div>
                  <div class="grow">
                    <div class="between">
                      <div class="alert-title">{{ a.title }}</div>
                      <span class="tag" :class="a.level === 'critical' ? 'red' : a.level === 'high' ? 'amber' : 'soft'">{{ a.created_at.slice(0,16) }}</span>
                    </div>
                    <div class="alert-desc">{{ a.detail }}</div>
                    <div class="row mt14" style="margin-top:6px">
                      <button class="btn sm ghost" @click="handleAlert(a)">标记已处理</button>
                    </div>
                  </div>
                </div>
                <div v-if="!data.alerts.length" class="empty">暂无待处理预警</div>
              </div>

              <!-- 饮食管理 -->
              <div v-if="tab==='diet'">
                <div v-if="!dietData" class="empty">正在生成个性化饮食处方…</div>
                <div v-else>
                  <div class="diet-hero">
                    <div class="diet-hero-main">
                      <div class="diet-kicker"><mb-icon name="food" :size="15"/> 个性化饮食处方 · 依据病种、体格与口味测算</div>
                      <h3>每天 {{ dietPlan.energy }} kcal，食盐不超过 {{ dietPlan.salt }} g</h3>
                      <div class="row wrap" style="gap:6px;margin-top:8px">
                        <span class="tag primary">BMI {{ dietPlan.bmi }}</span>
                        <span class="tag soft">标准体重 {{ dietPlan.std_weight }} kg</span>
                        <span class="tag soft" v-for="n in dietPlan.condition_notes" :key="n.name">{{ n.name }}</span>
                      </div>
                      <div class="diet-nutrients">
                        <div class="diet-nutrient" v-for="n in dietPlan.nutrients" :key="n.key">
                          <div class="dn-name">{{ n.name }}</div>
                          <div class="dn-val num">{{ n.value }}<small>{{ n.unit }}</small></div>
                          <div class="dn-note">{{ n.note }}</div>
                        </div>
                      </div>
                    </div>
                    <div class="diet-score">
                      <mb-ring :value="dietSummary.score" :size="92" :thickness="9"/>
                      <div class="diet-score-txt">
                        <b>{{ dietSummary.score }}<span> 分</span></b>
                        <span>近 7 天饮食执行</span>
                        <span class="tiny faint">{{ dietSummary.logged_days }} / 7 天有记录</span>
                      </div>
                      <button class="btn soft sm" @click="openDietLog('')"><mb-icon name="plus" :size="13"/> 记录一餐</button>
                    </div>
                  </div>

                  <div class="grid g-2-1 mt14">
                    <div class="card">
                      <div class="card-head"><h3>今日配餐方案</h3><span class="sub">按 25% / 35% / 30% / 10% 分配</span></div>
                      <div class="card-body">
                        <div class="meal-list">
                          <div class="meal-card" v-for="m in dietPlan.meals" :key="m.key">
                            <div class="meal-head">
                              <div class="meal-badge">{{ m.name }}</div>
                              <div class="grow">
                                <div class="small bold">{{ m.time }}</div>
                                <div class="tiny faint">约 {{ m.energy }} kcal · 占全天 {{ m.share }}%</div>
                              </div>
                              <span class="tag ok" v-if="dietSummary.meal_checked.includes(m.key)">已记录</span>
                              <button class="btn sm ghost" @click="openDietLog(m.key)">记录</button>
                            </div>
                            <ul class="meal-dishes"><li v-for="d in m.dishes" :key="d">{{ d }}</li></ul>
                            <div class="meal-tip">{{ m.tip }}</div>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div>
                      <div class="card">
                        <div class="card-head"><h3>今日执行</h3><span class="tag primary" v-if="dietSummary.today_logs.length">{{ dietSummary.today_logs.length }} 餐</span></div>
                        <div class="card-body">
                          <div class="diet-bar">
                            <div class="between" style="margin-bottom:4px">
                              <span class="small muted">能量</span>
                              <span class="small num"><b>{{ dietSummary.today_kcal }}</b> / {{ dietSummary.energy_target }} kcal</span>
                            </div>
                            <div class="progress"><i :style="{width: dietSummary.kcal_pct + '%'}"></i></div>
                          </div>
                          <div class="diet-bar">
                            <div class="between" style="margin-bottom:4px">
                              <span class="small muted">钠</span>
                              <span class="small num" :style="{color: dietSummary.today_sodium > dietSummary.sodium_target ? '#dc2626' : 'inherit'}">
                                <b>{{ dietSummary.today_sodium }}</b> / {{ dietSummary.sodium_target }} mg
                              </span>
                            </div>
                            <div class="progress"><i :style="{width: dietSummary.sodium_pct + '%', background: dietSummary.today_sodium > dietSummary.sodium_target ? '#dc2626' : 'var(--primary)'}"></i></div>
                          </div>
                          <div class="diet-today-list">
                            <div v-for="l in dietSummary.today_logs" :key="l.id" class="diet-log-row">
                              <span class="diet-log-meal">{{ l.meal_cn }}</span>
                              <span class="small grow">{{ l.foods }}</span>
                              <span class="tiny faint nowrap">{{ l.calories ? l.calories + ' kcal' : '—' }}</span>
                            </div>
                            <div v-if="!dietSummary.today_logs.length" class="small faint" style="padding:10px 0 2px;line-height:1.7">
                              今天还没有记录。记下吃了什么，系统会自动估算热量与钠，并据此调整建议。
                            </div>
                          </div>
                          <button class="btn soft sm mt14" style="width:100%" @click="openDietLog('')"><mb-icon name="plus" :size="13"/> 记录这一餐</button>
                        </div>
                      </div>

                      <div class="card mt14">
                        <div class="card-head"><h3>食物宜忌</h3><span class="sub">按病种自动匹配</span></div>
                        <div class="card-body">
                          <div class="food-group">
                            <div class="food-cap ok">优先选择</div>
                            <div class="food-item" v-for="x in dietPlan.foods.recommend" :key="x.name">
                              <span class="food-dot ok"></span>
                              <div><div class="food-name">{{ x.name }}</div><div class="food-why">{{ x.why }}</div></div>
                            </div>
                          </div>
                          <div class="food-group">
                            <div class="food-cap warn">限量或少吃</div>
                            <div class="food-item" v-for="x in dietPlan.foods.limit" :key="x.name">
                              <span class="food-dot warn"></span>
                              <div><div class="food-name">{{ x.name }}</div><div class="food-why">{{ x.why }}</div></div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div class="grid g2 mt14">
                    <div class="card">
                      <div class="card-head"><h3>病种饮食要点</h3></div>
                      <div class="card-body">
                        <div class="diet-note" v-for="n in dietPlan.condition_notes" :key="n.name">
                          <span class="tag primary">{{ n.name }}</span>
                          <div class="small">{{ n.text }}</div>
                        </div>
                        <div v-if="!dietPlan.condition_notes.length" class="small faint">暂无病种特异性饮食限制，按平衡膳食执行即可。</div>
                      </div>
                    </div>
                    <div class="card">
                      <div class="card-head"><h3>执行原则</h3><span class="sub">不追求一次全改</span></div>
                      <div class="card-body">
                        <div class="diet-principle" v-for="(p, i) in dietPlan.principles" :key="i">
                          <span class="diet-idx">{{ i + 1 }}</span><span class="small">{{ p }}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div class="card mt14">
                    <div class="card-head">
                      <h3>最近饮食记录</h3>
                      <span class="sub">近 14 天 · 共 {{ dietData.logs.length }} 条 · 拍照 {{ dietSummary.photo_count }} 次</span>
                    </div>
                    <div class="card-body" style="padding-top:8px">
                      <div class="diet-log-row" v-for="l in dietData.logs" :key="l.id">
                        <span class="tiny faint num nowrap">{{ l.log_date.slice(5) }}</span>
                        <span class="diet-log-meal">{{ l.meal_cn }}</span>
                        <span class="diet-thumb" v-if="l.image_url" @click="photoView = l">
                          <img :src="l.image_url" alt="饮食照片">
                          <span class="dt-score" v-if="l.photo_score">{{ l.photo_score }}</span>
                        </span>
                        <span class="small grow">{{ l.foods }}<span v-if="l.note" class="faint"> · {{ l.note }}</span></span>
                        <span class="tiny num nowrap">{{ l.calories ? l.calories + ' kcal' : '' }}</span>
                        <span class="tiny num nowrap" :class="l.sodium > 800 ? 'trend-down' : 'faint'">{{ l.sodium ? '钠 ' + l.sodium + ' mg' : '' }}</span>
                        <button class="msg-tool" @click="delDietLog(l)"><mb-icon name="trash" :size="12"/></button>
                      </div>
                      <div v-if="!dietData.logs.length" class="empty">还没有饮食记录，从今天的一餐开始吧</div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 记忆 -->
              <div v-if="tab==='memory'">
                <div class="between" style="margin-bottom:10px">
                  <div>
                    <div class="bold small">跨会话长期记忆</div>
                    <div class="tiny faint">每次对话后自动抽取，历史越多，建议越贴合个人情况</div>
                  </div>
                  <button class="btn sm soft" @click="addMemory"><mb-icon name="plus" :size="13"/> 手动添加</button>
                </div>
                <div class="memory-chip" v-for="m in data.memories" :key="m.id">
                  <span class="memory-kind">{{ m.kind_cn }}</span>
                  <span class="memory-text grow">{{ m.content }}</span>
                  <span class="tiny faint nowrap">引用 {{ m.use_count }} 次</span>
                  <button class="msg-tool" @click="delMemory(m)"><mb-icon name="trash" :size="12"/></button>
                </div>
                <div v-if="!data.memories.length" class="empty">暂无长期记忆，对话后会自动积累</div>
              </div>
            </div>
          </div>
        </div>

        <div class="mask" v-if="showMetric" @click.self="showMetric=false">
          <div class="modal" style="max-width:460px">
            <div class="modal-head"><h3>录入健康指标</h3></div>
            <div class="modal-body">
              <div class="field">
                <label>指标类型</label>
                <select class="select" v-model="form.metric_type">
                  <option value="sbp">收缩压（mmHg）</option>
                  <option value="dbp">舒张压（mmHg）</option>
                  <option value="glucose">血糖（mmol/L）</option>
                  <option value="weight">体重（kg）</option>
                  <option value="heart_rate">心率（次/分）</option>
                  <option value="spo2">血氧饱和度（%）</option>
                  <option value="temp">体温（℃）</option>
                  <option value="hrv">心率变异性 HRV（ms）</option>
                  <option value="resp_rate">呼吸频率（次/分）</option>
                </select>
              </div>
              <div class="field">
                <label>数值</label>
                <input class="input" type="number" step="0.1" v-model="form.value" placeholder="请输入测量值">
              </div>
              <div class="field">
                <label>备注</label>
                <input class="input" v-model="form.note" placeholder="如：空腹 / 服药后 / 运动后">
              </div>
              <div class="field">
                <label>测量时间（留空为当前时间）</label>
                <input class="input" v-model="form.measured_at" placeholder="2026-10-19 08:00:00">
              </div>
              <div class="tip-card warn" style="margin-top:12px">
                <mb-icon name="shield" :size="16"/>
                <div>录入后系统会自动判读：血压 ≥180/110、血糖 &lt;3.9 或 &gt;16.7、血氧 &lt;90% 将立即触发预警。</div>
              </div>
            </div>
            <div class="modal-foot">
              <button class="btn ghost" @click="showMetric=false">取消</button>
              <button class="btn" :disabled="saving" @click="addMetric">{{ saving ? '保存中…' : '保存' }}</button>
            </div>
          </div>
        </div>

        <div class="mask" v-if="showDietLog" @click.self="showDietLog=false">
          <div class="modal" style="max-width:480px">
            <div class="modal-head"><h3>记录饮食</h3></div>
            <div class="modal-body">
              <div class="auth-grid">
                <div class="field" style="margin-top:0">
                  <label>日期</label>
                  <input class="input" type="date" v-model="dietForm.log_date">
                </div>
                <div class="field" style="margin-top:0">
                  <label>餐次</label>
                  <select class="select" v-model="dietForm.meal">
                    <option value="breakfast">早餐</option>
                    <option value="lunch">午餐</option>
                    <option value="dinner">晚餐</option>
                    <option value="snack">加餐</option>
                  </select>
                </div>
              </div>
              <div class="field">
                <label>吃了什么</label>
                <textarea class="textarea" style="min-height:76px" v-model="dietForm.foods"
                          placeholder="如：杂粮饭 1 小碗、清蒸鱼、炒青菜、半个苹果"></textarea>
                <div class="field-help">尽量写清主食和菜量，系统会按关键词估算热量与钠</div>
              </div>
              <div class="auth-grid">
                <div class="field">
                  <label>热量<span class="opt">（选填，留空自动估算）</span></label>
                  <input class="input num" type="number" v-model="dietForm.calories" placeholder="kcal">
                </div>
                <div class="field">
                  <label>钠<span class="opt">（选填，留空自动估算）</span></label>
                  <input class="input num" type="number" v-model="dietForm.sodium" placeholder="mg">
                </div>
              </div>
              <div class="field">
                <label>备注<span class="opt">（选填）</span></label>
                <input class="input" v-model="dietForm.note" placeholder="如：外食、聚餐、没忍住吃了咸菜">
              </div>
              <div class="tip-card" style="margin-top:12px">
                <mb-icon name="food" :size="16"/>
                <div>记录会进入患者全景档案，用于评估饮食执行度，并让智能助手与专家的建议更具体。</div>
              </div>
            </div>
            <div class="modal-foot">
              <button class="btn ghost" @click="showDietLog=false">取消</button>
              <button class="btn" :disabled="savingDiet" @click="addDietLog">{{ savingDiet ? '保存中…' : '保存记录' }}</button>
            </div>
          </div>
        </div>
        <div class="mask" v-if="photoView" @click.self="photoView=null">
          <div class="modal" style="max-width:700px">
            <div class="modal-head">
              <h3>饮食照片分析 · {{ photoView.log_date }} {{ photoView.meal_cn }}</h3>
              <button class="icon-btn" @click="photoView=null"><mb-icon name="close" :size="16"/></button>
            </div>
            <div class="modal-body">
              <div class="photo-result">
                <img :src="photoView.image_url" alt="饮食照片">
                <div class="pr-side" v-if="photoView.analysis">
                  <mb-ring :value="photoView.analysis.score" :size="76" :thickness="8"/>
                  <div>
                    <b>{{ photoView.analysis.grade }}</b>
                    <span>结构分 {{ photoView.analysis.score }} · 置信度 {{ Math.round(photoView.analysis.confidence * 100) }}%</span>
                  </div>
                  <div class="pr-nums">
                    <div><b class="num">{{ photoView.analysis.estimated.kcal }}</b><span>kcal</span></div>
                    <div><b class="num">{{ photoView.analysis.estimated.sodium }}</b><span>mg 钠</span></div>
                  </div>
                </div>
              </div>
              <template v-if="photoView.analysis">
                <div class="pr-summary">{{ photoView.analysis.summary }}</div>
                <div class="dp-bars" style="margin-top:12px">
                  <div v-for="c in photoView.analysis.categories" :key="c.key">
                    <div class="between tiny"><span>{{ c.name }}</span><span class="num">{{ c.share }}%</span></div>
                    <div class="progress" style="height:6px"><i :style="{width: c.share + '%', background: c.color}"></i></div>
                  </div>
                </div>
                <div class="dp-find" v-for="f in photoView.analysis.findings" :key="f.title">
                  <span class="dp-dot" :class="f.level"></span>
                  <div><b>{{ f.title }}</b><span>{{ f.text }}</span></div>
                </div>
                <div class="tiny faint" style="line-height:1.7;margin-top:10px">{{ photoView.analysis.disclaimer }}</div>
              </template>
            </div>
            <div class="modal-foot"><button class="btn ghost" @click="photoView=null">关闭</button></div>
          </div>
        </div>
      </div>`,
  };
})();
