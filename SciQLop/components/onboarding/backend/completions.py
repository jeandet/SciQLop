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
        # SciQLopPlots' PlaceHolderManager inserts a temporary PlaceHolder
        # plot into the panel on dragEnterEvent/dragMoveEvent, before the
        # drop completes, and that insertion fires plot_added the same as
        # a real plot -- ignore it, or the tour advances mid-drag onto a
        # target that gets torn down the moment the real drop lands.
        return panel.plot_added, (lambda plot: plot.objectName() != "PlaceHolder")
    return _completion
