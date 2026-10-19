/* 医生工作台 · 概览 */
(function () {
  const { ref, computed, onMounted } = Vue;
  const Pages = (window.Pages = window.Pages || {});

  Pages.overview = {
    components: { MbIcon: Mb.Icon, MbLine: Mb.LineChart, MbDonut: Mb.Donut, MbBars: Mb.Bars },
    setup() {
      const data = ref(null);
      const loading = ref(true);
      const error = ref('');

      async function load() {
        loading.value = true;
        error.value = '';
        try {
          data.value = await API.get('/api/dashboard/overview');
          Store.alerts = data.value.kpi.alerts || 0;
        } catch (e) {
          error.value = e.message;
        } finally {
          loading.value = false;
        }
      }
      onMounted(load);

      const riskSegs = computed(() => {
        if (!data.value) return [];
        const r = data.value.risk;
        return [
          { label: '极高危', value: r.critical, color: '#b91c1c' },
          { label: '高危', value: r.high, color: '#ea580c' },
          { label: '中危', value: r.medium, color: '#d97706' },
          { label: '低危', value: r.low, color: '#059669' },
        ];
      });
      const diseaseBars = computed(() => (data.value ? data.value.diseases.map((d) => ({
        label: d.name, value: d.control_rate, count: d.count,
        color: d.control_rate >= 70 ? '#059669' : d.control_rate >= 50 ? '#d97706' : '#ea580c',
      })) : []));
      const activityPoints = computed(() => (data.value
        ? data.value.activity.map((a) => ({ label: a.date, value: a.count }))
        : []));
      const kpi = computed(() => (data.value ? data.value.kpi : {}));

      function openPatient(id) { ui.go('patient', { id }); }
      function goPatients(risk) { ui.go('patients', risk ? { risk } : {}); }

      return { data, loading, error, load, riskSegs, diseaseBars, activityPoints, kpi, openPatient, goPatients };
    },
    template: `
      <div>
        <div v-if="loading" class="empty">正在加载工作台数据…</div>
        <div v-else-if="error" class="empty">
          {{ error }}
          <div style="margin-top:10px"><button class="btn sm" @click="load">重新加载</button></div>
        </div>
        <div v-else>
          <div class="grid g4">
            <div class="card kpi" style="cursor:pointer" @click="goPatients()">
              <div class="kpi-top"><span class="kpi-ico"><mb-icon name="users" :size="15"/></span>在管患者</div>
              <div class="kpi-val num">{{ kpi.patients }}<small>人</small></div>
              <div class="kpi-foot"><span class="trend-up">●</span> 覆盖 {{ data.diseases.length }} 类慢病</div>
            </div>
            <div class="card kpi" style="cursor:pointer" @click="goPatients('high')">
              <div class="kpi-top"><span class="kpi-ico" style="background:#fff1f2;color:#dc2626"><mb-icon name="alert" :size="15"/></span>高风险人群</div>
              <div class="kpi-val num" style="color:#dc2626">{{ kpi.high_risk }}<small>人</small></div>
              <div class="kpi-foot">极高危 {{ data.risk.critical }} 人 · 高危 {{ data.risk.high }} 人</div>
            </div>
            <div class="card kpi">
              <div class="kpi-top"><span class="kpi-ico" style="background:#eff6ff;color:#2563eb"><mb-icon name="activity" :size="15"/></span>家庭血压达标率</div>
              <div class="kpi-val num">{{ kpi.bp_control }}<small>%</small></div>
              <div class="kpi-foot">血糖达标率 {{ kpi.glucose_control }}%</div>
            </div>
            <div class="card kpi" style="cursor:pointer" @click="goPatients('critical')">
              <div class="kpi-top"><span class="kpi-ico" style="background:#fffbeb;color:#d97706"><mb-icon name="bell" :size="15"/></span>待处理预警</div>
              <div class="kpi-val num" style="color:#d97706">{{ kpi.alerts }}<small>条</small></div>
              <div class="kpi-foot">随访计划依从性 {{ kpi.followup_rate }}%</div>
            </div>
          </div>

          <div class="grid g-2-1 mt14">
            <div class="card">
              <div class="card-head">
                <h3>风险分层与病种达标</h3>
                <span class="sub">按最新指标与依从性动态计算</span>
              </div>
              <div class="card-body">
                <div style="display:flex;gap:26px;align-items:center;flex-wrap:wrap">
                  <div style="display:flex;align-items:center;gap:16px">
                    <mb-donut :data="riskSegs" :size="138" :thickness="14"
                              :center="String(kpi.patients)" center-label="在管患者"/>
                    <div>
                      <div v-for="s in riskSegs" :key="s.label" class="between" style="gap:18px;margin-bottom:7px">
                        <span class="small" style="display:flex;align-items:center;gap:6px">
                          <i :style="{width:'8px',height:'8px',borderRadius:'2px',background:s.color,display:'inline-block'}"></i>
                          {{ s.label }}
                        </span>
                        <b class="small num">{{ s.value }} 人</b>
                      </div>
                    </div>
                  </div>
                  <div class="grow" style="min-width:240px;border-left:1px solid var(--line);padding-left:24px">
                    <div class="faint tiny" style="margin-bottom:10px;letter-spacing:1px">病种控制达标率</div>
                    <mb-bars :items="diseaseBars"/>
                  </div>
                </div>
              </div>
            </div>

            <div class="card">
              <div class="card-head">
                <h3>今日重点关注</h3>
                <span class="sub">按风险分排序</span>
                <div class="right"><button class="btn sm ghost" @click="goPatients('high')">全部<mb-icon name="arrow" :size="13"/></button></div>
              </div>
              <div class="card-body" style="padding-top:6px">
                <div v-for="p in data.focus" :key="p.id" class="alert-item" style="cursor:pointer" @click="openPatient(p.id)">
                  <div class="avatar" :style="{background:p.avatar_color, width:'34px', height:'34px', flex:'0 0 34px', borderRadius:'10px'}">{{ p.name.slice(-2) }}</div>
                  <div class="grow" style="min-width:0">
                    <div class="between">
                      <div class="row" style="gap:6px">
                        <span class="alert-title">{{ p.name }}</span>
                        <span class="tiny faint">{{ p.age }}岁{{ p.gender }}</span>
                        <span class="tag" :class="'risk-' + p.risk_level">{{ p.risk_label }}</span>
                      </div>
                      <span class="tiny num" style="color:#dc2626;font-weight:700">{{ p.risk_score }}</span>
                    </div>
                    <div class="alert-desc" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                      {{ p.reasons[0] || p.conditions.join('、') }}
                    </div>
                  </div>
                </div>
                <div v-if="!data.focus.length" class="empty">暂无高风险患者</div>
              </div>
            </div>
          </div>

          <div class="grid g-2-1 mt14">
            <div class="card">
              <div class="card-head">
                <h3>家庭监测活跃度</h3>
                <span class="sub">近 14 天指标上传条数</span>
                <div class="right">
                  <span class="tag" :class="kpi.devices_online ? 'ok' : 'soft'">设备 {{ kpi.devices_online }}/{{ kpi.devices }} 在线</span>
                </div>
              </div>
              <div class="card-body">
                <mb-line :points="activityPoints" name="记录条数" unit="条" color="var(--primary)"
                         :height="196" :decimals="0"/>
                <div class="row tiny faint" style="margin-top:8px;gap:14px">
                  <span>今日设备自动上报 {{ kpi.device_today }} 条</span>
                  <span>{{ kpi.device_patients }} 位患者已使用体征设备</span>
                  <span>自动入库并参与达标率与风险计算</span>
                </div>
              </div>
            </div>

            <div class="card">
              <div class="card-head">
                <h3>智能体与知识库</h3>
                <div class="right"><span class="tag ok">运行中</span></div>
              </div>
              <div class="card-body">
                <div class="ctx-item"><span class="ctx-k">推理引擎</span><span class="ctx-v">{{ data.agent.provider === 'builtin' ? '内置引擎' : data.agent.provider }}</span></div>
                <div class="ctx-item"><span class="ctx-k">模型</span><span class="ctx-v" style="max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ data.agent.model || '内置推理引擎' }}</span></div>
                <div class="ctx-item"><span class="ctx-k">知识库文档</span><span class="ctx-v">{{ data.kb.documents }} 篇 / {{ data.kb.chunks }} 片段</span></div>
                <div class="ctx-item"><span class="ctx-k">平均个性化成熟度</span><span class="ctx-v">{{ kpi.maturity }}%</span></div>
                <div class="ctx-item"><span class="ctx-k">管理计划</span><span class="ctx-v">{{ kpi.plans }} 份</span></div>
                <button class="btn soft" style="width:100%;margin-top:12px" @click="$root.go('chat')">
                  <mb-icon name="sparkles" :size="15"/> 打开智能助手
                </button>
              </div>
            </div>
          </div>

          <div class="card mt14">
            <div class="card-head">
              <h3>待处理预警</h3>
              <span class="sub">按危急程度排序</span>
              <div class="right"><span class="tag red">{{ data.alerts.length }} 条未处理</span></div>
            </div>
            <div class="card-body" style="padding-top:4px">
              <div v-for="a in data.alerts" :key="a.id" class="alert-item">
                <div class="alert-dot" :class="a.level"></div>
                <div class="grow" style="min-width:0">
                  <div class="between">
                    <div class="alert-title">{{ a.title }}</div>
                    <span class="tiny faint nowrap">{{ a.created_at.slice(5,16) }}</span>
                  </div>
                  <div class="alert-desc">{{ a.detail }}</div>
                  <div class="row" style="margin-top:5px">
                    <span class="tiny faint">患者：{{ a.name }}</span>
                    <button class="btn sm ghost" style="margin-left:auto" @click="openPatient(a.patient_id)">查看档案</button>
                  </div>
                </div>
              </div>
              <div v-if="!data.alerts.length" class="empty">暂无待处理预警</div>
            </div>
          </div>
        </div>
      </div>`,
  };
})();
