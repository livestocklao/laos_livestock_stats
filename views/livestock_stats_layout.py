from dash import html, dcc, Input, Output
import pandas as pd
import dash
from dash import html, dcc, ctx
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from dash import clientside_callback, ClientsideFunction

from utils.data_loader import load_livestock_stats
from utils.plots import create_livestock_province_map, create_livestock_animal_type_charts, create_livestock_composition_chart, create_district_stats_bar_chart
import re
from datetime import datetime



# ── Main tab definitions ──────────────────────────────────────────────────────
_MAIN_TABS = [
    ("national-overview", "🏠 National Overview"),
    ("farm-stats",         "🏪 Farm Statistics"),
    ("yearly-stats",       "📊 Yearly Stats"),
    ("district-stats",     "🗺️ District Level Statistics"),
    ("group-farming",      "👥 Group Farming Statistics"),
    ("breeding-stats",     "🧬 Breeding Stats"),
]
_TAB_VALUES = [v for v, _ in _MAIN_TABS]
# ── Button style for custom buttons ────────────────────────────────────────
_BUTTON_STYLES = {
    "national-overview": "🏠",
    "farm-stats": "🏪",
    "yearly-stats": "📊",
    "district-stats": "🗺️",
    "group-farming": "👥",
    "breeding-stats": "🧬",
}
# ── Animal emojis (display only — NOT the source of truth for which
#    buttons/ids exist; that's always derived from the real data columns
#    so it can never drift out of sync with what's actually rendered) ──────
_ANIMAL_EMOJIS = {
    "Catle": "🐄",
    "Buffalo": "🐃",
    "Sheep": "🐑",
    "Goat": "🐐",
    "Camel": "🐫",
    "Horse": "🐴",
    "Donkey": "🫏",
    "Mule": "🐴",
    "Poultry": "🐔",
    "Swine": "🐖",
    "Pig": "🐖",
    "Goat-Sheep": "🐐🐑",
    "Elp": "🦌",
    "Cattle": "🐄",
}
# ── Farm Statistics sub-tab definitions ──────────────────────────────────────
_FARM_STATS_SUB_TABS = [
    ("tabular-view", "⬅️"),
    ("distribution-charts", "➡️"),
]

_FARM_STATS_MAP_TABS = [
    ("farms", "Farms Count"),
    ("amount", "Livestock Count"),
]

_YEARLY_STATS_SUB_TABS = [
    ("tabular-view", "⬅️"),
    ("distribution-charts", "➡️"),
]

_YEARLY_STATS_YEAR_TABS = [
    ("2024", "2024"),
    ("2025", "2025"),
]

_REGION_LABELS = {"north", "south", "middle", "central", "east", "west"}

def _is_region_row(value):
    return str(value).strip().lower() in _REGION_LABELS

_GROUP_FARMING_MAP_TABS = [
    ("group", "Group Count"),
    ("animal", "Animal Count"),
]

# ── Table helper function with scrollable container ──────────────────────────
def _build_table_html(df_display, index_col_name="Index", max_height="400px", highlight_last_row=False):
    """Build an HTML table with custom styling and scrollable body.
    If `highlight_last_row` is True, the final row (e.g. a "Total" row) is
    rendered bold with a heavier top border to set it apart from the data.
    """
    n_rows = len(df_display)
    return html.Div(
        style={
            "overflowX": "auto",
            "overflowY": "auto",
            "maxHeight": max_height,
            "borderRadius": "8px",
        },
        children=[
            html.Table([
                html.Thead(
                    html.Tr([
                        html.Th(col, style={
                            "padding": "10px",
                            "textAlign": "center",
                            "fontFamily": "ubuntu",
                            "color": "white",
                            "fontSize": "16px",
                            "fontWeight": "bold",
                            "backgroundColor": "#264653",
                            "height": "45px",
                            "position": "sticky",
                            "top": 0,
                            "zIndex": 10,
                        })
                        for col in [index_col_name] + list(df_display.columns)
                    ]),
                    style={"display": "table-header-group"}
                ),
                html.Tbody([
                    html.Tr([
                        html.Td(str(idx), style={
                            "padding": "8px 10px",
                            "fontFamily": "ubuntu",
                            "fontSize": "15px",
                            "fontWeight": "bold",
                            "textAlign": "center",
                            "height": "42px",
                            "borderBottom": "1px solid #eee",
                            **({"borderTop": "2px solid #264653"} if is_last else {}),
                        }),
                        *[
                            html.Td(f"{val:,.0f}", style={
                                "padding": "8px 10px",
                                "fontFamily": "ubuntu",
                                "fontSize": "15px",
                                "fontWeight": "bold",
                                "textAlign": "center",
                                "height": "42px",
                                "borderBottom": "1px solid #eee",
                                **({"borderTop": "2px solid #264653", "backgroundColor": "#f7faf9"} if is_last else {}),
                            })
                            for val in row
                        ]
                    ])
                    for row_num, (idx, row) in enumerate(df_display.iterrows())
                    for is_last in [highlight_last_row and row_num == n_rows - 1]
                ])
            ], style={
                "width": "100%",
                "borderCollapse": "collapse",
            })
        ]
    )
def _build_national_table_with_total(df_2024, province_col="Province"):
    """Province x animal-type table with a trailing Total row."""
    animal_cols = [c for c in df_2024.columns if c != province_col]
    total_row = {province_col: "Total"}
    for c in animal_cols:
        total_row[c] = df_2024[c].sum()
    df_with_total = pd.concat([df_2024, pd.DataFrame([total_row])], ignore_index=True)
    df_indexed = df_with_total.set_index(province_col)
    return _build_table_html(
        df_indexed,
        index_col_name=province_col,
        max_height="calc(100vh - 320px)",  # Adjusted for dropdown
        highlight_last_row=True,
    )

def _build_farm_stats_table(data_farm, data_amount, province_col="Province"):
    """Build combined table showing both farm count and total amount data with merged headers."""
    import re
    
    def clean_header(val):
        """Remove spaces and all symbols from the beginning of header values"""
        if pd.isna(val):
            return val
        val = str(val).strip()
        val = re.sub(r'^[\s]*[^a-zA-Z0-9\s]+[\s]*', '', val)
        val = re.sub(r'^[\s]*[/\-:;,.!@#$%^&*()_+=\[\]{}|\\<>?~`]+[\s]*', '', val)
        return val
    
    # Get animal columns (excluding Province)
    animal_cols = [c for c in data_farm.columns if c != province_col]
    
    # Clean animal column names
    animal_cols_clean = [clean_header(col) for col in animal_cols]
    
    # Create combined dataframe with flat columns for easier iteration
    df_combined = pd.DataFrame()
    df_combined[province_col] = data_farm[province_col]
    
    # Store column order for header building
    column_pairs = []
    for idx, col in enumerate(animal_cols):
        farm_col = f"Farm_{col}"
        amount_col = f"Amount_{col}"
        df_combined[farm_col] = data_farm[col]
        df_combined[amount_col] = data_amount[col]
        column_pairs.append((col, farm_col, amount_col))
    
    # Add total row
    total_row = {province_col: "Total"}
    for col in df_combined.columns:
        if col != province_col:
            total_row[col] = df_combined[col].sum()
    
    df_with_total = pd.concat([df_combined, pd.DataFrame([total_row])], ignore_index=True)
    df_indexed = df_with_total.set_index(province_col)
    
    n_rows = len(df_indexed)
    
    # Define colors for different groups (same as breeding stats table)
    group_colors = [
        "#f8e8e8",  # Light pink/red
        "#e8f0e8",  # Light green
        "#e8e8f8",  # Light blue
        "#f8f0e8",  # Light peach
        "#f0f0e8",  # Light yellow
        "#e8f0f8",  # Light sky blue
        "#f8e8f0",  # Light purple
        "#f0e8f0",  # Light lavender
    ]
    
    # Assign group colors to each animal column
    col_colors = {}
    for idx, col in enumerate(animal_cols):
        col_colors[col] = group_colors[idx % len(group_colors)]
    
    # Build header rows
    # First header row: Animal names with colspan
    header_cell_style = {
        "padding": "10px",
        "textAlign": "center",
        "fontFamily": "ubuntu",
        "color": "white",
        "fontSize": "16px",
        "fontWeight": "bold",
        "backgroundColor": "#264653",
        "height": "45px",
        "position": "sticky",
        "top": 0,
        "zIndex": 10,
    }
    
    sub_header_cell_style = {
        "padding": "8px 10px",
        "textAlign": "center",
        "fontFamily": "ubuntu",
        "color": "white",
        "fontSize": "14px",
        "fontWeight": "500",
        "backgroundColor": "#2a6f7f",
        "height": "35px",
        "position": "sticky",
        "top": "45px",
        "zIndex": 10,
    }
    
    # First header row: Province + Animal names with colspan
    header_row1 = [html.Th(province_col, style={
        **header_cell_style,
        "rowSpan": "2",
        "borderRight": "0px solid #e0e0e0",  # Separator between Province and data
    })]
    
    for idx, col in enumerate(animal_cols):
        style = header_cell_style.copy()
        # Add left border for each animal group (except the first one)
        if idx > 0:
            style["borderLeft"] = "0px solid #e0e0e0"
        header_row1.append(html.Th(animal_cols_clean[idx], colSpan=2, style=style))
    
    # Second header row: Farm/Amount sub-headers
    header_row2 = []
    header_row2.append(html.Th("", style={
        **sub_header_cell_style,
        "borderRight": "0px solid #e0e0e0",  # Separator between Province and data
    }))
    
    for idx, col in enumerate(animal_cols):
        for sub_idx, sub in enumerate(['Farm', 'Amount']):
            style = sub_header_cell_style.copy()
            # Add left border for each animal group (except the first one)
            if idx > 0 and sub_idx == 0:
                style["borderLeft"] = "0px solid #e0e0e0"
            header_row2.append(html.Th(sub, style=style))
    
    # Build body rows
    body_rows = []
    for row_num, (idx, row) in enumerate(df_indexed.iterrows()):
        is_last = row_num == n_rows - 1
        
        # Province cell
        province_style = {
            "padding": "8px 10px",
            "fontFamily": "ubuntu",
            "fontSize": "15px",
            "fontWeight": "bold",
            "textAlign": "center",
            "height": "42px",
            "borderBottom": "1px solid #eee",
            "borderRight": "0px solid #e0e0e0",  # Separator between Province and data
        }
        if is_last:
            province_style["borderTop"] = "2px solid #264653"
            province_style["backgroundColor"] = "#f7faf9"
        
        row_cells = [html.Td(str(idx), style=province_style)]
        
        # Data cells for each animal
        for col_idx, col in enumerate(animal_cols):
            farm_val = row[f"Farm_{col}"]
            amount_val = row[f"Amount_{col}"]
            
            # Color for this animal group
            color = col_colors.get(col, "#ffffff")
            
            # Farm cell
            farm_style = {
                "padding": "8px 10px",
                "fontFamily": "ubuntu",
                "fontSize": "15px",
                "fontWeight": "bold",
                "textAlign": "center",
                "height": "42px",
                "borderBottom": "1px solid #eee",
                "backgroundColor": color,
            }
            # Add left border for each animal group (except the first one)
            if col_idx > 0:
                farm_style["borderLeft"] = "0px solid #e0e0e0"
            if is_last:
                farm_style["borderTop"] = "2px solid #264653"
                farm_style["backgroundColor"] = "#f7faf9"
            
            farm_display = f"{int(farm_val):,.0f}" if pd.notna(farm_val) and farm_val != 0 else "-"
            row_cells.append(html.Td(farm_display, style=farm_style))
            
            # Amount cell
            amount_style = {
                "padding": "8px 10px",
                "fontFamily": "ubuntu",
                "fontSize": "15px",
                "fontWeight": "bold",
                "textAlign": "center",
                "height": "42px",
                "borderBottom": "1px solid #eee",
                "backgroundColor": color,
            }
            if is_last:
                amount_style["borderTop"] = "2px solid #264653"
                amount_style["backgroundColor"] = "#f7faf9"
            
            amount_display = f"{int(amount_val):,.0f}" if pd.notna(amount_val) and amount_val != 0 else "-"
            row_cells.append(html.Td(amount_display, style=amount_style))
        
        body_rows.append(html.Tr(row_cells))
    
    return html.Div(
        style={
            "overflowX": "auto",
            "overflowY": "auto",
            "maxHeight": "calc(100vh - 370px)",
            "borderRadius": "8px",
        },
        children=[
            html.Table([
                html.Thead([
                    html.Tr(header_row1),
                    html.Tr(header_row2),
                ]),
                html.Tbody(body_rows),
            ], style={
                "width": "100%",
                "borderCollapse": "collapse",
            })
        ]
    )

