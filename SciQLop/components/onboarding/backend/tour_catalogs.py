from SciQLop.components.onboarding.backend.tour import TourStep
from SciQLop.components.onboarding.backend import targets, completions

_NO_PANEL_MESSAGE = (
    "Plot something first to see how overlaying catalogs works — replay "
    "this tour anytime from Tools → Take a Tour."
)

CATALOGS_STEPS: list[TourStep] = [
    TourStep(
        step_id="open_catalogs",
        title="Find the Catalogs browser",
        body="Your labeled time intervals live here — click to open the Catalogs browser.",
        resolver=targets.side_tab_resolver("Catalog Browser"),
        completion=completions.dock_visible("Catalog Browser"),
    ),
    TourStep(
        step_id="meet_providers",
        title="Three places catalogs come from",
        body=(
            "'My Catalogs' is your own local library. 'Shared' is "
            "collaborative catalogs other people are editing with you. "
            "'Remote' mirrors read-only catalogs from external services "
            "like AMDA."
        ),
        resolver=targets.resolve_catalog_tree,
    ),
    TourStep(
        step_id="create_catalog",
        title="Pick or create a catalog",
        body=(
            "Select an existing catalog to browse its events, or "
            "right-click 'My Catalogs' to create your own."
        ),
        resolver=targets.resolve_catalog_tree,
    ),
    TourStep(
        step_id="overlay_catalog",
        title="Overlay a catalog on a plot",
        body=(
            "Drag a catalog onto a graph to overlay it there, or "
            "right-click a panel → Catalogs to toggle one on or off."
        ),
        resolver=targets.resolve_any_plot_with_data,
        poll=True,
        timeout_s=15.0,
        timeout_message=_NO_PANEL_MESSAGE,
    ),
    TourStep(
        step_id="create_event",
        title="Label a time interval",
        body=(
            "The quickest way to label an interval: switch this panel to "
            "'Edit' mode (bottom toolbar, or right-click → Catalogs → "
            "Mode), then hold Shift, click to start, and click again to "
            "finish drawing a new event on the overlaid catalog."
        ),
        # Targets the whole panel, not just the plot or just the mode
        # dropdown in its bottom chrome -- the tip describes using both
        # (switch mode in the chrome, then draw on the plot itself), and
        # a resolver covering only one of them would dim/block the other,
        # the same class of bug fixed for add_event's old button-vs-tree
        # split (see resolve_catalogs_browser_widget's own history).
        resolver=targets.resolve_panel_widget,
    ),
]
