/* AI 智能助手 · 流式对话 */
(function () {
  const { ref, computed, onMounted, nextTick, watch } = Vue;
  const Pages = (window.Pages = window.Pages || {});

  function escapeHtml(s) {
    return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderMarkdown(text) {
    let html = escapeHtml(text || '');
    html = html.replace(/^#{1,4}\s*/gm, '');
    html = html.replace(/\[(\d{1,2})\]/g, (m, n) => `<span class="cite-link" data-cite="${n}">${n}</span>`);
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    const blocks = html.split(/\n{2,}/);
    return blocks.map((block) => {
      const lines = block.split('\n').filter((l) => l.trim() !== '');
      if (!lines.length) return '';
      if (lines.every((l) => /^\s*[-•·]\s+/.test(l))) {
        return '<ul>' + lines.map((l) => `<li>${l.replace(/^\s*[-•·]\s+/, '')}</li>`).join('') + '</ul>';
      }
      if (lines.every((l) => /^\s*>/.test(l))) {
        return '<blockquote>' + lines.map((l) => l.replace(/^\s*>\s?/, '')).join('<br>') + '</blockquote>';
      }
      return '<p>' + lines.join('<br>') + '</p>';
    }).join('');
  }

  Pages.chat = {
    components: { MbIcon: Mb.Icon, MbRing: Mb.Ring },
    setup() {
      const isPatient = Store.user && Store.user.role === 'patient';
      const patients = ref([]);
      const patientId = ref(isPatient ? Store.user.patient_id : (Store.params.patient || null));
      const conversations = ref([]);
      const convId = ref(null);
      const messages = ref([]);
      const ctx = ref(null);
      const input = ref('');
      const sending = ref(false);
      const streamText = ref('');
      const showCite = ref(false);
      const cite = ref(null);
      const loading = ref(false);
      const scrollBox = ref(null);

      const lastAssistant = computed(() => {
        for (let i = messages.value.length - 1; i >= 0; i--) {
          if (messages.value[i].role === 'assistant') return messages.value[i];
        }
        return null;
      });
      const evidence = computed(() => (lastAssistant.value ? lastAssistant.value.citations || [] : []));
      const activePatient = computed(() => patients.value.find((p) => p.id === patientId.value)
        || (ctx.value && ctx.value.profile ? ctx.value.profile : null));

      async function loadPatients() {
        if (isPatient) return;
        try {
          const d = await API.get('/api/patients?size=50');
          patients.value = d.items;
          if (!patientId.value && d.items.length) patientId.value = d.items[0].id;
        } catch (e) { ui.toast(e.message, 'err'); }
      }
      async function loadContext() {
        if (!patientId.value) return;
        try { ctx.value = await API.get('/api/patients/' + patientId.value); } catch (e) {}
      }
      async function loadConversations(selectLatest = true) {
        if (!patientId.value) return;
        const rows = await API.get('/api/conversations?patient_id=' + patientId.value);
        conversations.value = rows;
        if (selectLatest) {
          if (rows.length) await openConversation(rows[0].id);
          else { convId.value = null; messages.value = []; }
        }
      }
      async function openConversation(id) {
        const d = await API.get('/api/conversations/' + id + '/messages');
        convId.value = id;
        messages.value = d.messages;
        await scrollBottom();
      }
      function newConversation() {
        convId.value = null;
        messages.value = [];
        streamText.value = '';
      }
      async function switchPatient() {
        newConversation();
        await Promise.all([loadContext(), loadConversations(true)]);
      }

      async function scrollBottom() {
        await nextTick();
        const el = scrollBox.value;
        if (el) el.scrollTop = el.scrollHeight;
      }

      async function send(text) {
        const q = (text || input.value || '').trim();
        if (!q || sending.value || !patientId.value) return;
        input.value = '';
        sending.value = true;
        streamText.value = '';
        messages.value.push({ role: 'user', content: q, citations: [], meta: {} });
        await scrollBottom();
        const metaHolder = { provider: '', model: '', evidence: 0 };
        try {
          await API.streamChat({ patient_id: patientId.value, conversation_id: convId.value, message: q }, {
            conversation: (d) => { convId.value = d.conversation_id; },
            meta: (d) => {
              metaHolder.provider = d.provider;
              metaHolder.model = d.model;
              metaHolder.evidence = d.evidence_count;
              ctx.value = ctx.value || {};
              if (d.patient) {
                ctx.value.maturity = d.patient.maturity;
                ctx.value.risk = d.patient.risk;
                ctx.value.narrative = d.patient.narrative;
              }
              if (d.memories) {
                ctx.value.memories = d.memories.map((m) => ({ ...m, kind_cn: m.kind_cn || m.kind }));
              }
            },
            delta: (d) => { streamText.value += d.text; scrollBottom(); },
            done: async (d) => {
              messages.value.push({
                role: 'assistant', content: streamText.value, citations: d.citations || [],
                meta: { provider: d.provider, model: d.model, latency_ms: d.latency_ms,
                        flags: d.flags || [], evidence: d.citations ? d.citations.length : 0 },
              });
              streamText.value = '';
              await scrollBottom();
              if (d.new_memories) ui.toast(`已更新 ${d.new_memories} 条长期记忆`);
              await Promise.all([loadConversations(false), loadContext()]);
            },
            error: (msg) => {
              ui.toast(msg, 'err');
              messages.value.push({ role: 'assistant', content: '抱歉，服务暂时不可用：' + msg, citations: [], meta: {} });
              streamText.value = '';
            },
          });
        } catch (e) {
          ui.toast(e.message, 'err');
        } finally {
          sending.value = false;
          streamText.value = '';
          await scrollBottom();
        }
      }

      function onKey(e) {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
      }
      function openCite(idx) {
        cite.value = evidence.value[idx - 1];
        showCite.value = !!cite.value;
      }
      function onMessageClick(e) {
        const t = e.target.closest('[data-cite]');
        if (t) openCite(Number(t.dataset.cite));
      }
      async function removeConv(c, e) {
        e.stopPropagation();
        if (!window.confirm('删除这个会话？')) return;
        await API.del('/api/conversations/' + c.id);
        ui.toast('会话已删除');
        await loadConversations(true);
      }

      const quick = computed(() => {
        const list = ['最近我的血压控制得怎么样？', '平时饮食要注意什么？', '用药有什么需要留意的？', '下次什么时候复诊？'];
        return list;
      });

      onMounted(async () => {
        loading.value = true;
        await loadPatients();
        if (patientId.value) {
          await Promise.all([loadContext(), loadConversations(true)]);
        }
        loading.value = false;
        await scrollBottom();
      });

      return { isPatient, patients, patientId, conversations, convId, messages, ctx, input, sending,
               streamText, evidence, activePatient, lastAssistant, showCite, cite, loading, scrollBox,
               renderMarkdown, send, onKey, onMessageClick, openConversation, newConversation,
               switchPatient, removeConv, quick };
    },
    template: `
      <div class="chat-shell" v-if="!loading">
        <div class="chat-col">
          <div class="chat-col-head">
            <select class="select" v-if="!isPatient" v-model.number="patientId" @change="switchPatient" style="height:34px;padding:5px 8px;font-size:12.5px">
              <option v-for="p in patients" :key="p.id" :value="p.id">{{ p.name }} · {{ p.risk_label }}</option>
            </select>
            <div v-else class="grow bold small">{{ activePatient ? activePatient.name : '我的健康' }}</div>
            <button class="icon-btn" title="新建会话" @click="newConversation" style="flex:0 0 34px"><mb-icon name="plus" :size="16"/></button>
          </div>
          <div class="conv-list">
            <div v-for="c in conversations" :key="c.id" class="conv-item" :class="{active: c.id===convId}" @click="openConversation(c.id)">
              <div class="between">
                <div class="conv-title grow">{{ c.title }}</div>
                <button class="msg-tool" @click="removeConv(c, $event)"><mb-icon name="trash" :size="11"/></button>
              </div>
              <div class="conv-sub">{{ c.last_message || '暂无消息' }}</div>
            </div>
            <div v-if="!conversations.length" class="empty" style="padding:24px 8px;font-size:12px">还没有会话记录</div>
          </div>
        </div>

        <div class="chat-col chat-main">
          <div class="chat-head">
            <div class="avatar" :style="{background: activePatient ? activePatient.avatar_color : 'var(--primary)', width:'30px', height:'30px', flex:'0 0 30px'}">
              {{ activePatient ? activePatient.name.slice(-2) : '我' }}
            </div>
            <div class="grow" style="min-width:0">
              <div class="who">{{ activePatient ? activePatient.name : '我的智能助手' }}<small>家庭智能助手 · 已接入个人档案</small></div>
              <div class="tiny faint" v-if="activePatient">{{ activePatient.conditions.join('、') }} · {{ activePatient.risk_label }}</div>
            </div>
            <span class="tag ok" v-if="!sending">在线</span>
            <span class="tag soft" v-else>生成中</span>
          </div>

          <div class="messages" ref="scrollBox" @click="onMessageClick">
            <div v-if="!messages.length && !streamText" class="empty" style="padding-top:60px">
              <div style="font-size:15px;font-weight:700;color:var(--text);margin-bottom:6px">你好，我是您的家庭智能助手</div>
              <div style="max-width:420px;margin:0 auto;line-height:1.8">
                我了解您的诊断、用药与最近指标，回答会引用本地知识库的指南原文。数据越完整，建议越贴合您。
              </div>
              <div class="quick-qs" style="justify-content:center;margin-top:18px">
                <button class="quick-q" v-for="q in quick" :key="q" @click="send(q)">{{ q }}</button>
              </div>
            </div>

            <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
              <div class="msg-avatar">{{ m.role === 'user' ? '我' : 'AI' }}</div>
              <div class="msg-body">
                <div class="msg-bubble" v-html="renderMarkdown(m.content)"></div>
                <div class="msg-meta" v-if="m.role === 'assistant' && m.meta && m.meta.model">
                  <span>{{ m.meta.model }}</span>
                  <span v-if="m.meta.latency_ms">· {{ (m.meta.latency_ms/1000).toFixed(1) }}s</span>
                  <span v-if="m.meta.evidence">· {{ m.meta.evidence }} 条证据</span>
                  <span v-if="m.meta.flags && m.meta.flags.includes('llm_fallback')" class="tag amber">已降级内置引擎</span>
                  <span v-if="m.meta.flags && m.meta.flags.includes('emergency')" class="tag red">安全门禁</span>
                </div>
              </div>
            </div>

            <div v-if="streamText" class="msg assistant">
              <div class="msg-avatar">AI</div>
              <div class="msg-body">
                <div class="msg-bubble" v-html="renderMarkdown(streamText)"></div>
              </div>
            </div>
            <div v-else-if="sending" class="msg assistant">
              <div class="msg-avatar">AI</div>
              <div class="msg-body"><div class="msg-bubble"><span class="typing"><i></i><i></i><i></i></span></div></div>
            </div>
          </div>

          <div class="chat-input">
            <div class="quick-qs" v-if="messages.length">
              <button class="quick-q" v-for="q in quick.slice(0,3)" :key="q" @click="send(q)">{{ q }}</button>
            </div>
            <textarea v-model="input" rows="1" placeholder="描述您的症状或想了解的问题，回车发送，Shift+回车换行"
                      @keydown="onKey"></textarea>
            <div class="chat-actions">
              <span class="tiny faint">回答基于您的档案与本地知识库，不替代面诊</span>
              <button class="btn" style="margin-left:auto" :disabled="sending || !input.trim()" @click="send()">
                <mb-icon name="send" :size="14"/> {{ sending ? '生成中' : '发送' }}
              </button>
            </div>
          </div>
        </div>

        <div class="chat-col side">
          <div class="chat-col-head">
            <span style="font-size:12.5px;font-weight:700">本次回答依据</span>
            <div class="right" style="margin-left:auto"><span class="tag primary">{{ evidence.length }} 条</span></div>
          </div>
          <div class="side-panel" v-if="ctx">
            <div class="side-block">
              <div class="side-cap">患者画像</div>
              <div class="row" style="gap:10px;align-items:flex-start">
                <mb-ring :value="ctx.maturity.score" :size="52" :thickness="6"/>
                <div>
                  <div class="small bold">个性化成熟度 {{ ctx.maturity.score }}</div>
                  <div class="tiny faint">{{ ctx.maturity.stage }} · 数据越全，建议越准</div>
                </div>
              </div>
              <div class="ctx-item" style="margin-top:8px"><span class="ctx-k">风险分层</span><span class="ctx-v">{{ ctx.risk.label }}（{{ ctx.risk.score }}）</span></div>
              <div class="ctx-item" v-if="ctx.features.bp_avg7"><span class="ctx-k">近 7 天血压</span><span class="ctx-v">{{ ctx.features.bp_avg7.sbp.toFixed(0) }}/{{ ctx.features.bp_avg7.dbp.toFixed(0) }}</span></div>
              <div class="ctx-item" v-if="ctx.features.glucose_avg7"><span class="ctx-k">近 7 天血糖</span><span class="ctx-v">{{ ctx.features.glucose_avg7.toFixed(1) }} mmol/L</span></div>
              <div class="ctx-item"><span class="ctx-k">用药依从性</span><span class="ctx-v">{{ ctx.features.med_adherence }}%</span></div>
              <div class="ctx-item"><span class="ctx-k">记录覆盖</span><span class="ctx-v">{{ ctx.features.record_density }}%</span></div>
            </div>

            <div class="side-block">
              <div class="side-cap">证据引用</div>
              <div v-for="(c, i) in evidence" :key="c.chunk_id" class="evidence-item" @click="cite = c; showCite = true">
                <div class="evidence-head">
                  <span style="color:var(--primary-dark)">[{{ i+1 }}]</span>
                  <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ c.title }}</span>
                  <span class="evidence-score">{{ c.score.toFixed(2) }}</span>
                </div>
                <div class="evidence-snippet">{{ c.heading }} · {{ c.content }}</div>
              </div>
              <div v-if="!evidence.length" class="small faint" style="line-height:1.7">
                尚未产生引用。提出问题后，这里会列出命中的指南片段与相关度。
              </div>
            </div>

            <div class="side-block" v-if="ctx.memories && ctx.memories.length">
              <div class="side-cap">长期记忆</div>
              <div class="memory-chip" v-for="m in ctx.memories.slice(0,5)" :key="m.id">
                <span class="memory-kind">{{ m.kind_cn }}</span>
                <span class="memory-text">{{ m.content }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="mask" v-if="showCite && cite" @click.self="showCite=false">
          <div class="modal">
            <div class="modal-head">
              <h3>知识库原文</h3>
              <button class="icon-btn" style="margin-left:auto" @click="showCite=false"><mb-icon name="close" :size="15"/></button>
            </div>
            <div class="modal-body">
              <div class="row" style="gap:8px;flex-wrap:wrap;margin-bottom:10px">
                <span class="tag primary">{{ cite.title }}</span>
                <span class="tag soft">{{ cite.heading }}</span>
                <span class="tag soft">相关度 {{ cite.score }}</span>
              </div>
              <div class="chunk-body" style="font-size:13px">{{ cite.content }}</div>
            </div>
            <div class="modal-foot">
              <button class="btn ghost" @click="showCite=false">关闭</button>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty">正在准备助手…</div>`,
  };
})();
