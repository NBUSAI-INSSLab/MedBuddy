/* 本地知识库管理 */
(function () {
  const { ref, computed, onMounted } = Vue;
  const Pages = (window.Pages = window.Pages || {});

  Pages.kb = {
    components: { MbIcon: Mb.Icon },
    setup() {
      const docs = ref([]);
      const stats = ref({ documents: 0, chunks: 0, categories: [] });
      const idxStats = ref({});
      const q = ref('');
      const cat = ref('');
      const loading = ref(true);
      const showUpload = ref(false);
      const showDoc = ref(null);
      const docDetail = ref(null);
      const searchQ = ref('高血压患者家庭血压怎么测');
      const searchPid = ref('');
      const patients = ref([]);
      const results = ref([]);
      const searching = ref(false);
      const uploading = ref(false);
      const fileInput = ref(null);
      const form = ref({ title: '', category: '高血压', doc_type: 'guideline', source: '本地上传', version: '2025', content: '' });

      async function load() {
        loading.value = true;
        try {
          const params = new URLSearchParams();
          if (q.value) params.set('q', q.value);
          if (cat.value) params.set('category', cat.value);
          const d = await API.get('/api/kb/documents?' + params.toString());
          docs.value = d.items;
          stats.value = d.stats;
          idxStats.value = await API.get('/api/kb/stats');
        } catch (e) { ui.toast(e.message, 'err'); }
        finally { loading.value = false; }
      }
      async function loadPatients() {
        try { const d = await API.get('/api/patients?size=50'); patients.value = d.items; } catch (e) {}
      }
      onMounted(() => { load(); loadPatients(); });

      const categories = computed(() => {
        const s = new Set(stats.value.categories.map((c) => c.category));
        return Array.from(s);
      });
      const typeCn = { guideline: '指南', consensus: '共识', protocol: '规范', education: '宣教' };

      async function viewDoc(doc) {
        showDoc.value = doc;
        docDetail.value = null;
        try { docDetail.value = await API.get('/api/kb/documents/' + doc.id); } catch (e) { ui.toast(e.message, 'err'); }
      }
      async function delDoc(doc) {
        if (!window.confirm(`删除《${doc.title}》？该文档的 ${doc.chunk_count} 个片段将一并移除。`)) return;
        try { await API.del('/api/kb/documents/' + doc.id); ui.toast('文档已删除'); await load(); }
        catch (e) { ui.toast(e.message, 'err'); }
      }
      async function rebuild() {
        try { const d = await API.post('/api/kb/rebuild', {}); ui.toast(`索引已重建：${d.chunks} 个片段`); await load(); }
        catch (e) { ui.toast(e.message, 'err'); }
      }
      async function doSearch() {
        if (!searchQ.value.trim()) return;
        searching.value = true;
        try {
          const d = await API.post('/api/kb/search', {
            query: searchQ.value, patient_id: searchPid.value || undefined, top_k: 6,
          });
          results.value = d.results;
        } catch (e) { ui.toast(e.message, 'err'); }
        finally { searching.value = false; }
      }
      async function upload() {
        if (!form.value.title.trim() || form.value.content.trim().length < 30) {
          return ui.toast('请填写标题，正文至少 30 字', 'err');
        }
        uploading.value = true;
        try {
          const d = await API.post('/api/kb/documents', form.value);
          ui.toast(`已入库，切分为 ${d.chunks} 个片段`);
          showUpload.value = false;
          form.value.content = '';
          await load();
        } catch (e) { ui.toast(e.message, 'err'); }
        finally { uploading.value = false; }
      }
      async function onFile(ev) {
        const file = ev.target.files[0];
        if (!file) return;
        const fd = new FormData();
        fd.append('file', file);
        fd.append('category', form.value.category);
        fd.append('doc_type', form.value.doc_type);
        fd.append('source', form.value.source);
        fd.append('version', form.value.version);
        uploading.value = true;
        try {
          const d = await API.upload('/api/kb/documents', fd);
          ui.toast(`《${file.name}》已入库，${d.chunks} 个片段`);
          showUpload.value = false;
          await load();
        } catch (e) { ui.toast(e.message, 'err'); }
        finally { uploading.value = false; }
      }
      return { docs, stats, idxStats, q, cat, categories, loading, showUpload, showDoc, docDetail,
               searchQ, searchPid, patients, results, searching, uploading, form, fileInput, typeCn,
               load, viewDoc, delDoc, rebuild, doSearch, upload, onFile };
    },
    template: `
      <div>
        <div class="grid g4">
          <div class="card kb-stat">
            <div class="ico"><mb-icon name="book" :size="18"/></div>
            <div><b>{{ stats.documents }}</b><span>篇文档</span></div>
          </div>
          <div class="card kb-stat">
            <div class="ico"><mb-icon name="database" :size="18"/></div>
            <div><b>{{ stats.chunks }}</b><span>个检索片段</span></div>
          </div>
          <div class="card kb-stat">
            <div class="ico"><mb-icon name="cpu" :size="18"/></div>
            <div><b>{{ idxStats.indexed || 0 }}</b><span>已建索引</span></div>
          </div>
          <div class="card kb-stat">
            <div class="ico"><mb-icon name="search" :size="18"/></div>
            <div><b>{{ idxStats.queries || 0 }}</b><span>累计检索次数</span></div>
          </div>
        </div>

        <div class="grid g-2-1 mt14">
          <div class="card flush">
            <div class="card-head" style="padding-bottom:12px">
              <h3>知识库文档</h3>
              <div class="right">
                <div class="search-box">
                  <mb-icon name="search" :size="14"/>
                  <input class="input" style="min-width:170px;height:32px" v-model="q" @keyup.enter="load" placeholder="搜索文档">
                </div>
                <select class="select" v-model="cat" @change="load" style="height:32px;padding:4px 8px;font-size:12px">
                  <option value="">全部分类</option>
                  <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
                </select>
                <button class="btn sm ghost" @click="rebuild">重建索引</button>
                <button class="btn sm" @click="showUpload = true"><mb-icon name="upload" :size="13"/> 上传</button>
              </div>
            </div>
            <div>
              <div class="doc-item" v-for="d in docs" :key="d.id">
                <div class="doc-ico"><mb-icon name="doc" :size="16"/></div>
                <div class="grow" style="min-width:0">
                  <div class="doc-title">{{ d.title }}</div>
                  <div class="doc-meta">
                    <span class="tag soft">{{ d.category }}</span>
                    <span class="tag primary">{{ typeCn[d.doc_type] || d.doc_type }}</span>
                    <span>{{ d.source }}</span>
                    <span>{{ d.version }} 版</span>
                    <span>{{ d.chunk_count }} 片段</span>
                    <span>{{ (d.size/1000).toFixed(1) }}k 字</span>
                  </div>
                </div>
                <div class="row" style="gap:6px">
                  <button class="btn sm ghost" @click="viewDoc(d)">片段</button>
                  <button class="btn sm ghost" @click="delDoc(d)" style="color:#dc2626">删除</button>
                </div>
              </div>
              <div v-if="loading" class="empty">正在加载…</div>
              <div v-else-if="!docs.length" class="empty">没有匹配的文档</div>
            </div>
          </div>

          <div class="card">
            <div class="card-head">
              <h3>检索测试</h3>
              <span class="sub">混合检索：BM25 + 字符向量</span>
            </div>
            <div class="card-body">
              <textarea class="textarea" v-model="searchQ" style="min-height:64px" placeholder="输入临床问题，验证命中片段"></textarea>
              <div class="row mt14">
                <select class="select" v-model="searchPid" style="flex:1;font-size:12px">
                  <option value="">不限定患者（通用检索）</option>
                  <option v-for="p in patients" :key="p.id" :value="p.id">{{ p.name }} · 按病种加权</option>
                </select>
                <button class="btn" :disabled="searching" @click="doSearch">{{ searching ? '检索中' : '检索' }}</button>
              </div>
              <div class="tip-card" style="margin-top:12px;font-size:11.5px">
                <mb-icon name="shield" :size="15"/>
                <div>选择患者后，系统会按患者病种加权，并过滤其未患疾病的专科指南，避免跨病种建议。</div>
              </div>
              <div style="margin-top:14px">
                <div v-for="(r, i) in results" :key="r.chunk_id" class="search-result">
                  <div class="between">
                    <div class="small bold" style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                      [{{ i+1 }}] {{ r.title }}
                    </div>
                    <span class="row" style="gap:5px;flex:0 0 auto">
                      <span class="score-bar"><i :style="{width: (r.score*100) + '%'}"></i></span>
                      <span class="tiny num faint">{{ r.score.toFixed(2) }}</span>
                    </span>
                  </div>
                  <div class="tiny" style="color:var(--primary-dark);margin:3px 0">{{ r.heading }}</div>
                  <div class="small muted" style="display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden">{{ r.content }}</div>
                </div>
                <div v-if="!results.length && !searching" class="empty">输入问题后点击检索</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 上传 -->
        <div class="mask" v-if="showUpload" @click.self="showUpload=false">
          <div class="modal wide">
            <div class="modal-head">
              <h3>上传知识库文档</h3>
              <button class="icon-btn" style="margin-left:auto" @click="showUpload=false"><mb-icon name="close" :size="15"/></button>
            </div>
            <div class="modal-body">
              <div class="grid g2" style="gap:0 16px">
                <div class="field"><label>文档标题</label><input class="input" v-model="form.title" placeholder="如：社区高血压随访工作规范"></div>
                <div class="field"><label>分类</label>
                  <select class="select" v-model="form.category">
                    <option>高血压</option><option>糖尿病</option><option>血脂异常</option>
                    <option>慢性肾病</option><option>慢阻肺</option><option>冠心病</option>
                    <option>生活方式</option><option>监测规范</option><option>用药安全</option><option>综合管理</option>
                  </select>
                </div>
                <div class="field"><label>文档类型</label>
                  <select class="select" v-model="form.doc_type">
                    <option value="guideline">指南</option><option value="consensus">专家共识</option>
                    <option value="protocol">操作规范</option><option value="education">健康宣教</option>
                  </select>
                </div>
                <div class="field"><label>来源 / 版本</label>
                  <div class="row"><input class="input" v-model="form.source" placeholder="机构"><input class="input" v-model="form.version" style="width:90px"></div>
                </div>
              </div>
              <div class="field">
                <label>正文（支持 Markdown 标题，系统按标题切分）</label>
                <textarea class="textarea" v-model="form.content" style="min-height:180px"
                          placeholder="# 一级标题&#10;## 二级标题&#10;正文内容…"></textarea>
              </div>
              <div class="row" style="margin-top:12px">
                <input type="file" ref="fileInput" accept=".txt,.md,.markdown,.pdf" style="display:none" @change="onFile">
                <button class="btn ghost" @click="$refs.fileInput.click()"><mb-icon name="upload" :size="14"/> 选择 txt / md / pdf 文件</button>
                <span class="tiny faint">文件上传将直接解析并入库，正文框可留空</span>
              </div>
            </div>
            <div class="modal-foot">
              <button class="btn ghost" @click="showUpload=false">取消</button>
              <button class="btn" :disabled="uploading" @click="upload">{{ uploading ? '处理中…' : '切分并入库' }}</button>
            </div>
          </div>
        </div>

        <!-- 文档片段 -->
        <div class="mask" v-if="showDoc" @click.self="showDoc=null">
          <div class="modal wide">
            <div class="modal-head">
              <h3>{{ showDoc.title }}</h3>
              <button class="icon-btn" style="margin-left:auto" @click="showDoc=null"><mb-icon name="close" :size="15"/></button>
            </div>
            <div class="modal-body">
              <div class="row" style="gap:6px;flex-wrap:wrap;margin-bottom:12px">
                <span class="tag soft">{{ showDoc.category }}</span>
                <span class="tag primary">{{ typeCn[showDoc.doc_type] }}</span>
                <span class="tag soft">{{ showDoc.chunk_count }} 片段</span>
                <span class="tag soft">{{ showDoc.source }} · {{ showDoc.version }}</span>
              </div>
              <div class="chunk-view" v-if="docDetail">
                <div class="chunk-block" v-for="c in docDetail.chunks" :key="c.id">
                  <div class="chunk-head">片段 {{ c.idx + 1 }} · {{ c.heading }} · {{ c.tokens }} 词</div>
                  <div class="chunk-body">{{ c.content }}</div>
                </div>
              </div>
              <div v-else class="empty">加载中…</div>
            </div>
          </div>
        </div>
      </div>`,
  };
})();
