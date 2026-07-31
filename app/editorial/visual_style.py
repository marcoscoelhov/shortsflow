from __future__ import annotations

from typing import Any


VISUAL_STYLE_PROFILE_VERSION = "visual-style-v1"
VISUAL_STYLE_PROFILES: dict[str, dict[str, Any]] = {
    "analog_documentary": {
        "id": "analog_documentary",
        "version": VISUAL_STYLE_PROFILE_VERSION,
        "image_prompt_directive": (
            "analog documentary photography, natural available light, tactile 35mm film grain, "
            "restrained earth tones, candid physical detail"
        ),
        "finishing": {"contrast": 1.07, "saturation": 0.96, "accent_treatment": "warm_edge"},
    },
    "scientific_watercolor": {
        "id": "scientific_watercolor",
        "version": VISUAL_STYLE_PROFILE_VERSION,
        "image_prompt_directive": (
            "scientific watercolor illustration on textured paper, translucent pigment washes, "
            "precise natural forms, restrained blue and ochre palette"
        ),
        "finishing": {"contrast": 1.03, "saturation": 0.9, "accent_treatment": "paper_wash"},
    },
    "high_contrast_comic": {
        "id": "high_contrast_comic",
        "version": VISUAL_STYLE_PROFILE_VERSION,
        "image_prompt_directive": (
            "high-contrast editorial comic illustration, bold ink contours, dramatic shadow shapes, "
            "limited red cream and black palette, one continuous full-frame scene rather than comic panels"
        ),
        "finishing": {"contrast": 1.16, "saturation": 1.04, "accent_treatment": "ink_strike"},
    },
    "editorial_diorama": {
        "id": "editorial_diorama",
        "version": VISUAL_STYLE_PROFILE_VERSION,
        "image_prompt_directive": (
            "editorial miniature diorama photography, handcrafted physical materials, macro lens, "
            "shallow depth of field, controlled studio light"
        ),
        "finishing": {"contrast": 1.09, "saturation": 0.94, "accent_treatment": "miniature_spotlight"},
    },
}

NEGATIVE_SPACE_DIRECTIVE = (
    "reserve clean negative space in the upper and lower frame for editorial composition, "
    "keep the main subject inside the central safe area"
)


def resolve_visual_style_profile(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        profile_id = str(value.get("id") or value.get("profile_id") or "").strip()
    else:
        profile_id = str(value or "").strip()
    if not profile_id:
        return None
    selected = VISUAL_STYLE_PROFILES.get(profile_id)
    if selected is None:
        raise ValueError(f"unsupported visual_style_profile: {profile_id}")
    return {
        "id": selected["id"],
        "version": selected["version"],
        "image_prompt_directive": selected["image_prompt_directive"],
        "finishing": dict(selected["finishing"]),
    }


def public_visual_style_profile(value: Any) -> dict[str, Any] | None:
    profile = resolve_visual_style_profile(value)
    if profile is None:
        return None
    return {
        "id": profile["id"],
        "version": profile["version"],
        "finishing": profile["finishing"],
    }
