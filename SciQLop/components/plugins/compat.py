"""SciQLop ↔ plugin version compatibility (dev-build aware).

Single source of truth shared by the app store (gates what a user may install
or update to) and the plugin loader (gates what may load at startup).

Dev/pre/post/local builds are matched by their *base* release: ``0.13.0.dev0``
is treated as ``0.13.0``. Without this, PEP 440 ranks ``0.13.0.dev0`` *below*
``0.13.0``, so a plugin that requires ``>=0.13.0`` — i.e. the very release you
are developing — would be wrongly judged incompatible and hidden from the store.
"""
from __future__ import annotations

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

import SciQLop

_HOST_DIST = "sciqlop"


def host_version() -> str:
    return SciQLop.__version__


def host_satisfies(spec: str, host: str | None = None) -> bool:
    """Whether a SciQLop version specifier is satisfied by the host.

    An empty/missing or unparseable specifier is treated as compatible (the
    plugin made no claim). The host is compared by its base release so a dev
    build of the targeted version qualifies.
    """
    spec = (spec or "").strip()
    if not spec:
        return True
    try:
        specifier_set = SpecifierSet(spec, prereleases=True)
    except InvalidSpecifier:
        return True
    try:
        base = Version(host or host_version()).base_version
    except InvalidVersion:
        return True
    return specifier_set.contains(base, prereleases=True)


def sciqlop_specifier(python_dependencies: list[str]) -> str:
    """Intersect every SciQLop specifier declared in a plugin's deps.

    Plugins may list SciQLop more than once (e.g. a floor and a ceiling on
    separate lines); the combined set is what the host must satisfy. Non-SciQLop
    and unparseable entries are ignored.
    """
    combined = SpecifierSet("")
    for dep in python_dependencies or []:
        try:
            req = Requirement(dep)
        except InvalidRequirement:
            continue
        if req.name.lower().replace("_", "-").replace(".", "-") == _HOST_DIST:
            combined &= req.specifier
    return str(combined)


def plugin_is_compatible(python_dependencies: list[str], host: str | None = None) -> bool:
    """Whether the host satisfies a plugin's declared SciQLop requirement."""
    return host_satisfies(sciqlop_specifier(python_dependencies), host)
