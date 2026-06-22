"""
Weather Information Tab Layout for Animal Disease Monitoring Dashboard (Dash)
"""

from dash import html, dcc, Input, Output, State
import pandas as pd

from utils.data_loader import load_data_package
from utils.plots import create_weather_charts, create_weather_map

# ── Style constants ───────────────────────────────────────────────────────────

_CARD_COLORS_V  = ["#dbebe8", "#fde2dc", "#fdf3d1"]   # Vientiane
_CARD_COLORS_R  = ["#e8f4fd", "#fde7dc", "#fff6dd"]   # Rotating

_CARD_BASE = {
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
    "marginBottom": "8px",
}

_LABEL_STYLE = {
    "fontSize": "18px",
    "fontWeight": "500",
    "color": "#555",
    "marginBottom": "4px",
    "whiteSpace": "nowrap",
    "overflow": "hidden",
    "textOverflow": "ellipsis",
    "textAlign": "center",
}

_VALUE_STYLE = {
    "fontSize": "28px",
    "fontWeight": "600",
    "color": "#1e4d3b",
    "lineHeight": "1.2",
    "textAlign": "center",
    "display": "block",
    "marginTop": "8px",
}

_SECTION_TITLE = {
    "fontSize": "26px",
    "fontWeight": "600",
    "color": "#264653",
    "marginBottom": "20px",
    "marginTop": "8px",
    "letterSpacing": "0.04em",
    "display": "flex",
}

_PANEL_WRAP = {
    "backgroundColor": "#f7faf9",
    "borderRadius": "14px",
    "padding": "16px",
    "boxShadow": "0 2px 8px rgba(0,0,0,0.06)",
    # "border": "1px solid #dce3e0",
    "display": "flex",
    "flexDirection": "column",
}

