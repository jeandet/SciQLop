from dataclasses import dataclass


@dataclass(frozen=True)
class TourStep:
    step_id: str
    title: str
    body: str
    resolver_id: str
    poll: bool = False
    completion_signal_id: str | None = None
    timeout_s: float | None = None
    timeout_message: str | None = None


_OFFLINE_MESSAGE = (
    "Looks like data providers aren't ready yet — replay this tour anytime "
    "from Tools → Replay Onboarding Tour once you're online."
)

TOUR_STEPS: list[TourStep] = [
    TourStep(
        step_id="create_panel",
        title="Create your first plot panel",
        body="Click here to create your first plot panel.",
        resolver_id="add_panel_button",
        completion_signal_id="panel_created",
    ),
    TourStep(
        step_id="open_products",
        title="Find the Products browser",
        body="Your data lives here — click to open the Products browser.",
        resolver_id="products_side_tab",
        completion_signal_id="products_visible",
    ),
    TourStep(
        step_id="plot_product",
        title="Plot a real product",
        body="Drag this onto your empty panel to plot it.",
        resolver_id="first_candidate_product",
        poll=True,
        completion_signal_id="plot_added",
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
        resolver_id="latest_plot_widget",
    ),
    TourStep(
        step_id="shortcut_tip",
        title="One-click shortcut",
        body=(
            "Tip: next time, right-click any product → '+ New panel' "
            "to create a panel and plot it in one click."
        ),
        resolver_id="products_tree_widget",
    ),
]
