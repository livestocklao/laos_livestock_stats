"""
Key Diseases Tab Layout for Animal Disease Monitoring Dashboard (Dash)
"""
from dash import html, dcc, Input, Output
import pandas as pd
from utils.data_loader import load_key_diseases_data
from utils.plots import (
    key_disease_reports_overtime,
    key_disease_kde_distribution,
    key_disease_wrt_location,
    plot_disease_code_map,
)
# ── Disease filter ────────────────────────────────────────────────────────────
KEY_DISEASES: list = ["HPAI-P", "ND", "IBD", "MG"]
# ── Shared chart card wrapper style ──────────────────────────────────────────
def _chart_card(graph_id: str, height: int = 410) -> html.Div:
    return html.Div(
        dcc.Graph(
            id=graph_id,
            config={"displayModeBar": False},
            style={"height": f"{height}px"},
        ),
        style={
            "flex": "1",
            "backgroundColor": "#fff",
            "borderRadius": "14px",
            "padding": "10px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
            "border": "1px solid #dce3e0",
            "minWidth": "0",      # prevents flex children from overflowing
        }
    )
# ─────────────────────────────────────────────────────────────────────────────
# Layout builder
# ─────────────────────────────────────────────────────────────────────────────
def build_key_diseases_tab() -> html.Div:
    """
    Return the complete layout for the Key Diseases tab.
    Wire up callbacks separately with register_key_diseases_callbacks().
    """
    # Row 1 — reports-over-time + KDE distribution
    row_1 = html.Div([
        _chart_card("kd-overtime-chart"),
        _chart_card("kd-kde-chart"),
    ], style={
        "display": "flex",
        "flexDirection": "row",
        "gap": "14px",
        "marginBottom": "14px",
    })
    # Row 2 — location breakdown + disease code map
    row_2 = html.Div([
        _chart_card("kd-location-chart", height=380),
        _chart_card("kd-codemap-chart",  height=380),
    ], style={
        "display": "flex",
        "flexDirection": "row",
        "gap": "14px",
    })
    # Loading spinner wraps both rows so the user sees feedback on first load
    content = dcc.Loading(
        id="kd-loading",
        type="circle",
        color="#264653",
        children=html.Div([row_1, row_2]),
    )
    # Trigger: fires once on tab mount to populate all charts
    trigger = dcc.Interval(
        id="kd-load-trigger",
        interval=60 * 60 * 1000,   # effectively once; data refreshes hourly
        n_intervals=0,
        max_intervals=1,            # fire only on first render
    )
    return html.Div(
        [trigger, content],
        className="tab-content",
        style={"padding": "16px 18px 10px"},
    )
# ─────────────────────────────────────────────────────────────────────────────
# Callback registration
# ─────────────────────────────────────────────────────────────────────────────
def register_key_diseases_callbacks(app) -> None:
    """
    Register all Dash callbacks needed by the Key Diseases tab.
    Parameters
    ----------
    app : Dash application instance
    """
    @app.callback(
        Output("kd-overtime-chart",     "figure"),
        Output("kd-kde-chart",          "figure"),
        Output("kd-location-chart",     "figure"),
        Output("kd-codemap-chart",      "figure"),
        Input("kd-load-trigger",        "n_intervals"),
        prevent_initial_call=False,
    )
    def populate_key_diseases_charts(_n):
        # Load and filter data
        raw = load_key_diseases_data()
        if raw.empty:
            empty_fig = _empty_figure("No data available")
            return empty_fig, empty_fig, empty_fig, empty_fig
        data = raw[raw["disease_code"].isin(KEY_DISEASES)]
        if data.empty:
            empty_fig = _empty_figure(f"No records for: {', '.join(KEY_DISEASES)}")
            return empty_fig, empty_fig, empty_fig, empty_fig
        try:
            fig_overtime = key_disease_reports_overtime(data)
            fig_kde      = key_disease_kde_distribution(data)
            fig_location = key_disease_wrt_location(data)
            fig_codemap  = plot_disease_code_map(data)
            return fig_overtime, fig_kde, fig_location, fig_codemap
        except Exception as e:
            import traceback
            traceback.print_exc()
            err_fig = _empty_figure(f"Error rendering charts: {e}")
            return err_fig, err_fig, err_fig, err_fig
# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _empty_figure(message: str):
    """Return a blank Plotly figure with a centred message."""
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=16, color="#888"),
    )
    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        margin=dict(l=20, r=20, t=20, b=20),
    )
    return fig