def _build_yearly_stats_table(df_24, df_25, province_col="Province"):
    """Build combined table showing both years data with merged headers."""
    # Get animal columns (excluding Province)
    animal_cols = [c for c in df_24.columns if c != province_col]
    
    # Create combined dataframe with flat columns for easier iteration
    df_combined = pd.DataFrame()
    df_combined[province_col] = df_24[province_col]
    
    # Store column order for header building
    column_pairs = []
    for col in animal_cols:
        col_2024 = f"2024_{col}"
        col_2025 = f"2025_{col}"
        df_combined[col_2024] = df_24[col]
        df_combined[col_2025] = df_25[col]
        column_pairs.append((col, col_2024, col_2025))
    
    # Add total row
    total_row = {province_col: "Total"}
    for col in df_combined.columns:
        if col != province_col:
            total_row[col] = df_combined[col].sum()
    
    df_with_total = pd.concat([df_combined, pd.DataFrame([total_row])], ignore_index=True)
    df_indexed = df_with_total.set_index(province_col)
    
    n_rows = len(df_indexed)
    
    # Build header rows
    # First header row: Animal names with colspan
    header_row1 = [html.Th(province_col, style={
        "padding": "10px",
        "textAlign": "center",
        "fontFamily": "ubuntu",
        "color": "white",
        "fontSize": "16px",
        "fontWeight": "bold",
        "backgroundColor": "#264653",
        "height": "45px",
        "position": "sticky",
        "top": 0,
        "zIndex": 10,
        "rowSpan": "2",
    })]
    
    for col in animal_cols:
        header_row1.append(html.Th(col, colSpan=2, style={
            "padding": "10px",
            "textAlign": "center",
            "fontFamily": "ubuntu",
            "color": "white",
            "fontSize": "16px",
            "fontWeight": "bold",
            "backgroundColor": "#264653",
            "height": "45px",
            "position": "sticky",
            "top": 0,
            "zIndex": 10,
        }))
    
    # Second header row: 2024/2025 sub-headers
    header_row2 = []
    header_row2.append(html.Th("    ", style={
        "padding": "8px 10px",
        "textAlign": "center",
        "fontFamily": "ubuntu",
        "color": "white",
        "fontSize": "14px",
        "fontWeight": "500",
        "backgroundColor": "#2a6f7f",
        "height": "35px",
        "position": "sticky",
        "top": "45px",
        "zIndex": 10,
    }))
    for col in animal_cols:
        for year in ['2024', '2025']:
            header_row2.append(html.Th(year, style={
                "padding": "8px 10px",
                "textAlign": "center",
                "fontFamily": "ubuntu",
                "color": "white",
                "fontSize": "14px",
                "fontWeight": "500",
                "backgroundColor": "#2a6f7f",
                "height": "35px",
                "position": "sticky",
                "top": "45px",
                "zIndex": 10,
            }))
    
    return html.Div(
        style={
            "overflowX": "auto",
            "overflowY": "auto",
            "maxHeight": "calc(100vh - 370px)",
            "borderRadius": "8px",
        },
        children=[
            html.Table([
                html.Thead(
                    [
                        html.Tr(header_row1),
                        html.Tr(header_row2),
                    ]
                ),
                html.Tbody([
                    html.Tr([
                        html.Td(str(idx), style={
                            "padding": "8px 10px",
                            "fontFamily": "ubuntu",
                            "fontSize": "15px",
                            "fontWeight": "bold",
                            "textAlign": "center",
                            "height": "42px",
                            "borderBottom": "1px solid #eee",
                            **({"borderTop": "2px solid #264653"} if is_last else {}),
                        }),
                        *[
                            html.Td(f"{int(val):,.0f}" if pd.notna(val) and val != 0 else "-", style={
                                "padding": "8px 10px",
                                "fontFamily": "ubuntu",
                                "fontSize": "15px",
                                "fontWeight": "bold",
                                "textAlign": "center",
                                "height": "42px",
                                "borderBottom": "1px solid #eee",
                                **({"borderTop": "2px solid #264653", "backgroundColor": "#f7faf9"} if is_last else {}),
                            })
                            for val in row
                        ]
                    ])
                    for row_num, (idx, row) in enumerate(df_indexed.iterrows())
                    for is_last in [row_num == n_rows - 1]
                ])
            ], style={
                "width": "100%",
                "borderCollapse": "collapse",
            })
        ]
    )

def _build_yearly_stats_sub_tabs(selected_tab="tabular-view"):
    """Build sub-tab buttons for Yearly Stats left panel."""
    return html.Div(
        [
            html.Div([
                html.Div(
                    html.Button(
                        label,
                        id=f"ls-yearly-left-{value}",
                        className="ls-sub-tab-btn",
                        style={
                            "backgroundColor": "#264653" if value == selected_tab else "#f0f2f5",
                            "color": "white" if value == selected_tab else "#264653",
                            "border": "none",
                            "padding": "8px 16px",
                            "borderRadius": "20px",
                            "cursor": "pointer",
                            "fontSize": "15px",
                            "fontWeight": "500",
                            "transition": "all 0.3s ease",
                            "fontFamily": "ubuntu",
                            "margin": "0 3px",
                            "boxShadow": "0 2px 4px rgba(0,0,0,0.1)" if value == selected_tab else "none",
                        }
                    ),
                    style={"display": "inline-block"}
                )
                for value, label in _YEARLY_STATS_SUB_TABS
            ], style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "6px",
                "padding": "5px 0",
                "marginBottom": "10px",
            })
        ],
        id="ls-yearly-left-sub-tabs",
    )

def _build_yearly_stats_year_tabs(selected_tab="2024"):
    """Build sub-tab buttons for Yearly Stats right panel (year selection)."""
    return html.Div(
        [
            html.Div([
                html.Div(
                    html.Button(
                        label,
                        id=f"ls-yearly-right-{value}",
                        className="ls-sub-tab-btn",
                        style={
                            "backgroundColor": "#264653" if value == selected_tab else "#f0f2f5",
                            "color": "white" if value == selected_tab else "#264653",
                            "border": "none",
                            "padding": "8px 16px",
                            "borderRadius": "20px",
                            "cursor": "pointer",
                            "fontSize": "15px",
                            "fontWeight": "500",
                            "transition": "all 0.3s ease",
                            "fontFamily": "ubuntu",
                            "margin": "0 3px",
                            "boxShadow": "0 2px 4px rgba(0,0,0,0.1)" if value == selected_tab else "none",
                        }
                    ),
                    style={"display": "inline-block"}
                )
                for value, label in _YEARLY_STATS_YEAR_TABS
            ], style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "6px",
                "padding": "5px 0",
                "marginBottom": "10px",
            })
        ],
        id="ls-yearly-right-year-tabs",
    )

def _build_yearly_stats_map_card():
    """Right-panel card for Yearly Stats: year selector + choropleth."""
    return html.Div(
        [
            # Year selector buttons
            html.Div(
                id="ls-yearly-year-tabs-container",
                style={
                    "marginBottom": "10px",
                }
            ),
            html.Iframe(
                id="ls-yearly-province-map",
                srcDoc="",  # populated by callback via srcDoc property
                style={
                    "height": "calc(100vh - 380px)",
                    "width": "100%",
                    # "minHeight": "400px",
                    "border": "none",
                },
            ),
        ],
        style={
            "backgroundColor": "#fff",
            "borderRadius": "10px",
            "padding": "12px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
            "border": "1px solid #dce3e0",
            "height": "100%",
            "display": "flex",
            "flexDirection": "column",
        },
    )

def _placeholder_panel(label):
    """Generic 'coming soon' panel used for tabs whose spec hasn't been provided yet."""
    return html.Div(
        [
            html.Div("🚧", style={"fontSize": "36px", "marginBottom": "8px"}),
            html.Div(f"{label} — view coming soon", style={
                "fontSize": "15px", "color": "#888", "fontWeight": "500",
            }),
        ],
        style={
            "display": "flex",
            "flexDirection": "column",
            "alignItems": "center",
            "justifyContent": "center",
            "height": "400px",
            "backgroundColor": "#fff",
            "borderRadius": "10px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
            "border": "1px dashed #dce3e0",
        },
    )
