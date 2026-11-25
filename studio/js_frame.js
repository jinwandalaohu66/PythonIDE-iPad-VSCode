// This document has an opaque origin. Its worker can be stopped even in a tight loop.
const send = (kind, text = '') => parent.postMessage({channel:'project-javascript', kind, text}, '*')
let worker
async function start() {
  const file = new URL(location.href).searchParams.get('entry')
  const response = await fetch(new URL('.worker.js', location.href))
  if (!response.ok) throw Error('The JavaScript worker could not start.')
  const script = URL.createObjectURL(new Blob([await response.text()], {type:'text/javascript'}))
  worker = new Worker(script)
  worker.onmessage = ({data}) => {
    send(data.kind, data.text)
    if (data.kind === 'finished' || data.kind === 'failed') {
      worker.terminate()
      URL.revokeObjectURL(script)
    }
  }
  worker.onerror = event => {
    send('failed', event.message || 'The JavaScript worker could not load the project module.')
    worker.terminate()
    URL.revokeObjectURL(script)
  }
  worker.postMessage(file)
}
addEventListener('pagehide', () => worker?.terminate(), {once:true})
start().catch(error => send('failed', error.message))
