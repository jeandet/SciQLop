def panel_created(main_window, context):
    return main_window.panel_added


def dock_visible(dock_name):
    def _completion(main_window, context):
        dw = main_window.dock_manager.findDockWidget(dock_name)
        if dw is None:
            return None
        return dw.visibilityChanged, (lambda visible: visible)
    return _completion


def plot_added_to(context_key):
    def _completion(main_window, context):
        panel = context.get(context_key)
        if panel is None:
            return None
        return panel.plot_added
    return _completion
