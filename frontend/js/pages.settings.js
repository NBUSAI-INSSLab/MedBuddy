/* 平台配置：推理引擎 / 主题 / 运行状态 / 审计 */
(function () {
  const { ref, computed, onMounted } = Vue;
  const Pages = (window.Pages = window.Pages || {});

  const PRESETS = [
    { id: 'siliconflow', name: '硅基流动 · 开源在线', provider: 'openai_compatible',
      base_url: 'https://api.siliconflow.cn/v1', model: 'Qwen/Qwen3-8B',
      desc: 'Qwen3-8B 免费档，OpenAI 兼容，国内直连' },
    { id: 'modelscope', name: '魔搭社区 · 开源在线', provider: 'openai_compatible',
      base_url: 'https://api-inference.modelscope.cn/v1', model: 'Qwen/Qwen3-8B',
      desc: '阿里魔搭推理 API，每日免费额度' },
    { id: 'ollama', name: 'Ollama · 完全本地', provider: 'ollama',
      base_url: 'http://127.0.0.1:11434/v1', model: 'qwen2.5:7b',
      desc: '数据不出院，需本机安装 Ollama 并拉取模型' },
    { id: 'builtin', name: '内置推理引擎 · 离线', provider: 'builtin',
      base_url: '', model: '内置推理引擎',
      desc: '零依赖零密钥，基于患者数据与证据组装回答' },
  ];

  Pages.settings = {
    components: { MbIcon: Mb.Icon },
    setup() {
      const cfg = ref(null);
      const status = ref(null);
      const audit = ref([]);
      const tab = ref(Store.params.tab || 'agent');
      const testing = ref(false);
      const testResult = ref(null);
      const saving = ref(false);
      const custom = ref('#0d9488');
      const themes = Store.themes;
      const mqtt = ref(null);
      const mqttStatus = ref(null);
      const mqttTesting = ref(false);
      const mqttResult = ref(null);
      const mqttSaving = ref(false);

      async function load() {
        try {
          cfg.value = await API.get('/api/settings/agent');
          status.value = await API.get('/api/system/status');
          audit.value = await API.get('/api/audit?limit=40');
          mqtt.value = await API.get('/api/settings/mqtt');
          mqttStatus.value = await API.get('/api/settings/mqtt/status');
        } catch (e) { ui.toast(e.message, 'err'); }
      }
      onMounted(load);

      function applyPreset(p) {
        cfg.value.provider = p.provider;
        if (p.base_url) cfg.value.base_url = p.base_url;
        cfg.value.model = p.model;
        testResult.value = null;
      }
      async function test() {
        testing.value = true;
        testResult.value = null;
        try {
          const d = await API.post('/api/settings/agent/test', {
            provider: cfg.value.provider, base_url: cfg.value.base_url,
            api_key: cfg.value.api_key, model: cfg.value.model,
          });
          testResult.value = d;
        } catch (e) { testResult.value = { success: false, message: e.message }; }
        finally { testing.value = false; }
      }
      async function save() {
        saving.value = true;
        try {
          await API.put('/api/settings/agent', cfg.value);
          ui.toast('配置已保存');
          await load();
        } catch (e) { ui.toast(e.message, 'err'); }
        finally { saving.value = false; }
      }
      async function pickTheme(t) {
        Theme.applyTheme(t.id);
        try { await API.put('/api/auth/theme', { theme: t.id }); } catch (e) {}
        ui.toast('已切换为' + t.name + '主题');
      }
      async function pickCustom() {
        Theme.setCustomTheme(custom.value);
        try { await API.put('/api/auth/theme', { theme: 'custom' }); } catch (e) {}
        ui.toast('已应用自定义主色');
      }
      const providerCn = { builtin: '内置引擎', openai_compatible: '在线 / 兼容接口', ollama: '本地 Ollama' };
      const activePreset = computed(() => {
        if (!cfg.value) return '';
        const p = PRESETS.find((x) => x.provider === cfg.value.provider && x.base_url === cfg.value.base_url);
        return p ? p.id : '';
      });
      const themeActive = computed(() => Store.theme);

      async function saveMqtt() {
        mqttSaving.value = true;
        try {
          const r = await API.put('/api/settings/mqtt', mqtt.value);
          ui.toast(mqtt.value.enabled === '1' ? '配置已保存，网关正在连接…' : '配置已保存，网关已停止');
          mqttStatus.value = r.gateway ? { ...mqttStatus.value, ...r.gateway } : mqttStatus.value;
          await load();
        } catch (e) { ui.toast(e.message, 'err'); }
        finally { mqttSaving.value = false; }
      }
      async function testMqtt() {
        mqttTesting.value = true;
        mqttResult.value = null;
        try {
          mqttResult.value = await API.post('/api/settings/mqtt/test', mqtt.value);
        } catch (e) { mqttResult.value = { success: false, message: e.message }; }
        finally { mqttTesting.value = false; }
      }
      async function restartMqtt() {
        try {
          mqttStatus.value = await API.post('/api/settings/mqtt/restart', {});
          ui.toast('网关已重启');
        } catch (e) { ui.toast(e.message, 'err'); }
      }
      const gwRunning = computed(() => mqttStatus.value && mqttStatus.value.running);
      const gwConnected = computed(() => mqttStatus.value && mqttStatus.value.connected);

      return { cfg, status, audit, tab, testing, testResult, saving, custom, themes, PRESETS,
               applyPreset, test, save, pickTheme, pickCustom, providerCn, activePreset, themeActive,
               mqtt, mqttStatus, mqttTesting, mqttResult, mqttSaving,
               saveMqtt, testMqtt, restartMqtt, gwRunning, gwConnected };
    },
    template: `
      <div v-if="cfg">
        <div class="tabs" style="margin-bottom:14px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:0 8px">
          <button class="tab" :class="{active: tab==='agent'}" @click="tab='agent'">推理引擎</button>
          <button class="tab" :class="{active: tab==='iot'}" @click="tab='iot'">设备接入</button>
          <button class="tab" :class="{active: tab==='theme'}" @click="tab='theme'">主题外观</button>
          <button class="tab" :class="{active: tab==='system'}" @click="tab='system'">运行状态</button>
          <button class="tab" :class="{active: tab==='audit'}" @click="tab='audit'">审计日志</button>
        </div>

        <div v-if="tab==='agent'" class="grid g-2-1">
          <div class="card">
            <div class="card-head"><h3>模型接入</h3><span class="sub">支持开源在线模型与本地 Ollama</span></div>
            <div class="card-body">
              <div class="grid g2" style="gap:9px;margin-bottom:6px">
                <div v-for="p in PRESETS" :key="p.id" class="theme-card" :class="{active: activePreset===p.id}"
                     style="text-align:left" @click="applyPreset(p)">
                  <div class="row" style="gap:6px;margin-bottom:3px">
                    <span class="small bold">{{ p.name }}</span>
                  </div>
                  <div class="tiny faint" style="line-height:1.55">{{ p.desc }}</div>
                </div>
              </div>

              <div class="form-row">
                <label>接入方式</label>
                <div>
                  <select class="select" v-model="cfg.provider">
                    <option value="builtin">内置推理引擎（离线）</option>
                    <option value="openai_compatible">OpenAI 兼容接口（在线开源模型）</option>
                    <option value="ollama">本地 Ollama</option>
                  </select>
                  <div class="help">选择在线模型后需填写 Base URL、模型名与 API Key；Ollama 默认地址 127.0.0.1:11434/v1。</div>
                </div>
              </div>
              <div class="form-row" v-if="cfg.provider !== 'builtin'">
                <label>接口地址</label>
                <div><input class="input" v-model="cfg.base_url" placeholder="https://api.siliconflow.cn/v1"></div>
              </div>
              <div class="form-row" v-if="cfg.provider !== 'builtin'">
                <label>API Key</label>
                <div>
                  <input class="input" v-model="cfg.api_key" :placeholder="cfg.has_key ? '已保存密钥，留空则不修改' : 'sk-...'" autocomplete="off">
                  <div class="help">密钥仅保存在本机 SQLite，不回显明文。</div>
                </div>
              </div>
              <div class="form-row" v-if="cfg.provider !== 'builtin'">
                <label>模型名称</label>
                <div><input class="input" v-model="cfg.model" placeholder="Qwen/Qwen3-8B"></div>
              </div>
              <div class="form-row">
                <label>向量模型（可选）</label>
                <div>
                  <input class="input" v-model="cfg.embedding_model" placeholder="留空使用本地字符 n-gram 向量">
                  <div class="help">填入如 BAAI/bge-m3 后，知识库重建将调用 embedding 接口；失败自动回退本地向量。</div>
                </div>
              </div>
              <div class="form-row">
                <label>生成参数</label>
                <div class="row" style="gap:10px;flex-wrap:wrap">
                  <div style="flex:1;min-width:110px">
                    <span class="tiny faint">温度</span>
                    <input class="input" type="number" step="0.1" min="0" max="1.5" v-model.number="cfg.temperature">
                  </div>
                  <div style="flex:1;min-width:110px">
                    <span class="tiny faint">最大长度</span>
                    <input class="input" type="number" v-model.number="cfg.max_tokens">
                  </div>
                  <div style="flex:1;min-width:110px">
                    <span class="tiny faint">检索条数</span>
                    <input class="input" type="number" v-model.number="cfg.top_k">
                  </div>
                </div>
              </div>
              <div class="form-row">
                <label>安全门禁</label>
                <label class="switch">
                  <input type="checkbox" :checked="cfg.enable_safety === '1'"
                         @change="cfg.enable_safety = $event.target.checked ? '1' : '0'">
                  <i></i>
                  <span>启用红旗症状与危急值拦截（强烈建议开启）</span>
                </label>
              </div>
              <div class="form-row">
                <label>系统提示词</label>
                <div><textarea class="textarea" v-model="cfg.system_prompt" style="min-height:110px"></textarea></div>
              </div>

              <div class="row mt14">
                <button class="btn ghost" :disabled="testing" @click="test">
                  <mb-icon name="activity" :size="14"/> {{ testing ? '测试中…' : '测试连接' }}
                </button>
                <button class="btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存配置' }}</button>
                <span class="tiny faint" style="margin-left:auto">当前：{{ providerCn[cfg.provider] }}</span>
              </div>

              <div v-if="testResult" class="status-line"
                   :style="{background: testResult.success ? '#ecfdf5' : '#fef2f2', color: testResult.success ? '#047857' : '#b91c1c'}">
                <mb-icon :name="testResult.success ? 'check' : 'alert'" :size="15"/>
                <div>{{ testResult.message }}<span v-if="testResult.latency_ms"> · {{ testResult.latency_ms }}ms</span></div>
              </div>
              <div v-if="cfg.provider === 'builtin'" class="status-line" style="background:#f8fafc;color:#475569">
                <mb-icon name="shield" :size="15"/>
                <div>内置引擎不调用外部接口，直接基于患者数据与知识库证据组装回答，适合演示与断网环境。</div>
              </div>
            </div>
          </div>

          <div>
            <div class="card">
              <div class="card-head"><h3>当前生效</h3></div>
              <div class="card-body">
                <div class="ctx-item"><span class="ctx-k">接入方式</span><span class="ctx-v">{{ providerCn[cfg.provider] }}</span></div>
                <div class="ctx-item"><span class="ctx-k">模型</span><span class="ctx-v" style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ cfg.model || '内置推理引擎' }}</span></div>
                <div class="ctx-item"><span class="ctx-k">向量方案</span><span class="ctx-v" style="max-width:160px;text-align:right">{{ cfg.embedding_model || '本地 n-gram' }}</span></div>
                <div class="ctx-item"><span class="ctx-k">安全门禁</span><span class="ctx-v">{{ cfg.enable_safety === '1' ? '已开启' : '已关闭' }}</span></div>
                <div class="ctx-item"><span class="ctx-k">知识片段</span><span class="ctx-v">{{ status ? status.chunks : '—' }}</span></div>
                <div class="tip-card" style="margin-top:12px;font-size:11.5px">
                  <mb-icon name="brain" :size="15"/>
                  <div>每次对话后系统会抽取事实、偏好、困难与目标写入长期记忆，并重新计算个性化成熟度。</div>
                </div>
              </div>
            </div>
            <div class="card mt14">
              <div class="card-head"><h3>模型选型建议</h3></div>
              <div class="card-body small muted" style="line-height:1.9">
                <div>· 演示 / 内网：内置引擎或 Ollama qwen2.5:7b</div>
                <div>· 日常随访：Qwen3-8B（免费档，中文医疗语境好）</div>
                <div>· 复杂共病：DeepSeek-V3 / Qwen3-32B 以上</div>
                <div>· 合规要求高：全部本地部署，数据不出院</div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="tab==='iot'" class="grid g-2-1">
          <div class="card" v-if="mqtt">
            <div class="card-head"><h3>MQTT 接入配置</h3><span class="sub">心率、血压、血氧、体温、HRV 设备统一接入</span></div>
            <div class="card-body">
              <div class="form-row">
                <label>启用网关</label>
                <label class="switch">
                  <input type="checkbox" :checked="mqtt.enabled === '1'"
                         @change="mqtt.enabled = $event.target.checked ? '1' : '0'">
                  <i></i>
                  <span>保存后自动连接 Broker 并订阅主题</span>
                </label>
              </div>
              <div class="grid g2" style="gap:10px">
                <div class="form-col">
                  <label>Broker 地址</label>
                  <input class="input" v-model="mqtt.host" placeholder="127.0.0.1 或 mqtt.example.com">
                </div>
                <div class="form-col">
                  <label>端口</label>
                  <input class="input" type="number" v-model.number="mqtt.port" placeholder="1883">
                </div>
              </div>
              <div class="grid g2" style="gap:10px">
                <div class="form-col">
                  <label>用户名（可选）</label>
                  <input class="input" v-model="mqtt.username" autocomplete="off" placeholder="留空表示匿名">
                </div>
                <div class="form-col">
                  <label>密码（可选）</label>
                  <input class="input" type="password" v-model="mqtt.password" autocomplete="new-password"
                         :placeholder="mqtt.has_password ? '已保存，留空不修改' : '留空表示无密码'">
                </div>
              </div>
              <div class="form-row">
                <label>订阅主题</label>
                <div>
                  <input class="input num" v-model="mqtt.topic" placeholder="medbuddy/+/vitals">
                  <div class="help">「+」位置为设备序列号，例如 medbuddy/MB-BP-1001/vitals；也支持 medbuddy/patients/+/data。</div>
                </div>
              </div>
              <div class="grid g2" style="gap:10px">
                <div class="form-col">
                  <label>客户端 ID</label>
                  <input class="input" v-model="mqtt.client_id">
                </div>
                <div class="form-col">
                  <label>QoS</label>
                  <select class="select" v-model.number="mqtt.qos">
                    <option :value="0">0 · 最多一次</option>
                    <option :value="1">1 · 至少一次（推荐）</option>
                    <option :value="2">2 · 恰好一次</option>
                  </select>
                </div>
              </div>
              <div class="grid g2" style="gap:10px">
                <div class="form-col">
                  <label>报文格式</label>
                  <select class="select" v-model="mqtt.payload_format">
                    <option value="json">JSON（推荐）</option>
                    <option value="csv">CSV · k=v</option>
                  </select>
                </div>
                <div class="form-col">
                  <label>去重窗口（秒）</label>
                  <input class="input" type="number" v-model.number="mqtt.dedupe_seconds">
                </div>
              </div>
              <div class="grid g2" style="gap:10px">
                <div class="form-col">
                  <label>原始报文保留（天）</label>
                  <input class="input" type="number" v-model.number="mqtt.retention_days">
                </div>
                <div class="form-col">
                  <label>自动注册未登记设备</label>
                  <label class="switch" style="margin-top:7px">
                    <input type="checkbox" :checked="mqtt.auto_register === '1'"
                           @change="mqtt.auto_register = $event.target.checked ? '1' : '0'">
                    <i></i><span class="tiny">首次上报即建档</span>
                  </label>
                </div>
              </div>
              <div class="form-row">
                <label>传输加密</label>
                <label class="switch">
                  <input type="checkbox" :checked="mqtt.tls === '1'"
                         @change="mqtt.tls = $event.target.checked ? '1' : '0'">
                  <i></i>
                  <span>启用 TLS（自签证书不校验，适合内网自建 Broker）</span>
                </label>
              </div>

              <div class="row mt14">
                <button class="btn ghost" :disabled="mqttTesting" @click="testMqtt">
                  <mb-icon name="activity" :size="14"/> {{ mqttTesting ? '连接中…' : '测试连接' }}
                </button>
                <button class="btn" :disabled="mqttSaving" @click="saveMqtt">{{ mqttSaving ? '保存中…' : '保存并应用' }}</button>
                <span class="tiny faint" style="margin-left:auto">{{ gwConnected ? '网关已连接' : (gwRunning ? '网关重连中' : '网关未运行') }}</span>
              </div>

              <div v-if="mqttResult" class="status-line"
                   :style="{background: mqttResult.success ? '#ecfdf5' : '#fef2f2', color: mqttResult.success ? '#047857' : '#b91c1c'}">
                <mb-icon :name="mqttResult.success ? 'check' : 'alert'" :size="15"/>
                <div>{{ mqttResult.message }}<span v-if="mqttResult.latency_ms"> · {{ mqttResult.latency_ms }}ms</span></div>
              </div>
            </div>
          </div>

          <div>
            <div class="card">
              <div class="card-head">
                <h3>运行状态</h3>
                <div class="right">
                  <span class="dev-state" :class="gwConnected ? 'ok' : (gwRunning ? 'warn' : 'off')">
                    <i></i>{{ gwConnected ? '已连接' : (gwRunning ? '重连中' : '未启用') }}
                  </span>
                </div>
              </div>
              <div class="card-body" v-if="mqttStatus">
                <div class="ctx-item"><span class="ctx-k">Broker</span><span class="ctx-v num">{{ mqttStatus.broker || '—' }}</span></div>
                <div class="ctx-item"><span class="ctx-k">主题</span><span class="ctx-v num" style="max-width:170px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ mqttStatus.topic || '—' }}</span></div>
                <div class="ctx-item"><span class="ctx-k">已接入设备</span><span class="ctx-v">{{ mqttStatus.devices }} 台</span></div>
                <div class="ctx-item"><span class="ctx-k">收到报文</span><span class="ctx-v">{{ mqttStatus.stats.messages }} 条</span></div>
                <div class="ctx-item"><span class="ctx-k">入库指标</span><span class="ctx-v">{{ mqttStatus.stats.readings }} 条</span></div>
                <div class="ctx-item"><span class="ctx-k">近 1 小时</span><span class="ctx-v">{{ mqttStatus.last_readings }} 条报文</span></div>
                <div class="ctx-item"><span class="ctx-k">错误计数</span><span class="ctx-v">{{ mqttStatus.stats.errors }}</span></div>
                <button class="btn soft" style="width:100%;margin-top:10px" @click="restartMqtt">重启网关</button>
                <div v-if="mqttStatus.stats.last_error" class="status-line" style="background:#fef2f2;color:#b91c1c;margin-top:10px">
                  <mb-icon name="alert" :size="15"/><div>{{ mqttStatus.stats.last_error }}</div>
                </div>
              </div>
              <div class="card-body" v-else><div class="empty">暂无状态</div></div>
            </div>

            <div class="card mt14">
              <div class="card-head"><h3>最近事件</h3></div>
              <div class="card-body" style="padding-top:8px">
                <div v-for="(e, i) in (mqttStatus ? mqttStatus.events : [])" :key="i" class="row" style="align-items:flex-start;gap:7px;margin-bottom:6px">
                  <span class="tiny faint num nowrap" style="width:78px">{{ (e.created_at || '').slice(5,16) }}</span>
                  <span class="tag soft" style="flex:0 0 auto">{{ e.event }}</span>
                  <span class="tiny" style="color:var(--text-2)">{{ e.detail }}</span>
                </div>
                <div v-if="!mqttStatus || !mqttStatus.events.length" class="empty">暂无事件</div>
              </div>
            </div>
          </div>

          <div class="card mt14" style="grid-column:1 / -1">
            <div class="card-head"><h3>报文规范</h3><span class="sub">协议为 MQTT 3.1.1，主题第二段即设备序列号</span></div>
            <div class="card-body grid g2" style="gap:20px">
              <div>
                <div class="side-cap">JSON（推荐）</div>
                <div class="code-block">topic: medbuddy/MB-BP-1001/vitals
{
  "device_sn": "MB-BP-1001",
  "patient_id": 1,
  "ts": "2026-10-19 08:30:00",
  "vitals": {
    "sbp": 135, "dbp": 85,
    "heart_rate": 76, "spo2": 98,
    "temp": 36.5, "hrv": 42
  },
  "battery": 86, "signal": -58
}</div>
              </div>
              <div>
                <div class="side-cap">字段与校验</div>
                <div class="small muted" style="line-height:1.95">
                  · 支持别名：hr / pulse / SBP / DBP / spo / temperature / rmssd，也可用 bp:{sbp,dbp} 嵌套；<br>
                  · 量程校验：收缩压 50–300、心率 25–250、血氧 50–100、体温 30–45、HRV 1–400，越界丢弃并记录原因；<br>
                  · 同一设备同指标 2 秒内重复报文自动去重；<br>
                  · 未绑定设备可在报文带 patient_id 自助绑定；<br>
                  · 时间戳支持秒/毫秒时间戳与常见日期格式，缺省取服务端时间。
                </div>
                <div class="code-block" style="margin-top:10px">CSV 示例：hr=76,sbp=135,dbp=85,spo2=98,temp=36.5,hrv=42</div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="tab==='theme'" class="grid g-2-1">
          <div class="card">
            <div class="card-head"><h3>主题配色</h3><span class="sub">即时生效并同步到账号</span></div>
            <div class="card-body">
              <div class="theme-grid">
                <div v-for="t in themes" :key="t.id" class="theme-card" :class="{active: themeActive===t.id}" @click="pickTheme(t)">
                  <div class="theme-dot"
                       :style="{background: t.dual
                         ? 'linear-gradient(135deg,' + t.primary + ' 0 55%,' + t.accent + ' 55% 100%)'
                         : 'linear-gradient(135deg,' + t.primary + ',' + t.dark + ')'}"></div>
                  <div class="theme-name">{{ t.name }}</div>
                  <div class="tiny faint" style="margin-top:2px">{{ t.desc }}</div>
                </div>
              </div>
              <div class="form-row mt20">
                <label>自定义主色</label>
                <div class="row">
                  <input type="color" v-model="custom" style="width:46px;height:36px;border:1px solid var(--line);border-radius:8px;padding:2px;background:#fff">
                  <input class="input" v-model="custom" style="width:120px">
                  <button class="btn ghost" @click="pickCustom">应用</button>
                </div>
              </div>
              <div class="tip-card" style="margin-top:12px">
                <mb-icon name="sparkles" :size="15"/>
                <div>主题通过 CSS 变量驱动，切换后卡片、按钮、图表、登录页与侧栏标识同步更新；「橙蓝」为双色方案，橙色主色配蓝色点缀。</div>
              </div>
            </div>
          </div>
          <div class="card">
            <div class="card-head"><h3>预览</h3></div>
            <div class="card-body">
              <div class="tip-card" style="margin-bottom:10px"><mb-icon name="heart" :size="16"/><div>这是提示卡片的样式预览。</div></div>
              <div class="row" style="flex-wrap:wrap;margin-bottom:10px">
                <span class="tag primary">主要</span><span class="tag ok">正常</span>
                <span class="tag amber">关注</span><span class="tag red">危急</span>
              </div>
              <div class="progress" style="margin-bottom:10px"><i style="width:68%"></i></div>
              <div class="row"><button class="btn">主要按钮</button><button class="btn ghost">次要按钮</button><button class="btn soft">轻按钮</button></div>
            </div>
          </div>
        </div>

        <div v-if="tab==='system'" class="grid g-2-1">
          <div class="card">
            <div class="card-head"><h3>运行状态</h3><span class="sub">本地 SQLite + 内存索引</span></div>
            <div class="card-body">
              <div class="info-grid">
                <div class="info-item"><div class="k">平台版本</div><div class="v">{{ status.version }}</div></div>
                <div class="info-item"><div class="k">数据库大小</div><div class="v">{{ status.db_size_mb }} MB</div></div>
                <div class="info-item"><div class="k">在管患者</div><div class="v">{{ status.patients }} 人</div></div>
                <div class="info-item"><div class="k">指标记录</div><div class="v">{{ status.metrics }} 条</div></div>
                <div class="info-item"><div class="k">对话消息</div><div class="v">{{ status.messages }} 条</div></div>
                <div class="info-item"><div class="k">长期记忆</div><div class="v">{{ status.memories }} 条</div></div>
                <div class="info-item"><div class="k">知识库文档</div><div class="v">{{ status.documents }} 篇</div></div>
                <div class="info-item"><div class="k">索引片段</div><div class="v">{{ status.indexed }} 个</div></div>
                <div class="info-item"><div class="k">向量方案</div><div class="v">{{ status.embedding }}</div></div>
              </div>
              <div class="tip-card" style="margin-top:16px">
                <mb-icon name="database" :size="15"/>
                <div>患者数据、对话、记忆与知识库全部存放在 data/medbuddy.db，可直接备份该文件完成迁移。</div>
              </div>
            </div>
          </div>
          <div class="card">
            <div class="card-head"><h3>技术栈</h3></div>
            <div class="card-body small muted" style="line-height:2">
              <div>· 后端：Flask + SQLite（WAL）</div>
              <div>· 前端：Vue 3（本地化，无构建）</div>
              <div>· 检索：jieba BM25 + 字符 n-gram 向量</div>
              <div>· 模型：OpenAI 兼容 / Ollama / 内置</div>
              <div>· 流式：SSE（Server-Sent Events）</div>
              <div>· 安全：红旗症状 + 危急值双门禁</div>
            </div>
          </div>
        </div>

        <div v-if="tab==='audit'" class="card flush">
          <div class="card-head" style="padding-bottom:12px"><h3>审计日志</h3><span class="sub">记录登录、对话、指标、配置与知识库操作</span></div>
          <table class="table">
            <thead><tr><th style="width:150px">时间</th><th style="width:110px">操作者</th><th style="width:140px">动作</th><th>详情</th></tr></thead>
            <tbody>
              <tr v-for="a in audit" :key="a.id">
                <td class="small num faint">{{ a.created_at }}</td>
                <td class="small">{{ a.actor }}</td>
                <td><span class="tag soft">{{ a.action }}</span></td>
                <td class="small muted">{{ a.detail || a.target }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="!audit.length" class="empty">暂无日志</div>
        </div>
      </div>
      <div v-else class="empty">正在加载配置…</div>`,
  };
})();
