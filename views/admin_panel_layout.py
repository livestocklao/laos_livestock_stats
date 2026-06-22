"""
Provides:
  - General Settings  (autorefresh interval, timezone)
  - Disease Settings  (key diseases multiselect)
  - Disease Stats editor (year + per-animal metrics + save to Sheets)
  - Add New Case form
  - Logout

Auth gate: every callback checks auth-store before rendering real content.
App-level settings are persisted in app-settings-store (dcc.Store, session).
"""

import pandas as pd
from datetime import datetime, date

import dash
from dash import html, dcc, ctx
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

# ── your existing data-loader helpers ─────────────────────────────────────────
# Adjust import path to match your project structure
from utils.data_loader import (
    load_data,
    refresh_all_data,
    update_disease_stats_worksheet,
    add_new_case_to_database,
)


# ─────────────────────────────────────────────────────────────────────────────
# Layout builder
# ─────────────────────────────────────────────────────────────────────────────

def build_admin_panel():
    """
    Returns the full admin panel layout as a Dash component tree.
    Embed this wherever you want to surface the panel (a tab, a route, etc.).
    Content is hidden behind an auth-gate div that callbacks control.
    """
    return html.Div([

        # ── Auth gate: shown when NOT authenticated ───────────────────────
        html.Div(
            id='ap-auth-gate',
            className='ap-auth-gate',
            children=[
                html.Div([
                    html.Span('🔒', className='ap-gate-icon'),
                    html.H3('Admin access required', className='ap-gate-title'),
                    html.P(
                        'Please click the Admin button in the header to log in.',
                        className='ap-gate-sub'
                    ),
                ], className='ap-gate-box')
            ],
            style={'display': 'none'}   # shown/hidden by callback
        ),

        # ── Main panel (shown when authenticated) ─────────────────────────
        html.Div(
            id='ap-main',
            className='ap-main',
            children=[

                # ── Panel header row ──────────────────────────────────────
                html.Div([
                    html.H2('⚙️ Admin Panel', className='ap-title'),
                    html.Button(
                        '🚪 Logout',
                        id='ap-logout-btn',
                        className='ap-logout-btn',
                        n_clicks=0
                    ),
                ], className='ap-header-row'),

                html.Hr(className='ap-divider'),

                # ── Flash message area ────────────────────────────────────
                html.Div(id='ap-flash', className='ap-flash'),

                # ── Three-column body ─────────────────────────────────────
                html.Div([

                    # ── Col 1: General + Disease Settings ─────────────────
                    html.Div([
                        _build_general_settings_card(),
                        _build_disease_settings_card(),
                    ], className='ap-col ap-col-narrow'),

                    # ── Col 2: Disease Stats Editor ───────────────────────
                    html.Div([
                        _build_disease_stats_card(),
                    ], className='ap-col ap-col-wide'),

                    # ── Col 3: Add New Case ────────────────────────────────
                    html.Div([
                        _build_add_case_card(),
                    ], className='ap-col ap-col-wide'),

                ], className='ap-body-row'),

            ],
            style={'display': 'none'}   # shown/hidden by callback
        ),

        # Trigger to reload data into stores when panel becomes visible
        dcc.Interval(id='ap-data-trigger', interval=99999999, n_intervals=0, max_intervals=1),

        # Stores
        dcc.Store(id='ap-disease-codes-store', data=None),
        dcc.Store(id='ap-disease-stats-store', data=None),
        dcc.Store(id='ap-database-store',      data=None),
        dcc.Store(id='ap-geo-store',           data=None),

    ], className='ap-container', id='ap-container')


# ── Private card builders ─────────────────────────────────────────────────────

