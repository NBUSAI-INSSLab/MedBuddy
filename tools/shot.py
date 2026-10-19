"""通过 CDP 截图并收集控制台错误，用于本地 UI 验证。"""
import base64
import json
import sys
import time

import requests
import websocket

PORT = 9222


def new_tab(url):
    r = requests.put(f"http://127.0.0.1:{PORT}/json/new?{url}", timeout=5)
    return r.json()


def shot(url, out, actions=None, wait=2.5, width=1600, height=1000):
    tab = new_tab(url)
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=20)
    counter = [0]
    logs = []

    def send(method, params=None):
        counter[0] += 1
        ws.send(json.dumps({"id": counter[0], "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == counter[0]:
                return msg
            evt = msg.get("method", "")
            if evt == "Runtime.consoleAPICalled":
                args = [a.get("value", a.get("description", "")) for a in msg["params"].get("args", [])]
                if msg["params"].get("type") in ("error", "warning"):
                    logs.append(f"[console.{msg['params']['type']}] " + " ".join(str(a) for a in args))
            if evt == "Runtime.exceptionThrown":
                d = msg["params"]["exceptionDetails"]
                logs.append("[exception] " + (d.get("exception", {}).get("description") or d.get("text", "")))
            if evt == "Log.entryAdded":
                e = msg["params"]["entry"]
                if e.get("level") in ("error", "warning"):
                    logs.append(f"[log.{e['level']}] {e.get('text','')} {e.get('url','')}")

    send("Runtime.enable")
    send("Log.enable")
    send("Page.enable")
    send("Emulation.setDeviceMetricsOverride",
         {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
    send("Page.navigate", {"url": url})
    time.sleep(wait)

    if actions:
        for expr in actions:
            send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
            time.sleep(1.2)

    send("Page.navigate", {"url": url}) if actions else None
    if actions:
        time.sleep(2.2)

    result = send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    data = result.get("result", {}).get("data")
    if data:
        with open(out, "wb") as f:
            f.write(base64.b64decode(data))
        print(f"saved {out}")
    else:
        print("screenshot failed:", result)
    for line in logs:
        print(line)
    ws.close()


if __name__ == "__main__":
    url = sys.argv[1]
    out = sys.argv[2]
    shot(url, out)