_CHART_WRAP = {
    "backgroundColor": "#fff",
    "borderRadius": "14px",
    "padding": "5px",
    "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
    "border": "1px solid #dce3e0",
    "flex": "1",
    "minWidth": "0",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _metric_card(icon: str, label: str, value_id: str, bg: str) -> html.Div:
    return html.Div([
        html.Div(f"{icon} {label}", style=_LABEL_STYLE),
        html.Span("—", id=value_id, style=_VALUE_STYLE),
    ], style={**_CARD_BASE, "backgroundColor": bg})


def _metrics_grid(prefix: str, colors: list) -> html.Div:
    """3×2 grid of weather metric cards for one city."""
    metrics = [
        ("🌡️", "Temperature",     f"wi-{prefix}-temp",     colors[0]),
        ("💧", "Humidity",         f"wi-{prefix}-humidity", colors[0]),
        ("🔽", "Pressure",         f"wi-{prefix}-pressure", colors[1]),
        ("💨", "Wind Speed",       f"wi-{prefix}-wind",     colors[1]),
        ("👁️", "Visibility",      f"wi-{prefix}-vis",      colors[2]),
        ("🌅", "Sunrise / Sunset", f"wi-{prefix}-sun",      colors[2]),
    ]
    row1 = html.Div(
        [_metric_card(*m) for m in metrics[:2]],
        style={"display": "flex", "gap": "8px", "marginBottom": "8px"},
    )
    row2 = html.Div(
        [_metric_card(*m) for m in metrics[2:4]],
        style={"display": "flex", "gap": "8px", "marginBottom": "8px"},
    )
    row3 = html.Div(
        [_metric_card(*m) for m in metrics[4:]],
        style={"display": "flex", "gap": "8px"},
    )
    return html.Div([row1, row2, row3])


def _city_panel(title_id: str, prefix: str, colors: list,
                rotate_btn: bool = False) -> html.Div:
    title_children = [
        html.Span(""),
        html.Span("—", id=title_id,
                  style={"fontWeight": "700", "color": "#264653"}),
    ]
    if rotate_btn:
        title_children.append(html.Button(
            "🔄",
            id="wi-rotate-btn",
            title="Next region",
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
        ))
    return html.Div([
        html.Div(title_children, style=_SECTION_TITLE),
        _metrics_grid(prefix, colors),
    ], style={**_PANEL_WRAP, "flex": "1", "minWidth": "0"})


# ─────────────────────────────────────────────────────────────────────────────
# Layout builder
# ─────────────────────────────────────────────────────────────────────────────

def build_weather_info_tab() -> html.Div:
    """Return the complete layout for the Weather Information tab."""

    # ── Hidden stores & intervals ────────────────────────────────────────
    stores = html.Div([
        dcc.Store(id="wi-rotating-index", data=0),
        dcc.Store(id="wi-rotating-list",  data=[]),
        dcc.Interval(id="wi-region-interval", interval=8_000,  n_intervals=0),
        dcc.Interval(id="wi-load-trigger",
                     interval=60 * 60 * 1000, n_intervals=0, max_intervals=1),
    ], style={"display": "none"})

    # ── Top row: map + Vientiane cards + rotating cards ──────────────────
    map_col = html.Div([
        dcc.Graph(
            id="wi-weather-map",
            config={"displayModeBar": False},
            style={"height": "480px"},
        ),
    ], style={**_CHART_WRAP, "flex": "2", "marginRight": "14px", "maxWidth": "40%"})

    vientiane_panel = html.Div(
        _city_panel("wi-vientiane-title", "vientiane", _CARD_COLORS_V),
        style={"flex": "1", "minWidth": "0", "marginRight": "14px"},
    )

    rotating_panel = html.Div(
        _city_panel("wi-rotating-title", "rotating", _CARD_COLORS_R, rotate_btn=True),
        style={"flex": "1", "minWidth": "0"},
    )

    top_row = html.Div(
        [map_col, vientiane_panel, rotating_panel],
        style={
            "display": "flex",
            "flexDirection": "row",
            "marginBottom": "14px",
        }
    )

    # ── Bottom row: temperature chart + humidity chart ────────────────────
    bottom_row = dcc.Loading(
        id="wi-charts-loading",
        type="circle",
        color="#264653",
        children=html.Div([
            html.Div(
                dcc.Graph(id="wi-temp-chart",
                          config={"displayModeBar": False},
                          style={"height": "340px"}),
                style={**_CHART_WRAP, "marginRight": "14px"},
            ),
            html.Div(
                dcc.Graph(id="wi-humidity-chart",
                          config={"displayModeBar": False},
                          style={"height": "340px"}),
                style=_CHART_WRAP,
            ),
        ], style={"display": "flex", "flexDirection": "row"}),
    )

    return html.Div(
        [stores, top_row, bottom_row],
        className="tab-content",
        style={"padding": "16px 18px 10px"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Callback registration
# ─────────────────────────────────────────────────────────────────────────────

def register_weather_info_callbacks(app) -> None:
    """Register all Dash callbacks needed by the Weather Information tab."""

    # ── 1. Populate rotating region list ─────────────────────────────────
    @app.callback(
        Output("wi-rotating-list", "data"),
        Input("wi-region-interval", "n_intervals"),
        prevent_initial_call=False,
    )
    def wi_populate_regions(_n):
        pkg = load_data_package()
        regions = pkg.weather_data[
            pkg.weather_data["region"] != "Vientiane Capital"
        ]["region"].tolist()
        return regions

    # ── 2. Advance rotating region index ─────────────────────────────────
    @app.callback(
        Output("wi-rotating-index", "data"),
        Input("wi-region-interval", "n_intervals"),
        Input("wi-rotate-btn",      "n_clicks"),
        State("wi-rotating-index",  "data"),
        State("wi-rotating-list",   "data"),
        prevent_initial_call=True,
    )
    def wi_advance_region(_interval, _clicks, current_idx, region_list):
        if not region_list:
            return 0
        return (current_idx + 1) % len(region_list)

    # ── 3. Update weather metric cards ───────────────────────────────────
    @app.callback(
        # Vientiane
        Output("wi-vientiane-title",    "children"),
        Output("wi-vientiane-temp",     "children"),
        Output("wi-vientiane-humidity", "children"),
        Output("wi-vientiane-pressure", "children"),
        Output("wi-vientiane-wind",     "children"),
        Output("wi-vientiane-vis",      "children"),
        Output("wi-vientiane-sun",      "children"),
        # Rotating
        Output("wi-rotating-title",    "children"),
        Output("wi-rotating-temp",     "children"),
        Output("wi-rotating-humidity", "children"),
        Output("wi-rotating-pressure", "children"),
        Output("wi-rotating-wind",     "children"),
        Output("wi-rotating-vis",      "children"),
        Output("wi-rotating-sun",      "children"),
        Input("wi-rotating-index", "data"),
        State("wi-rotating-list",  "data"),
        prevent_initial_call=False,
    )
    def wi_update_cards(current_idx, region_list):
        pkg = load_data_package()
        weather_data = pkg.weather_data

        def _fmt_sun(row):
            try:
                sr = pd.to_datetime(row["sunrise"]).strftime("%H:%M")
                ss = pd.to_datetime(row["sunset"]).strftime("%H:%M")
                return f"{sr} / {ss}"
            except Exception:
                return "N/A"

        def _extract(row):
            if row["region"] == "Vientiane Capital":
                name = f"🏛️ {row["region"]}"
            else:
                name = f"📍 {row["region"]}"
            return (
                name,
                f"{row['temperature']:.1f} °C",
                f"{row['humidity']:.0f} %",
                f"{row['pressure']:.0f} hPa",
                f"{row['wind_speed']:.1f} m/s",
                f"{row['visibility']:.1f} km",
                _fmt_sun(row),
            )

        v_rows = weather_data[weather_data["region"] == "Vientiane Capital"]
        v_vals = _extract(v_rows.iloc[0]) if not v_rows.empty \
            else ("Vientiane Capital", "—", "—", "—", "—", "—", "—")

        other = weather_data[weather_data["region"] != "Vientiane Capital"]
        if other.empty or not region_list:
            r_vals = ("—", "—", "—", "—", "—", "—", "—")
        else:
            name   = region_list[current_idx % len(region_list)]
            r_rows = weather_data[weather_data["region"] == name]
            r_vals = _extract(r_rows.iloc[0]) if not r_rows.empty \
                else (name, "—", "—", "—", "—", "—", "—")

        return (*v_vals, *r_vals)

    # ── 4. Weather map + charts (load once) ──────────────────────────────
    @app.callback(
        Output("wi-weather-map",    "figure"),
        Output("wi-temp-chart",     "figure"),
        Output("wi-humidity-chart", "figure"),
        Input("wi-load-trigger",    "n_intervals"),
        prevent_initial_call=False,
    )
    def wi_populate_charts(_n):
        try:
            pkg          = load_data_package()
            weather_data = pkg.weather_data

            fig_map              = create_weather_map(weather_data)
            temp_chart, hum_chart = create_weather_charts(weather_data)

            return fig_map, temp_chart, hum_chart

        except Exception as e:
            import traceback
            traceback.print_exc()
            empty = _empty_figure(f"Error: {e}")
            return empty, empty, empty


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _empty_figure(message: str):
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_annotation(
        text=message, xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=16, color="#888"),
    )
    fig.update_layout(
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        margin=dict(l=20, r=20, t=20, b=20),
    )
    return fig
