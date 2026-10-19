/* 请求封装 + SSE 客户端 */
(function () {
  async function request(method, url, body) {
    const opt = { method, credentials: 'same-origin', headers: {} };
    if (body !== undefined) {
      opt.headers['Content-Type'] = 'application/json';
      opt.body = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(url, opt);
    } catch (e) {
      throw new Error('网络连接失败，请确认服务是否运行');
    }
    let data = null;
    try { data = await res.json(); } catch (e) { /* 非 JSON */ }
    if (res.status === 401) {
      Store.user = null;
      throw new Error('登录已过期，请重新登录');
    }
    if (!res.ok || !data || data.ok === false) {
      throw new Error((data && data.error) || `请求失败（${res.status}）`);
    }
    return data.data;
  }

  window.API = {
    get: (url) => request('GET', url),
    post: (url, body) => request('POST', url, body || {}),
    put: (url, body) => request('PUT', url, body || {}),
    del: (url) => request('DELETE', url),

    async upload(url, formData) {
      const res = await fetch(url, { method: 'POST', body: formData, credentials: 'same-origin' });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || '上传失败');
      return data.data;
    },

    /* 流式对话：handlers = {conversation, meta, delta, done, error} */
    async streamChat(payload, handlers) {
      return this.stream('/api/chat/stream', payload, handlers);
    },

    /* 通用 SSE：POST JSON，按事件名分发给 handlers */
    async stream(url, payload, handlers) {
      let res;
      try {
        res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify(payload),
        });
      } catch (e) {
        handlers.error && handlers.error('网络连接失败，请确认服务是否运行');
        return;
      }
      if (!res.ok) {
        let msg = `请求失败（${res.status}）`;
        try { const d = await res.json(); if (d.error) msg = d.error; } catch (e) {}
        handlers.error && handlers.error(msg);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      const dispatch = (raw) => {
        let evt = 'message', data = [];
        raw.split('\n').forEach((line) => {
          if (line.startsWith('event:')) evt = line.slice(6).trim();
          else if (line.startsWith('data:')) data.push(line.slice(5).trim());
        });
        if (!data.length) return;
        let payloadObj = {};
        try { payloadObj = JSON.parse(data.join('\n')); } catch (e) { return; }
        if (evt === 'end') return;
        const fn = handlers[evt];
        if (fn) fn(payloadObj);
      };
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf('\n\n')) >= 0) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          if (raw.trim()) dispatch(raw);
        }
      }
    },
  };
})();
