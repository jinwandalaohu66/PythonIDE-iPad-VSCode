function display(value) {
  if (value instanceof Error) return value.stack || value.message
  if (typeof value === 'string') return value
  try { return JSON.stringify(value, (_, v) => typeof v === 'bigint' ? String(v) + 'n' : v) ?? String(value) }
  catch { return String(value) }
}
const send = (kind, text = '') => postMessage({kind, text})
let pending = '', last = -Infinity, timer
function flush() {
  clearTimeout(timer)
  timer = undefined
  if (!pending) return
  send('output', pending)
  pending = ''
  last = performance.now()
}
for (const method of ['log','info','warn','error','debug','dir','table']) {
  console[method] = (...args) => {
    pending = (pending + args.map(display).join(' ') + '\n').slice(-65536)
    if (performance.now() - last >= 80) flush()
    else if (!timer) timer = setTimeout(() => { timer = undefined; flush() }, 80)
  }
}
addEventListener('message', async ({data}) => {
  try { await import(data); flush(); send('finished') }
  catch (error) { flush(); send('failed', display(error)) }
}, {once:true})
