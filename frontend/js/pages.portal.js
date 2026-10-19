/* 患者端 · 我的健康 */
(function () {
  const { ref, computed, onMounted } = Vue;
  const Pages = (window.Pages = window.Pages || {});

  Pages.portal = {
    components: { MbIcon: Mb.Icon, MbLine: Mb.LineChart, MbRing: Mb.Ring },
    setup() {
      const d = ref(null);
      const loading = ref(true);
      const metric = ref('bp');

      const diet = ref(null);
      const photoOpen = ref(false);
      const photoMeal = ref('breakfast');
      const photoHint = ref('');
      const photoPreview = ref('');
      const photoFile = ref(null);
      const uploading = ref(false);
      const photoResult = ref(null);
      const fileInput = ref(null);

      async function load() {
        loading.value = true;
        try { d.value = await API.get('/api/my/profile'); }
        catch (e) { ui.toast(e.message, 'err'); }
        finally { loading.value = false; }
      }
      async function loadDiet() {
        try { diet.value = await API.get('/api/my/diet'); }
        catch (e) { /* 未绑定档案时忽略 */ }
      }
      onMounted(() => { load(); loadDiet(); });

      const bpPoints = computed(() => (d.value ? (d.value.series.sbp || []).map((r) => ({ label: r.measured_at, value: r.value })) : []));
      const bpPoints2 = computed(() => (d.value ? (d.value.series.dbp || []).map((r) => ({ label: r.measured_at, value: r.value })) : []));
      const glucosePoints = computed(() => (d.value ? (d.value.series.glucose || []).map((r) => ({ label: r.measured_at, value: r.value })) : []));
      const weightPoints = computed(() => (d.value ? (d.value.series.weight || []).map((r) => ({ label: r.measured_at, value: r.value })) : []));

      const chart = computed(() => {
        if (!d.value) return {};
        if (metric.value === 'bp') return { points: bpPoints.value, points2: bpPoints2.value, name: '收缩压', name2: '舒张压', unit: 'mmHg', decimals: 0,
          target: Number((d.value.features.bp_target || '140/90').split('/')[0]), targetLabel: '目标 ' + d.value.features.bp_target };
        if (metric.value === 'glucose') return { points: glucosePoints.value, points2: [], name: '血糖', unit: 'mmol/L', decimals: 1, target: 7.0, targetLabel: '空腹目标 7.0' };
        return { points: weightPoints.value, points2: [], name: '体重', unit: 'kg', decimals: 1 };
      });

      const maturityParts = computed(() => {
        if (!d.value) return [];
        const f = d.value.features;
        return [
          { label: '建档时长', value: Math.min(100, Math.round(f.managed_days / 90 * 100)) },
          { label: '指标记录', value: Math.min(100, Math.round(f.metric_count / 60 * 100)) },
          { label: '对话次数', value: Math.min(100, Math.round(f.chat_turns / 20 * 100)) },
          { label: '记忆条数', value: Math.min(100, Math.round(f.memory_count / 12 * 100)) },
        ];
      });

      function consult() { ui.go('expert'); }

      const mealNames = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' };
      const todayLogs = computed(() => (diet.value ? (diet.value.summary.today_logs || []) : []));
      const slots = computed(() => ['breakfast', 'lunch', 'dinner'].map((k) => ({
        key: k, name: mealNames[k],
        log: todayLogs.value.find((l) => l.meal === k && l.has_photo) || null,
      })));
      const latestAnalysis = computed(() => {
        if (!diet.value) return null;
        return (diet.value.logs || []).find((l) => l.analysis) || null;
      });
      const dietSummary = computed(() => (diet.value ? diet.value.summary : null));

      function openPhoto(meal) {
        photoMeal.value = typeof meal === 'string' ? meal : 'breakfast';
        photoPreview.value = '';
        photoFile.value = null;
        photoHint.value = '';
        photoResult.value = null;
        photoOpen.value = true;
      }
      function pickFile() { if (fileInput.value) fileInput.value.click(); }
      function onFile(e) {
        const f = e.target.files && e.target.files[0];
        if (!f) return;
        if (!/^image\//.test(f.type)) return ui.toast('请选择图片文件', 'err');
        if (f.size > 8 * 1024 * 1024) return ui.toast('照片不能超过 8 MB', 'err');
        photoFile.value = f;
        photoPreview.value = URL.createObjectURL(f);
      }
      function resetPhoto() {
        photoResult.value = null;
        photoPreview.value = '';
        photoFile.value = null;
        photoHint.value = '';
        if (fileInput.value) fileInput.value.value = '';
      }
      async function submitPhoto() {
        if (!photoFile.value) return ui.toast('请先拍照或选择照片', 'err');
        uploading.value = true;
        try {
          const fd = new FormData();
          fd.append('photo', photoFile.value);
          fd.append('meal', photoMeal.value);
          fd.append('hint', photoHint.value.trim());
          const r = await API.upload('/api/my/diet/photo', fd);
          photoResult.value = r.analysis;
          photoResult.value.image_url = r.image_url;
          await loadDiet();
          ui.toast('已记录并完成分析');
        } catch (e) { ui.toast(e.message, 'err'); }
        finally { uploading.value = false; }
      }

      return { d, loading, metric, chart, maturityParts, consult, load,
               diet, dietSummary, slots, latestAnalysis, mealNames,
               photoOpen, photoMeal, photoHint, photoPreview, uploading, photoResult, fileInput,
               openPhoto, pickFile, onFile, resetPhoto, submitPhoto };
    },
    template: `
      <div v-if="d">
        <div class="portal-hero">
          <div class="between" style="position:relative;z-index:2;align-items:flex-start">
            <div>
              <h2>{{ d.patient.name }}，您好</h2>
              <p>{{ d.narrative }}</p>
            </div>
            <div style="text-align:center;flex:0 0 auto">
              <mb-ring :value="d.maturity.score" :size="76" :thickness="7" color="rgba(255,255,255,.92)"/>
              <div class="tiny" style="opacity:.9;margin-top:4px">个性化成熟度 {{ d.maturity.score }}</div>
            </div>
          </div>
          <div class="metrics">
            <div class="m" v-if="d.features.bp_latest">
              <b>{{ d.features.bp_latest.sbp.toFixed(0) }}/{{ d.features.bp_latest.dbp.toFixed(0) }}</b>
              <span>最近血压 mmHg</span>
            </div>
            <div class="m" v-if="d.features.glucose_latest">
              <b>{{ d.features.glucose_latest.value.toFixed(1) }}</b>
              <span>最近血糖 mmol/L</span>
            </div>
            <div class="m"><b>{{ d.features.bp_control_rate }}%</b><span>近 30 天血压达标率</span></div>
            <div class="m"><b>{{ d.features.med_adherence }}%</b><span>用药依从性</span></div>
            <div class="m"><b>{{ d.risk.label }}</b><span>当前风险分层</span></div>
          </div>
        </div>

        <div class="grid g-2-1 mt14">
          <div class="card">
            <div class="card-head">
              <h3>我的指标趋势</h3>
              <div class="right">
                <button class="btn sm" :class="metric==='bp' ? '' : 'ghost'" @click="metric='bp'">血压</button>
                <button class="btn sm" :class="metric==='glucose' ? '' : 'ghost'" @click="metric='glucose'" v-if="d.series.glucose">血糖</button>
                <button class="btn sm" :class="metric==='weight' ? '' : 'ghost'" @click="metric='weight'" v-if="d.series.weight">体重</button>
              </div>
            </div>
            <div class="card-body">
              <mb-line :points="chart.points" :points2="chart.points2" :name="chart.name" :name2="chart.name2"
                       :unit="chart.unit" :target="chart.target" :target-label="chart.targetLabel"
                       :decimals="chart.decimals" :height="236"/>
            </div>
          </div>

          <div class="card">
            <div class="card-head"><h3>我的管理计划</h3><span class="tag primary">{{ d.plan ? d.plan.status === 'active' ? '进行中' : '已完成' : '待制定' }}</span></div>
            <div class="card-body">
              <div v-if="d.plan">
                <div class="bold small">{{ d.plan.title }}</div>
                <div class="tiny faint" style="margin:4px 0 10px">下次随访 {{ d.plan.next_visit }} · 依从性 {{ Math.round((d.plan.adherence||0)*100) }}%</div>
                <div class="row" style="align-items:flex-start;margin-bottom:7px" v-for="g in d.plan.goals" :key="g">
                  <span style="color:var(--primary);margin-top:2px"><mb-icon name="check" :size="13"/></span>
                  <span class="small">{{ g }}</span>
                </div>
              </div>
              <div v-else class="small muted">医生尚未为您制定管理计划。</div>
              <button class="btn mt14" style="width:100%" @click="consult"><mb-icon name="stethoscope" :size="15"/> 找专家会诊</button>
            </div>
          </div>
        </div>

        <div class="grid g3 mt14">
          <div class="card">
            <div class="card-head"><h3>正在服用的药</h3><span class="sub">{{ d.medications.length }} 种</span></div>
            <div class="card-body" style="padding-top:6px">
              <div class="med-item" v-for="m in d.medications" :key="m.id">
                <div class="med-ico"><mb-icon name="pill" :size="14"/></div>
                <div class="grow" style="min-width:0">
                  <div class="med-name">{{ m.drug_name }}</div>
                  <div class="med-spec">{{ m.dosage }} · {{ m.frequency }} · {{ m.timing }}</div>
                </div>
              </div>
              <div v-if="!d.medications.length" class="empty">暂无用药记录</div>
            </div>
          </div>

          <div class="card">
            <div class="card-head"><h3>需要留意</h3><span class="tag red" v-if="d.alerts.length">{{ d.alerts.length }}</span></div>
            <div class="card-body" style="padding-top:6px">
              <div v-for="a in d.alerts.slice(0,3)" :key="a.id" class="alert-item">
                <div class="alert-dot" :class="a.level"></div>
                <div><div class="alert-title">{{ a.title }}</div><div class="alert-desc">{{ a.detail }}</div></div>
              </div>
              <div v-if="!d.alerts.length" class="tip-card"><mb-icon name="check" :size="15"/><div>暂无需特别处理的提醒，继续保持。</div></div>
            </div>
          </div>

          <div class="card">
            <div class="card-head"><h3>助手越来越懂我</h3></div>
            <div class="card-body">
              <div v-for="p in maturityParts" :key="p.label" style="margin-bottom:9px">
                <div class="between" style="margin-bottom:3px">
                  <span class="tiny muted">{{ p.label }}</span>
                  <span class="tiny num faint">{{ p.value }}%</span>
                </div>
                <div class="progress" style="height:5px"><i :style="{width: p.value + '%'}"></i></div>
              </div>
              <div class="tiny faint" style="line-height:1.7;margin-top:8px">
                记录越多、交流越多，助手对您的用药习惯、口味偏好和实际困难就越了解，建议也更具体。
              </div>
            </div>
          </div>
        </div>

        <div class="card mt14">
          <div class="card-head">
            <h3>今日饮食</h3>
            <span class="sub">拍照上传，平台自动分析这一餐的搭配</span>
            <div class="right">
              <span class="tag primary" v-if="dietSummary && dietSummary.photo_today">{{ dietSummary.photo_today }} 餐已记录</span>
              <button class="btn sm" @click="openPhoto('breakfast')"><mb-icon name="upload" :size="13"/> 拍照上传</button>
            </div>
          </div>
          <div class="card-body">
            <div class="diet-today">
              <div class="meal-slot" v-for="s in slots" :key="s.key" :class="{filled: s.log}" @click="openPhoto(s.key)">
                <div class="ms-photo">
                  <img v-if="s.log && s.log.image_url" :src="s.log.image_url" :alt="s.name">
                  <div v-else class="ms-add"><mb-icon name="plus" :size="18"/><span>拍{{ s.name }}</span></div>
                  <span class="ms-score" v-if="s.log && s.log.photo_score">{{ s.log.photo_score }}</span>
                </div>
                <div class="ms-name">{{ s.name }}</div>
                <div class="ms-meta tiny faint" v-if="s.log">{{ s.log.calories }} kcal · 钠 {{ s.log.sodium }} mg</div>
                <div class="ms-meta tiny faint" v-else>点击拍照记录</div>
              </div>

              <div class="diet-panel" v-if="latestAnalysis">
                <div class="dp-head">
                  <mb-ring :value="latestAnalysis.analysis.score" :size="66" :thickness="7"/>
                  <div style="min-width:0">
                    <b>{{ mealNames[latestAnalysis.meal] }} · {{ latestAnalysis.analysis.grade }}</b>
                    <div class="tiny faint" style="margin-top:2px">
                      估算 {{ latestAnalysis.analysis.estimated.kcal }} kcal · 钠 {{ latestAnalysis.analysis.estimated.sodium }} mg
                    </div>
                    <div class="tiny faint">置信度 {{ Math.round(latestAnalysis.analysis.confidence * 100) }}% · 本地分析</div>
                  </div>
                </div>
                <div class="dp-bars">
                  <div v-for="c in latestAnalysis.analysis.categories" :key="c.key">
                    <div class="between tiny"><span>{{ c.name }}</span><span class="num">{{ c.share }}%</span></div>
                    <div class="progress" style="height:5px"><i :style="{width: c.share + '%', background: c.color}"></i></div>
                  </div>
                </div>
                <div class="dp-find" v-for="f in latestAnalysis.analysis.findings.slice(0, 2)" :key="f.title">
                  <span class="dp-dot" :class="f.level"></span>
                  <div><b>{{ f.title }}</b><span>{{ f.text }}</span></div>
                </div>
              </div>
              <div class="diet-panel empty" v-else>
                <div class="dp-empty">
                  <div class="dp-empty-ico"><mb-icon name="food" :size="24"/></div>
                  <b>还没有饮食照片</b>
                  <p>把餐盘放在光线充足的地方俯拍一张，平台会分析蔬菜、主食、蛋白的比例，估算热量与钠，并对照你的饮食处方给出建议。</p>
                </div>
              </div>
            </div>
            <div class="between" style="margin-top:12px">
              <span class="tiny faint">近 7 天已记录 {{ dietSummary ? dietSummary.photo_days : 0 }} 天 · 平均结构分 {{ dietSummary ? dietSummary.avg_photo_score : 0 }}</span>
            </div>
          </div>
        </div>

        <div class="card mt14" v-if="d.memories.length">
          <div class="card-head"><h3>助手记住的关于您</h3><span class="sub">可随时在对话中补充或修正</span></div>
          <div class="card-body" style="display:flex;flex-wrap:wrap;gap:8px">
            <div class="memory-chip" v-for="m in d.memories" :key="m.id" style="flex:1 1 260px;margin:0">
              <span class="memory-kind">{{ m.kind_cn }}</span>
              <span class="memory-text">{{ m.content }}</span>
            </div>
          </div>
        </div>
      </div>
      <div v-else-if="loading" class="empty">正在加载健康档案…</div>
      <div v-else class="empty">当前账号未绑定患者档案</div>

      <div class="mask" v-if="photoOpen" @click.self="photoOpen=false">
        <div class="modal" style="max-width:620px">
          <div class="modal-head">
            <h3>{{ photoResult ? '这一餐的分析' : '拍照记录饮食' }}</h3>
            <button class="icon-btn" @click="photoOpen=false"><mb-icon name="close" :size="16"/></button>
          </div>
          <div class="modal-body">
            <template v-if="!photoResult">
              <div class="photo-drop" :class="{has: photoPreview}" @click="pickFile">
                <img v-if="photoPreview" :src="photoPreview" alt="饮食照片预览">
                <div v-else class="photo-drop-empty">
                  <mb-icon name="upload" :size="26"/>
                  <b>拍照或从相册选择</b>
                  <small>俯拍整盘、光线充足，让食物占画面 60% 以上</small>
                </div>
                <span class="photo-retake" v-if="photoPreview">重新选择</span>
              </div>
              <input ref="fileInput" type="file" accept="image/*" capture="environment"
                     style="display:none" @change="onFile">

              <div class="field">
                <label>这是哪一餐</label>
                <div class="seg">
                  <button v-for="(n, k) in mealNames" :key="k" :class="{active: photoMeal===k}" @click="photoMeal=k">{{ n }}</button>
                </div>
              </div>
              <div class="field">
                <label>补充说明<span class="opt">（选填，能让估算更准）</span></label>
                <input class="input" v-model="photoHint" maxlength="60" placeholder="如：杂粮饭、清蒸鱼、炒青菜">
              </div>
              <div class="tip-card">
                <mb-icon name="sparkles" :size="15"/>
                <div>照片在本地完成分析，识别食物结构与占比，估算热量与钠，并对照你的饮食处方给出改进建议。</div>
              </div>
            </template>

            <template v-else>
              <div class="photo-result">
                <img :src="photoResult.image_url" alt="饮食照片">
                <div class="pr-side">
                  <mb-ring :value="photoResult.score" :size="76" :thickness="8"/>
                  <div>
                    <b>{{ photoResult.grade }}</b>
                    <span>结构分 {{ photoResult.score }}</span>
                  </div>
                  <div class="pr-nums">
                    <div><b class="num">{{ photoResult.estimated.kcal }}</b><span>kcal</span></div>
                    <div><b class="num">{{ photoResult.estimated.sodium }}</b><span>mg 钠</span></div>
                  </div>
                </div>
              </div>
              <div class="pr-summary">{{ photoResult.summary }}</div>
              <div class="dp-bars" style="margin-top:12px">
                <div v-for="c in photoResult.categories" :key="c.key">
                  <div class="between tiny"><span>{{ c.name }}</span><span class="num">{{ c.share }}% · {{ c.energy }} kcal</span></div>
                  <div class="progress" style="height:6px"><i :style="{width: c.share + '%', background: c.color}"></i></div>
                </div>
              </div>
              <div class="dp-find" v-for="f in photoResult.findings" :key="f.title">
                <span class="dp-dot" :class="f.level"></span>
                <div><b>{{ f.title }}</b><span>{{ f.text }}</span></div>
              </div>
              <div class="pr-tips">
                <div class="side-cap" style="margin-bottom:4px">下一步建议</div>
                <div v-for="(s, i) in photoResult.suggestions" :key="i" class="pr-tip">
                  <span class="diet-idx">{{ i + 1 }}</span><span>{{ s }}</span>
                </div>
              </div>
              <div class="tiny faint" style="line-height:1.7;margin-top:10px">{{ photoResult.disclaimer }}</div>
            </template>
          </div>
          <div class="modal-foot">
            <template v-if="!photoResult">
              <button class="btn ghost" @click="photoOpen=false">取消</button>
              <button class="btn" :disabled="uploading" @click="submitPhoto">
                {{ uploading ? '正在分析…' : '上传并分析' }}
              </button>
            </template>
            <template v-else>
              <button class="btn ghost" @click="resetPhoto">再拍一张</button>
              <button class="btn" @click="photoOpen=false">完成</button>
            </template>
          </div>
        </div>
      </div>`,
  };
})();
