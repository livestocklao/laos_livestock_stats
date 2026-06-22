"""
Overview Tab Layout for Animal Disease Monitoring Dashboard (Dash)
"""

from dash import html, dcc, Input, Output, State
import pandas as pd
import time

from utils.data_loader import load_overview_data
from utils.plots import quick_overview_table, display_animal_stats
import plotly.graph_objects as go



_VIENTIANE_COLORS = ["#dbebe8", "#fde2dc", "#fdf3d1"]   # row-1, row-2 cols
_ROTATING_COLORS  = ["#e8f4fd", "#fde7dc", "#fff6dd"]

_CARD_STYLE_BASE = {
    "borderRadius": "10px",
    "padding": "14px 16px",
    "flex": "1",
    "minWidth": "0",
    "boxShadow": "0 2px 6px rgba(0,0,0,0.07)",
    "transition": "transform 0.2s ease, box-shadow 0.2s ease",
    "cursor": "default",
    "minHeight": "120px",
    "display": "flex",
    "flexDirection": "column",
    "justifyContent": "center",
    "alignItems": "center",
    "marginBottom": "10px",
}

_LABEL_STYLE = {
    "fontSize": "20px",
    "fontWeight": "500",
    "color": "#555",
    "marginBottom": "4px",
    "whiteSpace": "nowrap",
    "overflow": "hidden",
    "textOverflow": "ellipsis",
    "textAlign": "center",
}

_VALUE_STYLE = {
    "fontSize": "32px",
    "fontWeight": "500",
    "color": "#1e4d3b",
    "lineHeight": "1.2",
    "textAlign": "center",
    "display": "block",
    "marginTop": "10px",
}

_SECTION_TITLE_STYLE = {
    "fontSize": "26px",
    "fontWeight": "600",
    "color": "#264653",
    "marginBottom": "18px",
    "marginTop": "8px",
    "letterSpacing": "0.04em",
}

# ---------------------------------------------------------------------------
# Helper: single KPI card
# ---------------------------------------------------------------------------
def _kpi_card(icon: str, label: str, value_id: str, bg: str) -> html.Div:
    """One metric card with an icon, label and a dynamic value span."""
    style = {**_CARD_STYLE_BASE, "backgroundColor": bg}
    return html.Div([
        html.Div(f"{icon} {label}", style=_LABEL_STYLE),
        html.Span("—", id=value_id, style=_VALUE_STYLE),
    ], style=style)


# ---------------------------------------------------------------------------
# Weather cards section builder
# ---------------------------------------------------------------------------
def _weather_cards_row(prefix: str, title_id: str, colors: list, rotate_btn: bool) -> html.Div:
    """
    Build a 3+3 grid of weather KPI cards for one city.

    prefix       : e.g. "vientiane" or "rotating"
    title_id     : id for the city name heading
    colors       : list of 3 bg colours (applied per column across both rows)
    rotate_btn   : show the 🔄 rotate button next to the title
    """
    metrics = [
        ("🌡️", "Temperature",    f"{prefix}-temp",     colors[0]),
        ("💧", "Humidity",        f"{prefix}-humidity", colors[1]),
        ("🔽", "Pressure",        f"{prefix}-pressure", colors[2]),
        ("💨", "Wind Speed",      f"{prefix}-wind",     colors[0]),
        ("👁️", "Visibility",     f"{prefix}-vis",      colors[1]),
        ("🌅", "Sunrise / Sunset",f"{prefix}-sun",      colors[2]),
    ]

    # Row 1: first 3 cards
    row1 = html.Div(
        [_kpi_card(m[0], m[1], m[2], m[3]) for m in metrics[:3]],
        style={"display": "flex", "gap": "10px", "marginBottom": "10px"}
    )
    # Row 2: last 3 cards
    row2 = html.Div(
        [_kpi_card(m[0], m[1], m[2], m[3]) for m in metrics[3:]],
        style={"display": "flex", "gap": "10px"}
    )

    # Title row
    title_children = [
        html.Span("", style={"marginRight": "4px"}),
        html.Span("—", id=title_id, style={"fontWeight": "700", "color": "#264653"}),
    ]
    if rotate_btn:
        title_children.append(
            html.Button(
                "🔄",
                id="rotate-region-btn",
                title="Click to advance to next region",
                style={
                    "marginLeft": "auto",
                    "marginRight": "0px",
                    "background": "none",
                    "border": "0px solid #ccc",
                    "borderRadius": "20%",
                    "cursor": "pointer",
                    "fontSize": "24px",
                    "lineHeight": "1",
                    "padding": "2px 6px",
                    "verticalAlign": "middle",
                    "color": "#555",
                }
            )
        )

    title_row = html.Div(title_children, style={**_SECTION_TITLE_STYLE, "display": "flex", "alignItems": "center"})

    return html.Div([title_row, row1, row2], style={"flex": "1", "minWidth": "0"})


