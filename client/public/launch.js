// Keep the exit available even if an editor asset fails to load.
(() => {
  const zh = navigator.language.toLowerCase().startsWith('zh')
  const button = document.getElementById('startup-close')
  const message = document.getElementById('message')
  document.documentElement.lang = zh ? 'zh-Hans' : 'en'
  message.textContent = zh ? '正在打开工作区…' : 'Opening your workspace…'
  button.textContent = zh ? '关闭' : 'Close'
  window.workbenchClosed = () => {
    document.getElementById('workbench').hidden = true
    document.getElementById('loading').hidden = false
    message.textContent = zh ? '工作台已关闭' : 'Workbench closed'
    button.hidden = true
  }
  button.onclick = async () => {
    if (window.requestWorkbenchClose) return window.requestWorkbenchClose()
    const rpc = async (action, fields = {}) => {
      const reply = await fetch(new URL('rpc', document.baseURI), {method:'POST',
        headers:{'Content-Type':'application/json','X-Studio-Request':'1'},
        body:JSON.stringify({action,...fields})})
      const data = await reply.json()
      if (!reply.ok) throw Error(data.error)
      return data.result
    }
    try {
      const {active} = await rpc('hello')
      await rpc('close', {project:active.key})
      window.workbenchClosed()
    } catch (error) { message.textContent = error.message }
  }
})()
