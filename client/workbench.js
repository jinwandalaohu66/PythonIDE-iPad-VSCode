import {initialize, getService, IEditorGroupsService, ITextFileService} from '@codingame/monaco-vscode-api'
import {URI} from '@codingame/monaco-vscode-api/vscode/vs/base/common/uri'
import {registerExtension, ExtensionHostKind} from '@codingame/monaco-vscode-api/extensions'
import 'vscode/localExtensionHost'
import workbench from '@codingame/monaco-vscode-workbench-service-override'
import configuration from '@codingame/monaco-vscode-configuration-service-override'
import dialogs from '@codingame/monaco-vscode-dialogs-service-override'
import explorer from '@codingame/monaco-vscode-explorer-service-override'
import files, {registerCustomProvider} from '@codingame/monaco-vscode-files-service-override'
import languages from '@codingame/monaco-vscode-languages-service-override'
import model from '@codingame/monaco-vscode-model-service-override'
import notifications from '@codingame/monaco-vscode-notifications-service-override'
import search from '@codingame/monaco-vscode-search-service-override'
import storage from '@codingame/monaco-vscode-storage-service-override'
import textmate from '@codingame/monaco-vscode-textmate-service-override'
import theme from '@codingame/monaco-vscode-theme-service-override'
import '@codingame/monaco-vscode-python-default-extension'
import '@codingame/monaco-vscode-theme-defaults-default-extension'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import GrammarWorker from '@codingame/monaco-vscode-textmate-service-override/worker?worker'
import SearchWorker from '@codingame/monaco-vscode-search-service-override/worker?worker'
import '@codingame/monaco-vscode-javascript-default-extension'
import '@codingame/monaco-vscode-html-default-extension'
import '@codingame/monaco-vscode-css-default-extension'
import '@codingame/monaco-vscode-markdown-basics-default-extension'
import {MenuId, MenuRegistry} from '@codingame/monaco-vscode-api/vscode/vs/platform/actions/common/actions'
import {CommandsRegistry} from '@codingame/monaco-vscode-api/vscode/vs/platform/commands/common/commands'
import {Codicon} from '@codingame/monaco-vscode-api/vscode/vs/base/common/codicons'
import {Drafts} from './drafts.js'
import {captureTabs, openTabs} from './tabs.js'
import {RunOutput} from './output.js'
import {registerPreviews, runJavaScript} from './previews.js'
import {ProjectFiles, request} from './project.js'

window.MonacoEnvironment = {
  getWorker(_id, label) {
    if (label === 'TextMateWorker') return new GrammarWorker()
    if (label === 'localFileSearchWorker') return new SearchWorker()
    return new EditorWorker()
  }
}

const id = key => 'pythonideWorkbench.' + key
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
const running = job => ['running','input','stopping'].includes(job.status)

