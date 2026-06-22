"""
Disease Statistics Tab Layout for Animal Disease Monitoring Dashboard (Dash)
============================================================================
Translates the Streamlit DiseaseStatsDashboard into Dash/Plotly.

Layout
------
  ┌─────────────────────────────────────────────────────────┐
  │  LEFT (map, taller)   │  RIGHT                           │
  │                       │  ┌──────┬──────┬──────┐          │
  │  create_disease_map   │  │Cases │Viral │Region│  metrics │
  │                       │  └──────┴──────┴──────┘          │
  │                       │  plot_disease_outbreak_overtime   │
  │                       │  plot_key_disease_distribution    │
  └─────────────────────────────────────────────────────────┘

Usage in app.py
---------------
    from disease_stats_layout import build_disease_stats_tab, register_disease_stats_callbacks

    dcc.Tab(
        label='Disease Statistics',
        value='disease-statistics',
        className='custom-tab',
        selected_className='tab--selected',
        children=build_disease_stats_tab(),
    )

    register_disease_stats_callbacks(app)
"""

from dash import html, dcc, Input, Output
import pandas as pd

from utils.data_loader import load_data_package, load_key_diseases_data
from utils.plots import (
    create_disease_map,
    plot_disease_outbreak_overtime,
    calculate_disease_metrics,
    plot_key_disease_distribution,
)

# ── Disease filter (used for the key-disease distribution chart) ────────────
KEY_DISEASES: list = ["HPAI-P", "ND", "IBD", "MG"]

# ── Shared style helpers ──────────────────────────────────────────────────────

_CARD_COLORS = ["#fff", "#fff", "#fff"]

_CARD_BASE = {
    "borderRadius": "10px",
    "padding": "14px 16px",
    "flex": "1",
    "minWidth": "0",
    "boxShadow": "0 2px 6px rgba(0,0,0,0.07)",
    "transition": "transform 0.2s ease, box-shadow 0.2s ease",
    "cursor": "default",
    "minHeight": "100px",
    "display": "flex",
    "flexDirection": "column",
    "justifyContent": "center",
    "alignItems": "center",
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
}


# ── Metric KPI card ───────────────────────────────────────────────────────────

def _metric_card(label, value_id, bg):
    return html.Div([
        html.Div(label, style=_LABEL_STYLE),
        html.Span("—", id=value_id, style=_VALUE_STYLE),
    ], style={**_CARD_BASE, "backgroundColor": bg})


# ─────────────────────────────────────────────────────────────────────────────
# Layout builder
# ─────────────────────────────────────────────────────────────────────────────

def build_disease_stats_tab() -> html.Div:
    """Return the complete layout for the Disease Statistics tab."""

    # ── Trigger (fires once on mount to populate all charts/metrics) ─────
    stores = html.Div([
        dcc.Interval(id="ds-load-trigger", interval=60 * 60 * 1000,
                     n_intervals=0, max_intervals=1),
    ], style={"display": "none"})

    # ── Metric cards row ─────────────────────────────────────────────────
    metrics_row = html.Div([
        _metric_card("Total Reported Cases",  "ds-metric-cases",  _CARD_COLORS[0]),
        _metric_card("Most Viral Disease",    "ds-metric-viral",  _CARD_COLORS[1]),
        _metric_card("Most Affected Region",  "ds-metric-region", _CARD_COLORS[2]),
    ], style={"display": "flex", "gap": "12px", "marginBottom": "12px"})

    # ── Right column: metrics + outbreak chart + key disease chart ───────
    right_col = html.Div([
        metrics_row,
        html.Div(
            dcc.Graph(
                id="ds-outbreak-chart",
                config={"displayModeBar": False},
                style={"height": "340px"},
            ),
            style={
                "backgroundColor": "#fff",
                "borderRadius": "14px",
                "padding": "10px",
                "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
                "border": "1px solid #dce3e0",
                "marginBottom": "14px",
            }
        ),
        html.Div(
            dcc.Graph(
                id="ds-key-disease-chart",
                config={"displayModeBar": False},
                style={"height": "350px"},
            ),
            style={
                "backgroundColor": "#fff",
                "borderRadius": "14px",
                "padding": "10px",
                "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
                "border": "1px solid #dce3e0",
            }
        ),
    ], style={"flex": "1", "minWidth": "0", "display": "flex", "flexDirection": "column"})

    # ── Left column: folium disease map embedded via iframe (taller) ─────
    left_col = html.Div([
        html.Iframe(
            id="ds-disease-map",
            srcDoc="",          # populated by callback
            style={
                "width": "100%",
                "height": "calc(100vh - 260px)",
                "border": "none",
                "borderRadius": "10px",
            },
        ),
    ], style={
        "flex": "1",
        "minWidth": "0",
        "backgroundColor": "#fff",
        "borderRadius": "14px",
        "padding": "10px",
        "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
        "border": "1px solid #dce3e0",
        "marginRight": "14px",
    })

    # ── Main content row ─────────────────────────────────────────────────
    main_row = dcc.Loading(
        id="ds-loading",
        type="circle",
        color="#264653",
        children=html.Div(
            [left_col, right_col],
            style={"display": "flex", "flexDirection": "row"}
        ),
    )

    return html.Div(
        [stores, main_row],
        className="tab-content",
        style={"padding": "16px 18px 10px"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Callback registration
# ─────────────────────────────────────────────────────────────────────────────

def register_disease_stats_callbacks(app) -> None:
    """Register all Dash callbacks needed by the Disease Statistics tab."""

    @app.callback(
        Output("ds-disease-map",       "srcDoc"),
        Output("ds-outbreak-chart",    "figure"),
        Output("ds-key-disease-chart", "figure"),
        Output("ds-metric-cases",      "children"),
        Output("ds-metric-viral",      "children"),
        Output("ds-metric-region",     "children"),
        Input("ds-load-trigger",       "n_intervals"),
        prevent_initial_call=False,
    )
    def ds_populate_charts(_n):
        try:
            import os
            os.makedirs("assets/temp", exist_ok=True)
            pkg      = load_data_package()
            database = pkg.database
            geo_data = pkg.geo_data

            # Merge for map
            map_data = pd.merge(database, geo_data, on="location", how="left")

            folium_map   = create_disease_map(map_data)
            map_html     = folium_map.get_root().render()
            fig_outbreak = plot_disease_outbreak_overtime(database)

            # Key disease distribution chart (same data scope as Key Diseases tab)
            raw_kd = load_key_diseases_data()
            kd_data = raw_kd[raw_kd["disease_code"].isin(KEY_DISEASES)] if not raw_kd.empty else raw_kd
            if kd_data.empty:
                fig_key_disease = _empty_figure(f"No records for: {', '.join(KEY_DISEASES)}")
            else:
                fig_key_disease = plot_key_disease_distribution(kd_data)

            metrics = calculate_disease_metrics(database)
            total_cases  = f"{metrics.get('total_cases', 0):,}"
            most_viral   = str(metrics.get('most_viral',   "N/A"))
            most_affected = str(metrics.get('most_affected', "N/A"))

            return (
                map_html, fig_outbreak, fig_key_disease,
                total_cases, most_viral, most_affected,
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            error_html = f"<p style='color:red;padding:20px'>Error rendering map: {e}</p>"
            err_fig = _empty_figure(f"Error: {e}")
            return error_html, err_fig, err_fig, "—", "—", "—"


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