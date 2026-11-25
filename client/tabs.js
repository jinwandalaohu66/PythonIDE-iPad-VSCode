import {GroupsOrder} from '@codingame/monaco-vscode-api/vscode/vs/workbench/services/editor/common/editorGroupsService'

export function captureTabs(api, groups, project) {
  const ordered = groups.getGroups(GroupsOrder.GRID_APPEARANCE).slice(0, 6)
  const snapshots = ordered.map((group, index) => {
    const tabs = group.editors.filter(editor => editor.resource?.scheme === 'studio')
    const active = group.activeEditor?.resource
    const focused = active?.scheme === 'studio' ? project.relative(active) : null
    const editor = api.window.visibleTextEditors.find(item => item.viewColumn === index + 1 &&
      item.document.uri.toString() === active?.toString())
    const caret = editor?.selection.active
    const paths = tabs.slice(0, 40).map(tab => project.relative(tab.resource))
    if (focused && !paths.includes(focused)) paths.push(focused)
    return {paths, active:focused, cursor:caret ? [caret.line, caret.character] : null}
  })
  return {groups:snapshots, activeGroup:Math.max(0,ordered.indexOf(groups.activeGroup))}
}

export async function openTabs(api, project, folder, layout, entry) {
  const selected = []
  for (const [index, group] of (Array.isArray(layout?.groups) ? layout.groups.slice(0, 6) : []).entries()) {
    let active, last
    const options = {viewColumn:index+1, preview:false, preserveFocus:true}
    for (const path of Array.isArray(group?.paths) ? group.paths.slice(0, 41) : []) {
      if (typeof path !== 'string') continue
      try {
        // A user may have moved or removed a tab's file outside the workbench.
        await project.call('stat', {path})
      } catch (error) {
        if (['EntryNotFound','NoPermissions','FileNotFound'].includes(error.code)) continue
        throw error
      }
      const doc = await api.workspace.openTextDocument(api.Uri.joinPath(folder, path))
      await api.window.showTextDocument(doc, options)
      last = doc
      if (path === group.active) active = doc
    }
    if (active || last) {
      const doc = active || last
      if (active && Array.isArray(group.cursor) && group.cursor.every(Number.isInteger)) {
        const point = doc.validatePosition(new api.Position(Math.max(0,group.cursor[0]), Math.max(0,group.cursor[1])))
        options.selection = new api.Range(point,point)
      }
      await api.window.showTextDocument(doc, options)
      selected[index] = {doc, options}
    }
  }
  const focus = selected[layout?.activeGroup] || selected.find(Boolean)
  if (focus) await api.window.showTextDocument(focus.doc, {...focus.options, preserveFocus:false})
  else if (entry) {
    const doc = await api.workspace.openTextDocument(api.Uri.joinPath(folder, entry))
    await api.window.showTextDocument(doc, {preview:false})
  }
}