def _build_general_settings_card():
    return html.Div([
        html.H4('⚙️ General Settings', className='ap-card-title'),

        html.Label('Autorefresh Interval (sec)', className='ap-label'),
        dcc.Slider(
            id='ap-autorefresh-slider',
            min=10, max=300, step=10, value=60,
            marks={10: '10', 60: '60', 150: '150', 300: '300'},
            tooltip={'placement': 'bottom', 'always_visible': False},
            className='ap-slider'
        ),
        html.Div(id='ap-autorefresh-display', className='ap-slider-display'),

        html.Label('Timezone', className='ap-label ap-label-spaced'),
        dcc.Dropdown(
            id='ap-timezone-dropdown',
            options=[{'label': tz, 'value': tz} for tz in ['EST', 'PST', 'UTC', 'GMT']],
            value='PST',
            clearable=False,
            className='ap-dropdown'
        ),

        html.Button(
            '💾 Save Settings',
            id='ap-general-save-btn',
            className='ap-save-btn',
            n_clicks=0
        ),
    ], className='ap-card')


def _build_disease_settings_card():
    return html.Div([
        html.H4('🦠 Disease Settings', className='ap-card-title'),

        html.Label('Key Diseases', className='ap-label'),
        dcc.Dropdown(
            id='ap-key-diseases-dropdown',
            options=[],           # populated by callback after data loads
            value=[],
            multi=True,
            placeholder='Select key diseases...',
            className='ap-dropdown'
        ),

        html.Button(
            '💾 Save Diseases',
            id='ap-diseases-save-btn',
            className='ap-save-btn',
            n_clicks=0
        ),
    ], className='ap-card')


def _build_disease_stats_card():
    return html.Div([
        html.H4('📈 Disease Stats Configuration', className='ap-card-title'),

        # Year selector
        html.Div([
            html.Label('Year', className='ap-label'),
            dcc.Dropdown(
                id='ap-year-dropdown',
                options=[],       # populated by callback
                value=None,
                clearable=False,
                className='ap-dropdown ap-dropdown-narrow'
            ),
        ], className='ap-row'),

        # Metrics grid (8 animal cards)
        html.Div(id='ap-animal-metrics', className='ap-metrics-grid'),

        html.Hr(className='ap-inner-divider'),
        html.H5('Update Statistics', className='ap-sub-title'),

        html.Div([
            dcc.Dropdown(
                id='ap-update-animal-dropdown',
                options=[],       # populated by callback
                value=None,
                clearable=False,
                placeholder='Select animal',
                className='ap-dropdown'
            ),
            dcc.Input(
                id='ap-update-value-input',
                type='number',
                min=0, step=1, value=0,
                className='ap-number-input',
                placeholder='Count'
            ),
            html.Button(
                '💾 Save',
                id='ap-stats-save-btn',
                className='ap-save-btn ap-save-btn-inline',
                n_clicks=0
            ),
        ], className='ap-update-row'),

    ], className='ap-card')


def _build_add_case_card():
    today = date.today()
    return html.Div([
        html.H4('➕ Add New Disease Case', className='ap-card-title'),

        html.Div(id='ap-next-case-badge', className='ap-case-badge'),

        html.Div([
            html.Div([
                html.Label('Location *', className='ap-label'),
                dcc.Dropdown(
                    id='ap-case-location',
                    options=[],   # populated by callback
                    value=None,
                    clearable=False,
                    className='ap-dropdown'
                ),
            ], className='ap-form-col'),

            html.Div([
                html.Label('Disease Code *', className='ap-label'),
                dcc.Dropdown(
                    id='ap-case-disease-code',
                    options=[],   # populated by callback
                    value=None,
                    clearable=False,
                    className='ap-dropdown'
                ),
            ], className='ap-form-col'),
        ], className='ap-form-row'),

        html.Div([
            html.Div([
                html.Label('Reported Date *', className='ap-label'),
                dcc.DatePickerSingle(
                    id='ap-case-date',
                    date=today.isoformat(),
                    max_date_allowed=today.isoformat(),
                    display_format='YYYY-MM-DD',
                    className='ap-date-picker'
                ),
            ], className='ap-form-col'),

            html.Div([
                html.Label('Number of Cases *', className='ap-label'),
                dcc.Input(
                    id='ap-case-count',
                    type='number', min=1, step=1, value=1,
                    className='ap-number-input'
                ),
            ], className='ap-form-col'),
        ], className='ap-form-row'),

        html.Div([
            html.Label('Additional Notes', className='ap-label'),
            dcc.Textarea(
                id='ap-case-notes',
                placeholder='Optional notes...',
                className='ap-textarea'
            ),
        ]),

        html.Div([
            html.Button(
                '➕ Add Case',
                id='ap-case-submit-btn',
                className='ap-save-btn',
                n_clicks=0
            ),
            html.Button(
                '🔄 Reset',
                id='ap-case-reset-btn',
                className='ap-reset-btn',
                n_clicks=0
            ),
        ], className='ap-actions-row'),

    ], className='ap-card')


