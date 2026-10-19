/* 我的设备：患者自行接入家庭体征设备、日常测量与数据同步 */
(function () {
  const { ref, computed, onMounted, onUnmounted } = Vue;
  const Pages = (window.Pages = window.Pages || {});

  const TYPES = [
    { key: 'bp', name: '电子血压计', icon: 'heart', prefix: 'MB-BP-', model: 'OMRON HEM-7361T', vendor: '欧姆龙',
      desc: '测量收缩压、舒张压与心率' },
    { key: 'ox', name: '指夹血氧仪', icon: 'drop', prefix: 'MB-OX-', model: 'YUWELL YX306', vendor: '鱼跃',
      desc: '测量血氧饱和度与脉率' },
    { key: 'temp', name: '红外体温计', icon: 'activity', prefix: 'MB-TM-', model: 'BRAUN BNT400', vendor: '博朗',
      desc: '测量体温，支持连续记录' },
    { key: 'hrv', name: '智能手环', icon: 'trend', prefix: 'MB-WR-', model: 'HUAWEI Band 9', vendor: '华为',
      desc: '记录心率变异性、静息心率与体温' },
  ];

  Pages.devices = {
    components: { MbIcon: Mb.Icon },
    setup() {
      const data = ref(null);
      const feed = ref([]);
      const loading = ref(true);
      const auto = ref(true);
      const busy = ref(false);
      const showAdd = ref(false);
      const addType = ref('bp');
      const rawTarget = ref(null);
      const rawRows = ref([]);
      const form = ref({ device_sn: '', name: '', model: '', vendor: '' });
      let timer = null;

      async function load(silent) {
        if (!silent) loading.value = true;
        try {
          const d = await API.get('/api/devices');
          data.value = d;
          feed.value = await API.get('/api/device-readings?limit=14');
        } catch (e) {
          if (!silent) ui.toast(e.message, 'err');
        } finally {
          loading.value = false;
        }
      }
      onMounted(async () => {
        await load();
        timer = setInterval(() => { if (auto.value) load(true); }, 8000);
      });
      onUnmounted(() => clearInterval(timer));

      const items = computed(() => (data.value ? data.value.items : []));
      const summary = computed(() => (data.value ? data.value.summary : {}));
      const latestAt = computed(() => {
        const times = items.value.map((d) => d.last_seen).filter(Boolean).sort();
        return times.length ? times[times.length - 1] : null;
      });
      const typeOf = (d) => {
        const sn = (d.device_sn || '').toUpperCase();
        if (sn.indexOf('BP') >= 0) return TYPES[0];
        if (sn.indexOf('OX') >= 0) return TYPES[1];
        if (sn.indexOf('TM') >= 0 || sn.indexOf('TP') >= 0) return TYPES[2];
        if (sn.indexOf('WR') >= 0 || sn.indexOf('HRV') >= 0) return TYPES[3];
        return { key: 'other', name: '体征设备', icon: 'cpu', desc: '通用体征采集设备' };
      };

      function openAdd() {
        addType.value = 'bp';
        pickType('bp');
        showAdd.value = true;
      }
      function pickType(key) {
        addType.value = key;
        const t = TYPES.find((x) => x.key === key) || TYPES[0];
        form.value = {
          device_sn: t.prefix + String(Math.floor(1000 + Math.random() * 9000)),
          name: t.name, model: t.model, vendor: t.vendor,
        };
      }
      async function create() {
        if (!form.value.device_sn.trim()) return ui.toast('请填写设备序列号', 'err');
        busy.value = true;
        try {
          await API.post('/api/devices', {
            device_sn: form.value.device_sn.trim(), name: form.value.name.trim() || undefined,
            model: form.value.model.trim() || undefined, vendor: form.value.vendor.trim() || undefined,
          });
          ui.toast('设备已接入，等待第一条测量数据');
          showAdd.value = false;
          await load();
        } catch (e) { ui.toast(e.message, 'err'); }
        finally { busy.value = false; }
      }
      async function measure(d) {
        busy.value = true;
        try {
          const r = await API.post('/api/devices/' + d.id + '/simulate', { count: 1 });
          ui.toast('测量完成，已同步到健康档案');
          await load(true);
        } catch (e) { ui.toast(e.message, 'err'); }
        finally { busy.value = false; }
      }
      async function openRaw(d) {
        rawTarget.value = d;
        try { rawRows.value = await API.get('/api/devices/' + d.id + '/readings?limit=16'); }
        catch (e) { rawRows.value = []; }
      }
      async function remove(d) {
        if (!window.confirm('解除「' + d.name + '」的接入？已上传的体征数据会保留在健康档案中。')) return;
        try {
          await API.del('/api/devices/' + d.id);
          ui.toast('设备已解除接入');
          await load();
        } catch (e) { ui.toast(e.message, 'err'); }
      }
      function ago(t) {
        if (!t) return '从未';
        const d = new Date(t.replace(/-/g, '/'));
        const s = Math.floor((Date.now() - d.getTime()) / 1000);
        if (s < 60) return s + ' 秒前';
        if (s < 3600) return Math.floor(s / 60) + ' 分钟前';
        if (s < 86400) return Math.floor(s / 3600) + ' 小时前';
        return Math.floor(s / 86400) + ' 天前';
      }
      const batteryColor = (v) => (v == null ? 'var(--faint)' : v < 20 ? '#dc2626' : v < 40 ? '#d97706' : 'var(--ok)');
      const signalText = (v) => (v == null ? '—' : v > -60 ? '强' : v > -75 ? '中' : '弱');

      return { data, feed, loading, auto, busy, showAdd, addType, form, rawTarget, rawRows,
               items, summary, latestAt, TYPES, typeOf, load, openAdd, pickType, create, measure,
               openRaw, remove, ago, batteryColor, signalText };
    },
    template: `
      <div>
        <div v-if="loading" class="empty">正在读取您的设备…</div>
        <div v-else>
          <div class="dev-hero">
            <div class="dev-hero-copy">
              <div class="dev-kicker"><span class="live-dot"></span> 家庭体征设备 · 数据自动同步健康档案</div>
              <h2>把家里的设备接进来</h2>
              <p>血压计、血氧仪、体温计、智能手环接入后，日常测量会自动写入你的档案，医生看到的趋势与预警都来自这些真实数据。</p>
              <div class="dev-hero-actions">
                <button class="btn light" @click="openAdd"><mb-icon name="plus" :size="15"/> 接入新设备</button>
                <button class="btn ghost light" @click="$root.go('portal')"><mb-icon name="heart" :size="15"/> 查看健康档案</button>
              </div>
            </div>
            <div class="dev-hero-stats">
              <div class="dhs"><b>{{ summary.total || 0 }}</b><span>已接入设备</span></div>
              <div class="dhs"><b>{{ summary.online || 0 }}</b><span>当前在线</span></div>
              <div class="dhs"><b>{{ summary.today_readings || 0 }}</b><span>今日测量</span></div>
            </div>
            <div class="dev-orb dev-orb-a"></div>
            <div class="dev-orb dev-orb-b"></div>
          </div>

          <div class="grid g3 mt14">
            <div class="card kpi">
              <div class="kpi-top"><span class="kpi-ico"><mb-icon name="cpu" :size="15"/></span>设备状态</div>
              <div class="kpi-val num">{{ summary.online || 0 }}<small>/ {{ summary.total || 0 }} 在线</small></div>
              <div class="kpi-foot">离线设备下次开机后会自动补传缓存数据</div>
            </div>
            <div class="card kpi">
              <div class="kpi-top"><span class="kpi-ico" style="background:#eff6ff;color:#2563eb"><mb-icon name="activity" :size="15"/></span>最近同步</div>
              <div class="kpi-val" style="font-size:20px">{{ latestAt ? ago(latestAt) : '暂无数据' }}</div>
              <div class="kpi-foot">数据通道每 8 秒自动刷新</div>
            </div>
            <div class="card kpi">
              <div class="kpi-top"><span class="kpi-ico" style="background:#fff7ed;color:#ea580c"><mb-icon name="bell" :size="15"/></span>近 24 小时提醒</div>
              <div class="kpi-val num" style="color:#ea580c">{{ summary.alerts_24h || 0 }}<small>条</small></div>
              <div class="kpi-foot">异常读数会自动通知签约医生</div>
            </div>
          </div>

          <div class="card mt14">
            <div class="card-head">
              <h3>我的设备</h3>
              <span class="sub">点击「立即测量」可在没有硬件时体验一次完整的数据链路</span>
              <div class="right">
                <label class="switch"><input type="checkbox" v-model="auto"><i></i><span class="tiny">自动刷新</span></label>
                <button class="btn sm" @click="openAdd"><mb-icon name="plus" :size="13"/> 接入</button>
              </div>
            </div>
            <div class="card-body">
              <div v-if="items.length" class="mydev-grid">
                <div class="mydev" v-for="d in items" :key="d.id">
                  <div class="mydev-top">
                    <div class="mydev-ico" :class="typeOf(d).key"><mb-icon :name="typeOf(d).icon" :size="19"/></div>
                    <div class="grow" style="min-width:0">
                      <div class="mydev-name">{{ d.name }}</div>
                      <div class="mydev-sub num">{{ d.device_sn }} · {{ d.model || '未填写型号' }}</div>
                    </div>
                    <span class="dev-state" :class="d.status === 'online' ? 'ok' : 'off'"><i></i>{{ d.status === 'online' ? '在线' : '离线' }}</span>
                  </div>
                  <div class="mydev-vital">
                    <template v-if="d.latest"><span class="num">{{ d.latest.text }}</span><small>{{ ago(d.latest.at) }}</small></template>
                    <template v-else><span class="faint">还没有测量数据</span></template>
                  </div>
                  <div class="mydev-meta">
                    <span>今日 <b class="num">{{ d.today_count }}</b> 条</span>
                    <span>电量 <b class="num" :style="{color: batteryColor(d.battery)}">{{ d.battery != null ? d.battery + '%' : '—' }}</b></span>
                    <span>信号 {{ signalText(d.signal) }}</span>
                  </div>
                  <div class="mydev-foot">
                    <button class="btn sm" :disabled="busy" @click="measure(d)"><mb-icon name="activity" :size="13"/> 立即测量</button>
                    <button class="btn sm ghost" @click="openRaw(d)">测量记录</button>
                    <button class="msg-tool" title="解除接入" @click="remove(d)"><mb-icon name="trash" :size="13"/></button>
                  </div>
                </div>
              </div>
              <div v-else class="dev-empty">
                <div class="dev-empty-ico"><mb-icon name="cpu" :size="26"/></div>
                <div>
                  <div class="bold">还没有接入设备</div>
                  <div class="small muted" style="margin-top:3px">用手机或家用网关扫描设备即可完成接入，也可以在下方手动登记序列号。</div>
                </div>
                <button class="btn" @click="openAdd"><mb-icon name="plus" :size="15"/> 接入第一台设备</button>
              </div>
            </div>
          </div>

          <div class="grid g-2-1 mt14">
            <div class="card">
              <div class="card-head"><h3>实时体征</h3><span class="sub">最近 14 次上报</span>
                <div class="right"><span class="live-dot"></span><span class="tiny faint">实时</span></div>
              </div>
              <div class="card-body feed-list" style="max-height:318px;overflow:auto">
                <div v-for="f in feed" :key="f.id" class="feed-item">
                  <div class="feed-dot" :class="f.status === 'ok' ? 'ok' : 'warn'"></div>
                  <div class="grow" style="min-width:0">
                    <div class="between">
                      <span class="small bold">{{ f.device_name }}</span>
                      <span class="tiny faint nowrap">{{ f.at.slice(11, 19) }}</span>
                    </div>
                    <div class="tiny" style="color:var(--text-2);margin-top:2px">{{ f.text || '未识别到有效体征' }}</div>
                    <div class="tiny faint">{{ f.count }} 条指标 · {{ f.status === 'ok' ? '已入库' : f.status }}</div>
                  </div>
                </div>
                <div v-if="!feed.length" class="empty">暂无上报记录，先接一台设备试试</div>
              </div>
            </div>

            <div class="card">
              <div class="card-head"><h3>接入指引</h3><span class="sub">三步完成</span></div>
              <div class="card-body">
                <div class="dev-step"><span class="ds-idx">1</span><div><b>选择设备并登记序列号</b><div class="tiny faint">序列号在机身背面或电池仓内，接入后归属你本人档案。</div></div></div>
                <div class="dev-step"><span class="ds-idx">2</span><div><b>让设备连上家庭网络</b><div class="tiny faint">按说明书把设备或网关指向平台的 MQTT 地址，家用网关只需配置一次。</div></div></div>
                <div class="dev-step"><span class="ds-idx">3</span><div><b>日常测量即可</b><div class="tiny faint">测量后数据自动上传，异常读数会提醒医生，也会出现在首页概览。</div></div></div>
                <div class="tip-card" style="margin-top:6px">
                  <mb-icon name="shield" :size="15"/>
                  <div>体征数据仅用于本人健康管理，采用本地存储，不替代临床诊断。</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 接入设备 -->
        <div class="mask" v-if="showAdd" @click.self="showAdd=false">
          <div class="modal" style="max-width:520px">
            <div class="modal-head"><h3>接入新设备</h3><button class="icon-btn" @click="showAdd=false"><mb-icon name="close" :size="16"/></button></div>
            <div class="modal-body">
              <div class="field" style="margin-top:0">
                <label>设备类型</label>
                <div class="type-grid">
                  <button v-for="t in TYPES" :key="t.key" class="type-card" :class="{active: addType===t.key}" @click="pickType(t.key)">
                    <span class="type-ico"><mb-icon :name="t.icon" :size="17"/></span>
                    <b>{{ t.name }}</b>
                    <small>{{ t.desc }}</small>
                  </button>
                </div>
              </div>
              <div class="field">
                <label>设备序列号 *</label>
                <input class="input num" v-model="form.device_sn" placeholder="MB-BP-1001">
                <div class="field-help">自动生成的是示例编号，请改成机身上的真实序列号</div>
              </div>
              <div class="auth-grid">
                <div class="field">
                  <label>设备名称</label>
                  <input class="input" v-model="form.name" placeholder="客厅血压计">
                </div>
                <div class="field">
                  <label>厂商</label>
                  <input class="input" v-model="form.vendor" placeholder="欧姆龙">
                </div>
              </div>
              <div class="tip-card" style="margin-top:12px">
                <mb-icon name="users" :size="15"/>
                <div>接入后设备自动绑定到你的健康档案，测量数据将参与趋势分析与个性化建议。</div>
              </div>
            </div>
            <div class="modal-foot">
              <button class="btn ghost" @click="showAdd=false">取消</button>
              <button class="btn" :disabled="busy" @click="create">{{ busy ? '接入中…' : '确认接入' }}</button>
            </div>
          </div>
        </div>

        <!-- 测量记录 -->
        <div class="mask" v-if="rawTarget" @click.self="rawTarget=null">
          <div class="modal" style="max-width:560px">
            <div class="modal-head"><h3>{{ rawTarget.name }} · 测量记录</h3></div>
            <div class="modal-body" style="max-height:60vh;overflow:auto">
              <div v-for="r in rawRows" :key="r.id" class="raw-row">
                <div class="between">
                  <span class="tiny faint num">{{ r.at }}</span>
                  <span class="tag" :class="r.status === 'ok' ? 'ok' : 'red'">{{ r.status === 'ok' ? '已记录' : r.status }}</span>
                </div>
                <div class="small" style="margin:3px 0">{{ r.text || '—' }}</div>
              </div>
              <div v-if="!rawRows.length" class="empty">暂无测量记录</div>
            </div>
            <div class="modal-foot"><button class="btn ghost" @click="rawTarget=null">关闭</button></div>
          </div>
        </div>
      </div>`,
  };
})();
