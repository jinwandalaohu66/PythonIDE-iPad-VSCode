"""Present through PythonIDE's existing UI API and fit only our own web view."""


def fit_native(address):
    from objc_util import ObjCClass, on_main_thread

    @on_main_thread
    def attach():
        application = ObjCClass("UIApplication").sharedApplication()
        web_class = ObjCClass("WKWebView")
        controller_class = ObjCClass("UIViewController")
        for scene in application.connectedScenes():
            if scene.activationState() != 0 or not scene.respondsToSelector_("windows"):
                continue
            for window in scene.windows():
                pending = [window]
                while pending:
                    item = pending.pop()
                    if item.isKindOfClass_(web_class):
                        url = item.URL()
                        if url is None or str(url.absoluteString()) != address:
                            continue
                        controller = item.nextResponder()
                        while controller is not None and not controller.isKindOfClass_(controller_class):
                            controller = controller.nextResponder()
                        if controller is None:
                            continue
                        container = controller.view()
                        safe = container.safeAreaLayoutGuide()
                        # The public ui presenter owns dismissal. Keep the editor
                        # above its scrolling canvas and let UIKit size it.
                        container.addSubview_(item)
                        item.setTranslatesAutoresizingMaskIntoConstraints_(False)
                        item.scrollView().setContentInsetAdjustmentBehavior_(2)
                        for anchor, edge in [(item.leadingAnchor(), safe.leadingAnchor()),
                                             (item.trailingAnchor(), safe.trailingAnchor()),
                                             (item.topAnchor(), safe.topAnchor()),
                                             (item.bottomAnchor(), container.keyboardLayoutGuide().topAnchor())]:
                            anchor.constraintEqualToAnchor_(edge).setActive_(True)
                        return True
                    pending.extend(item.subviews())
        return False

    return attach


def present(studio):
    import ui

    root = ui.View()
    studio.host_view_id = root._view_id
    root.background_color = "#181818"
    editor = ui.WebView()
    editor.background_color = "#181818"
    editor.flex = "WH"
    root.add_subview(editor)
    try:
        root.present("fullscreen", hide_title_bar=True, close_action=studio.finished.set)
        _, _, width, height = root.frame
        if width <= 0 or height <= 0:
            width, height = ui.get_window_size()
        editor.frame = (0, 0, width, height)
        editor.load_url(studio.address)
        try:
            fit = fit_native(studio.address)
        except (ImportError, AttributeError, RuntimeError, NotImplementedError):
            fit = None
        if fit:
            for _ in range(12):
                if studio.finished.wait(0.25) or fit():
                    break
        studio.finished.wait()
    finally:
        studio.host_view_id = None
        root.close()
