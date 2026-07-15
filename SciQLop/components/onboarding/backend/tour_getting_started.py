from SciQLop.components.onboarding.backend.tour import Tour, TourStep
from SciQLop.components.onboarding.backend.registry import register_tour
from SciQLop.components.onboarding.backend import targets, completions
from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
from SciQLop.components.onboarding.backend.tour_settings import SETTINGS_STEPS

_OFFLINE_MESSAGE = (
    "Looks like data providers aren't ready yet — replay this tour anytime "
    "from Tools → Take a Tour once you're online."
)

GETTING_STARTED = Tour(
    id="getting_started",
    title="Getting Started",
    description=(
        "Create your first plot panel, plot a real product, browse "
        "catalogs, and find your way around Settings."
    ),
    steps=[
        TourStep(
            step_id="create_panel",
            title="Create your first plot panel",
            body="Click here to create your first plot panel.",
            resolver=targets.resolve_add_panel_button,
            completion=completions.panel_created,
        ),
        TourStep(
            step_id="open_products",
            title="Find the Products browser",
            body="Your data lives here — click to open the Products browser.",
            resolver=targets.side_tab_resolver("Products"),
            completion=completions.dock_visible("Products"),
        ),
        TourStep(
            step_id="plot_product",
            title="Plot a real product",
            body="Drag this onto your empty panel to plot it.",
            resolver=targets.resolve_first_candidate_product,
            poll=True,
            completion=completions.plot_added_to("create_panel"),
            timeout_s=10.0,
            timeout_message=_OFFLINE_MESSAGE,
        ),
        TourStep(
            step_id="overlay_vs_new_subplot",
            title="Adding more data",
            body=(
                "Adding more data: drop a product in the middle of a graph to "
                "overlay it there, or near its top/bottom edge (watch for the "
                "blue highlight) to stack it as a new plot in this panel."
            ),
            resolver=targets.resolve_latest_plot_widget,
        ),
        TourStep(
            step_id="shortcut_tip",
            title="One-click shortcut",
            body=(
                "Tip: next time, right-click any product → '+ New panel' "
                "to create a panel and plot it in one click."
            ),
            resolver=targets.resolve_products_tree_widget,
        ),
        *CATALOGS_STEPS,
        *SETTINGS_STEPS,
    ],
)

register_tour(GETTING_STARTED)
