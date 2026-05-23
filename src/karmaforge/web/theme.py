"""Brutalist Data Lab theme for KarmaForge Gradio app — warm paper edition."""

import gradio as gr


def create_theme() -> gr.Theme:
    return gr.themes.Soft(
        primary_hue="amber",
        neutral_hue="stone",
        font=gr.themes.GoogleFont("Space Mono"),
        font_mono=gr.themes.GoogleFont("Space Mono"),
    ).set(
        body_background_fill="#faf7f2",
        body_background_fill_dark="#faf7f2",
        block_background_fill="#f5f0e8",
        block_background_fill_dark="#f5f0e8",
        block_border_color="#e0d5c5",
        block_border_color_dark="#e0d5c5",
        block_border_width="1px",
        button_primary_background_fill="#d97706",
        button_primary_background_fill_hover="#b85c05",
        button_primary_text_color="#faf7f2",
        button_secondary_background_fill="#faf7f2",
        button_secondary_background_fill_hover="#fef3e0",
        button_secondary_text_color="#d97706",
        button_secondary_border_color="#d97706",
        input_background_fill="#fdfaf6",
        input_background_fill_dark="#fdfaf6",
        input_border_color="#e0d5c5",
        input_border_color_dark="#e0d5c5",
        body_text_color="#3d3025",
        body_text_color_dark="#3d3025",
        body_text_color_subdued="#8b7355",
        body_text_color_subdued_dark="#8b7355",
        link_text_color="#d97706",
        link_text_color_dark="#d97706",
        color_accent="#d97706",
        color_accent_soft="#fef3e0",
        border_color_primary="#d97706",
        border_color_primary_dark="#d97706",
    )
