const _wsInstances = new Map()

export function connectProgressWS(token, onMessage) {
  if (_wsInstances.has(token)) return _wsInstances.get(token)

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${window.location.host}/ws/progress?token=${token}`
  let ws = null
  let reconnectTimer = null
  let stopped = false

  function connect() {
    if (stopped) return
    ws = new WebSocket(url)

    ws.onopen = () => {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'pong') return
        if (data.type === 'ping') {
          ws.send('ping')
          return
        }
        if (onMessage) onMessage(data)
      } catch {}
    }

    ws.onclose = () => {
      if (!stopped) {
        reconnectTimer = setTimeout(connect, 3000)
      }
    }

    ws.onerror = () => {
      ws.close()
    }
  }

  connect()

  const handle = {
    close() {
      stopped = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (ws) ws.close()
      _wsInstances.delete(token)
    },
  }

  _wsInstances.set(token, handle)
  return handle
}

export function disconnectProgressWS(token) {
  const handle = _wsInstances.get(token)
  if (handle) {
    handle.close()
    _wsInstances.delete(token)
  }
}