def _build_animal_selector_buttons(animal_cols):
    """Build animal selector buttons with emojis, including a "Total"
    (All Animals) button — this MUST always be rendered, since the
    callbacks in register_livestock_stats_callbacks() target
    'ls-animal-btn-Total' as an Input/Output id."""
    if not animal_cols:
        return html.Div("No animal data available", style={"padding": "10px", "color": "#888"})

    # "Total" first, then one button per real data column (using the exact
    # column names so they always match what create_livestock_province_map
    # expects, e.g. "Poultry").
    all_animals = [("Total", "🌐 All Animals")] + [
        (c, f"{_ANIMAL_EMOJIS.get(c, '🐾')} {c}") for c in animal_cols
    ]

    return html.Div(
        [
            html.Div([
                html.Div(
                    html.Button(
                        label,
                        id=f"ls-animal-btn-{value}",
                        className="ls-animal-selector-btn",
                        style={
                            "backgroundColor": "#264653" if value == "Total" else "#f0f2f5",
                            "color": "white" if value == "Total" else "#264653",
                            "border": "none",
                            "padding": "8px 16px",
                            "borderRadius": "20px",
                            "cursor": "pointer",
                            "fontSize": "18px",
                            "fontWeight": "500",
                            "transition": "all 0.3s ease",
                            "fontFamily": "ubuntu",
                            "margin": "0 3px",
                            "boxShadow": "0 2px 4px rgba(0,0,0,0.1)" if value == "Total" else "none",
                        }
                    ),
                    style={"display": "inline-block"}
                )
                for value, label in all_animals
            ], style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "6px",
                "padding": "5px 0",
            })
        ],
        id="ls-animal-selector-container",
    )

def _build_farm_stats_sub_tabs(selected_tab="tabular-view"):
    """Build sub-tab buttons for Farm Statistics left panel."""
    return html.Div(
        [
            html.Div([
                html.Div(
                    html.Button(
                        label,
                        id=f"ls-farm-left-{value}",
                        className="ls-sub-tab-btn",
                        style={
                            "backgroundColor": "#264653" if value == selected_tab else "#f0f2f5",
                            "color": "white" if value == selected_tab else "#264653",
                            "border": "none",
                            "padding": "8px 16px",
                            "borderRadius": "20px",
                            "cursor": "pointer",
                            "fontSize": "15px",
                            "fontWeight": "500",
                            "transition": "all 0.3s ease",
                            "fontFamily": "ubuntu",
                            "margin": "0 3px",
                            "boxShadow": "0 2px 4px rgba(0,0,0,0.1)" if value == selected_tab else "none",
                        }
                    ),
                    style={"display": "inline-block"}
                )
                for value, label in _FARM_STATS_SUB_TABS
            ], style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "6px",
                "padding": "5px 0",
                "marginBottom": "10px",
            })
        ],
        id="ls-farm-left-sub-tabs",
    )

def _build_farm_stats_map_tabs(selected_tab="farms"):
    """Build sub-tab buttons for Farm Statistics right panel (map view)."""
    return html.Div(
        [
            html.Div([
                html.Div(
                    html.Button(
                        label,
                        id=f"ls-farm-right-{value}",
                        className="ls-sub-tab-btn",
                        style={
                            "backgroundColor": "#264653" if value == selected_tab else "#f0f2f5",
                            "color": "white" if value == selected_tab else "#264653",
                            "border": "none",
                            "padding": "8px 16px",
                            "borderRadius": "20px",
                            "cursor": "pointer",
                            "fontSize": "15px",
                            "fontWeight": "500",
                            "transition": "all 0.3s ease",
                            "fontFamily": "ubuntu",
                            "margin": "0 3px",
                            "boxShadow": "0 2px 4px rgba(0,0,0,0.1)" if value == selected_tab else "none",
                        }
                    ),
                    style={"display": "inline-block"}
                )
                for value, label in _FARM_STATS_MAP_TABS
            ], style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "6px",
                "padding": "5px 0",
                "marginBottom": "10px",
            })
        ],
        id="ls-farm-right-sub-tabs",
    )
def _build_national_map_card():
    """Right-panel card for National Overview: animal-selector buttons + choropleth."""
    return html.Div(
        [
            # Animal selector buttons
            html.Div(
                id="ls-animal-buttons-container",
                style={
                    "marginBottom": "10px",
                }
            ),
            html.Iframe(
                id="ls-province-map",
                srcDoc="",  # populated by callback via srcDoc property
                style={
                    "height": "calc(100vh - 420px)",
                    "width": "100%",
                    # "minHeight": "400px",
                    "border": "none",
                },
            ),
        ],
        style={
            "backgroundColor": "#fff",
            "borderRadius": "10px",
            "padding": "12px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
            "border": "1px solid #dce3e0",
            "height": "100%",
            "display": "flex",
            "flexDirection": "column",
        },
    )

def _build_farm_stats_map_card():
    """Right-panel card for Farm Statistics: map type selector + choropleth."""
    return html.Div(
        [
            # Farm/Amount selector buttons
            html.Div(
                id="ls-farm-map-tabs-container",
                style={
                    "marginBottom": "10px",
                }
            ),
            html.Iframe(
                id="ls-farm-province-map",
                srcDoc="",  # populated by callback via srcDoc property
                style={
                    "height": "calc(100vh - 380px)",
                    "width": "100%",
                    "minHeight": "400px",
                    "border": "none",
                },
            ),
        ],
        style={
            "backgroundColor": "#fff",
            "borderRadius": "10px",
            "padding": "12px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
            "border": "1px solid #dce3e0",
            "height": "100%",
            "display": "flex",
            "flexDirection": "column",
        },
    )

def _build_selector_buttons():
    """Build custom selector buttons with emojis instead of tabs."""
    return html.Div(
        [
            html.Div([
                html.Div(
                    html.Button(
                        label,
                        id=f"ls-btn-{value}",
                        className="ls-selector-btn",
                        style={
                            "backgroundColor": "#264653" if value == "national-overview" else "#f0f2f5",
                            "color": "white" if value == "national-overview" else "#264653",
                            "border": "none",
                            "padding": "10px 20px",
                            "borderRadius": "25px",
                            "cursor": "pointer",
                            "fontSize": "19px",
                            "fontWeight": "500",
                            "transition": "all 0.3s ease",
                            "fontFamily": "ubuntu",
                            "margin": "0 4px",
                            "boxShadow": "0 2px 4px rgba(0,0,0,0.1)" if value == "national-overview" else "none",
                        }
                    ),
                    style={"display": "inline-block"}
                )
                for value, label in _MAIN_TABS
            ], style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "8px",
                "marginBottom": "15px",
                "padding": "5px 0",
            })
        ],
        id="ls-selector-container",
    )

def _build_district_stats_table(df_display, province_col="Province", max_height="calc(100vh - 320px)"):
    """Province/District table for stats_by_district.

    Rows whose Province-column value ends with "Province" (a province-level
    subtotal row) get a tinted background to set them apart from the
    "...District" detail rows. Same header/cell styling as the other tables.
    """
    df_indexed = df_display.set_index(province_col)
    animal_cols = list(df_indexed.columns)

    def _is_province_row(idx):
        return str(idx).strip().lower().endswith("province")

    return html.Div(
        style={
            "overflowX": "auto",
            "overflowY": "auto",
            "maxHeight": max_height,
            "borderRadius": "8px",
        },
        children=[
            html.Table([
                html.Thead(
                    html.Tr([
                        html.Th(col, style={
                            "padding": "10px",
                            "textAlign": "center",
                            "fontFamily": "ubuntu",
                            "color": "white",
                            "fontSize": "16px",
                            "fontWeight": "bold",
                            "backgroundColor": "#264653",
                            "height": "45px",
                            "position": "sticky",
                            "top": 0,
                            "zIndex": 10,
                        })
                        for col in [province_col] + animal_cols
                    ]),
                    style={"display": "table-header-group"}
                ),
                html.Tbody([
                    html.Tr([
                        html.Td(str(idx), style={
                            "padding": "8px 10px",
                            "fontFamily": "ubuntu",
                            "fontSize": "15px",
                            "fontWeight": "bold",
                            "textAlign": "center",
                            "height": "42px",
                            "borderBottom": "1px solid #eee",
                            "backgroundColor": "#dde9e6" if is_province else "#fff",
                        }),
                        *[
                            html.Td(f"{val:,.0f}" if pd.notna(val) else "-", style={
                                "padding": "8px 10px",
                                "fontFamily": "ubuntu",
                                "fontSize": "15px",
                                "fontWeight": "bold",
                                "textAlign": "center",
                                "height": "42px",
                                "borderBottom": "1px solid #eee",
                                "backgroundColor": "#dde9e6" if is_province else "#fff",
                            })
                            for val in row
                        ]
                    ])
                    for idx, row in df_indexed.iterrows()
                    for is_province in [_is_province_row(idx)]
                ])
            ], style={
                "width": "100%",
                "borderCollapse": "collapse",
            })
        ]
    )
    
def _build_district_animal_selector_buttons(animal_cols):
    """Same as _build_animal_selector_buttons but with ids scoped to the
    District Stats tab so its callbacks don't collide with National
    Overview's ls-animal-btn-* ids."""
    if not animal_cols:
        return html.Div("No animal data available", style={"padding": "10px", "color": "#888"})
    all_animals = [("Total", "🌐 All Animals")] + [
        (c, f"{_ANIMAL_EMOJIS.get(c, '🐾')} {c}") for c in animal_cols
    ]
    return html.Div(
        [
            html.Div([
                html.Div(
                    html.Button(
                        label,
                        id=f"ls-district-animal-btn-{value}",
                        className="ls-animal-selector-btn",
                        style={
                            "backgroundColor": "#264653" if value == "Total" else "#f0f2f5",
                            "color": "white" if value == "Total" else "#264653",
                            "border": "none",
                            "padding": "8px 16px",
                            "borderRadius": "20px",
                            "cursor": "pointer",
                            "fontSize": "18px",
                            "fontWeight": "500",
                            "transition": "all 0.3s ease",
                            "fontFamily": "ubuntu",
                            "margin": "0 3px",
                            "boxShadow": "0 2px 4px rgba(0,0,0,0.1)" if value == "Total" else "none",
                        }
                    ),
                    style={"display": "inline-block"}
                )
                for value, label in all_animals
            ], style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "6px",
                "padding": "5px 0",
            })
        ],
        id="ls-district-animal-selector-container",
    )
    
def _build_district_stats_chart_card():
    """Right-panel card for District Stats: animal-selector buttons + horizontal bar chart."""
    return html.Div(
        [
            html.Div(
                id="ls-district-animal-buttons-container",
                style={"marginBottom": "10px"}
            ),
            dcc.Graph(
                id="ls-district-bar-chart",
                figure={},
                config={"displayModeBar": False},
                style={
                    "height": "calc(100vh - 420px)",
                    "width": "100%",
                },
            ),
        ],
        style={
            "backgroundColor": "#fff",
            "borderRadius": "10px",
            "padding": "12px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
            "border": "1px solid #dce3e0",
            "height": "100%",
            "display": "flex",
            "flexDirection": "column",
        },
    )

