/* 专家会诊 · 数字人专家与多学科专家团 */
(function () {
  const { ref, computed, onMounted, nextTick } = Vue;
  const Pages = (window.Pages = window.Pages || {});

  function escapeHtml(s) {
    return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderMarkdown(text) {
    let html = escapeHtml(text || '');
    html = html.replace(/^#{1,4}\s*/gm, '');
    html = html.replace(/\[(\d{1,2})\]/g, (m, n) => `<span class="cite-link">${n}</span>`);
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

  const TEAM_QUESTIONS = [
    '几位专家一起帮我看看最近的指标',
    '饮食和用药怎么配合？',
    '我现在最该先改哪一件事？',
  ];

  Pages.expert = {
    components: { MbIcon: Mb.Icon, MbRing: Mb.Ring },
    setup() {
      const roster = ref(null);
      const loading = ref(true);
      const view = ref('hall');
      const detail = ref(null);
      const messages = ref([]);
      const live = ref([]);
      const sending = ref(false);
      const input = ref('');
      const activeSpeaker = ref(null);
      const summon = ref(null);
      const summoning = ref(false);
      const topic = ref('');
      const sessions = ref([]);
      const counts = ref({});
      const scrollBox = ref(null);

      const patient = computed(() => (roster.value ? roster.value.patient : null));
      const experts = computed(() => (roster.value ? roster.value.experts : []));
      const teams = computed(() => (roster.value ? roster.value.teams : []));
      const target = computed(() => (detail.value ? detail.value.session.target : null));
      const speakers = computed(() => (detail.value ? detail.value.speakers : []));
      const quick = computed(() => {
        if (!target.value) return TEAM_QUESTIONS;
        return target.value.type === 'team' ? TEAM_QUESTIONS : (target.value.questions || TEAM_QUESTIONS);
      });

      function orbStyle(o) {
        if (!o) return { background: 'var(--primary)' };
        return { background: `linear-gradient(135deg, ${o.color || '#334155'}, ${o.color2 || '#64748b'})` };
      }
      function speakerOf(m) {
        return speakers.value.find((s) => s.id === m.speaker_id) || {
          id: m.speaker_id, name: m.speaker_name || '专家', initials: (m.speaker_name || '专').slice(-1),
          title: m.speaker_title || '', color: '#334155', color2: '#64748b',
        };
      }

      async function load(showLoading) {
        if (showLoading) loading.value = true;
        try {
          const d = await API.get('/api/expert/roster');
          roster.value = d;
          sessions.value = d.sessions;
          counts.value = d.counts;
        } catch (e) {
          ui.toast(e.message, 'err');
        } finally {
          loading.value = false;
        }
      }

      async function scrollBottom() {
        await nextTick();
        const el = scrollBox.value;
        if (el) el.scrollTop = el.scrollHeight;
      }

      async function openSession(id) {
        try {
          const d = await API.get('/api/expert/sessions/' + id);
          detail.value = d;
          messages.value = d.messages;
          live.value = [];
          view.value = 'consult';
          await scrollBottom();
        } catch (e) {
          ui.toast(e.message, 'err');
        }
      }
      function back() {
        view.value = 'hall';
        detail.value = null;
        messages.value = [];
        live.value = [];
        activeSpeaker.value = null;
      }
      function startSummon(t) {
        summon.value = t;
        topic.value = '';
      }
      async function confirmSummon() {
        if (!summon.value || summoning.value) return;
        summoning.value = true;
        try {
          const d = await API.post('/api/expert/sessions', {
            target_type: summon.value.type,
            target_id: summon.value.id,
            topic: topic.value.trim(),
          });
          summon.value = null;
          detail.value = d;
          messages.value = d.messages;
          live.value = [];
          view.value = 'consult';
          await load(false);
          await scrollBottom();
          ui.toast(d.session.target_name + ' 已接入会诊');
        } catch (e) {
          ui.toast(e.message, 'err');
        } finally {
          summoning.value = false;
        }
      }
      async function removeSession(s, e) {
        if (e) e.stopPropagation();
        if (!window.confirm('删除这条会诊记录？')) return;
        try {
          await API.del('/api/expert/sessions/' + s.id);
          if (detail.value && detail.value.session.id === s.id) back();
          await load(false);
          ui.toast('会诊记录已删除');
        } catch (err) { ui.toast(err.message, 'err'); }
      }

      async function send(text) {
        const q = (text || input.value || '').trim();
        if (!q || sending.value || !detail.value) return;
        input.value = '';
        sending.value = true;
        live.value = [];
        messages.value.push({ role: 'user', content: q, meta: {} });
        await scrollBottom();
        try {
          await API.stream('/api/expert/sessions/' + detail.value.session.id + '/stream', { message: q }, {
            speaker: (sp) => {
              activeSpeaker.value = sp;
              live.value.push({ speaker: sp, text: '' });
              scrollBottom();
            },
            delta: (d) => {
              if (!live.value.length) live.value.push({ speaker: activeSpeaker.value, text: '' });
              live.value[live.value.length - 1].text += d.text;
              scrollBottom();
            },
            error: (msg) => { ui.toast(msg, 'err'); },
          });
          const d = await API.get('/api/expert/sessions/' + detail.value.session.id);
          detail.value = d;
          messages.value = d.messages;
          live.value = [];
          activeSpeaker.value = null;
          await load(false);
          await scrollBottom();
        } catch (e) {
          ui.toast(e.message, 'err');
        } finally {
          sending.value = false;
          live.value = [];
        }
      }
      function onKey(e) {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
      }
      function pickTopic(q) { topic.value = q; }
      function questionsOf(t) {
        return t && t.type === 'team' ? TEAM_QUESTIONS : ((t && t.questions) || TEAM_QUESTIONS);
      }

      onMounted(() => load(true));

      return {
        roster, loading, view, detail, messages, live, sending, input, activeSpeaker,
        summon, summoning, topic, sessions, counts, scrollBox, patient, experts, teams,
        target, speakers, quick, orbStyle, speakerOf, load, openSession, back, startSummon,
        confirmSummon, removeSession, send, onKey, pickTopic, questionsOf, renderMarkdown,
      };
    },
    template: `
      <div v-if="loading" class="empty">正在接入专家会诊…</div>
      <div v-else-if="roster">
        <!-- 专家大厅 -->
        <div v-if="view==='hall'">
          <div class="expert-hero">
            <div class="expert-hero-copy">
              <div class="expert-kicker"><span class="live-dot"></span> 多学科数字人会诊 · 已接入您的全景档案</div>
              <h2>把专科医生请到身边</h2>
              <p>{{ experts.length }} 位数字人专家与 {{ teams.length }} 个专家团随时待命。会诊会读取您的诊断、用药、指标与饮食记录，给出各专科的独立意见，再由全科医生汇总成可执行的计划。</p>
              <div class="expert-hero-tags">
                <span>{{ patient.name }} · {{ patient.age }}岁{{ patient.gender }}</span>
                <span>{{ patient.conditions.join('、') }}</span>
                <span>风险 {{ patient.risk.label }}</span>
              </div>
            </div>
            <div class="expert-hero-stats">
              <div class="eh-stat"><b>{{ experts.length }}</b><span>数字人专家</span></div>
              <div class="eh-stat"><b>{{ teams.length }}</b><span>多学科专家团</span></div>
              <div class="eh-stat"><b>{{ sessions.length }}</b><span>我的会诊</span></div>
            </div>
            <div class="expert-hero-orb orb-a"></div>
            <div class="expert-hero-orb orb-b"></div>
          </div>

          <div class="section-head mt20">
            <div>
              <div class="section-title">专家数字人</div>
              <div class="section-sub">按专科选择，随时召唤，单独为您会诊</div>
            </div>
            <span class="tag primary">{{ experts.length }} 位在线</span>
          </div>
          <div class="expert-grid">
            <div class="expert-card" v-for="e in experts" :key="e.id">
              <div class="expert-top">
                <div class="expert-orb" :style="orbStyle(e)">
                  <span>{{ e.initials }}</span>
                  <i class="orb-pulse"></i>
                </div>
                <div class="grow" style="min-width:0">
                  <div class="expert-name">{{ e.name }}<span class="live-dot" style="margin-left:6px"></span></div>
                  <div class="expert-title">{{ e.title }}</div>
                  <div class="expert-org">{{ e.org }}</div>
                </div>
                <span class="tag ok">在线</span>
              </div>
              <div class="expert-tags">
                <span class="tag soft" v-for="t in e.tags" :key="t">{{ t }}</span>
              </div>
              <p class="expert-intro">{{ e.intro }}</p>
              <div class="expert-style"><mb-icon name="sparkles" :size="12"/> {{ e.style }}</div>
              <div class="ea-chips" style="margin-top:8px" v-if="e.skills && e.skills.length">
                <span class="chip skill" v-for="s in e.skills.slice(0,3)" :key="s.key">{{ s.name }}</span>
                <span class="chip tool" v-if="e.tools && e.tools.length" :title="e.tools.map((x) => x.name).join('、')">
                  <mb-icon name="cpu" :size="10"/> {{ e.tools.length }} 个工具
                </span>
              </div>
              <div class="expert-foot">
                <span class="tiny faint">{{ e.years }} 年经验 · 会诊 {{ counts[e.id] || 0 }} 次</span>
                <button class="btn sm" @click="startSummon(e)"><mb-icon name="stethoscope" :size="13"/> 召唤会诊</button>
              </div>
            </div>
          </div>

          <div class="section-head mt20">
            <div>
              <div class="section-title">专家团</div>
              <div class="section-sub">多位专家围绕同一份档案依次发言，覆盖不同专业视角</div>
            </div>
            <span class="tag primary">{{ teams.length }} 个团队</span>
          </div>
          <div class="team-grid">
            <div class="team-card" v-for="t in teams" :key="t.id">
              <div class="team-top">
                <div class="team-orbs">
                  <span v-for="m in t.members" :key="m.id" :style="orbStyle(m)">{{ m.initials }}</span>
                </div>
                <div class="grow" style="min-width:0">
                  <div class="expert-name">{{ t.name }}</div>
                  <div class="tiny faint">{{ t.members.length }} 位专家 · 依次会诊</div>
                </div>
              </div>
              <p class="expert-intro">{{ t.desc }}</p>
              <div class="expert-tags">
                <span class="tag soft" v-for="x in t.tags" :key="x">{{ x }}</span>
              </div>
              <div class="team-flow">
                <span v-for="(m, i) in t.members" :key="m.id">
                  <b>{{ m.name }}</b><small>{{ m.dept }}</small>
                </span>
              </div>
              <div class="team-foot">
                <span class="tiny faint">{{ t.scenario }}</span>
                <button class="btn sm" @click="startSummon(t)"><mb-icon name="team" :size="13"/> 发起会诊</button>
              </div>
            </div>
          </div>

          <div class="card mt20" v-if="sessions.length">
            <div class="card-head"><h3>我的会诊记录</h3><span class="sub">共 {{ sessions.length }} 次 · 点击继续</span></div>
            <div class="card-body" style="padding-top:6px">
              <div class="consult-row" v-for="s in sessions" :key="s.id" @click="openSession(s.id)">
                <div class="consult-ico"><mb-icon :name="s.target_type === 'team' ? 'team' : 'stethoscope'" :size="15"/></div>
                <div class="grow" style="min-width:0">
                  <div class="small bold">{{ s.title }}</div>
                  <div class="tiny faint">{{ s.target_name }} · {{ s.updated_at.slice(5, 16) }} · {{ s.message_count }} 条消息</div>
                </div>
                <button class="msg-tool" @click="removeSession(s, $event)"><mb-icon name="trash" :size="12"/></button>
                <mb-icon name="arrow" :size="14"/>
              </div>
            </div>
          </div>
          <div class="card mt20" v-else>
            <div class="empty" style="padding:26px 16px">
              还没有会诊记录。选一位专家或一个专家团，先说说您最近最困扰的问题。
            </div>
          </div>
        </div>

        <!-- 会诊室 -->
        <div v-else class="consult-shell">
          <aside class="consult-side">
            <button class="btn sm ghost" style="width:100%" @click="back">← 返回专家大厅</button>
            <div class="consult-target" v-if="target">
              <div v-if="target.type === 'team'" class="team-orbs big">
                <span v-for="m in target.members" :key="m.id" :style="orbStyle(m)">{{ m.initials }}</span>
              </div>
              <div v-else class="expert-orb" :style="orbStyle(target)"><span>{{ target.initials }}</span></div>
              <div class="bold small" style="margin-top:8px">{{ target.name }}</div>
              <div class="tiny faint">{{ target.type === 'team' ? target.members.length + ' 位专家协同会诊' : target.title }}</div>
              <div class="expert-tags" style="margin-top:8px">
                <span class="tag soft" v-for="t in target.tags" :key="t">{{ t }}</span>
              </div>
            </div>

            <div class="side-cap mt14">患者档案摘要</div>
            <div class="consult-snapshot" v-if="patient">
              <div class="ctx-item"><span class="ctx-k">风险分层</span><span class="ctx-v">{{ patient.risk.label }}</span></div>
              <div class="ctx-item"><span class="ctx-k">在管诊断</span><span class="ctx-v" style="max-width:150px">{{ patient.conditions.join('、') }}</span></div>
              <div class="ctx-item" v-if="patient.bp"><span class="ctx-k">最近血压</span><span class="ctx-v num">{{ patient.bp.sbp.toFixed(0) }}/{{ patient.bp.dbp.toFixed(0) }}</span></div>
              <div class="ctx-item" v-if="patient.glucose"><span class="ctx-k">最近血糖</span><span class="ctx-v num">{{ patient.glucose.value.toFixed(1) }} mmol/L</span></div>
              <div class="ctx-item"><span class="ctx-k">在用药物</span><span class="ctx-v">{{ patient.med_count }} 种</span></div>
              <div class="ctx-item"><span class="ctx-k">年龄</span><span class="ctx-v">{{ patient.age }} 岁</span></div>
            </div>

            <div class="side-cap mt14">历史会诊</div>
            <div class="consult-history">
              <div v-for="s in sessions.slice(0, 6)" :key="s.id" class="conv-item"
                   :class="{active: detail && s.id === detail.session.id}" @click="openSession(s.id)">
                <div class="conv-title">{{ s.title }}</div>
                <div class="conv-sub">{{ s.target_name }} · {{ s.updated_at.slice(5, 16) }}</div>
              </div>
              <div v-if="!sessions.length" class="tiny faint">暂无历史记录</div>
            </div>
          </aside>

          <section class="consult-main">
            <div class="chat-head">
              <div v-if="target" class="speaker-stack">
                <span v-for="m in (target.type === 'team' ? target.members : [target])" :key="m.id"
                      :style="orbStyle(m)">{{ m.initials }}</span>
              </div>
              <div class="grow" style="min-width:0">
                <div class="who">{{ target.name }}<small>{{ target.type === 'team' ? '多学科协同会诊' : target.title }}</small></div>
                <div class="tiny faint">{{ patient.name }} · {{ patient.conditions.join('、') }} · 已读取全景档案</div>
              </div>
              <span class="tag ok" v-if="!sending">在线</span>
              <span class="tag soft" v-else>会诊中…</span>
            </div>

            <div class="messages" ref="scrollBox">
              <div class="consult-welcome" v-if="messages.length <= 1 && !live.length">
                <mb-icon name="stethoscope" :size="20"/>
                <div>会诊已开始。您可以直接描述症状、指标变化或生活中的困难，{{ target.type === 'team' ? '各位专家会依次作答' : target.name + ' 会结合档案给出判断' }}。</div>
              </div>

              <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role === 'user' ? 'user' : 'assistant'">
                <div class="msg-avatar" :style="m.role === 'user' ? {} : orbStyle(speakerOf(m))">
                  {{ m.role === 'user' ? '我' : speakerOf(m).initials }}
                </div>
                <div class="msg-body">
                  <div class="speaker-line" v-if="m.role === 'expert'">
                    <b>{{ m.speaker_name }}</b><span>{{ m.speaker_title }}</span>
                  </div>
                  <div class="msg-bubble" v-html="renderMarkdown(m.content)"></div>
                  <div class="msg-meta" v-if="m.role === 'expert' && m.meta && m.meta.model">
                    <span>{{ m.meta.model }}</span>
                    <span v-if="m.meta.latency_ms">· {{ (m.meta.latency_ms / 1000).toFixed(1) }}s</span>
                    <span v-if="m.meta.citations && m.meta.citations.length">· {{ m.meta.citations.length }} 条指南依据</span>
                    <span v-if="m.meta.skills && m.meta.skills.length" :title="m.meta.skills.join('、')">· {{ m.meta.skills.length }} 项技能</span>
                    <span v-if="m.meta.tools && m.meta.tools.length" :title="m.meta.tools.join('、')">· {{ m.meta.tools.length }} 个工具</span>
                    <span v-if="m.meta.flags && m.meta.flags.includes('llm_fallback')" class="tag amber">已降级规则引擎</span>
                    <span v-if="m.meta.flags && m.meta.flags.includes('emergency')" class="tag red">安全门禁</span>
                  </div>
                </div>
              </div>

              <div v-for="(l, i) in live" :key="'live' + i" class="msg assistant">
                <div class="msg-avatar" :style="orbStyle(l.speaker)">{{ l.speaker.initials }}</div>
                <div class="msg-body">
                  <div class="speaker-line"><b>{{ l.speaker.name }}</b><span>{{ l.speaker.title }}</span></div>
                  <div class="msg-bubble" v-html="renderMarkdown(l.text)"></div>
                </div>
              </div>

              <div v-if="sending && !live.length" class="msg assistant">
                <div class="msg-avatar" style="background:var(--primary)">专</div>
                <div class="msg-body"><div class="msg-bubble"><span class="typing"><i></i><i></i><i></i></span></div></div>
              </div>
            </div>

            <div class="chat-input">
              <div class="quick-qs" v-if="messages.length > 1">
                <button class="quick-q" v-for="q in quick.slice(0, 3)" :key="q" @click="send(q)">{{ q }}</button>
              </div>
              <textarea v-model="input" rows="1" placeholder="描述您的症状、指标变化或最想解决的问题，回车发送"
                        @keydown="onKey"></textarea>
              <div class="chat-actions">
                <span class="tiny faint">会诊意见基于您的档案与本地指南，不替代线下面诊</span>
                <button class="btn" style="margin-left:auto" :disabled="sending || !input.trim()" @click="send()">
                  <mb-icon name="send" :size="14"/> {{ sending ? '会诊中' : '发送' }}
                </button>
              </div>
            </div>
          </section>
        </div>

        <!-- 召唤弹窗 -->
        <div class="mask" v-if="summon" @click.self="summon = null">
          <div class="modal" style="max-width:520px">
            <div class="modal-head">
              <h3>召唤{{ summon.type === 'team' ? '专家团' : '专家数字人' }}</h3>
              <button class="icon-btn" style="margin-left:auto" @click="summon = null"><mb-icon name="close" :size="15"/></button>
            </div>
            <div class="modal-body">
              <div class="summon-target">
                <div class="expert-orb" :style="orbStyle(summon)"><span>{{ summon.initials || '团' }}</span></div>
                <div style="min-width:0">
                  <div class="bold">{{ summon.name }}</div>
                  <div class="tiny faint">{{ summon.type === 'team' ? summon.members.map((m) => m.name).join(' · ') : summon.title }}</div>
                  <div class="tiny faint">{{ summon.type === 'team' ? summon.desc : summon.intro }}</div>
                </div>
              </div>
              <div class="field">
                <label>想咨询什么<span class="opt">（选填，也可进入会诊后再说）</span></label>
                <input class="input" v-model="topic" maxlength="40" placeholder="如：最近血压总是早上偏高">
              </div>
              <div class="quick-qs" style="margin-top:12px">
                <button class="quick-q" v-for="q in questionsOf(summon)" :key="q" @click="pickTopic(q)">{{ q }}</button>
              </div>
              <div class="tip-card warn" style="margin-top:14px">
                <mb-icon name="shield" :size="16"/>
                <div>会诊会读取您的诊断、用药与近期指标。若正在出现胸痛、呼吸困难、意识改变等急症，请立即拨打 120，不要等待线上回复。</div>
              </div>
            </div>
            <div class="modal-foot">
              <button class="btn ghost" @click="summon = null">取消</button>
              <button class="btn" :disabled="summoning" @click="confirmSummon">{{ summoning ? '接入中…' : '开始会诊' }}</button>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty">暂无法加载专家会诊</div>`,
  };
})();
