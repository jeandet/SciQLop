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
        step_id="create_catalog",
        title="Create a catalog",
        body="Right-click a provider here to create a new catalog.",
        resolver=targets.resolve_catalog_tree,
    ),
    TourStep(
        step_id="add_event",
        title="Label a time interval",
        body="Select a catalog, then click 'Add Event' to label a time interval.",
        # The catalog tree (select a catalog) and the Add Event button --
        # part of the event table's toolbar, on the OTHER side of the
        # browser -- are two separate widgets. Targeting just the tree
        # (the original fix for 72a61c53's abort-the-whole-tour bug --
        # the tree is unconditional, the button is hidden until a catalog
        # is selected) spotlighted only half of what this tip describes,
        # leaving the Add Event button dimmed and unreachable behind the
        # coach mark. The whole browser widget is just as unconditional
        # (constructed once in mainwindow.py) and its cutout naturally
        # covers both halves.
        resolver=targets.resolve_catalogs_browser_widget,
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
]
