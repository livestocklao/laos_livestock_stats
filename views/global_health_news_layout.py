"""
Global Health News Tab Layout for Animal Disease Monitoring Dashboard (Dash)
============================================================================
Translates the Streamlit GlobalNewsDashboard into Dash/Plotly.

Layout
------
  ┌──────────────────────────────────────────────────────────────┐
  │  TOP ROW                                                     │
  │  [Total] [Press Rel] [Newsletter] [Statements] [Latest]  🔍  │
  │                                               [Year ▾]       │
  ├──────────────────────────────────────────────────────────────┤
  │  ARTICLES GRID  (3 per row, paginated)                       │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
  │  │ image    │  │ image    │  │ image    │                    │
  │  │ title    │  │ title    │  │ title    │                    │
  │  │ date     │  │ date     │  │ date     │                    │
  │  │ excerpt  │  │ excerpt  │  │ excerpt  │                    │
  │  │ tag  btn │  │ tag  btn │  │ tag  btn │                    │
  │  └──────────┘  └──────────┘  └──────────┘                   │
  └──────────────────────────────────────────────────────────────┘

Usage in app.py
---------------
    from global_news_layout import build_global_news_tab, register_global_news_callbacks

    dcc.Tab(
        label='Global Health News',
        value='global-health-news',
        className='custom-tab',
        selected_className='tab--selected',
        children=build_global_news_tab(),
    )

    register_global_news_callbacks(app)
"""

from dash import html, dcc, Input, Output, State, ALL
import pandas as pd
from datetime import datetime
from difflib import SequenceMatcher

from utils.data_loader import load_data_package

# ── Config ────────────────────────────────────────────────────────────────────

ARTICLES_PER_PAGE = 9      # 3 per row × 3 rows
ARTICLES_PER_ROW  = 3
DEFAULT_IMAGE_URL = "https://via.placeholder.com/400x200?text=No+Image"

TAG_COLORS = {
    "Statement":     "#3b82f6",
    "Press Release": "#22c55e",
    "Newsletter":    "#eab308",
    "Report":        "#f97316",
    "Alert":         "#ef4444",
    "default":       "#9ca3af",
}

TAG_EMOJI = {
    "Statement":     "🔵",
    "Press Release": "🟢",
    "Newsletter":    "🟡",
    "Report":        "🟠",
    "Alert":         "🔴",
    "default":       "⚪",
}

# ── Style constants ───────────────────────────────────────────────────────────

_METRIC_CARD = {
    "backgroundColor": "#f7faf9",
    "borderRadius": "10px",
    "padding": "12px 16px",
    "flex": "1",
    "minWidth": "0",
    "boxShadow": "0 2px 6px rgba(0,0,0,0.07)",
    "display": "flex",
    "flexDirection": "column",
    "justifyContent": "center",
    "alignItems": "center",
    "border": "1px solid #dce3e0",
}

_METRIC_LABEL = {
    "fontSize": "12px",
    "fontWeight": "600",
    "color": "#666",
    "marginBottom": "4px",
    "textAlign": "center",
}

_METRIC_VALUE = {
    "fontSize": "22px",
    "fontWeight": "700",
    "color": "#1e4d3b",
    "textAlign": "center",
}

_ARTICLE_CARD = {
    "backgroundColor": "#E4F2EC",
    "borderRadius": "12px",
    "padding": "0",
    "border": "1px solid #c8dfd6",
    "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
    "display": "flex",
    "flexDirection": "column",
    "overflow": "hidden",
    "height": "100%",
}

_ARTICLE_BODY = {
    "padding": "14px",
    "display": "flex",
    "flexDirection": "column",
    "flex": "1",
}


# ── Data helpers ──────────────────────────────────────────────────────────────