# ---------------------------------------------------------------------------
# Full overview tab layout
# ---------------------------------------------------------------------------
def build_overview_tab() -> html.Div:
    """
    Return the complete layout for the Overview tab.
    Wire up callbacks separately with register_overview_callbacks().
    """
    # ── Weather section ──────────────────────────────────────────────────
    weather_section = html.Div([
        # Vientiane side
        _weather_cards_row(
            prefix="vientiane",
            title_id="vientiane-title",
            colors=_VIENTIANE_COLORS,
            rotate_btn=False,
        ),
        # Divider
        html.Div(style={
            "width": "1px",
            "backgroundColor": "#dce3e0",
            "margin": "0 18px",
            "alignSelf": "stretch",
        }),
        # Rotating city side
        _weather_cards_row(
            prefix="rotating",
            title_id="rotating-title",
            colors=_ROTATING_COLORS,
            rotate_btn=True,
        ),
    ], style={
        "display": "flex",
        "flexDirection": "row",
        "gap": "0",
        "backgroundColor": "#f7faf9",
        "borderRadius": "14px",
        "padding": "18px 22px",
        "boxShadow": "0 2px 8px rgba(0,0,0,0.06)",
        # "border": "1px solid #dce3e0",
        "min-height": "260px",
        "margin": "10px 1px 15px"  # top, left/right, bottom
    })

    # ── Plots section ────────────────────────────────────────────────────
    plots_section = html.Div([
        # Left: quick overview chart
        html.Div([
            dcc.Graph(
                id="overview-quick-chart",
                config={"displayModeBar": False},
                # style={"height": "380px", "overflow": "hidden"},
            )
        ], style={
            "flex": "2",
            "backgroundColor": "#fff",
            "borderRadius": "14px",
            "padding": "5px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
            "border": "1px solid #dce3e0",
            "marginRight": "14px",
        }),

        # Right: animal stats + navigation
        html.Div([
            # Animal selector row: prev btn | image | name | next btn
            html.Div([
                html.Button(
                    "⬅",
                    id="animal-prev-btn",
                    style=_nav_btn_style(),
                ),
                html.Img(
                    id="animal-image",
                    src="",
                    style={"height": "80px", "objectFit": "contain", "margin": "0 18px"},
                ),
                html.Span(
                    "—",
                    id="animal-name-display",
                    style={"fontWeight": "700", "fontSize": "26px", "color": "#264653", "flex": "1"},
                ),
                html.Button(
                    "➡",
                    id="animal-next-btn",
                    style=_nav_btn_style(),
                ),
            ], style={
                "display": "flex",
                "alignItems": "center",
                "marginBottom": "18px",
                "padding": "0 10px",
            }),
            dcc.Graph(
                id="animal-stats-chart",
                config={"displayModeBar": False},
                style={"height": "340px"},
            ),
        ], style={
            "flex": "1",
            "backgroundColor": "#fff",
            "borderRadius": "14px",
            "padding": "10px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
            "border": "1px solid #dce3e0",
            "display": "flex",
            "flexDirection": "column",
        }),
    ], style={"display": "flex", "flexDirection": "row"})

    # ── Hidden stores for rotating state ─────────────────────────────────
    stores = html.Div([
        # NEW: Shared data store for weather and disease stats
        dcc.Store(id="shared-data-store", data={}),
        dcc.Store(id="rotating-region-index", data=0),   # index into non-Vientiane list
        dcc.Store(id="rotating-region-list",  data=[]),
        dcc.Store(id="current-animal-index",  data=1),   # 1-based (matches ANIMAL_MAP)
        # Auto-advance interval for region (every 10 seconds)
        dcc.Interval(
            id="region-rotation-interval",
            interval=10_000,   # 10 seconds
            n_intervals=0,
        ),
        # NEW: Auto-advance interval for animal (every 8 seconds)
        dcc.Interval(
            id="animal-rotation-interval",
            interval=8_000,    # 8 seconds for animal rotation
            n_intervals=0,
        ),
    ], style={"display": "none"})

    return html.Div([
        stores,
        weather_section,
        plots_section,
    ], className="tab-content", style={"padding": "6px 18px 10px"})


