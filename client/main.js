import './layout.css'

const zh = navigator.language.toLowerCase().startsWith('zh')
const t = zh ? {
  run:'运行当前文件', preview:'在侧边打开预览', stop:'停止运行', close:'关闭工作台', project:'打开项目文件夹…',
  runWithArguments:'带参数运行…', argumentsPrompt:'输入本次运行的参数。含空格的参数请用引号括起来。',
  invalidArguments:'请补全未闭合的引号或末尾的转义字符。', choosePython:'请先打开一个 Python 文件。',
  output:'运行输出', input:'输入一行并按回车', send:'发送输入', frames:'定位错误', choose:'请先打开可运行的文件。',
  savedFailed:'文件尚未全部保存。', idle:'就绪', running:'运行中', inputState:'等待输入', stopping:'正在停止',
  stopped:'已停止', finished:'已完成', failed:'运行出错', save:'保存', discard:'不保存', cancel:'取消',
  prompt:'要保存对以下文件的更改吗？', runningPrompt:'有脚本正在运行。要停止并继续吗？', stopContinue:'停止并继续',
  stillRunning:'脚本还在等待原生调用返回。工作台将保持打开。', changed:'编辑内容刚刚发生变化，请再次确认。',
  recovered:'已恢复未保存的编辑。', conflict:'磁盘文件已变化。恢复内容已单独打开，可用“另存为”保存。',
  unreadableDrafts(name, count) {
    const which = name ? `草稿「${name}」` : `${count} 份草稿`
    return `${which}未能恢复。原件已保留在 .workbench-drafts 文件夹中。`
  },
  showDrafts:'查看草稿列表', skippedDrafts:'未恢复的草稿',
  recoveryFailed:'恢复副本写入失败，请手动保存。', disconnected:'未能连接本机工作台。请保留此页面并重试。',
  restored:'已重新连接本机工作台。', empty:'尚无运行输出', startedFailed:'工作台未能打开', previewTitle:'预览',
  closePanel:'关闭', type:'输入', untitled:'未命名'
} : {
  run:'Run Active File', preview:'Open Preview to the Side', stop:'Stop Running File', close:'Close Workbench', project:'Open Project Folder…',
  runWithArguments:'Run with Arguments…', argumentsPrompt:'Enter arguments for this run. Quote arguments that contain spaces.',
  invalidArguments:'Finish the quoted argument or the trailing escape.', choosePython:'Open a Python file first.',
  output:'Run Output', input:'Type a line and press Enter', send:'Send input', frames:'Go to error', choose:'Open a runnable file first.',
  savedFailed:'Some files still have unsaved changes.', idle:'Ready', running:'Running', inputState:'Waiting for input', stopping:'Stopping',
  stopped:'Stopped', finished:'Finished', failed:'Failed', save:'Save', discard:"Don't Save", cancel:'Cancel',
  prompt:'Save changes to these files?', runningPrompt:'A script is running. Stop it and continue?', stopContinue:'Stop and Continue',
  stillRunning:'The script is waiting for a native call to return. The workbench will stay open.', changed:'The edits changed. Please confirm again.',
  recovered:'Unsaved edits were restored.', conflict:'The file on disk changed. The recovered text opened separately. Use Save As to keep it.',
  unreadableDrafts(name, count) {
    const which = name ? `“${name}”` : `${count} ${count === 1 ? 'draft' : 'drafts'}`
    return `Could not restore ${which}. The recovery data is still in .workbench-drafts.`
  },
  showDrafts:'Show Draft List', skippedDrafts:'Unrestored Drafts',
  recoveryFailed:'Could not store the recovery copy. Save your file.', disconnected:'Could not reach the local workbench. Keep this page open and try again.',
  restored:'Reconnected to the local workbench.', empty:'No output yet', startedFailed:'Could not open the workbench', previewTitle:'Preview',
  closePanel:'Close', type:'Input', untitled:'Untitled'
}
function sizeViewport() {
  const viewport = window.visualViewport
  if (!viewport || viewport.scale !== 1) return
  document.documentElement.style.setProperty('--viewport-height', Math.round(viewport.height) + 'px')
}
window.visualViewport?.addEventListener('resize', sizeViewport)
sizeViewport()
async function open() {
  if (zh) await import('@codingame/monaco-vscode-language-pack-zh-hans')
  const {start} = await import('./workbench.js')
  await start(t)
}
open().catch(error => {
  document.getElementById('loading').hidden = false
  document.getElementById('message').textContent = t.startedFailed + ' · ' + error.message
  console.error(error)
})
