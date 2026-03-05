"""TUI launcher -- tries new TUI, falls back to old.

Called by ``dgc_cli.cmd_tui()`` or directly.  The new architecture lives
in ``dharma_swarm.tui`` (package); the old monolithic TUI lives in
``dharma_swarm.tui`` (module, renamed to ``tui_legacy`` once migration is
complete).  During the transition period both coexist.
"""

from __future__ import annotations

import sys


def launch_tui() -> None:
    """Launch the DGC TUI (new architecture first, fallback to old).

    The new Textual TUI in ``dharma_swarm/tui/`` is attempted first.
    If it fails for any reason (missing widgets, import errors, Textual
    version mismatch, etc.) we fall back to the proven old monolithic
    ``tui.py`` implementation.

    Raises:
        SystemExit: If both TUI implementations fail.
    """
    try:
        from dharma_swarm.tui import run

        run()
    except Exception as exc:
        print(
            f"New TUI failed ({exc}), falling back to old TUI...",
            file=sys.stderr,
        )
        try:
            from dharma_swarm.tui_legacy import DGCApp  # type: ignore[import-untyped]

            DGCApp().run()
        except ImportError:
            # tui_legacy doesn't exist yet -- old tui.py hasn't been renamed
            try:
                # The old module may still be importable if tui/ package
                # shadow hasn't fully taken over.  Try the run_tui entry.
                from dharma_swarm import tui as _old_tui  # type: ignore[attr-defined]

                if hasattr(_old_tui, "run_tui"):
                    _old_tui.run_tui()
                elif hasattr(_old_tui, "DGCApp"):
                    _old_tui.DGCApp().run()
                else:
                    raise AttributeError("No run_tui or DGCApp in old tui module")
            except Exception as exc2:
                print(f"Old TUI also failed: {exc2}", file=sys.stderr)
                sys.exit(1)
        except Exception as exc2:
            print(f"Old TUI also failed: {exc2}", file=sys.stderr)
            sys.exit(1)