def _nav_btn_style():
    return {
        "background": "#264653",
        "color": "#fff",
        "border": "none",
        "borderRadius": "8px",
        "padding": "6px 14px",
        "fontSize": "22px",
        "cursor": "pointer",
        "flexShrink": "0",
    }


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------
ANIMAL_MAP = {
    1: "HORSE",
    2: "CATTLE",
    3: "BUFFALO",
    4: "GOAT",
    5: "PIG",
    6: "DOG",
    7: "POULTRY",
    8: "FISH",
}
TOTAL_ANIMALS = len(ANIMAL_MAP)


def register_overview_callbacks(app):
    """
    Register all Dash callbacks needed by the overview tab.

    Parameters
    ----------
    app                     : Dash application instance
    """

    # ── 1. Load data once and store in shared store ──────────────────────
    @app.callback(
        Output("shared-data-store", "data"),
        Input("region-rotation-interval", "n_intervals"),
        prevent_initial_call=False,
    )
    def load_shared_data(_n):
        """Load disease stats and weather data once and cache in store."""
        disease_stats, weather_data = load_overview_data()
        return {
            "disease_stats": disease_stats.to_dict('records'),
            "weather_data": weather_data.to_dict('records')
        }

    # ── 2. Populate rotating-region-list from shared data ────────────────────
    @app.callback(
        Output("rotating-region-list", "data"),
        Input("shared-data-store", "data"),
        prevent_initial_call=False,
    )
    def populate_region_list(shared_data):
        if not shared_data:
            return []
        weather_data = pd.DataFrame(shared_data["weather_data"])
        regions = weather_data[weather_data["region"] != "Vientiane Capital"]["region"].tolist()
        return regions

    # ── 3. Advance region index (auto-rotation OR manual button) ─────────
    @app.callback(
        Output("rotating-region-index", "data"),
        Input("region-rotation-interval", "n_intervals"),
        Input("rotate-region-btn", "n_clicks"),
        State("rotating-region-index", "data"),
        State("rotating-region-list", "data"),
        prevent_initial_call=True,
    )
    def advance_region(_interval, _btn_clicks, current_idx, region_list):
        if not region_list:
            return 0
        return (current_idx + 1) % len(region_list)

    # ── 4. Update weather cards (Vientiane + Rotating) from shared data ───
    @app.callback(
        # Vientiane outputs
        Output("vientiane-title",    "children"),
        Output("vientiane-temp",     "children"),
        Output("vientiane-humidity", "children"),
        Output("vientiane-pressure", "children"),
        Output("vientiane-wind",     "children"),
        Output("vientiane-vis",      "children"),
        Output("vientiane-sun",      "children"),
        # Rotating outputs
        Output("rotating-title",    "children"),
        Output("rotating-temp",     "children"),
        Output("rotating-humidity", "children"),
        Output("rotating-pressure", "children"),
        Output("rotating-wind",     "children"),
        Output("rotating-vis",      "children"),
        Output("rotating-sun",      "children"),
        # Triggers
        Input("shared-data-store", "data"),
        Input("rotating-region-index", "data"),
        State("rotating-region-list",  "data"),
        prevent_initial_call=False,
    )
    def update_weather_cards(shared_data, current_idx, region_list):
        # Return default values if no data
        if not shared_data:
            return ("—", "—", "—", "—", "—", "—", "—") * 2

        weather_data = pd.DataFrame(shared_data["weather_data"])

        def _fmt_sun(row):
            try:
                sr = pd.to_datetime(row["sunrise"]).strftime("%H:%M")
                ss = pd.to_datetime(row["sunset"]).strftime("%H:%M")
                return f"{sr} / {ss}"
            except Exception:
                return "N/A"

        def _extract(row):
            return (
                row["region"],
                f"{row['temperature']:.1f} °C",
                f"{row['humidity']:.0f} %",
                f"{row['pressure']:.0f} hPa",
                f"{row['wind_speed']:.1f} m/s",
                f"{row['visibility']:.1f} km",
                _fmt_sun(row),
            )

        # Vientiane (always fixed)
        v_rows = weather_data[weather_data["region"] == "Vientiane Capital"]
        if v_rows.empty:
            vt, vtemp, vhum, vpres, vwind, vvis, vsun = ("Vientiane Capital", "—", "—", "—", "—", "—", "—")
        else:
            vt, vtemp, vhum, vpres, vwind, vvis, vsun = _extract(v_rows.iloc[0])

        # Rotating region
        other = weather_data[weather_data["region"] != "Vientiane Capital"]
        if other.empty or not region_list:
            rt, rtemp, rhum, rpres, rwind, rvis, rsun = ("—", "—", "—", "—", "—", "—", "—")
        else:
            idx = current_idx % len(region_list)
            region_name = region_list[idx]
            r_rows = weather_data[weather_data["region"] == region_name]
            if r_rows.empty:
                rt, rtemp, rhum, rpres, rwind, rvis, rsun = (region_name, "—", "—", "—", "—", "—", "—")
            else:
                rt, rtemp, rhum, rpres, rwind, rvis, rsun = _extract(r_rows.iloc[0])
        
        vt = f"🏛️ {vt}"  # add location pin emoji to title
        rt = f"📍 {rt}"  # add location pin emoji to title

        return (
            vt, vtemp, vhum, vpres, vwind, vvis, vsun,
            rt, rtemp, rhum, rpres, rwind, rvis, rsun,
        )

    # ── 5. Quick overview chart from shared data ──────────────────────────
    @app.callback(
        Output("overview-quick-chart", "figure"),
        Input("shared-data-store", "data"),
        prevent_initial_call=False,
    )
    def update_quick_chart(shared_data):
        if not shared_data:
            # Return empty figure or placeholder
            import plotly.graph_objects as go
            return go.Figure()
        disease_stats = pd.DataFrame(shared_data["disease_stats"])
        return quick_overview_table(disease_stats)

    # ── 6. Animal navigation: prev / next buttons AND auto-rotation ──────
    @app.callback(
        Output("current-animal-index", "data"),
        Input("animal-prev-btn", "n_clicks"),
        Input("animal-next-btn", "n_clicks"),
        Input("animal-rotation-interval", "n_intervals"),  # NEW: auto-rotation trigger
        State("current-animal-index", "data"),
        prevent_initial_call=True,
    )
    def navigate_animal(prev_clicks, next_clicks, _interval, current_idx):
        from dash import ctx
        trigger = ctx.triggered_id
        
        # Manual navigation via buttons
        if trigger == "animal-prev-btn":
            return ((current_idx - 2) % TOTAL_ANIMALS) + 1
        elif trigger == "animal-next-btn":
            return (current_idx % TOTAL_ANIMALS) + 1
        # Auto-rotation via interval
        elif trigger == "animal-rotation-interval":
            return (current_idx % TOTAL_ANIMALS) + 1
        
        return current_idx

    # ── 7. Update animal display (image + name + chart) from shared data ──
    @app.callback(
        Output("animal-image",        "src"),
        Output("animal-name-display", "children"),
        Output("animal-stats-chart",  "figure"),
        Input("shared-data-store", "data"),
        Input("current-animal-index", "data"),
        prevent_initial_call=False,
    )
    def update_animal_section(shared_data, animal_idx):
        if not shared_data:
            # Return placeholder values
            animal_name = ANIMAL_MAP.get(animal_idx, "CATTLE")
            return f"assets/icons/{animal_idx}.png", animal_name.capitalize(), go.Figure()
        
        disease_stats = pd.DataFrame(shared_data["disease_stats"])
        animal_name = ANIMAL_MAP.get(animal_idx, "CATTLE")
        image_src   = f"assets/icons/{animal_idx}.png"
        fig         = display_animal_stats(disease_stats, animal=animal_name)
        return image_src, animal_name.capitalize(), fig