def _build_group_farming_table(farming_amount_group, farming_amount_animal, province_col="Province"):
    """Combined Group Count / Animal Count table (multi-index header like
    Farm Stats / Yearly Stats), with North/Middle/South region rows tinted
    to stand out from per-province rows."""
    animal_cols = [c for c in farming_amount_group.columns if c != province_col]

    df_combined = pd.DataFrame()
    df_combined[province_col] = farming_amount_group[province_col]
    for col in animal_cols:
        df_combined[f"Group_{col}"] = farming_amount_group[col]
        df_combined[f"Animal_{col}"] = farming_amount_animal[col]

    # Total row sums province-level rows only, so North/Middle/South
    # subtotals (if they already roll up other rows) aren't double-counted.
    is_region_mask = df_combined[province_col].apply(_is_region_row)
    total_row = {province_col: "Total"}
    for col in df_combined.columns:
        if col != province_col:
            total_row[col] = df_combined.loc[~is_region_mask, col].sum()

    df_with_total = pd.concat([df_combined, pd.DataFrame([total_row])], ignore_index=True)
    df_indexed = df_with_total.set_index(province_col)
    n_rows = len(df_indexed)

    header_row1 = [html.Th(province_col, style={
        "padding": "10px", "textAlign": "center", "fontFamily": "ubuntu",
        "color": "white", "fontSize": "16px", "fontWeight": "bold",
        "backgroundColor": "#264653", "height": "45px",
        "position": "sticky", "top": 0, "zIndex": 10, "rowSpan": "2",
    })]
    for col in animal_cols:
        header_row1.append(html.Th(col, colSpan=2, style={
            "padding": "10px", "textAlign": "center", "fontFamily": "ubuntu",
            "color": "white", "fontSize": "16px", "fontWeight": "bold",
            "backgroundColor": "#264653", "height": "45px",
            "position": "sticky", "top": 0, "zIndex": 10,
        }))

    header_row2 = [html.Th("    ", style={
        "padding": "8px 10px", "textAlign": "center", "fontFamily": "ubuntu",
        "color": "white", "fontSize": "14px", "fontWeight": "500",
        "backgroundColor": "#2a6f7f", "height": "35px",
        "position": "sticky", "top": "45px", "zIndex": 10,
    })]
    for col in animal_cols:
        for sub in ["Group Count", "Animal Count"]:
            header_row2.append(html.Th(sub, style={
                "padding": "8px 10px", "textAlign": "center", "fontFamily": "ubuntu",
                "color": "white", "fontSize": "14px", "fontWeight": "500",
                "backgroundColor": "#2a6f7f", "height": "35px",
                "position": "sticky", "top": "45px", "zIndex": 10,
            }))

    return html.Div(
        style={
            "overflowX": "auto",
            "overflowY": "auto",
            "maxHeight": "calc(100vh - 320px)",
            "borderRadius": "8px",
        },
        children=[
            html.Table([
                html.Thead([html.Tr(header_row1), html.Tr(header_row2)]),
                html.Tbody([
                    html.Tr([
                        html.Td(str(idx), style={
                            "padding": "8px 10px",
                            "fontFamily": "ubuntu",
                            "fontSize": "15px",
                            "fontWeight": "bold",
                            "textAlign": "center",
                            "height": "42px",
                            "borderBottom": "1px solid #eee",
                            "backgroundColor": "#fcecd9" if is_region else ("#f7faf9" if is_last else "#fff"),
                            **({"borderTop": "2px solid #264653"} if is_last else {}),
                        }),
                        *[
                            html.Td(f"{int(val):,.0f}" if pd.notna(val) and val != 0 else "-", style={
                                "padding": "8px 10px",
                                "fontFamily": "ubuntu",
                                "fontSize": "15px",
                                "fontWeight": "bold",
                                "textAlign": "center",
                                "height": "42px",
                                "borderBottom": "1px solid #eee",
                                "backgroundColor": "#fcecd9" if is_region else ("#f7faf9" if is_last else "#fff"),
                                **({"borderTop": "2px solid #264653"} if is_last else {}),
                            })
                            for val in row
                        ]
                    ])
                    for row_num, (idx, row) in enumerate(df_indexed.iterrows())
                    for is_last in [row_num == n_rows - 1]
                    for is_region in [(not is_last) and _is_region_row(idx)]
                ])
            ], style={"width": "100%", "borderCollapse": "collapse"})
        ]
    )

def _build_group_farming_map_tabs(selected_tab="group"):
    """Build sub-tab buttons for Group Farming Statistics right panel (map view)."""
    return html.Div(
        [
            html.Div([
                html.Div(
                    html.Button(
                        label,
                        id=f"ls-group-right-{value}",
                        className="ls-sub-tab-btn",
                        style={
                            "backgroundColor": "#264653" if value == selected_tab else "#f0f2f5",
                            "color": "white" if value == selected_tab else "#264653",
                            "border": "none",
                            "padding": "8px 16px",
                            "borderRadius": "20px",
                            "cursor": "pointer",
                            "fontSize": "15px",
                            "fontWeight": "500",
                            "transition": "all 0.3s ease",
                            "fontFamily": "ubuntu",
                            "margin": "0 3px",
                            "boxShadow": "0 2px 4px rgba(0,0,0,0.1)" if value == selected_tab else "none",
                        }
                    ),
                    style={"display": "inline-block"}
                )
                for value, label in _GROUP_FARMING_MAP_TABS
            ], style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "6px",
                "padding": "5px 0",
                "marginBottom": "10px",
            })
        ],
        id="ls-group-right-sub-tabs",
    )

def _build_group_farming_map_card():
    """Right-panel card for Group Farming Statistics: metric selector + choropleth."""
    return html.Div(
        [
            html.Div(
                id="ls-group-map-tabs-container",
                style={"marginBottom": "10px"}
            ),
            html.Iframe(
                id="ls-group-farming-province-map",
                srcDoc="",
                style={
                    "height": "calc(100vh - 380px)",
                    "width": "100%",
                    "minHeight": "400px",
                    "border": "none",
                },
            ),
        ],
        style={
            "backgroundColor": "#fff",
            "borderRadius": "10px",
            "padding": "12px",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
            "border": "1px solid #dce3e0",
            "height": "100%",
            "display": "flex",
            "flexDirection": "column",
        },
    )

