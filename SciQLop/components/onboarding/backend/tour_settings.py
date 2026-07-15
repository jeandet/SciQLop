from SciQLop.components.onboarding.backend.tour import Tour, TourStep
from SciQLop.components.onboarding.backend.registry import register_tour
from SciQLop.components.onboarding.backend import targets, completions

SETTINGS = Tour(
    id="settings",
    title="Settings",
    description="Find where SciQLop's appearance, plugins, and workspace options live.",
    steps=[
        TourStep(
            step_id="open_settings",
            title="Find Settings",
            body="Click here to open Settings.",
            resolver=targets.side_tab_resolver("Settings"),
            completion=completions.dock_visible("Settings"),
        ),
        TourStep(
            step_id="browse_categories",
            title="Browse categories",
            body=(
                "Settings are organized by category — try Appearance for "
                "instant visual feedback, or Plugins/Workspaces to manage "
                "what's loaded."
            ),
            resolver=targets.resolve_settings_category_list,
        ),
    ],
)

register_tour(SETTINGS)