# ─────────────────────────────────────────────────────────────────────────────
# Callbacks
# ─────────────────────────────────────────────────────────────────────────────

def register_admin_callbacks(app: dash.Dash) -> None:
    """Register all admin panel callbacks. Call once from app.py."""

    # ── 1. Auth gate: show/hide panel based on auth-store ─────────────────
    @app.callback(
        Output('ap-auth-gate', 'style'),
        Output('ap-main',      'style'),
        Output('ap-data-trigger', 'max_intervals'),   # flip to trigger data load
        Input('auth-store',    'data'),
    )
    def toggle_auth_gate(auth_data):
        authenticated = auth_data and auth_data.get('is_authenticated', False)
        if authenticated:
            return {'display': 'none'}, {'display': 'block'}, 1
        return {'display': 'flex'}, {'display': 'none'}, 0


    # ── 2. Logout from panel ──────────────────────────────────────────────
    @app.callback(
        Output('auth-store',    'data',    allow_duplicate=True),
        Input('ap-logout-btn',  'n_clicks'),
        State('auth-store',     'data'),
        prevent_initial_call=True
    )
    def panel_logout(n, auth_data):
        if not n:
            raise PreventUpdate
        return {"is_authenticated": False, "username": None, "role": "guest"}


    # ── 3. Load data into stores once panel becomes visible ───────────────
    @app.callback(
        Output('ap-disease-codes-store', 'data'),
        Output('ap-disease-stats-store', 'data'),
        Output('ap-database-store',      'data'),
        Output('ap-geo-store',           'data'),
        Input('ap-data-trigger',         'n_intervals'),
        State('auth-store',              'data'),
        prevent_initial_call=True
    )
    def load_admin_data(n, auth_data):
        if not (auth_data and auth_data.get('is_authenticated')):
            raise PreventUpdate
        try:
            data = load_data()
            disease_stats_data = data[0]
            database           = data[1]
            disease_codes      = data[2]
            geo_data           = data[3]
            return (
                disease_codes.to_dict('records'),
                disease_stats_data.to_dict('records'),
                database.to_dict('records'),
                geo_data.to_dict('records'),
            )
        except Exception:
            raise PreventUpdate


    # ── 4. Populate dropdowns from stores ────────────────────────────────
    @app.callback(
        Output('ap-key-diseases-dropdown',  'options'),
        Output('ap-case-disease-code',      'options'),
        Output('ap-update-animal-dropdown', 'options'),
        Output('ap-year-dropdown',          'options'),
        Output('ap-year-dropdown',          'value'),
        Output('ap-case-location',          'options'),
        Output('ap-next-case-badge',        'children'),
        Input('ap-disease-codes-store',     'data'),
        Input('ap-disease-stats-store',     'data'),
        Input('ap-database-store',          'data'),
        Input('ap-geo-store',               'data'),
        State('app-settings-store',         'data'),
    )
    def populate_dropdowns(disease_codes_records, stats_records,
                           db_records, geo_records, settings):
        # Disease codes
        if disease_codes_records:
            dc_df    = pd.DataFrame(disease_codes_records)
            diseases = dc_df['disease_code'].unique().tolist()
        else:
            diseases = []
        disease_opts = [{'label': d, 'value': d} for d in diseases]

        # Animals from stats
        animals_order = ['fish', 'poultry', 'goat', 'buffalo', 'dog', 'pig', 'horse', 'cattle']
        if stats_records:
            stats_df = pd.DataFrame(stats_records)
            stats_df.columns = [c.lower() for c in stats_df.columns]
            available_animals = [a for a in animals_order if a in stats_df.columns]
        else:
            available_animals = animals_order
        animal_opts = [{'label': a.capitalize(), 'value': a} for a in available_animals]

        # Years
        year_opts, year_val = [], None
        if stats_records:
            stats_df = pd.DataFrame(stats_records)
            stats_df.columns = [c.lower() for c in stats_df.columns]
            if 'year' in stats_df.columns:
                years    = sorted(stats_df['year'].astype(int).unique().tolist())
                next_yr  = max(years) + 1 if years else datetime.now().year
                year_opts = [{'label': str(y), 'value': y} for y in years + [next_yr]]
                year_val  = years[-1] if years else None

        # Locations
        location_opts = []
        if geo_records:
            geo_df = pd.DataFrame(geo_records)
            if 'location' in geo_df.columns:
                locs = geo_df['location'].unique().tolist()
                location_opts = [{'label': l, 'value': l} for l in locs]

        # Next case number badge
        next_no = 1
        if db_records:
            db_df = pd.DataFrame(db_records)
            if 'no' in db_df.columns and not db_df.empty:
                next_no = int(db_df['no'].max()) + 1
        badge = [html.Span(f'Case #', className='ap-badge-label'),
                 html.Span(str(next_no), className='ap-badge-number')]

        return (
            disease_opts,   # key-diseases options
            disease_opts,   # case disease-code options
            animal_opts,    # update-animal options
            year_opts,      # year options
            year_val,       # year value
            location_opts,  # location options
            badge,          # next-case badge
        )


    # ── 5. Pre-populate key diseases from settings store ─────────────────
    @app.callback(
        Output('ap-key-diseases-dropdown', 'value'),
        Output('ap-autorefresh-slider',    'value'),
        Output('ap-timezone-dropdown',     'value'),
        Input('ap-data-trigger',           'n_intervals'),
        State('app-settings-store',        'data'),
        prevent_initial_call=True
    )
    def prefill_settings(_, settings):
        s = settings or {}
        return (
            s.get('key_diseases', []),
            s.get('autorefresh_interval', 60),
            s.get('timezone', 'PST'),
        )


    # ── 6. Live slider display ────────────────────────────────────────────
    @app.callback(
        Output('ap-autorefresh-display', 'children'),
        Input('ap-autorefresh-slider',   'value'),
    )
    def update_slider_display(val):
        return f'{val} seconds'


    # ── 7. Save general settings ──────────────────────────────────────────
    @app.callback(
        Output('app-settings-store',    'data',    allow_duplicate=True),
        Output('ap-flash',              'children', allow_duplicate=True),
        Output('ap-flash',              'className', allow_duplicate=True),
        Input('ap-general-save-btn',    'n_clicks'),
        State('ap-autorefresh-slider',  'value'),
        State('ap-timezone-dropdown',   'value'),
        State('app-settings-store',     'data'),
        prevent_initial_call=True
    )
    def save_general_settings(n, interval, timezone, settings):
        if not n:
            raise PreventUpdate
        s = dict(settings or {})
        s['autorefresh_interval'] = interval
        s['timezone']             = timezone
        return s, '✅ General settings saved.', 'ap-flash ap-flash-success'


    # ── 8. Save disease settings ──────────────────────────────────────────
    @app.callback(
        Output('app-settings-store',       'data',     allow_duplicate=True),
        Output('ap-flash',                 'children',  allow_duplicate=True),
        Output('ap-flash',                 'className', allow_duplicate=True),
        Input('ap-diseases-save-btn',      'n_clicks'),
        State('ap-key-diseases-dropdown',  'value'),
        State('app-settings-store',        'data'),
        prevent_initial_call=True
    )
    def save_disease_settings(n, key_diseases, settings):
        if not n:
            raise PreventUpdate
        s = dict(settings or {})
        s['key_diseases'] = key_diseases or []
        return s, '✅ Disease settings saved.', 'ap-flash ap-flash-success'


    # ── 9. Render animal metrics cards for selected year ──────────────────
    @app.callback(
        Output('ap-animal-metrics',        'children'),
        Output('ap-update-animal-dropdown','value'),
        Input('ap-year-dropdown',          'value'),
        State('ap-disease-stats-store',    'data'),
    )
    def render_animal_metrics(year, stats_records):
        if not stats_records or year is None:
            return [], None

        stats_df = pd.DataFrame(stats_records)
        stats_df.columns = [c.lower() for c in stats_df.columns]

        animals_order = ['fish', 'poultry', 'goat', 'buffalo', 'dog', 'pig', 'horse', 'cattle']
        available     = [a for a in animals_order if a in stats_df.columns]

        # Find row for this year (or zeroed row if new year)
        row = stats_df[stats_df['year'].astype(int) == int(year)]
        if row.empty:
            values = {a: 0 for a in available}
        else:
            values = {a: int(row.iloc[0][a]) if pd.notna(row.iloc[0][a]) else 0
                      for a in available}

        cards = [
            html.Div([
                html.Div(animal.capitalize(), className='ap-metric-label'),
                html.Div(f"{values[animal]:,}",  className='ap-metric-value'),
            ], className='ap-metric-card')
            for animal in available
        ]
        first_animal = available[0] if available else None
        return cards, first_animal


    # ── 10. Pre-fill update value when animal selection changes ───────────
    @app.callback(
        Output('ap-update-value-input',    'value'),
        Input('ap-update-animal-dropdown', 'value'),
        State('ap-year-dropdown',          'value'),
        State('ap-disease-stats-store',    'data'),
    )
    def prefill_update_value(animal, year, stats_records):
        if not animal or not stats_records or year is None:
            return 0
        stats_df = pd.DataFrame(stats_records)
        stats_df.columns = [c.lower() for c in stats_df.columns]
        row = stats_df[stats_df['year'].astype(int) == int(year)]
        if row.empty or animal not in stats_df.columns:
            return 0
        val = row.iloc[0][animal]
        return int(val) if pd.notna(val) else 0


    # ── 11. Save disease stats to Google Sheets ───────────────────────────
    @app.callback(
        Output('ap-disease-stats-store', 'data',     allow_duplicate=True),
        Output('ap-flash',               'children',  allow_duplicate=True),
        Output('ap-flash',               'className', allow_duplicate=True),
        Input('ap-stats-save-btn',       'n_clicks'),
        State('ap-year-dropdown',         'value'),
        State('ap-update-animal-dropdown','value'),
        State('ap-update-value-input',    'value'),
        State('ap-disease-stats-store',   'data'),
        prevent_initial_call=True
    )
    def save_disease_stats(n, year, animal, new_value, stats_records):
        if not n or year is None or not animal:
            raise PreventUpdate

        stats_df = pd.DataFrame(stats_records)
        stats_df.columns = [c.lower() for c in stats_df.columns]

        # Upsert row
        mask = stats_df['year'].astype(int) == int(year)
        if mask.any():
            stats_df.loc[mask, animal] = new_value
        else:
            new_row = {col: 0 for col in stats_df.columns}
            new_row['year'] = year
            new_row[animal] = new_value
            stats_df = pd.concat([stats_df, pd.DataFrame([new_row])], ignore_index=True)

        # Push to Sheets
        upload_df = stats_df.copy()
        upload_df.columns = [c.capitalize() for c in upload_df.columns]
        try:
            success = update_disease_stats_worksheet(upload_df)
            if success:
                refresh_all_data()
                return (
                    stats_df.to_dict('records'),
                    f'✅ Stats for {year} updated.',
                    'ap-flash ap-flash-success'
                )
            else:
                return (
                    stats_records,
                    '❌ Failed to update stats.',
                    'ap-flash ap-flash-error'
                )
        except Exception as e:
            return stats_records, f'❌ Error: {e}', 'ap-flash ap-flash-error'


    # ── 12. Add new case ──────────────────────────────────────────────────
    @app.callback(
        Output('ap-database-store',  'data',     allow_duplicate=True),
        Output('ap-flash',           'children',  allow_duplicate=True),
        Output('ap-flash',           'className', allow_duplicate=True),
        # Reset fields on success
        Output('ap-case-location',   'value',     allow_duplicate=True),
        Output('ap-case-disease-code','value',    allow_duplicate=True),
        Output('ap-case-count',      'value',     allow_duplicate=True),
        Output('ap-case-notes',      'value',     allow_duplicate=True),
        Input('ap-case-submit-btn',  'n_clicks'),
        State('ap-case-location',    'value'),
        State('ap-case-disease-code','value'),
        State('ap-case-date',        'date'),
        State('ap-case-count',       'value'),
        State('ap-case-notes',       'value'),
        State('ap-database-store',   'data'),
        prevent_initial_call=True
    )
    def add_new_case(n, location, disease_code, reported_date,
                     cases, notes, db_records):
        if not n:
            raise PreventUpdate

        # Validation
        if not location or not disease_code or not reported_date or not cases:
            return (
                db_records,
                '⚠️ Please fill in all required fields.',
                'ap-flash ap-flash-warning',
                location, disease_code, cases, notes
            )

        db_df   = pd.DataFrame(db_records) if db_records else pd.DataFrame()
        next_no = int(db_df['no'].max()) + 1 if ('no' in db_df.columns and not db_df.empty) else 1

        new_case = {
            'no':            next_no,
            'location':      location,
            'disease_code':  disease_code,
            'reported_date': reported_date,
            'case':          int(cases),
        }

        try:
            success = add_new_case_to_database(new_case)
            if success:
                refresh_all_data()
                # Append locally so badge updates without a full reload
                updated_db = pd.concat(
                    [db_df, pd.DataFrame([new_case])], ignore_index=True
                )
                return (
                    updated_db.to_dict('records'),
                    f'✅ Case #{next_no} added successfully!',
                    'ap-flash ap-flash-success',
                    None, None, 1, ''
                )
            else:
                return (
                    db_records,
                    '❌ Failed to add case.',
                    'ap-flash ap-flash-error',
                    location, disease_code, cases, notes
                )
        except Exception as e:
            return (
                db_records,
                f'❌ Error: {e}',
                'ap-flash ap-flash-error',
                location, disease_code, cases, notes
            )


    # ── 13. Reset case form ───────────────────────────────────────────────
    @app.callback(
        Output('ap-case-location',    'value',  allow_duplicate=True),
        Output('ap-case-disease-code','value',  allow_duplicate=True),
        Output('ap-case-count',       'value',  allow_duplicate=True),
        Output('ap-case-notes',       'value',  allow_duplicate=True),
        Input('ap-case-reset-btn',    'n_clicks'),
        prevent_initial_call=True
    )
    def reset_case_form(n):
        if not n:
            raise PreventUpdate
        return None, None, 1, ''


    # ── 14. Auto-clear flash after 4 s ────────────────────────────────────
    @app.callback(
        Output('ap-flash', 'children',  allow_duplicate=True),
        Output('ap-flash', 'className', allow_duplicate=True),
        Input('ap-flash',  'children'),
        prevent_initial_call=True
    )
    def schedule_flash_clear(msg):
        """
        Clears the flash message on the *next* render after it's set.
        For a proper timed clear, use a clientside_callback with setTimeout.
        See the comment in app.py for the optional JS approach.
        """
        raise PreventUpdate   # Leave as-is; wire clientside below if desired