def _build_breeding_stats_table(df_raw, max_height="calc(100vh - 320px)"):
    import re
    
    def clean_header(val):
        """Remove spaces and all symbols from the beginning of header values"""
        if pd.isna(val):
            return val
        val = str(val).strip()
        # Remove common symbols from the start
        val = re.sub(r'^[\s]*[/\-:;,.!@#$%^&*()_+=\[\]{}|\\<>?~`]+[\s]*', '', val)
        val = re.sub(r'^[\s]*[^a-zA-Z0-9\s]+[\s]*', '', val)
        return val

    # Keep the RAW (pre-forward-fill) row 0 around — this is what tells us
    # which columns are the actual START of a merged header cell
    header_row1_raw = df_raw.iloc[0].tolist()
    header_row1_vals = df_raw.iloc[0].ffill().tolist()
    header_row2_vals = df_raw.iloc[1].fillna("").tolist()
    
    # Clean both header rows
    header_row1_vals = [clean_header(val) for val in header_row1_vals]
    header_row2_vals = [clean_header(val) for val in header_row2_vals]

    data_rows = df_raw.iloc[2:].reset_index(drop=True)
    n_cols = len(header_row1_vals)
    n_rows = len(data_rows)

    # Columns where row 0 ORIGINALLY had its own value (not inherited via ffill)
    valid_header_cols = []
    for i in range(n_cols):
        raw_val = header_row1_raw[i]
        if pd.notna(raw_val) and str(raw_val).strip() not in ('', 'nan', 'None'):
            valid_header_cols.append(i)

    # Pastel colors cycled per group
    group_colors = [
        "#f8e8e8",  # Light pink/red
        "#e8f0e8",  # Light green
        "#e8e8f8",  # Light blue
        "#f8f0e8",  # Light peach
        "#f0f0e8",  # Light yellow
        "#e8f0f8",  # Light sky blue
        "#f8e8f0",  # Light purple
        "#f0e8f0",  # Light lavender
    ]

    # Determine which group each column belongs to
    col_group = {}
    group_index = 0
    for i in range(n_cols):
        if i in valid_header_cols:
            group_index += 1
        col_group[i] = group_index

    # Get unique animal groups from valid header columns
    animal_groups = []
    for i in valid_header_cols:
        if i < len(header_row1_vals):
            animal_groups.append(header_row1_vals[i])
    
    # Get sub-headers for each group (from header_row2 at the group start)
    group_sub_headers = {}
    for i in valid_header_cols:
        group_name = header_row1_vals[i]
        if group_name not in group_sub_headers:
            # Collect all sub-headers until next valid header
            sub_headers = []
            j = i
            while j < n_cols and (j not in valid_header_cols or j == i):
                if j < len(header_row2_vals) and header_row2_vals[j]:
                    sub_headers.append(header_row2_vals[j])
                else:
                    sub_headers.append("")
                j += 1
            group_sub_headers[group_name] = sub_headers

    header_cell_style = {
        "padding": "10px",
        "textAlign": "center",
        "fontFamily": "ubuntu",
        "color": "white",
        "fontSize": "16px",
        "fontWeight": "bold",
        "backgroundColor": "#264653",
        "height": "45px",
        "position": "sticky",
        "top": 0,
        "zIndex": 10,
        "whiteSpace": "nowrap",
    }

    sub_header_cell_style = {
        "padding": "8px 10px",
        "textAlign": "center",
        "fontFamily": "ubuntu",
        "color": "white",
        "fontSize": "14px",
        "fontWeight": "500",
        "backgroundColor": "#2a6f7f",
        "height": "35px",
        "position": "sticky",
        "top": "45px",
        "zIndex": 10,
        "whiteSpace": "nowrap",
    }

    # Build header row 1 (Animal groups with merged spans)
    header_row1 = []
    # First column is Province (or similar) - keep it separate
    if 0 in valid_header_cols:
        # If Province is a valid header, handle it specially
        header_row1.append(html.Th("Province", style={
            **header_cell_style,
            "rowSpan": "2",
            "borderRight": "0px solid #e0e0e0",
            "minWidth": "120px",
        }))
    else:
        header_row1.append(html.Th("", style={
            **header_cell_style,
            "rowSpan": "2",
            "borderRight": "0px solid #e0e0e0",
            "minWidth": "120px",
        }))
    
    # Build groups for header row 1
    col_idx = 0
    processed_indices = set()
    for i in valid_header_cols:
        if i in processed_indices:
            continue
        # Find span for this group
        span = 1
        j = i + 1
        while j < n_cols and j not in valid_header_cols:
            span += 1
            j += 1
        # Skip Province column (index 0)
        if i == 0:
            processed_indices.add(i)
            continue
        
        style = header_cell_style.copy()
        # Add left border for each group after the first
        if len(header_row1) > 1:
            style["borderLeft"] = "0px solid #e0e0e0"
        
        label = header_row1_vals[i] if i < len(header_row1_vals) else ""
        header_row1.append(html.Th(str(label), colSpan=span, style=style))
        
        # Mark all columns in this group as processed
        for k in range(i, j):
            processed_indices.add(k)

    # Build header row 2 (Sub-headers: Farm, Number of male breeder, etc.)
    header_row2 = []
    # Province sub-header (empty)
    header_row2.append(html.Th("", style={
        **sub_header_cell_style,
        "borderRight": "0px solid #e0e0e0",
    }))
    
    # Sub-headers for each group
    for i in valid_header_cols:
        if i == 0:  # Skip Province
            continue
        # Get sub-headers for this group
        sub_headers = []
        j = i
        while j < n_cols and (j not in valid_header_cols or j == i):
            if j < len(header_row2_vals) and header_row2_vals[j]:
                sub_headers.append(header_row2_vals[j])
            else:
                sub_headers.append("")
            j += 1
        
        for sub_idx, sub_header in enumerate(sub_headers):
            style = sub_header_cell_style.copy()
            # Add left border for the first sub-header of each group (except the first group)
            if i != valid_header_cols[0] and sub_idx == 0:
                style["borderLeft"] = "0px solid #e0e0e0"
            header_row2.append(html.Th(str(sub_header) if sub_header else "    ", style=style))

    def _fmt(val, col_idx, is_last):
        if col_idx == 0 and is_last:
            return "Total"
        if pd.isna(val) or str(val).strip() == "":
            return "-"
        if col_idx == 0:
            return str(val)
        try:
            return f"{float(val):,.0f}"
        except (TypeError, ValueError):
            return str(val)

    body_rows = []
    for row_num, (_, row) in enumerate(data_rows.iterrows()):
        is_last = row_num == n_rows - 1
        row_cells = []
        
        # Province column (index 0)
        province_style = {
            "padding": "8px 10px",
            "fontFamily": "ubuntu",
            "fontSize": "15px",
            "fontWeight": "bold",
            "textAlign": "center",
            "height": "42px",
            "borderBottom": "1px solid #eee",
            "borderRight": "0px solid #e0e0e0",
            "minWidth": "120px",
        }
        if is_last:
            province_style["borderTop"] = "2px solid #264653"
            province_style["backgroundColor"] = "#f7faf9"
        
        province_val = _fmt(row.iloc[0], 0, is_last)
        row_cells.append(html.Td(province_val, style=province_style))
        
        # Data columns (1 to n_cols-1)
        for c in range(1, n_cols):
            cell_style = {
                "padding": "8px 10px",
                "fontFamily": "ubuntu",
                "fontSize": "15px",
                "fontWeight": "bold",
                "textAlign": "center",
                "height": "42px",
                "borderBottom": "1px solid #eee",
                "whiteSpace": "nowrap",
            }
            
            # Add left border if this column starts a new group
            if c in valid_header_cols:
                cell_style["borderLeft"] = "0px solid #e0e0e0"
            
            # Add background color based on group
            group_num = col_group.get(c, 0)
            if group_num > 0:
                cell_style["backgroundColor"] = group_colors[(group_num - 1) % len(group_colors)]
            
            if is_last:
                cell_style["borderTop"] = "2px solid #264653"
                cell_style["backgroundColor"] = "#f7faf9"
                if c in valid_header_cols:
                    cell_style["borderLeft"] = "0px solid #e0e0e0"
            
            row_cells.append(html.Td(_fmt(row.iloc[c], c, is_last), style=cell_style))
        
        body_rows.append(html.Tr(row_cells))

    return html.Div(
        style={
            "overflowX": "auto",
            "overflowY": "auto",
            "maxHeight": max_height,
            "borderRadius": "8px",
        },
        children=[
            html.Table([
                html.Thead([html.Tr(header_row1), html.Tr(header_row2)]),
                html.Tbody(body_rows),
            ], style={"width": "100%", "borderCollapse": "collapse"})
        ]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Layout builder
# ─────────────────────────────────────────────────────────────────────────────
def build_livestock_stats_tab() -> html.Div:
    """Return the complete layout for the Livestock Statistics tab."""
    
    stores = html.Div([
        dcc.Store(id="ls-load-trigger", data=0),
        dcc.Store(id='ls-auto-click-store', data=None),
        dcc.Store(id="ls-selected-animal", data="Total"),  # Add this store
        dcc.Store(id="ls-farm-left-tab", data="tabular-view"),  # Farm stats left sub-tab
        dcc.Store(id="ls-farm-right-tab", data="farms"),  # Farm stats right sub-tab
        dcc.Store(id="ls-yearly-left-tab", data="tabular-view"),  # Yearly stats left sub-tab
        dcc.Store(id="ls-yearly-right-tab", data="2024"),  # Yearly stats right sub-tab (year selection)
        dcc.Store(id="ls-district-selected-animal", data="Total"),  # District stats animal filter
        dcc.Store(id="ls-group-farming-right-tab", data="group"),  # Group farming right panel metric
    ], style={"display": "none"})
    # ── Custom selector buttons instead of tabs ──────────────────────────
    selector_buttons = _build_selector_buttons()
    # ── Left panels (one per tab, toggled via display style) ─────────────
    left_panels = []
    for value, label in _MAIN_TABS:
        if value == "national-overview":
            content = html.Div(
                id="ls-national-table-container",
                style={
                    "backgroundColor": "#fff",
                    "borderRadius": "10px",
                    "padding": "10px",
                    "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
                    "border": "1px solid #dce3e0",
                    "height": "100%",
                },
            )
        elif value == "farm-stats":
            # Farm Statistics left panel with sub-tabs
            content = html.Div([
                _build_farm_stats_sub_tabs(),
                html.Div(id="ls-farm-left-content", style={"height": "100%"})
            ], style={
                "backgroundColor": "#fff",
                "borderRadius": "10px",
                "padding": "10px",
                "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
                "border": "1px solid #dce3e0",
                "height": "100%",
            })
        elif value == "yearly-stats":
            # Yearly Statistics left panel with sub-tabs
            content = html.Div([
                _build_yearly_stats_sub_tabs(),
                html.Div(id="ls-yearly-left-content", style={"height": "100%"})
            ], style={
                "backgroundColor": "#fff",
                "borderRadius": "10px",
                "padding": "10px",
                "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
                "border": "1px solid #dce3e0",
                "height": "100%",
            })
        elif value == "district-stats":
            content = html.Div(
                id="ls-district-table-container",
                style={
                    "backgroundColor": "#fff",
                    "borderRadius": "10px",
                    "padding": "10px",
                    "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
                    "border": "1px solid #dce3e0",
                    "height": "100%",
                },
            )
        elif value == "group-farming":
            content = html.Div(
                id="ls-group-farming-table-container",
                style={
                    "backgroundColor": "#fff",
                    "borderRadius": "10px",
                    "padding": "10px",
                    "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
                    "border": "1px solid #dce3e0",
                    "height": "100%",
                },
            )
        elif value == "breeding-stats":
            content = html.Div(
                id="ls-breeding-table-container",
                style={
                    "backgroundColor": "#fff",
                    "borderRadius": "10px",
                    "padding": "10px",
                    "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
                    "border": "1px solid #dce3e0",
                    "height": "100%",
                },
            )
        else:
            content = _placeholder_panel(label)
        left_panels.append(
            html.Div(
                content,
                id=f"ls-left-{value}",
                style={"display": "block", "height": "100%"} if value == "national-overview" else {"display": "none"},
            )
        )
    # ── Right panels (one per tab, toggled via display style) ────────────
    right_panels = []
    for value, label in _MAIN_TABS:
        if value == "national-overview":
            content = _build_national_map_card()
        elif value == "farm-stats":
            content = _build_farm_stats_map_card()
        elif value == "yearly-stats":
            content = _build_yearly_stats_map_card()
        elif value == "district-stats":
            content = _build_district_stats_chart_card()
        elif value == "group-farming":
            content = _build_group_farming_map_card()
        elif value == "breeding-stats":
            content = html.Div()
        else:
            content = _placeholder_panel(label)
        right_panels.append(
            html.Div(
                content,
                id=f"ls-right-{value}",
                style={"display": "flex", "flexDirection": "column", "height": "100%"} if value == "national-overview" else {"display": "none"},
            )
        )
    left_col = html.Div(left_panels, id="ls-left-col", style={
        "flex": "6",
        "minWidth": "0",
        "marginRight": "15px",
        "display": "flex",
        "flexDirection": "column",
        "height": "100%",
    })
    right_col = html.Div(right_panels, id="ls-right-col", style={
        "flex": "4",
        "minWidth": "0",
        "display": "flex",
        "flexDirection": "column",
        "height": "100%",
    })

    main_row = html.Div(
        [
            html.Div(
                dcc.Loading(
                    id="ls-loading-left",
                    type="circle",
                    color="#264653",
                    children=left_col,
                    style={"width": "100%"},
                ),
                id="ls-left-col-wrapper",
                style={"flex": "6", "minWidth": "0"},
            ),
            html.Div(
                dcc.Loading(
                    id="ls-loading-right",
                    type="circle",
                    color="#264653",
                    children=right_col,
                    style={"width": "100%"},
                ),
                id="ls-right-col-wrapper",
                style={"flex": "4", "minWidth": "0"},
            ),
        ],
        style={"display": "flex", "flexDirection": "row", "alignItems": "stretch", "width": "100%"},
    )
    return html.Div(
        [stores, selector_buttons, main_row],
        className="tab-content",
        style={"padding": "16px 18px 10px", "width": "100%", "boxSizing": "border-box"},
    )
# ─────────────────────────────────────────────────────────────────────────────
# Callback registration
# ─────────────────────────────────────────────────────────────────────────────
def register_livestock_stats_callbacks(app) -> None:
    """Register all Dash callbacks needed by the Livestock Statistics tab."""
    try:
        livestock_stats,_, _, _, _ ,_, _, _, _ = load_livestock_stats()
        _animal_values = ["Total"] + [c for c in livestock_stats.columns if c != "Province"]
    except Exception:
        _animal_values = ["Total"]

    # ── 1. Handle main button clicks and toggle panel visibility ──────────
    @app.callback(
        [Output(f"ls-left-{v}", "style") for v in _TAB_VALUES]
        + [Output(f"ls-right-{v}", "style") for v in _TAB_VALUES]
        + [Output(f"ls-btn-{v}", "style") for v in _TAB_VALUES]
        + [Output("ls-left-col-wrapper", "style"), Output("ls-right-col-wrapper", "style")],
        [Input(f"ls-btn-{v}", "n_clicks") for v in _TAB_VALUES],
        prevent_initial_call=True,
    )
    def ls_handle_main_button_clicks(*args):
        if not ctx.triggered:
            raise PreventUpdate
        
        triggered_id = ctx.triggered_id
        if triggered_id is None:
            raise PreventUpdate
        
        selected_value = triggered_id.replace('ls-btn-', '')
        print("Selected main tab:", selected_value)
        
        # Build styles for panels
        left_styles = [
            {"display": "block", "height": "100%"} if v == selected_value else {"display": "none"}
            for v in _TAB_VALUES
        ]
        right_styles = [
            {"display": "flex", "flexDirection": "column", "height": "100%"} if v == selected_value else {"display": "none"}
            for v in _TAB_VALUES
        ]
        
        # Build styles for main buttons
        button_styles = []
        for v in _TAB_VALUES:
            if v == selected_value:
                button_styles.append({
                    "backgroundColor": "#264653",
                    "color": "white",
                    "border": "none",
                    "padding": "10px 20px",
                    "borderRadius": "25px",
                    "cursor": "pointer",
                    "fontSize": "19px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 4px",
                    "boxShadow": "0 2px 8px rgba(38, 70, 83, 0.3)",
                    "transform": "scale(1.05)",
                })
            else:
                button_styles.append({
                    "backgroundColor": "#f0f2f5",
                    "color": "#264653",
                    "border": "none",
                    "padding": "10px 20px",
                    "borderRadius": "25px",
                    "cursor": "pointer",
                    "fontSize": "19px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 4px",
                    "boxShadow": "none",
                    "transform": "scale(1)",
                })
        if selected_value == "breeding-stats":
            left_col_style = {"flex": "1 1 100%", "minWidth": "0"}
            right_col_style = {"display": "none"}
        else:
            left_col_style = {"flex": "6", "minWidth": "0"}
            right_col_style = {"flex": "4", "minWidth": "0"}

        return left_styles + right_styles + button_styles + [left_col_style, right_col_style]

        # return left_styles + right_styles + button_styles + [left_col_style, right_col_style]
        # return left_styles + right_styles + button_styles
    
    # ── 2. National Overview — table with Total row ───────────────────────
    @app.callback(
        Output("ls-national-table-container", "children"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_update_national_table(_trigger):
        try:
            livestock_stats,_ , _, _, _ ,_, _, _, _ = load_livestock_stats()
            return _build_national_table_with_total(livestock_stats)
        except Exception as e:
            return html.Div(f"Error loading table: {str(e)}",
                            style={"color": "red", "padding": "10px"})
    # ── 3. National Overview — populate animal selector buttons ───────────
    @app.callback(
        Output("ls-animal-buttons-container", "children"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_populate_animal_buttons(_trigger):
        try:
            livestock_stats, _, _, _, _ ,_, _, _, _ = load_livestock_stats()
            animal_cols = [c for c in livestock_stats.columns if c != "Province"]
        except Exception:
            animal_cols = []
        
        return _build_animal_selector_buttons(animal_cols)
    # ── 4. Handle animal button clicks using a store ──────────────────────
    @app.callback(
        Output("ls-selected-animal", "data"),
        [Input(f"ls-animal-btn-{v}", "n_clicks") for v in _animal_values],
        prevent_initial_call=True,
    )
    def ls_update_selected_animal(*args):
        if not ctx.triggered:
            raise PreventUpdate
        
        triggered_id = ctx.triggered_id
        if triggered_id is None:
            raise PreventUpdate
        
        selected_value = triggered_id.replace('ls-animal-btn-', '')
        return selected_value
    # ── 5. Update map based on selected animal (from store) ──────────────
    @app.callback(
        Output("ls-province-map", "srcDoc"),
        Input("ls-selected-animal", "data"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_update_province_map(selected_animal, _trigger):
        if selected_animal is None:
            selected_animal = "Total"
        
        try:
            livestock_stats, _, _, _, _ ,_, _, _, _ = load_livestock_stats()
            animal_cols = [c for c in livestock_stats.columns if c != "Province"]
            df_map = livestock_stats.copy()
            if not selected_animal or selected_animal == "Total":
                df_map["Total"] = df_map[animal_cols].sum(axis=1)
                value_col = "Total"
            else:
                value_col = selected_animal
            # fig = create_livestock_province_map(df_map, animal_col=value_col)
            fmap = create_livestock_province_map(df_map, animal_col=value_col)
            return fmap.get_root().render()
            
        except Exception as e:
            from plotly import graph_objects as go
            fig = go.Figure()
            fig.add_annotation(
                text=f"Error: {e}", xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False, font=dict(size=14, color="#888"),
            )
            fig.update_layout(
                plot_bgcolor="white", 
                paper_bgcolor="white",
                xaxis=dict(visible=False), 
                yaxis=dict(visible=False),
                margin=dict(l=0, r=0, t=0, b=0),
            )
            return fig
    # ── 6. Update animal button styles when clicked ───────────────────────
    @app.callback(
        [Output(f"ls-animal-btn-{v}", "style") for v in _animal_values],
        [Input(f"ls-animal-btn-{v}", "n_clicks") for v in _animal_values],
        prevent_initial_call=True,
    )
    def ls_update_animal_button_styles(*args):
        if not ctx.triggered:
            raise PreventUpdate
        
        triggered_id = ctx.triggered_id
        if triggered_id is None:
            raise PreventUpdate
        
        selected_value = triggered_id.replace('ls-animal-btn-', '')
        
        # Build styles for animal buttons
        button_styles = []
        for v in _animal_values:
            if v == selected_value:
                button_styles.append({
                    "backgroundColor": "#264653",
                    "color": "white",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "13px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "0 2px 8px rgba(38, 70, 83, 0.3)",
                    "transform": "scale(1.05)",
                })
            else:
                button_styles.append({
                    "backgroundColor": "#f0f2f5",
                    "color": "#264653",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "13px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "none",
                    "transform": "scale(1)",
                })
        
        return button_styles

    # ── 7. Farm Statistics - Left sub-tab button clicks ───────────────────
    @app.callback(
        Output("ls-farm-left-tab", "data"),
        [Input("ls-farm-left-tabular-view", "n_clicks"),
         Input("ls-farm-left-distribution-charts", "n_clicks")],
        prevent_initial_call=True,
    )
    def ls_farm_left_tab_click(tabular_clicks, charts_clicks):
        if not ctx.triggered:
            raise PreventUpdate
        
        triggered_id = ctx.triggered_id
        if triggered_id is None:
            raise PreventUpdate
        
        return triggered_id.replace('ls-farm-left-', '')

    # ── 8. Farm Statistics - Update left sub-tab button styles ────────────
    @app.callback(
        [Output("ls-farm-left-tabular-view", "style"),
         Output("ls-farm-left-distribution-charts", "style")],
        Input("ls-farm-left-tab", "data"),
        prevent_initial_call=False,
    )
    def ls_farm_left_tab_styles(selected_tab):
        if selected_tab is None:
            selected_tab = "tabular-view"
        
        styles = []
        for value, _ in _FARM_STATS_SUB_TABS:
            if value == selected_tab:
                styles.append({
                    "backgroundColor": "#264653",
                    "color": "white",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "15px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "0 2px 8px rgba(38, 70, 83, 0.3)",
                    "transform": "scale(1.05)",
                })
            else:
                styles.append({
                    "backgroundColor": "#f0f2f5",
                    "color": "#264653",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "15px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "none",
                    "transform": "scale(1)",
                })
        
        return styles

    # ── 9. Farm Statistics - Update left panel content ────────────────────
    @app.callback(
        Output("ls-farm-left-content", "children"),
        Input("ls-farm-left-tab", "data"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_farm_left_content(selected_tab, _trigger):
        if selected_tab is None:
            selected_tab = "tabular-view"
        
        try:
            _, _, _, data_farm, data_amount, _, _, _, _ = load_livestock_stats()
            
            if selected_tab == "tabular-view":
                # Build combined table showing both farm count and animal count
                return _build_farm_stats_table(data_farm, data_amount)
            elif selected_tab == "distribution-charts":
                # Create distribution charts - farm count distribution and animal count distribution
                fig_farm, fig_amount = create_livestock_animal_type_charts(data_farm, data_amount)
                return html.Div(
                        [
                            html.Div(
                                dcc.Graph(
                                    figure=fig_farm,
                                    config={"displayModeBar": False},
                                    style={"height": "500px", "width": "100%"},
                                ),
                                style={
                                    "flex": "1",
                                    "backgroundColor": "#fff",
                                    "borderRadius": "10px",
                                    "padding": "10px",
                                    "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
                                    "border": "1px solid #dce3e0",
                                    "margin": "25px 10px",
                                }
                            ),
                            html.Div(
                                dcc.Graph(
                                    figure=fig_amount,
                                    config={"displayModeBar": False},
                                    style={"height": "500px", "width": "100%"},
                                ),
                                style={
                                    "flex": "1",
                                    "backgroundColor": "#fff",
                                    "borderRadius": "10px",
                                    "padding": "10px",
                                    "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
                                    "border": "1px solid #dce3e0",
                                    "margin": "25px 10px",
                                }
                            ),
                        ],
                        style={
                            "display": "flex",
                            "flexDirection": "row",
                            "alignItems": "center",
                            "height": "calc(100vh - 370px)"
                        }
                    )
        except Exception as e:
            return html.Div(f"Error loading farm statistics: {str(e)}",
                            style={"color": "red", "padding": "10px"})

    # ── 10. Farm Statistics - Right sub-tab button clicks ─────────────────
    @app.callback(
        Output("ls-farm-right-tab", "data"),
        [Input("ls-farm-right-farms", "n_clicks"),
         Input("ls-farm-right-amount", "n_clicks")],
        prevent_initial_call=True,
    )
    def ls_farm_right_tab_click(farms_clicks, amount_clicks):
        if not ctx.triggered:
            raise PreventUpdate
        
        triggered_id = ctx.triggered_id
        if triggered_id is None:
            raise PreventUpdate
        
        return triggered_id.replace('ls-farm-right-', '')

    # ── 11. Farm Statistics - Update right sub-tab button styles ──────────
    @app.callback(
        [Output("ls-farm-right-farms", "style"),
         Output("ls-farm-right-amount", "style")],
        Input("ls-farm-right-tab", "data"),
        prevent_initial_call=False,
    )
    def ls_farm_right_tab_styles(selected_tab):
        if selected_tab is None:
            selected_tab = "farms"
        
        styles = []
        for value, _ in _FARM_STATS_MAP_TABS:
            if value == selected_tab:
                styles.append({
                    "backgroundColor": "#264653",
                    "color": "white",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "15px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "0 2px 8px rgba(38, 70, 83, 0.3)",
                    "transform": "scale(1.05)",
                })
            else:
                styles.append({
                    "backgroundColor": "#f0f2f5",
                    "color": "#264653",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "15px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "none",
                    "transform": "scale(1)",
                })
        
        return styles

    # ── 12. Farm Statistics - Populate map tabs container ──────────────────
    @app.callback(
        Output("ls-farm-map-tabs-container", "children"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_populate_farm_map_tabs(_trigger):
        return _build_farm_stats_map_tabs()

    # ── 13. Farm Statistics - Update map based on selected metric ─────────
    @app.callback(
        Output("ls-farm-province-map", "srcDoc"),
        Input("ls-farm-right-tab", "data"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_update_farm_map(selected_metric, _trigger):
        if selected_metric is None:
            selected_metric = "farms"
        
        try:
            _, _, _, data_farm, data_amount, _, _, _, _ = load_livestock_stats()
            
            if selected_metric == "farms":
                # Use farm data - sum all animal columns to get total farms per province
                df_map = data_farm.copy()
                animal_cols = [c for c in df_map.columns if c != "Province"]
                df_map["Total Farms"] = df_map[animal_cols].sum(axis=1)
                fig = create_livestock_province_map(df_map, animal_col="Total Farms")
                
            else:  # amount
                # Use amount data - sum all animal columns to get total animals per province
                df_map = data_amount.copy()
                animal_cols = [c for c in df_map.columns if c != "Province"]
                df_map["Total Animals"] = df_map[animal_cols].sum(axis=1)
                fig = create_livestock_province_map(df_map, animal_col="Total Animals")
            
            return fig.get_root().render()
        except Exception as e:
            from plotly import graph_objects as go
            fig = go.Figure()
            fig.add_annotation(
                text=f"Error: {e}", xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False, font=dict(size=14, color="#888"),
            )
            fig.update_layout(
                plot_bgcolor="white", 
                paper_bgcolor="white",
                xaxis=dict(visible=False), 
                yaxis=dict(visible=False),
                margin=dict(l=0, r=0, t=0, b=0),
            )
            return fig
        
    # ── 14. Yearly Stats - Left sub-tab button clicks ───────────────────
    @app.callback(
        Output("ls-yearly-left-tab", "data"),
        [Input("ls-yearly-left-tabular-view", "n_clicks"),
        Input("ls-yearly-left-distribution-charts", "n_clicks")],
        prevent_initial_call=True,
    )
    def ls_yearly_left_tab_click(tabular_clicks, charts_clicks):
        if not ctx.triggered:
            raise PreventUpdate
        
        triggered_id = ctx.triggered_id
        if triggered_id is None:
            raise PreventUpdate
        
        return triggered_id.replace('ls-yearly-left-', '')

    # ── 15. Yearly Stats - Update left sub-tab button styles ────────────
    @app.callback(
        [Output("ls-yearly-left-tabular-view", "style"),
        Output("ls-yearly-left-distribution-charts", "style")],
        Input("ls-yearly-left-tab", "data"),
        prevent_initial_call=False,
    )
    def ls_yearly_left_tab_styles(selected_tab):
        if selected_tab is None:
            selected_tab = "tabular-view"
        
        styles = []
        for value, _ in _YEARLY_STATS_SUB_TABS:
            if value == selected_tab:
                styles.append({
                    "backgroundColor": "#264653",
                    "color": "white",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "15px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "0 2px 8px rgba(38, 70, 83, 0.3)",
                    "transform": "scale(1.05)",
                })
            else:
                styles.append({
                    "backgroundColor": "#f0f2f5",
                    "color": "#264653",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "15px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "none",
                    "transform": "scale(1)",
                })
        
        return styles

    # ── 16. Yearly Stats - Update left panel content ────────────────────
    @app.callback(
        Output("ls-yearly-left-content", "children"),
        Input("ls-yearly-left-tab", "data"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_yearly_left_content(selected_tab, _trigger):
        if selected_tab is None:
            selected_tab = "tabular-view"
        
        try:
            livestock_stats, df_24, df_25, data_farm, data_amount, _, _, _, _ = load_livestock_stats()
            
            if selected_tab == "tabular-view":
                # Build combined table showing both years data
                return _build_yearly_stats_table(df_24, df_25)
            elif selected_tab == "distribution-charts":                
                # Create pie charts for both years
                fig_2024 = create_livestock_composition_chart(df_24, year="2024")
                fig_2025 = create_livestock_composition_chart(df_25, year="2025")
                
                return html.Div(
                    [
                        html.Div(
                            dcc.Graph(
                                figure=fig_2024,
                                config={"displayModeBar": False},
                                style={"height": "500px", "width": "100%"},
                            ),
                            style={
                                "flex": "1",
                                "backgroundColor": "#fff",
                                "borderRadius": "10px",
                                "padding": "10px",
                                "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
                                "border": "1px solid #dce3e0",
                                "margin": "25px 10px",
                            }
                        ),
                        html.Div(
                            dcc.Graph(
                                figure=fig_2025,
                                config={"displayModeBar": False},
                                style={"height": "500px", "width": "100%"},
                            ),
                            style={
                                "flex": "1",
                                "backgroundColor": "#fff",
                                "borderRadius": "10px",
                                "padding": "10px",
                                "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
                                "border": "1px solid #dce3e0",
                                "margin": "25px 10px",
                            }
                        ),
                    ],
                    style={
                        "display": "flex",
                        "flexDirection": "row",
                        "alignItems": "center",
                        "height": "calc(100vh - 370px)"
                    }
                )
        except Exception as e:
            return html.Div(f"Error loading yearly statistics: {str(e)}",
                            style={"color": "red", "padding": "10px"})

    # ── 17. Yearly Stats - Populate year tabs container ──────────────────
    @app.callback(
        Output("ls-yearly-year-tabs-container", "children"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_populate_yearly_year_tabs(_trigger):
        return _build_yearly_stats_year_tabs()

    # ── 18. Yearly Stats - Right sub-tab button clicks ───────────────────
    @app.callback(
        Output("ls-yearly-right-tab", "data"),
        [Input("ls-yearly-right-2024", "n_clicks"),
        Input("ls-yearly-right-2025", "n_clicks")],
        prevent_initial_call=True,
    )
    def ls_yearly_right_tab_click(year2024_clicks, year2025_clicks):
        if not ctx.triggered:
            raise PreventUpdate
        
        triggered_id = ctx.triggered_id
        if triggered_id is None:
            raise PreventUpdate
        
        return triggered_id.replace('ls-yearly-right-', '')

    # ── 19. Yearly Stats - Update right sub-tab button styles ──────────
    @app.callback(
        [Output("ls-yearly-right-2024", "style"),
        Output("ls-yearly-right-2025", "style")],
        Input("ls-yearly-right-tab", "data"),
        prevent_initial_call=False,
    )
    def ls_yearly_right_tab_styles(selected_tab):
        if selected_tab is None:
            selected_tab = "2024"
        
        styles = []
        for value, _ in _YEARLY_STATS_YEAR_TABS:
            if value == selected_tab:
                styles.append({
                    "backgroundColor": "#264653",
                    "color": "white",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "15px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "0 2px 8px rgba(38, 70, 83, 0.3)",
                    "transform": "scale(1.05)",
                })
            else:
                styles.append({
                    "backgroundColor": "#f0f2f5",
                    "color": "#264653",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "15px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "none",
                    "transform": "scale(1)",
                })
        
        return styles

    # ── 20. Yearly Stats - Update map based on selected year ────────────
    @app.callback(
        Output("ls-yearly-province-map", "srcDoc"),
        Input("ls-yearly-right-tab", "data"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_update_yearly_map(selected_year, _trigger):
        if selected_year is None:
            selected_year = "2024"
        
        try:
            livestock_stats, df_24, df_25, data_farm, data_amount, _, _, _, _ = load_livestock_stats()
            
            # Select the appropriate dataframe based on year
            if selected_year == "2024":
                df_map = df_24.copy()
            else:  # 2025
                df_map = df_25.copy()
            
            # Sum all animal columns to get total animals per province
            animal_cols = [c for c in df_map.columns if c != "Province"]
            df_map["Total"] = df_map[animal_cols].sum(axis=1)
            fig = create_livestock_province_map(df_map, animal_col="Total")
            
            # Update the colorbar title to indicate the year
            # fig.update_traces(
            #     colorbar=dict(title=f"Total Animals ({selected_year})", thickness=14, len=0.75),
            #     hovertemplate="<b>%{location}</b><br>Total Animals: %{z:,.0f}<extra></extra>"
            # )
            
            # Clean up margins and padding to maximize chart area
            # fig.update_layout(
            #     margin=dict(l=0, r=0, t=0, b=0),
            #     paper_bgcolor='rgba(0,0,0,0)',
            #     plot_bgcolor='rgba(0,0,0,0)',
            # )
            
            return fig.get_root().render()
        except Exception as e:
            from plotly import graph_objects as go
            fig = go.Figure()
            fig.add_annotation(
                text=f"Error: {e}", xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False, font=dict(size=14, color="#888"),
            )
            fig.update_layout(
                plot_bgcolor="white", 
                paper_bgcolor="white",
                xaxis=dict(visible=False), 
                yaxis=dict(visible=False),
                margin=dict(l=0, r=0, t=0, b=0),
            )
            return fig

    # ── 21. District Stats — table ─────────────────────────────────────
    @app.callback(
        Output("ls-district-table-container", "children"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_update_district_table(_trigger):
        try:
            _, _, _, _, _, stats_by_district, _, _, _ = load_livestock_stats()
            return _build_district_stats_table(stats_by_district)
        except Exception as e:
            return html.Div(f"Error loading table: {str(e)}",
                            style={"color": "red", "padding": "10px"})

# Canonical district-animal-button values, derived from stats_by_district
    try:
        _, _, _, _, _, stats_by_district, _, _, _ = load_livestock_stats()
        _district_animal_values = ["Total"] + [c for c in stats_by_district.columns if c != "Province"]
    except Exception:
        _district_animal_values = ["Total"]

    # ── District Stats — populate animal selector buttons ─────────────────
    @app.callback(
        Output("ls-district-animal-buttons-container", "children"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_populate_district_animal_buttons(_trigger):
        try:
            _, _, _, _, _, stats_by_district, _, _, _ = load_livestock_stats()
            animal_cols = [c for c in stats_by_district.columns if c != "Province"]
        except Exception:
            animal_cols = []
        return _build_district_animal_selector_buttons(animal_cols)

    # ── District Stats — handle animal button clicks ──────────────────────
    @app.callback(
        Output("ls-district-selected-animal", "data"),
        [Input(f"ls-district-animal-btn-{v}", "n_clicks") for v in _district_animal_values],
        prevent_initial_call=True,
    )
    def ls_update_district_selected_animal(*args):
        if not ctx.triggered:
            raise PreventUpdate
        triggered_id = ctx.triggered_id
        if triggered_id is None:
            raise PreventUpdate
        return triggered_id.replace('ls-district-animal-btn-', '')

    # ── District Stats — update animal button styles ───────────────────────
    @app.callback(
        [Output(f"ls-district-animal-btn-{v}", "style") for v in _district_animal_values],
        [Input(f"ls-district-animal-btn-{v}", "n_clicks") for v in _district_animal_values],
        prevent_initial_call=True,
    )
    def ls_update_district_animal_button_styles(*args):
        if not ctx.triggered:
            raise PreventUpdate
        triggered_id = ctx.triggered_id
        if triggered_id is None:
            raise PreventUpdate
        selected_value = triggered_id.replace('ls-district-animal-btn-', '')

        button_styles = []
        for v in _district_animal_values:
            if v == selected_value:
                button_styles.append({
                    "backgroundColor": "#264653",
                    "color": "white",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "13px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "0 2px 8px rgba(38, 70, 83, 0.3)",
                    "transform": "scale(1.05)",
                })
            else:
                button_styles.append({
                    "backgroundColor": "#f0f2f5",
                    "color": "#264653",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "13px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "none",
                    "transform": "scale(1)",
                })
        return button_styles

    # ── District Stats — update bar chart based on selected animal ────────
    @app.callback(
        Output("ls-district-bar-chart", "figure"),
        Input("ls-district-selected-animal", "data"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_update_district_bar_chart(selected_animal, _trigger):
        if selected_animal is None:
            selected_animal = "Total"
        try:
            _, _, _, _, _, stats_by_district, _, _, _ = load_livestock_stats()
            animal_cols = [c for c in stats_by_district.columns if c != "Province"]

            # Province-level rows only (e.g. "Vientiane Province"), suffix stripped
            mask = stats_by_district["Province"].astype(str).str.strip().str.lower().str.endswith("province")
            df_prov = stats_by_district[mask].copy()
            df_prov["Province"] = (
                df_prov["Province"].astype(str)
                .str.replace(r"\s*province\s*$", "", case=False, regex=True)
                .str.strip()
            )

            if not selected_animal or selected_animal == "Total":
                df_prov["Total"] = df_prov[animal_cols].sum(axis=1)
                value_col = "Total"
            else:
                value_col = selected_animal

            return create_district_stats_bar_chart(df_prov, value_col)
        except Exception as e:
            from plotly import graph_objects as go
            fig = go.Figure()
            fig.add_annotation(
                text=f"Error: {e}", xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False, font=dict(size=14, color="#888"),
            )
            fig.update_layout(
                plot_bgcolor="white",
                paper_bgcolor="white",
                xaxis=dict(visible=False),
                yaxis=dict(visible=False),
                margin=dict(l=0, r=0, t=0, b=0),
            )
            return fig

    # ── Group Farming — populate table ─────────────────────────────────
    @app.callback(
        Output("ls-group-farming-table-container", "children"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_update_group_farming_table(_trigger):
        try:
            _, _, _, _, _, _, farming_amount_group, farming_amount_animal, _ = load_livestock_stats()
            return _build_group_farming_table(farming_amount_group, farming_amount_animal)
        except Exception as e:
            return html.Div(f"Error loading table: {str(e)}",
                            style={"color": "red", "padding": "10px"})

    # ── Group Farming — right sub-tab button clicks ────────────────────
    @app.callback(
        Output("ls-group-farming-right-tab", "data"),
        [Input("ls-group-right-group", "n_clicks"),
         Input("ls-group-right-animal", "n_clicks")],
        prevent_initial_call=True,
    )
    def ls_group_farming_right_tab_click(group_clicks, animal_clicks):
        if not ctx.triggered:
            raise PreventUpdate
        triggered_id = ctx.triggered_id
        if triggered_id is None:
            raise PreventUpdate
        return triggered_id.replace('ls-group-right-', '')

    # ── Group Farming — right sub-tab button styles ────────────────────
    @app.callback(
        [Output("ls-group-right-group", "style"),
         Output("ls-group-right-animal", "style")],
        Input("ls-group-farming-right-tab", "data"),
        prevent_initial_call=False,
    )
    def ls_group_farming_right_tab_styles(selected_tab):
        if selected_tab is None:
            selected_tab = "group"

        styles = []
        for value, _ in _GROUP_FARMING_MAP_TABS:
            if value == selected_tab:
                styles.append({
                    "backgroundColor": "#264653",
                    "color": "white",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "15px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "0 2px 8px rgba(38, 70, 83, 0.3)",
                    "transform": "scale(1.05)",
                })
            else:
                styles.append({
                    "backgroundColor": "#f0f2f5",
                    "color": "#264653",
                    "border": "none",
                    "padding": "8px 16px",
                    "borderRadius": "20px",
                    "cursor": "pointer",
                    "fontSize": "15px",
                    "fontWeight": "500",
                    "transition": "all 0.3s ease",
                    "fontFamily": "ubuntu",
                    "margin": "0 3px",
                    "boxShadow": "none",
                    "transform": "scale(1)",
                })
        return styles

    # ── Group Farming — populate map tabs container ────────────────────
    @app.callback(
        Output("ls-group-map-tabs-container", "children"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_populate_group_farming_map_tabs(_trigger):
        return _build_group_farming_map_tabs()

    # ── Group Farming — update map based on Group/Animal selection ─────
    @app.callback(
        Output("ls-group-farming-province-map", "srcDoc"),
        Input("ls-group-farming-right-tab", "data"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_update_group_farming_map(selected_metric, _trigger):
        if selected_metric is None:
            selected_metric = "group"
        try:
            _, _, _, _, _, _, farming_amount_group, farming_amount_animal, _ = load_livestock_stats()

            df_source = farming_amount_group if selected_metric == "group" else farming_amount_animal
            # Drop North/Middle/South region rows — the choropleth needs
            # real province names to match the geojson features.
            df_map = df_source[~df_source["Province"].apply(_is_region_row)].copy()
            animal_cols = [c for c in df_map.columns if c != "Province"]
            label = "Total Group Count" if selected_metric == "group" else "Total Animal Count"
            df_map[label] = df_map[animal_cols].sum(axis=1)

            fig = create_livestock_province_map(df_map, animal_col=label)
            return fig.get_root().render()
        except Exception as e:
            from plotly import graph_objects as go
            fig = go.Figure()
            fig.add_annotation(
                text=f"Error: {e}", xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False, font=dict(size=14, color="#888"),
            )
            fig.update_layout(
                plot_bgcolor="white",
                paper_bgcolor="white",
                xaxis=dict(visible=False),
                yaxis=dict(visible=False),
                margin=dict(l=0, r=0, t=0, b=0),
            )
            return fig

    # ── Breeding Stats — populate table (raw, as-is) ────────────────────
    @app.callback(
        Output("ls-breeding-table-container", "children"),
        Input("ls-load-trigger", "data"),
        prevent_initial_call=False,
    )
    def ls_update_breeding_table(_trigger):
        try:
            _, _, _, _, _, _, _, _, breeding_animal_stats = load_livestock_stats()
            return _build_breeding_stats_table(breeding_animal_stats)
        except Exception as e:
            return html.Div(f"Error loading table: {str(e)}",
                            style={"color": "red", "padding": "10px"})
    
    # Add this store to your layout if you haven't already
    # dcc.Store(id='ls-auto-click-store', data=None)

    # callback to handle auto-clicks when main tabs are selected
    @app.callback(
        Output("ls-auto-click-store", "data"),  # Use a separate store for the trigger
        [Input(f"ls-btn-{v}", "n_clicks") for v in _TAB_VALUES],
        prevent_initial_call=True,
    )
    def ls_handle_auto_clicks(*args):
        if not ctx.triggered:
            raise PreventUpdate
        
        triggered_id = ctx.triggered_id
        if triggered_id is None:
            raise PreventUpdate
        
        selected_tab = triggered_id.replace('ls-btn-', '')
        
        # Return the selected tab to trigger the clientside callback
        return selected_tab

    # Clientside callback to perform the actual DOM clicks
    app.clientside_callback(
        """
        function(selected_tab) {
            if (!selected_tab) {
                return window.dash_clientside.no_update;
            }
            
            console.log('Auto-click executing for tab:', selected_tab);
            
            // Small delay to ensure DOM elements are rendered
            setTimeout(function() {
                // National Overview - click "Total" animal button
                if (selected_tab === 'national-overview') {
                    var btn = document.getElementById('ls-animal-btn-Total');
                    if (btn) {
                        console.log('Clicking National Overview Total button');
                        btn.click();
                    } else {
                        console.warn('ls-animal-btn-Total not found');
                    }
                }
                
                // Farm Statistics - click "Farms Count" button
                if (selected_tab === 'farm-stats') {
                    var btn = document.getElementById('ls-farm-right-farms');
                    if (btn) {
                        console.log('Clicking Farm Stats Farms Count button');
                        btn.click();
                    } else {
                        console.warn('ls-farm-right-farms not found');
                    }
                }
                
                // Yearly Stats - click "2024" button
                if (selected_tab === 'yearly-stats') {
                    var btn = document.getElementById('ls-yearly-right-2024');
                    if (btn) {
                        console.log('Clicking Yearly Stats 2024 button');
                        btn.click();
                    } else {
                        console.warn('ls-yearly-right-2024 not found');
                    }
                }
                
                // Group Farming - click "Group Count" button
                if (selected_tab === 'group-farming') {
                    var btn = document.getElementById('ls-group-right-group');
                    if (btn) {
                        console.log('Clicking Group Farming Group Count button');
                        btn.click();
                    } else {
                        console.warn('ls-group-right-group not found');
                    }
                }
            }, 200);  // Increased delay to ensure panel is fully rendered
            
            return window.dash_clientside.no_update;
        }
        """,
        Output("ls-auto-click-store", "data", allow_duplicate=True),  # Same output as input
        Input("ls-auto-click-store", "data"),
        prevent_initial_call=True
    )