def _clean_news(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["year"] = df["date"].dt.year
    df["title"]     = df.get("title",     pd.Series(dtype=str)).fillna("Untitled")
    df["main_text"] = df.get("main_text", pd.Series(dtype=str)).fillna("No content available")
    df["tag"]       = df.get("tag",       pd.Series(dtype=str)).fillna("Article")
    df["url"]       = df.get("url",       pd.Series(dtype=str)).fillna("#")
    df["image_url"] = df.get("image_url", pd.Series(dtype=str)).fillna(DEFAULT_IMAGE_URL)
    df["date_text"] = df["date"].dt.strftime("%B %d, %Y").fillna("Unknown")
    return df.sort_values("date", ascending=False, na_position="last").reset_index(drop=True)


def _days_ago(date_value) -> str:
    if pd.isna(date_value):
        return "Unknown"
    try:
        days = (datetime.now() - pd.to_datetime(date_value)).days
        if days == 0:   return "Today"
        if days == 1:   return "Yesterday"
        if days < 30:   return f"{days} days ago"
        if days < 365:
            m = days // 30
            return f"{m} month{'s' if m > 1 else ''} ago"
        y = days // 365
        return f"{y} year{'s' if y > 1 else ''} ago"
    except Exception:
        return "Unknown"


def _search(df: pd.DataFrame, query: str, threshold: float = 0.3) -> pd.DataFrame:
    if not query or not query.strip():
        return df
    q = query.lower().strip()
    # fast substring check first, fall back to similarity
    mask = (
        df["title"].str.lower().str.contains(q, na=False) |
        df["main_text"].str.lower().str.contains(q, na=False)
    )
    if mask.any():
        return df[mask].copy()
    # fuzzy fallback
    def sim(text):
        if pd.isna(text): return 0
        return SequenceMatcher(None, q, str(text).lower()).ratio()
    scores = df[["title", "main_text"]].applymap(sim).max(axis=1)
    return df[scores >= threshold].copy()


def _tag_stats(df: pd.DataFrame) -> dict:
    counts = df["tag"].value_counts().to_dict()
    return {
        "total":         len(df),
        "press_release": counts.get("Press Release", 0),
        "newsletter":    counts.get("Newsletter",    0),
        "statement":     counts.get("Statement",     0),
        "latest":        _days_ago(df["date"].max() if len(df) else None),
    }


# ── UI component builders ─────────────────────────────────────────────────────

def _stat_card(label: str, value_id: str) -> html.Div:
    return html.Div([
        html.Div(label, style=_METRIC_LABEL),
        html.Span("—", id=value_id, style=_METRIC_VALUE),
    ], style=_METRIC_CARD)


def _article_card(article: pd.Series) -> html.Div:
    image_url = article["image_url"]
    if pd.isna(image_url) or image_url == "":
        image_url = DEFAULT_IMAGE_URL

    tag      = article["tag"]
    tag_bg   = TAG_COLORS.get(tag, TAG_COLORS["default"])
    tag_em   = TAG_EMOJI.get(tag, TAG_EMOJI["default"])
    days_ago = _days_ago(article["date"])
    date_str = article.get("date_text", "")
    excerpt  = str(article["main_text"])[:300] + ("..." if len(str(article["main_text"])) > 300 else "")
    url      = article["url"]
    has_url  = pd.notna(url) and url not in ("#", "", None)

    read_more = html.A(
        "Read More →",
        href=url if has_url else "#",
        target="_blank",
        style={
            "backgroundColor": "#264653" if has_url else "#ccc",
            "color": "white",
            "padding": "6px 14px",
            "borderRadius": "6px",
            "fontSize": "13px",
            "textDecoration": "none",
            "pointerEvents": "auto" if has_url else "none",
        }
    )

    return html.Div([
        # Image
        html.Img(
            src=image_url,
            style={
                "width": "100%",
                "height": "160px",
                "objectFit": "cover",
            },
            # graceful fallback via onerror
        ),
        # Body
        html.Div([
            # Title
            html.H4(article["title"], style={
                "fontSize": "15px",
                "fontWeight": "700",
                "color": "#1e3a2f",
                "marginBottom": "6px",
                "lineHeight": "1.4",
            }),
            # Date badge
            html.Span(
                f"📅 {date_str}  ({days_ago})",
                style={
                    "fontSize": "11px",
                    "backgroundColor": "#d1fae5",
                    "color": "#065f46",
                    "padding": "2px 8px",
                    "borderRadius": "10px",
                    "marginBottom": "8px",
                    "display": "inline-block",
                    "width": "fit-content",
                }
            ),
            # Excerpt
            html.P(excerpt, style={
                "fontSize": "13px",
                "color": "#444",
                "lineHeight": "1.5",
                "flex": "1",
                "marginTop": "8px",
                "marginBottom": "10px",
            }),
            # Footer: tag + read more
            html.Div([
                html.Span(
                    f"{tag_em} {tag}",
                    style={
                        "fontSize": "12px",
                        "fontWeight": "600",
                        "color": tag_bg,
                    }
                ),
                read_more,
            ], style={
                "display": "flex",
                "justifyContent": "space-between",
                "alignItems": "center",
                "marginTop": "auto",
            }),
        ], style=_ARTICLE_BODY),
    ], style=_ARTICLE_CARD)


def _articles_grid(articles: pd.DataFrame) -> html.Div:
    """Build the 3-column article grid from a filtered/paginated dataframe."""
    if articles.empty:
        return html.Div("No articles found matching your filters.",
                        style={"color": "#888", "padding": "20px", "textAlign": "center"})

    rows = []
    for i in range(0, len(articles), ARTICLES_PER_ROW):
        batch = articles.iloc[i: i + ARTICLES_PER_ROW]
        cols  = []
        for _, row in batch.iterrows():
            cols.append(html.Div(
                _article_card(row),
                style={"flex": "1", "minWidth": "0"},
            ))
        # pad row to 3 if fewer articles
        while len(cols) < ARTICLES_PER_ROW:
            cols.append(html.Div(style={"flex": "1"}))

        rows.append(html.Div(cols, style={
            "display": "flex",
            "gap": "16px",
            "marginBottom": "16px",
            "alignItems": "stretch",
        }))

    return html.Div(rows)


def _pagination_controls(total_pages: int, current_page: int) -> html.Div:
    if total_pages <= 1:
        return html.Div()

    buttons = []
    for p in range(1, total_pages + 1):
        active = p == current_page
        buttons.append(html.Button(
            str(p),
            id={"type": "page-btn", "index": p},
            style={
                "padding": "6px 12px",
                "margin": "0 3px",
                "border": "1px solid #264653",
                "borderRadius": "6px",
                "backgroundColor": "#264653" if active else "white",
                "color": "white" if active else "#264653",
                "cursor": "pointer",
                "fontWeight": "700" if active else "400",
                "fontSize": "14px",
            }
        ))

    return html.Div(buttons, style={
        "display": "flex",
        "justifyContent": "center",
        "marginTop": "20px",
        "flexWrap": "wrap",
    })


# ─────────────────────────────────────────────────────────────────────────────
# Layout builder
# ─────────────────────────────────────────────────────────────────────────────

def build_global_news_tab() -> html.Div:
    """Return the complete layout for the Global Health News tab."""

    # ── Stores ───────────────────────────────────────────────────────────
    stores = html.Div([
        dcc.Store(id="gn-news-data",    data=[]),   # cleaned articles as records
        dcc.Store(id="gn-current-page", data=1),
        dcc.Interval(id="gn-load-trigger",
                     interval=60 * 60 * 1000, n_intervals=0, max_intervals=1),
    ], style={"display": "none"})

    # ── Top bar: 5 metric cards + search & year filter ───────────────────
    metrics_row = html.Div([
        _stat_card("📰 Total Articles",  "gn-stat-total"),
        _stat_card("📢 Press Releases",  "gn-stat-press"),
        _stat_card("📧 Newsletters",     "gn-stat-newsletter"),
        _stat_card("📝 Statements",      "gn-stat-statements"),
        _stat_card("🕐 Latest Article",  "gn-stat-latest"),
        # filters panel
        html.Div([
            dcc.Dropdown(
                id="gn-year-filter",
                placeholder="📅 Filter by Year",
                clearable=True,
                style={"marginBottom": "8px", "fontSize": "13px"},
            ),
            dcc.Input(
                id="gn-search-input",
                type="text",
                placeholder="🔎 Search articles...",
                debounce=True,
                style={
                    "width": "100%",
                    "padding": "8px 12px",
                    "borderRadius": "8px",
                    "border": "1px solid #ccc",
                    "fontSize": "13px",
                    "boxSizing": "border-box",
                }
            ),
        ], style={
            "flex": "1.4",
            "minWidth": "180px",
            "display": "flex",
            "flexDirection": "column",
            "justifyContent": "center",
            "padding": "0 4px",
        }),
    ], style={
        "display": "flex",
        "gap": "10px",
        "marginBottom": "18px",
        "alignItems": "stretch",
    })

    # ── Article count heading ─────────────────────────────────────────────
    count_heading = html.Div([
        html.Span("📰 ", style={"fontSize": "20px"}),
        html.Span("Latest Articles", style={"fontSize": "20px", "fontWeight": "700", "color": "#264653"}),
        html.Span(" (", style={"fontSize": "16px", "color": "#888"}),
        html.Span("—", id="gn-article-count", style={"fontSize": "16px", "color": "#888"}),
        html.Span(")", style={"fontSize": "16px", "color": "#888"}),
    ], style={"marginBottom": "14px"})

    # ── Grid + pagination (populated by callback) ─────────────────────────
    articles_area = dcc.Loading(
        id="gn-loading",
        type="circle",
        color="#264653",
        children=html.Div(id="gn-articles-grid"),
    )

    pagination = html.Div(id="gn-pagination")

    return html.Div(
        [stores, metrics_row, count_heading, articles_area, pagination],
        className="tab-content",
        style={"padding": "16px 18px 10px"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Callback registration
# ─────────────────────────────────────────────────────────────────────────────

def register_global_news_callbacks(app) -> None:
    """Register all Dash callbacks needed by the Global Health News tab."""

    # ── 1. Load data once, populate store + year dropdown + metrics ──────
    @app.callback(
        Output("gn-news-data",       "data"),
        Output("gn-year-filter",     "options"),
        Output("gn-stat-total",      "children"),
        Output("gn-stat-press",      "children"),
        Output("gn-stat-newsletter", "children"),
        Output("gn-stat-statements", "children"),
        Output("gn-stat-latest",     "children"),
        Input("gn-load-trigger",     "n_intervals"),
        prevent_initial_call=False,
    )
    def gn_load_data(_n):
        try:
            pkg  = load_data_package()
            df   = _clean_news(pkg.news_data)
            records = df.to_dict("records")

            years = sorted(
                df["year"].dropna().unique().astype(int).tolist(),
                reverse=True
            )
            year_opts = [{"label": str(y), "value": y} for y in years]

            stats = _tag_stats(df)
            return (
                records,
                year_opts,
                f"{stats['total']:,}",
                f"{stats['press_release']:,}",
                f"{stats['newsletter']:,}",
                f"{stats['statement']:,}",
                stats["latest"],
            )
        except Exception as e:
            import traceback; traceback.print_exc()
            return [], [], "—", "—", "—", "—", f"Error: {e}"

    # ── 2. Reset to page 1 whenever filters change ───────────────────────
    @app.callback(
        Output("gn-current-page", "data"),
        Input("gn-year-filter",   "value"),
        Input("gn-search-input",  "value"),
        prevent_initial_call=True,
    )
    def gn_reset_page(_year, _search):
        return 1

    # ── 3. Page button clicks → update current page ───────────────────────
    @app.callback(
        Output("gn-current-page", "data", allow_duplicate=True),
        Input({"type": "page-btn", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def gn_page_click(n_clicks_list):
        from dash import ctx
        if not ctx.triggered_id:
            return 1
        return ctx.triggered_id["index"]

    # ── 4. Render grid + pagination + article count ───────────────────────
    @app.callback(
        Output("gn-articles-grid",  "children"),
        Output("gn-pagination",     "children"),
        Output("gn-article-count",  "children"),
        Input("gn-news-data",       "data"),
        Input("gn-year-filter",     "value"),
        Input("gn-search-input",    "value"),
        Input("gn-current-page",    "data"),
        prevent_initial_call=False,
    )
    def gn_render_grid(records, year_filter, search_query, current_page):
        if not records:
            return html.Div("Loading articles...", style={"color": "#888", "padding": "20px"}), html.Div(), "0"

        df = pd.DataFrame(records)
        # restore datetime
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")

        # apply filters
        if year_filter:
            df = df[df["year"] == year_filter]
        if search_query and search_query.strip():
            df = _search(df, search_query)

        total       = len(df)
        total_pages = max(1, (total + ARTICLES_PER_PAGE - 1) // ARTICLES_PER_PAGE)
        page        = max(1, min(current_page or 1, total_pages))

        start = (page - 1) * ARTICLES_PER_PAGE
        end   = start + ARTICLES_PER_PAGE
        page_df = df.iloc[start:end]

        grid       = _articles_grid(page_df)
        pagination = _pagination_controls(total_pages, page)

        return grid, pagination, str(total)