export async function start(t) {
  const info = await request('hello')
  const project = new ProjectFiles(info.active)
  const folder = URI.from({scheme:'studio', path:project.root})
  registerCustomProvider('studio', project)
  await initialize({
    ...files(), ...configuration(), ...storage(), ...model(), ...languages(), ...textmate(),
    ...theme(), ...workbench(), ...explorer(), ...search(), ...dialogs(), ...notifications()
  }, document.getElementById('workbench'), {
    workspaceProvider:{workspace:{folderUri:folder}, trusted:true, async open() { return false }},
    productConfiguration:{nameShort:'PythonIDE Workbench', nameLong:'PythonIDE Workbench'},
    configurationDefaults:{
      'workbench.startupEditor':'none', 'workbench.colorTheme':'Default Dark Modern',
      'workbench.secondarySideBar.defaultVisibility':'hidden', 'workbench.tips.enabled':false,
      'window.commandCenter':false, 'window.customTitleBarVisibility':'always',
      'workbench.editor.alwaysShowEditorActions':true,
      'editor.minimap.enabled':false, 'breadcrumbs.enabled':true, 'editor.fontSize':14,
      'telemetry.telemetryLevel':'off', 'files.autoSave':'off', 'workbench.editor.enablePreview':false
    }
  })
  const scripts = 'resourceScheme == studio && resourceExtname =~ /^(\\.py|\\.js|\\.mjs)$/i'
  const pythonFiles = 'resourceScheme == studio && resourceExtname =~ /^\\.py$/i'
  const previews = 'resourceScheme == studio && resourceExtname =~ /^(\\.html?|\\.md|\\.markdown)$/i'
  const busy = id('running')
  const extension = registerExtension({
    name:'workbench-actions', publisher:'pythonide', version:'0.2.1', engines:{vscode:'*'},
    contributes:{
      commands:['run','runWithArguments','preview','stop','project','close'].map(key => ({
        command:id(key), title:t[key], category:'PythonIDE',
        icon:'$(' + ({run:'play', runWithArguments:'play', preview:'open-preview', stop:'debug-stop', project:'folder-opened', close:'close'})[key] + ')'
      })),
      menus:{
        'editor/title':[
          {command:id('run'), when:scripts + ' && !' + busy, group:'navigation@1'},
          {command:id('stop'), when:busy, group:'navigation@1'},
          {command:id('preview'), when:previews, group:'navigation@2'}
        ],
        'view/title':[{command:id('project'), when:'view == workbench.explorer.fileView', group:'workspace'}],
        commandPalette:[
          {command:id('run'), when:scripts + ' && !' + busy},
          {command:id('runWithArguments'), when:pythonFiles + ' && !' + busy},
          {command:id('stop'), when:busy}, {command:id('preview'), when:previews}
        ]
      },
      keybindings:[
        {command:id('run'), key:'ctrl+f5', when:scripts + ' && !' + busy},
        {command:id('preview'), key:'ctrl+k v', mac:'cmd+k v', when:previews}
      ]
    }
  }, ExtensionHostKind.LocalProcess)
  const api = await extension.getApi()
  const groups = await getService(IEditorGroupsService)
  const drafts = new Drafts(api, project, t)
  const preview = registerPreviews(api, t, project)
  let job = {status:'idle', output:''}, mode = 'python', name = ''
  let timer, generation = 0, busyAction = false, ended = false, lost = false, stopJS
  const dirty = () => api.workspace.textDocuments.filter(doc => doc.isDirty)
  const signature = () => JSON.stringify(dirty().map(doc => [doc.uri.toString(), doc.version]).sort())
  const alert = message => api.window.showErrorMessage(message)
  function render(snapshot) {
    const wasRunning = running(job)
    job = snapshot
    output.render({...snapshot, name})
    if (wasRunning !== running(job)) api.commands.executeCommand('setContext', busy, running(job))
  }
  function schedule() {
    clearTimeout(timer)
    if (!ended && !busyAction && mode === 'python' && (running(job) || lost)) {
      timer = setTimeout(refresh, document.hidden ? 1400 : lost ? 1000 : 220)
    }
  }
  async function refresh() {
    if (ended || busyAction || mode !== 'python') return
    const at = generation
    try {
      const snapshot = await project.call('status')
      if (at !== generation || ended) return
      render(snapshot)
      if (lost) { lost = false; api.window.showInformationMessage(t.restored); drafts.flush().catch(() => {}) }
    } catch {
      if (at !== generation || ended) return
      if (!lost) api.window.showWarningMessage(t.disconnected)
      lost = true
    } finally { schedule() }
  }
  async function action(fn) {
    if (busyAction || ended) return false
    busyAction = true
    generation++
    clearTimeout(timer)
    try { await fn(); return true }
    catch (error) { alert(error.message); return false }
    finally { busyAction = false; schedule() }
  }
  async function save() {
    if (!await api.workspace.saveAll(true) || dirty().length) throw Error(t.savedFailed)
  }
  const output = new RunOutput(t,
    text => action(async () => { render(await project.call('input', {job:job.id, prompt:job.prompt, text})) }),
    frame => action(async () => {
      const doc = await api.workspace.openTextDocument(api.Uri.joinPath(folder, frame.path))
      const point = new api.Position(Math.max(0, Math.min(doc.lineCount, frame.line) - 1), 0)
      await api.window.showTextDocument(doc, {selection:new api.Range(point, point), preview:false, viewColumn:api.ViewColumn.One})
    }), job => project.call('libraryRecovery', {job}).catch(error => alert(error.message)))
  function target(uri, context) {
    // The title menu can reuse its action URI across tabs with the same
    // language. Its group context is current, even in an unfocused split.
    const groupId = context?.groupId ?? uri?.groupId
    const group = groupId == null ? groups.activeGroup : groups.getGroup(groupId)
    const selected = group?.activeEditor?.resource
    if (selected?.scheme !== 'studio') throw Error(t.choose)
    return api.Uri.parse(selected.toString())
  }
  function run(uri, context, withArguments = false) {
    return action(async () => {
      if (running(job)) return
      const path = project.relative(target(uri, context))
      if (!/\.(py|m?js)$/i.test(path)) throw Error(t.choose)
      const isPython = /\.py$/i.test(path)
      const request = {path}
      if (withArguments) {
        if (!isPython) throw Error(t.choosePython)
        const text = await api.window.showInputBox({
          title:t.runWithArguments, prompt:t.argumentsPrompt, placeHolder:'--title "My report" --width 800',
          validateInput:async argumentsText => {
            try {
              return await project.call('validateRunArguments', {argumentsText}) ? undefined : t.invalidArguments
            } catch {
              return t.disconnected
            }
          }
        })
        if (text === undefined) return
        request.argumentsText = text
      }
      await save()
      await output.show()
      name = path
      if (isPython) {
        mode = 'python'
        const started = await project.call('run', request)
        output.automaticJob = started.id
        render(started)
      } else {
        mode = 'javascript'
        stopJS = await runJavaScript(project, path, render)
      }
    })
  }
  async function stop() {
    if (!running(job)) return
    if (mode === 'javascript') { stopJS?.(); return }
    render(await project.call('stop', {job:job.id}))
  }
  async function leave(next, targetKey) {
    await action(async () => {
      const before = signature()
      const docs = dirty()
      let decision
      if (docs.length) {
        const cancel = {title:t.cancel, isCloseAffordance:true}
        decision = await api.window.showWarningMessage(t.prompt, {
          modal:true, detail:docs.map(doc => doc.uri.scheme === 'studio' ? project.relative(doc.uri) : doc.fileName.split('/').pop()).join('\n')
        }, {title:t.save}, {title:t.discard}, cancel)
        if (!decision || decision.title === t.cancel) return
      }
      if (running(job)) {
        const choice = await api.window.showWarningMessage(t.runningPrompt, {modal:true}, t.stopContinue)
        if (choice !== t.stopContinue) return
      }
      if (before !== signature()) throw Error(t.changed)
      if (decision?.title === t.save) await save()
      const confirmed = signature()
      if (running(job)) {
        await stop()
        for (let i = 0; running(job) && i < 25; i++) {
          await delay(120)
          render(await project.call('status'))
        }
        if (running(job)) throw Error(t.stillRunning)
      }
      const discard = decision?.title === t.discard
      const surface = document.getElementById('workbench')
      surface.inert = true
      try {
        if (!discard) await drafts.flush()
        await drafts.suspend()
        if (signature() !== confirmed) throw Error(t.changed)
        await project.leave(next, {target:targetKey, discard, clearDrafts:discard ? drafts.references() : [],
          editors:captureTabs(api, groups, project)})
        ended = true
        window.removeEventListener('beforeunload', beforeUnload)
        if (next === 'close') window.workbenchClosed()
        else location.reload()
      } finally {
        if (!ended) { surface.inert = false; drafts.resume() }
      }
    })
  }
  function beforeUnload(event) {
    if (!ended && dirty().length) { event.preventDefault(); event.returnValue = '' }
  }
  async function pickProject() {
    if (busyAction || ended) return
    const options = info.projects.map(item => ({label:item.name, description:item.key === info.active.key ? '✓' : '', key:item.key}))
    const picked = await api.window.showQuickPick(options, {title:t.project, placeHolder:t.project})
    if (picked && picked.key !== info.active.key) await leave('select', picked.key)
  }
  api.commands.registerCommand(id('run'), (uri, context) => run(uri, context))
  api.commands.registerCommand(id('runWithArguments'), (uri, context) => run(uri, context, true))
  api.commands.registerCommand(id('preview'), (uri, context) => action(async () => {
    const file = target(uri, context)
    if (/\.html?$/i.test(file.path)) await save()
    await preview(file)
  }))
  api.commands.registerCommand(id('stop'), () => action(stop))
  api.commands.registerCommand(id('project'), pickProject)
  window.requestWorkbenchClose = () => leave('close')
  api.commands.registerCommand(id('close'), window.requestWorkbenchClose)
  for (const command of ['workbench.action.files.openFolder','workbench.action.files.openFolderViaWorkspace']) {
    CommandsRegistry.registerCommand(command, pickProject)
  }
  MenuRegistry.appendMenuItem(MenuId.TitleBar, {command:{id:id('close'), title:t.close, icon:Codicon.close}, group:'navigation', order:100})
  MenuRegistry.appendMenuItem(MenuId.MenubarFileMenu, {command:{id:id('project'), title:t.project}, group:'2_open', order:2.5})
  MenuRegistry.appendMenuItem(MenuId.MenubarFileMenu, {command:{id:id('close'), title:t.close}, group:'z_exit', order:100})
  await api.commands.executeCommand('workbench.view.explorer')
  await openTabs(api, project, folder, info.editors, info.entry)
  await drafts.restore(folder)
  drafts.watch(await getService(ITextFileService))
  await refresh()
  document.getElementById('loading').hidden = true
  window.addEventListener('beforeunload', beforeUnload)
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && !ended) { refresh(); drafts.flush().catch(() => {}) }
  })
}
