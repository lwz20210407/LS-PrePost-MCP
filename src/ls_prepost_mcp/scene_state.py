"""Managed custom-fringe coverage: never animate unknown or mixed physical fields."""


def fringe_coverage(previous, definition, state, job_directory):
    same = previous and previous.get("status") == "verified" and previous.get("definition") == definition
    frames = dict(previous.get("frames", {})) if same else {}
    frames[str(state)] = job_directory
    return dict(status="verified", definition=definition, frames=frames)


def require_movie_field_coverage(metadata, last):
    field = metadata.get("managed_fringe")
    if field is None:
        return None
    if field.get("status") != "verified":
        raise ValueError(
            "Custom fringe coverage is uncertain; render a consistent field sequence or reopen the model"
        )
    missing = [state for state in range(1, last + 1) if str(state) not in field.get("frames", {})]
    if missing:
        raise ValueError("Custom fringe is not defined for all movie states: " + str(missing[:20]))
    return dict(
        definition=field["definition"],
        frames={str(state): field["frames"][str(state)] for state in range(1, last + 1)},
        coverage_verified=True,
        color_range=field.get("color_range"),
    )
