/* 轻量 SVG 图表组件（无外部依赖） */
(function () {
  const { computed, ref } = Vue;
  const C = {};

  function smoothPath(pts) {
    if (!pts.length) return '';
    if (pts.length === 1) return `M${pts[0][0]},${pts[0][1]}`;
    let d = `M${pts[0][0]},${pts[0][1]}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] || pts[i];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = pts[i + 2] || p2;
      const t = 0.18;
      const c1x = p1[0] + (p2[0] - p0[0]) * t;
      const c1y = p1[1] + (p2[1] - p0[1]) * t;
      const c2x = p2[0] - (p3[0] - p1[0]) * t;
      const c2y = p2[1] - (p3[1] - p1[1]) * t;
      d += ` C${c1x},${c1y} ${c2x},${c2y} ${p2[0]},${p2[1]}`;
    }
    return d;
  }

  C.LineChart = {
    props: {
      points: { type: Array, default: () => [] },
      points2: { type: Array, default: () => [] },
      name: { type: String, default: '数值' },
      name2: { type: String, default: '' },
      color: { type: String, default: 'var(--primary)' },
      color2: { type: String, default: '#94a3b8' },
      unit: { type: String, default: '' },
      target: { type: Number, default: null },
      targetLabel: { type: String, default: '' },
      height: { type: Number, default: 230 },
      decimals: { type: Number, default: 0 },
    },
    setup(props) {
      const hi = ref(-1);
      const W = 760, pad = { l: 46, r: 14, t: 16, b: 26 };
      const H = computed(() => props.height);
      const iw = computed(() => W - pad.l - pad.r);
      const ih = computed(() => H.value - pad.t - pad.b);

      const values = computed(() => {
        const v = props.points.map((p) => Number(p.value)).filter((x) => !isNaN(x));
        props.points2.forEach((p) => { if (!isNaN(Number(p.value))) v.push(Number(p.value)); });
        if (props.target != null) v.push(props.target);
        return v;
      });
      const bounds = computed(() => {
        const v = values.value;
        if (!v.length) return { min: 0, max: 1 };
        let min = Math.min(...v), max = Math.max(...v);
        if (max === min) { max = min + (min === 0 ? 1 : Math.abs(min) * 0.12); min = min - Math.abs(min) * 0.12; }
        const p = (max - min) * 0.16;
        return { min: Math.max(0, min - p), max: max + p };
      });
      const x = (i, n) => (n <= 1 ? pad.l + iw.value / 2 : pad.l + (iw.value * i) / (n - 1));
      const y = (v) => pad.t + ih.value * (1 - (v - bounds.value.min) / (bounds.value.max - bounds.value.min));

      const coords = computed(() => props.points.map((p, i) =>
        [x(i, props.points.length), y(Number(p.value))]));
      const coords2 = computed(() => props.points2.map((p, i) =>
        [x(i, props.points2.length), y(Number(p.value))]));
      const line1 = computed(() => smoothPath(coords.value));
      const line2 = computed(() => smoothPath(coords2.value));
      const area1 = computed(() => {
        const c = coords.value;
        if (c.length < 2) return '';
        return `${line1.value} L${c[c.length - 1][0]},${pad.t + ih.value} L${c[0][0]},${pad.t + ih.value} Z`;
      });
      const ticks = computed(() => {
        const n = 4, out = [];
        for (let i = 0; i <= n; i++) {
          const v = bounds.value.min + ((bounds.value.max - bounds.value.min) * i) / n;
          out.push({ v, y: y(v) });
        }
        return out;
      });
      const xLabels = computed(() => {
        const n = props.points.length;
        if (!n) return [];
        const step = Math.max(1, Math.ceil(n / 6));
        const out = [];
        for (let i = 0; i < n; i += step) out.push({ x: x(i, n), text: (props.points[i].label || '').slice(0, 10).slice(5) });
        if (out[out.length - 1] && out[out.length - 1].x < x(n - 1, n) - 12) {
          out.push({ x: x(n - 1, n), text: (props.points[n - 1].label || '').slice(0, 10).slice(5) });
        }
        return out;
      });
      const hover = computed(() => {
        if (hi.value < 0 || hi.value >= props.points.length) return null;
        const p = props.points[hi.value];
        const cx = x(hi.value, props.points.length);
        return {
          p, cx, cy: y(Number(p.value)),
          left: Math.min(78, Math.max(10, (cx / W) * 100)),
          p2: props.points2[hi.value] || null,
          cy2: props.points2[hi.value] ? y(Number(props.points2[hi.value].value)) : null,
          align: (cx / W) > 0.72 ? 'right' : 'left',
        };
      });
      const targetY = computed(() => (props.target == null ? null : y(props.target)));
      const last = computed(() => {
        const c = coords.value;
        return c.length ? { x: c[c.length - 1][0], y: c[c.length - 1][1] } : null;
      });

      function onMove(ev) {
        const rect = ev.currentTarget.getBoundingClientRect();
        const px = ((ev.clientX - rect.left) / rect.width) * W;
        const n = props.points.length;
        if (n < 1) return;
        const idx = Math.round(((px - pad.l) / iw.value) * (n - 1));
        hi.value = Math.min(n - 1, Math.max(0, idx));
      }
      const fmt = (v) => Number(v).toFixed(props.decimals);

      return { hi, W, H, pad, iw, ih, line1, line2, area1, coords, coords2, ticks,
               xLabels, hover, targetY, last, onMove, fmt, bounds };
    },
    template: `
      <div class="lc-wrap" style="position:relative">
        <svg :viewBox="'0 0 ' + W + ' ' + H" preserveAspectRatio="xMidYMid meet"
             style="width:100%;height:auto;display:block;overflow:visible"
             @mousemove="onMove" @mouseleave="hi=-1">
          <defs>
            <linearGradient :id="'lg-' + name" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" :stop-color="color" stop-opacity=".18"/>
              <stop offset="100%" :stop-color="color" stop-opacity="0"/>
            </linearGradient>
          </defs>
          <g>
            <line v-for="t in ticks" :key="'g'+t.v" :x1="pad.l" :x2="W-pad.r" :y1="t.y" :y2="t.y"
                  stroke="#eef2f6" stroke-width="1"/>
            <text v-for="t in ticks" :key="'t'+t.v" :x="pad.l-8" :y="t.y+4" text-anchor="end"
                  font-size="10" fill="#94a3b8">{{ fmt(t.v) }}</text>
          </g>
          <g v-if="targetY !== null">
            <line :x1="pad.l" :x2="W-pad.r" :y1="targetY" :y2="targetY" stroke="#f59e0b"
                  stroke-width="1.2" stroke-dasharray="5 5" opacity=".75"/>
            <text :x="W-pad.r" :y="targetY-6" text-anchor="end" font-size="9.5" fill="#b45309">{{ targetLabel || ('目标 ' + target) }}</text>
          </g>
          <path :d="area1" :fill="'url(#lg-' + name + ')'" v-if="area1"/>
          <path :d="line2" fill="none" :stroke="color2" stroke-width="1.8" stroke-dasharray="4 3"
                stroke-linejoin="round" v-if="line2 && coords2.length > 1" opacity=".9"/>
          <path :d="line1" fill="none" :stroke="color" stroke-width="2.4" stroke-linejoin="round"
                stroke-linecap="round" v-if="line1"/>
          <circle v-if="last" :cx="last.x" :cy="last.y" r="4.2" :fill="color" stroke="#fff" stroke-width="2"/>
          <g v-if="hover">
            <line :x1="hover.cx" :x2="hover.cx" :y1="pad.t" :y2="pad.t+ih" stroke="#cbd5e1"
                  stroke-width="1" stroke-dasharray="3 3"/>
            <circle :cx="hover.cx" :cy="hover.cy" r="4.6" :fill="color" stroke="#fff" stroke-width="2"/>
            <circle v-if="hover.cy2" :cx="hover.cx" :cy="hover.cy2" r="4" :fill="color2" stroke="#fff" stroke-width="2"/>
          </g>
          <text v-for="l in xLabels" :key="'x'+l.x" :x="l.x" :y="H-8" text-anchor="middle"
                font-size="10" fill="#94a3b8">{{ l.text }}</text>
        </svg>
        <div v-if="hover" class="lc-tip"
             :style="{ left: hover.left + '%', top: '6px', transform: hover.align === 'right' ? 'translateX(-100%)' : 'none' }">
          <div class="lc-tip-t">{{ (hover.p.label || '').slice(0, 10) }}</div>
          <div class="lc-tip-r"><i :style="{background: color}"></i>{{ name }} <b>{{ fmt(hover.p.value) }}</b> {{ unit }}</div>
          <div class="lc-tip-r" v-if="hover.p2"><i :style="{background: color2}"></i>{{ name2 }} <b>{{ fmt(hover.p2.value) }}</b> {{ unit }}</div>
        </div>
      </div>`,
  };

  C.Donut = {
    props: {
      data: { type: Array, default: () => [] },
      size: { type: Number, default: 132 },
      thickness: { type: Number, default: 13 },
      center: { type: String, default: '' },
      centerLabel: { type: String, default: '' },
    },
    setup(props) {
      const total = computed(() => props.data.reduce((s, d) => s + (d.value || 0), 0) || 1);
      const r = computed(() => (props.size - props.thickness) / 2);
      const circ = computed(() => 2 * Math.PI * r.value);
      const segs = computed(() => {
        let acc = 0;
        return props.data.map((d) => {
          const frac = (d.value || 0) / total.value;
          const seg = { ...d, dash: frac * circ.value, offset: -acc * circ.value, frac };
          acc += frac;
          return seg;
        });
      });
      return { total, r, circ, segs };
    },
    template: `
      <div class="donut" :style="{width: size+'px', height: size+'px'}">
        <svg :viewBox="'0 0 ' + size + ' ' + size" :width="size" :height="size">
          <circle :cx="size/2" :cy="size/2" :r="r" fill="none" stroke="#eef2f6" :stroke-width="thickness"/>
          <circle v-for="s in segs" :key="s.label" :cx="size/2" :cy="size/2" :r="r" fill="none"
                  :stroke="s.color" :stroke-width="thickness" stroke-linecap="butt"
                  :stroke-dasharray="s.dash + ' ' + (circ - s.dash)"
                  :stroke-dashoffset="s.offset - circ/4"/>
        </svg>
        <div class="donut-center">
          <b>{{ center }}</b><span>{{ centerLabel }}</span>
        </div>
      </div>`,
  };

  C.Ring = {
    props: { value: { type: Number, default: 0 }, size: { type: Number, default: 62 },
             thickness: { type: Number, default: 6 }, color: { type: String, default: 'var(--primary)' } },
    setup(props) {
      const r = computed(() => (props.size - props.thickness) / 2);
      const circ = computed(() => 2 * Math.PI * r.value);
      const dash = computed(() => (Math.min(100, Math.max(0, props.value)) / 100) * circ.value);
      return { r, circ, dash };
    },
    template: `
      <svg :width="size" :height="size" :viewBox="'0 0 ' + size + ' ' + size">
        <circle :cx="size/2" :cy="size/2" :r="r" fill="none" stroke="#eef2f6" :stroke-width="thickness"/>
        <circle :cx="size/2" :cy="size/2" :r="r" fill="none" :stroke="color" :stroke-width="thickness"
                stroke-linecap="round" :stroke-dasharray="dash + ' ' + circ"
                :stroke-dashoffset="circ/4" transform-origin="center" style="transform:rotate(-90deg);transform-origin:center"/>
      </svg>`,
  };

  C.Bars = {
    props: { items: { type: Array, default: () => [] }, unit: { type: String, default: '%' } },
    setup(props) {
      const max = computed(() => Math.max(100, ...props.items.map((i) => i.value || 0)) || 100);
      return { max };
    },
    template: `
      <div>
        <div v-for="it in items" :key="it.label" style="margin-bottom:11px">
          <div class="between" style="margin-bottom:4px">
            <span class="small" style="font-weight:600">{{ it.label }}<span class="faint tiny" v-if="it.count"> · {{ it.count }}人</span></span>
            <span class="small num" style="font-weight:700">{{ it.value }}{{ unit }}</span>
          </div>
          <div class="progress"><i :style="{ width: Math.min(100, it.value/max*100) + '%', background: it.color || 'var(--primary)' }"></i></div>
        </div>
        <div v-if="!items.length" class="empty">暂无数据</div>
      </div>`,
  };

  C.Spark = {
    props: { points: { type: Array, default: () => [] }, color: { type: String, default: 'var(--primary)' },
             height: { type: Number, default: 42 } },
    setup(props) {
      const W = 220;
      const coords = computed(() => {
        const n = props.points.length;
        const vals = props.points.map((p) => Number(p.value ?? p.count ?? 0));
        const mx = Math.max(...vals, 1), mn = Math.min(...vals, 0);
        return vals.map((v, i) => [n <= 1 ? W / 2 : (i * W) / (n - 1), props.height - 4 - ((v - mn) / (mx - mn || 1)) * (props.height - 8)]);
      });
      const path = computed(() => smoothPath(coords.value));
      const area = computed(() => {
        const c = coords.value;
        if (c.length < 2) return '';
        return `${path.value} L${c[c.length - 1][0]},${props.height} L${c[0][0]},${props.height} Z`;
      });
      return { W, path, area };
    },
    template: `
      <svg :viewBox="'0 0 ' + W + ' ' + height" preserveAspectRatio="none" :style="{width:'100%',height:height+'px',display:'block'}">
        <path :d="area" :fill="color" opacity=".10"/>
        <path :d="path" fill="none" :stroke="color" stroke-width="2" stroke-linejoin="round"/>
      </svg>`,
  };

const PATHS = {
    grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.6"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.6"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.6"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.6"/>',
    users: '<circle cx="9" cy="8" r="3.2"/><path d="M2.8 20c.5-3.5 3.1-5.4 6.2-5.4s5.7 1.9 6.2 5.4"/><path d="M16.4 5.6a3 3 0 010 5.6"/><path d="M18.3 20c-.2-2.1-.8-3.7-1.9-4.8"/>',
    usercheck: '<circle cx="9.2" cy="8" r="3.2"/><path d="M3 20c.5-3.5 3.1-5.4 6.2-5.4 1.3 0 2.4.3 3.4.9"/><path d="M15.6 15.4l2 2 4.4-4.4"/>',
    chat: '<path d="M20.5 11.6c0 4.3-3.8 7.7-8.5 7.7-1 0-2-.2-2.9-.5L4.5 21l1.2-3.8A7.3 7.3 0 013.5 11.6C3.5 7.3 7.3 3.9 12 3.9s8.5 3.4 8.5 7.7z"/>',
    book: '<path d="M4.2 5.4A2.4 2.4 0 016.6 3H20v15.4H6.6a2.4 2.4 0 00-2.4 2.4z"/><path d="M4.2 5.4v15.4"/><path d="M8 7.5h8M8 11h6"/>',
    sliders: '<path d="M4 6.5h9M17.5 6.5H20M4 12h3.5M12 12h8M4 17.5h9M17.5 17.5H20"/><circle cx="15.2" cy="6.5" r="2.1"/><circle cx="9.5" cy="12" r="2.1"/><circle cx="15.2" cy="17.5" r="2.1"/>',
    bell: '<path d="M18 8.5a6 6 0 10-12 0c0 6.5-2.5 7-2.5 7h17S18 15 18 8.5z"/><path d="M10.2 20.5a2 2 0 003.6 0"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/>',
    send: '<path d="M21.5 2.5L10.8 13.2"/><path d="M21.5 2.5l-6.8 19-3.9-8.3-8.3-3.9z"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    heart: '<path d="M20.4 5.8a4.8 4.8 0 00-6.8 0L12 7.4l-1.6-1.6a4.8 4.8 0 00-6.8 6.8L12 21l8.4-8.4a4.8 4.8 0 000-6.8z"/>',
    activity: '<path d="M3 12.5h3.6l2.2-6.3 3.2 12 2.6-7.2 1.6 3.5H21"/>',
    shield: '<path d="M12 3.2l8 2.8v5.7c0 4.9-3.4 7.9-8 9.1-4.6-1.2-8-4.2-8-9.1V6z"/><path d="M9 12.2l2.2 2.2 4-4.2"/>',
    database: '<ellipse cx="12" cy="5.4" rx="7.6" ry="2.8"/><path d="M4.4 5.4v13.2c0 1.5 3.4 2.8 7.6 2.8s7.6-1.3 7.6-2.8V5.4"/><path d="M4.4 12c0 1.5 3.4 2.8 7.6 2.8s7.6-1.3 7.6-2.8"/>',
    cpu: '<rect x="6" y="6" width="12" height="12" rx="2.2"/><rect x="9.2" y="9.2" width="5.6" height="5.6" rx="1.2"/><path d="M9.5 3v3M14.5 3v3M9.5 18v3M14.5 18v3M3 9.5h3M3 14.5h3M18 9.5h3M18 14.5h3"/>',
    trash: '<path d="M4 7h16M9.5 7V4.8h5V7M6.2 7l.9 13.2h9.8L17.8 7"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    check: '<path d="M4.5 12.5l5 5L20 6.5"/>',
    arrow: '<path d="M4.5 12h15M13 5.5l6.5 6.5-6.5 6.5"/>',
    calendar: '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M8 3v4M16 3v4M3.5 10h17"/>',
    pill: '<path d="M10.4 20.5a4.9 4.9 0 01-6.9-6.9l6.2-6.2a4.9 4.9 0 016.9 6.9z"/><path d="M7 7l10 10"/>',
    sparkles: '<path d="M12 3.2l1.9 4.6 4.6 1.9-4.6 1.9L12 16.2l-1.9-4.6L5.5 9.7l4.6-1.9z"/><path d="M18.5 15.5l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z"/>',
    logout: '<path d="M14.5 12H3.5M7.5 8l-4 4 4 4M13.5 4h5a2 2 0 012 2v12a2 2 0 01-2 2h-5"/>',
    filter: '<path d="M3.5 5h17l-6.6 7.6V20l-3.8-2v-5.4z"/>',
    doc: '<path d="M6.5 3h7.2L19 8.3V21H6.5z"/><path d="M13.5 3v5.5H19"/><path d="M9.5 13h6M9.5 16.5h4"/>',
    clock: '<circle cx="12" cy="12" r="8.6"/><path d="M12 7.2v5.2l3.2 2"/>',
    alert: '<path d="M12 3.4l9 16.4H3z"/><path d="M12 9.4v4.4M12 17h.01"/>',
    drop: '<path d="M12 3.2s6.2 6.8 6.2 10.8a6.2 6.2 0 11-12.4 0C5.8 10 12 3.2 12 3.2z"/>',
    upload: '<path d="M12 16V4M7.5 8.5L12 4l4.5 4.5"/><path d="M4 15.5v3A2.5 2.5 0 006.5 21h11a2.5 2.5 0 002.5-2.5v-3"/>',
    brain: '<path d="M9.5 4.2a3 3 0 00-3 3 3 3 0 00-1.6 5.5A3 3 0 006.4 18a3 3 0 005.6 1.4V4.6a2.4 2.4 0 00-2.5-.4z"/><path d="M14.5 4.2a3 3 0 013 3 3 3 0 011.6 5.5A3 3 0 0117.6 18a3 3 0 01-5.6 1.4V4.6a2.4 2.4 0 012.5-.4z"/>',
    edit: '<path d="M4 20h4l10.5-10.5a2.1 2.1 0 00-3-3L5 17z"/><path d="M13.5 6.5l3 3"/>',
    trend: '<path d="M4 16.5l5-5 3.5 3.5L20 7.5"/><path d="M15 7.5h5v5"/>',
    stethoscope: '<path d="M6 3v5a4 4 0 008 0V3"/><path d="M4.5 3h3M12.5 3h3"/><path d="M10 12v3a4.5 4.5 0 009 0v-2.2"/><circle cx="19" cy="10.5" r="2.2"/>',
    food: '<path d="M12 7.5c-2.5-2-6.5-.8-6.5 3.5 0 4 3 9 5 9 .8 0 1.2-.5 1.5-.5s.7.5 1.5.5c2 0 5-5 5-9 0-4.3-4-5.5-6.5-3.5z"/><path d="M12 7.5c0-2 1.2-3.5 3.2-4"/><path d="M11.6 5.2c-1.4-.6-2.6-.5-3.6 0"/>',
    team: '<circle cx="8" cy="8.5" r="2.6"/><circle cx="16.5" cy="9.5" r="2.2"/><path d="M2.8 19.5c.4-3.1 2.7-4.8 5.4-4.8s5 1.7 5.4 4.8"/><path d="M14.2 19.2c.3-2.5 2-4 4.1-4 2 0 3.6 1.3 4 3.8"/>',
  };

  C.Icon = {
    props: { name: { type: String, default: 'grid' }, size: { type: [Number, String], default: 18 } },
    computed: {
      inner() { return PATHS[this.name] || ''; },
    },
    template: `<svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"
              style="display:block;flex:0 0 auto" v-html="inner"></svg>`,
  };

  window.Mb = C;
})();
