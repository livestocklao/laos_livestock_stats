import pandas as pd
from datetime import datetime, date
import dash
from dash import html, dcc, ctx
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
from utils.data_loader import (
    load_key_diseases_data,
    load_overview_data,
    refresh_all_data,
    update_disease_stats_worksheet,
    add_new_case_to_database,
)

import logging

logger = logging.getLogger(__name__)

# Hardcoded fallback key diseases (used to seed settings on first load)
KEY_DISEASES: list = ["HPAI-P", "ND", "IBD", "MG"]

# Column order expected in disease_stats (lowercase)
ANIMAL_COLUMNS = ['horse', 'cattle', 'buffalo', 'goat', 'pig', 'dog', 'poultry', 'fish']


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_disease_codes() -> list[str]:
    """Return unique disease codes from the key-diseases sheet."""
    try:
        raw = load_key_diseases_data()
        return sorted(raw["disease_code"].dropna().unique().tolist())
    except Exception as e:
        logger.error(f"Failed to load disease codes: {e}")
        return []


def _load_disease_stats() -> pd.DataFrame:
    """Return the disease stats DataFrame (Year + animal columns)."""
    try:
        disease_stats, _ = load_overview_data()
        # Normalise column names to lowercase for internal use
        disease_stats.columns = [c.strip().lower() for c in disease_stats.columns]
        return disease_stats
    except Exception as e:
        logger.error(f"Failed to load disease stats: {e}")
        return pd.DataFrame()


def _load_database() -> pd.DataFrame:
    """Load the disease case database sheet."""
    try:
        from utils.data_loader import load_data_package          # keep import local
        pkg = load_data_package()
        df = pkg.database
        df.columns = [c.strip().lower() for c in df.columns]
        return df
    except Exception as e:
        logger.error(f"Failed to load database: {e}")
        return pd.DataFrame(columns=['no', 'location', 'disease_code',
                                     'reported_date', 'case'])


def _load_geo() -> pd.DataFrame:
    """Load geo/location data."""
    try:
        from utils.data_loader import load_data_package
        pkg = load_data_package()
        df = pkg.geo_data
        df.columns = [c.strip().lower() for c in df.columns]
        return df
    except Exception as e:
        logger.error(f"Failed to load geo data: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Layout builder
# ─────────────────────────────────────────────────────────────────────────────

def build_admin_panel():
    return html.Div([
        # ── Auth gate ────────────────────────────────────────────────────
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
            style={'display': 'none'}
        ),
        # ── Main panel ────────────────────────────────────────────────────
        html.Div(
            id='ap-main',
            className='ap-main',
            children=[
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
                html.Div(id='ap-flash', className='ap-flash'),
                html.Div([
                    html.Div([
                        _build_general_settings_card(),
                        _build_disease_settings_card(),
                    ], className='ap-col ap-col-narrow'),
                    html.Div([
                        _build_disease_stats_card(),
                    ], className='ap-col ap-col-wide'),
                    html.Div([
                        _build_add_case_card(),
                    ], className='ap-col ap-col-wide'),
                ], className='ap-body-row'),
            ],
            style={'display': 'none'}
        ),
        # Trigger: fires once when panel becomes visible (max_intervals toggled by auth)
        dcc.Interval(id='ap-data-trigger', interval=99999999, n_intervals=0, max_intervals=0),
        # Stores
        dcc.Store(id='ap-disease-codes-store', data=None),
        dcc.Store(id='ap-disease-stats-store', data=None),
        dcc.Store(id='ap-database-store',      data=None),
        dcc.Store(id='ap-geo-store',           data=None),
        dcc.Store(id='ap-flash-trigger',       data=None),
    ], className='ap-container', id='ap-container')


# ── Private card builders ──────────────────────────────────────────────────

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
            options=[],
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
        html.Div([
            html.Label('Year', className='ap-label'),
            dcc.Dropdown(
                id='ap-year-dropdown',
                options=[],
                value=None,
                clearable=False,
                className='ap-dropdown ap-dropdown-narrow'
            ),
        ], className='ap-row'),
        html.Div(id='ap-animal-metrics', className='ap-metrics-grid'),
        html.Hr(className='ap-inner-divider'),
        html.H5('Update Statistics', className='ap-sub-title'),
        html.Div([
            dcc.Dropdown(
                id='ap-update-animal-dropdown',
                options=[],
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
                    options=[],
                    value=None,
                    clearable=False,
                    className='ap-dropdown'
                ),
            ], className='ap-form-col'),
            html.Div([
                html.Label('Disease Code *', className='ap-label'),
                dcc.Dropdown(
                    id='ap-case-disease-code',
                    options=[],
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

    # ── 1. Auth gate ──────────────────────────────────────────────────────
    @app.callback(
        Output('ap-auth-gate',    'style'),
        Output('ap-main',         'style'),
        Output('ap-data-trigger', 'max_intervals'),
        Input('auth-store',       'data'),
    )
    def toggle_auth_gate(auth_data):
        authenticated = auth_data and auth_data.get('is_authenticated', False)
        if authenticated:
            return {'display': 'none'}, {'display': 'block'}, 1
        return {'display': 'flex'}, {'display': 'none'}, 0

    # ── 2. Logout ─────────────────────────────────────────────────────────
    @app.callback(
        Output('auth-store',   'data',    allow_duplicate=True),
        Input('ap-logout-btn', 'n_clicks'),
        prevent_initial_call=True
    )
    def panel_logout(n):
        if not n:
            raise PreventUpdate
        return {"is_authenticated": False, "username": None, "role": "guest"}

    # ── 3. Load all data into stores (fires once on login) ────────────────
    #
    #  Uses the concrete loader functions so we are not dependent on
    #  load_data_package() returning the right attribute names.
    #
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

        # Disease codes -------------------------------------------------------
        disease_codes_records = []
        try:
            raw = load_key_diseases_data()
            codes = sorted(raw["disease_code"].dropna().unique().tolist())
            disease_codes_records = [{'disease_code': c} for c in codes]
        except Exception as e:
            logger.error(f"load_key_diseases_data failed: {e}")

        # Disease stats -------------------------------------------------------
        disease_stats_records = []
        try:
            disease_stats, _ = load_overview_data()
            disease_stats.columns = [c.strip().lower() for c in disease_stats.columns]
            disease_stats_records = disease_stats.to_dict('records')
        except Exception as e:
            logger.error(f"load_overview_data failed: {e}")

        # Database (case records) ---------------------------------------------
        database_records = []
        try:
            db_df = _load_database()
            database_records = db_df.to_dict('records')
        except Exception as e:
            logger.error(f"_load_database failed: {e}")

        # Geo data (locations) ------------------------------------------------
        geo_records = []
        try:
            geo_df = _load_geo()
            geo_records = geo_df.to_dict('records')
        except Exception as e:
            logger.error(f"_load_geo failed: {e}")

        return disease_codes_records, disease_stats_records, database_records, geo_records

    # ── 4. Populate all dropdowns from stores ─────────────────────────────
    #
    #  Also sets ap-key-diseases-dropdown VALUE here (not in a separate
    #  callback) to avoid the race between options and value updates.
    #
    @app.callback(
        Output('ap-key-diseases-dropdown',  'options'),
        Output('ap-key-diseases-dropdown',  'value'),      # ← set here, not in cb 5
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

        # ── Disease codes ────────────────────────────────────────────────
        if disease_codes_records:
            dc_df    = pd.DataFrame(disease_codes_records)
            diseases = dc_df['disease_code'].dropna().unique().tolist()
        else:
            diseases = []
        disease_opts = [{'label': d, 'value': d} for d in sorted(diseases)]

        # Key-diseases value: prefer settings store, fall back to KEY_DISEASES
        s = settings or {}
        stored_key_diseases = s.get('key_diseases')
        if stored_key_diseases is not None:
            # Stored value exists — keep it (even if empty list)
            key_diseases_value = stored_key_diseases
        else:
            # First time: seed from hardcoded list, filtered to known codes
            if diseases:
                key_diseases_value = [d for d in KEY_DISEASES if d in diseases]
            else:
                key_diseases_value = list(KEY_DISEASES)

        # ── Animals from disease_stats columns ───────────────────────────
        if stats_records:
            stats_df = pd.DataFrame(stats_records)
            stats_df.columns = [c.strip().lower() for c in stats_df.columns]
            # Preserve the preferred order; only include cols that exist
            available_animals = [a for a in ANIMAL_COLUMNS if a in stats_df.columns]
            if not available_animals:
                # Fallback: any non-year column
                available_animals = [c for c in stats_df.columns if c != 'year']
        else:
            available_animals = ANIMAL_COLUMNS

        animal_opts = [{'label': a.capitalize(), 'value': a} for a in available_animals]

        # ── Years ────────────────────────────────────────────────────────
        year_opts, year_val = [], None
        if stats_records:
            stats_df = pd.DataFrame(stats_records)
            stats_df.columns = [c.strip().lower() for c in stats_df.columns]
            if 'year' in stats_df.columns:
                years     = sorted(stats_df['year'].dropna().astype(int).unique().tolist())
                next_yr   = (max(years) + 1) if years else datetime.now().year
                year_opts = ([{'label': str(y), 'value': y} for y in years]
                             + [{'label': f'{next_yr} (new)', 'value': next_yr}])
                year_val  = years[-1] if years else None

        # ── Locations ────────────────────────────────────────────────────
        location_opts = []
        if geo_records:
            geo_df = pd.DataFrame(geo_records)
            # Accept either 'location' or 'province' column
            loc_col = next((c for c in geo_df.columns
                            if c in ('location', 'province', 'district')), None)
            if loc_col:
                locs = sorted(geo_df[loc_col].dropna().unique().tolist())
                location_opts = [{'label': l, 'value': l} for l in locs]

        # ── Next case badge ──────────────────────────────────────────────
        next_no = 1
        if db_records:
            db_df = pd.DataFrame(db_records)
            if 'no' in db_df.columns and not db_df.empty:
                try:
                    next_no = int(pd.to_numeric(db_df['no'], errors='coerce').dropna().max()) + 1
                except (ValueError, TypeError):
                    next_no = len(db_df) + 1

        badge = [
            html.Span('Case #', className='ap-badge-label'),
            html.Span(str(next_no), className='ap-badge-number'),
        ]

        return (
            disease_opts,       # key-diseases options
            key_diseases_value, # key-diseases value  ← replaces cb 5
            disease_opts,       # case disease-code options
            animal_opts,        # update-animal options
            year_opts,          # year options
            year_val,           # year value
            location_opts,      # location options
            badge,              # next-case badge
        )

    # ── 5. Pre-fill general settings (autorefresh + timezone only) ────────
    #
    #  Removed key-diseases value from here to avoid the duplicate-output
    #  conflict with callback 4.
    #
    @app.callback(
        Output('ap-autorefresh-slider', 'value'),
        Output('ap-timezone-dropdown',  'value'),
        Input('ap-data-trigger',        'n_intervals'),
        State('app-settings-store',     'data'),
        prevent_initial_call=True
    )
    def prefill_general_settings(_, settings):
        s = settings or {}
        return (
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
        Output('app-settings-store',   'data',    allow_duplicate=True),
        Output('ap-flash',             'children', allow_duplicate=True),
        Output('ap-flash',             'className', allow_duplicate=True),
        Input('ap-general-save-btn',   'n_clicks'),
        State('ap-autorefresh-slider', 'value'),
        State('ap-timezone-dropdown',  'value'),
        State('app-settings-store',    'data'),
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
        Output('app-settings-store',      'data',     allow_duplicate=True),
        Output('ap-flash',                'children',  allow_duplicate=True),
        Output('ap-flash',                'className', allow_duplicate=True),
        Input('ap-diseases-save-btn',     'n_clicks'),
        State('ap-key-diseases-dropdown', 'value'),
        State('app-settings-store',       'data'),
        prevent_initial_call=True
    )
    def save_disease_settings(n, key_diseases, settings):
        if not n:
            raise PreventUpdate
        s = dict(settings or {})
        s['key_diseases'] = key_diseases or []
        return s, '✅ Disease settings saved.', 'ap-flash ap-flash-success'

    # ── 9. Render animal metric cards for selected year ───────────────────
    @app.callback(
        Output('ap-animal-metrics',         'children'),
        Output('ap-update-animal-dropdown', 'value'),
        Input('ap-year-dropdown',           'value'),
        State('ap-disease-stats-store',     'data'),
    )
    def render_animal_metrics(year, stats_records):
        if not stats_records or year is None:
            return [], None

        stats_df = pd.DataFrame(stats_records)
        stats_df.columns = [c.strip().lower() for c in stats_df.columns]
        available = [a for a in ANIMAL_COLUMNS if a in stats_df.columns]
        if not available:
            available = [c for c in stats_df.columns if c != 'year']

        row = stats_df[stats_df['year'].astype(int) == int(year)]
        if row.empty:
            values = {a: 0 for a in available}
        else:
            values = {
                a: int(row.iloc[0][a]) if pd.notna(row.iloc[0][a]) else 0
                for a in available
            }

        cards = [
            html.Div([
                html.Div(a.capitalize(), className='ap-metric-label'),
                html.Div(f"{values[a]:,}", className='ap-metric-value'),
            ], className='ap-metric-card')
            for a in available
        ]
        return cards, (available[0] if available else None)

    # ── 10. Pre-fill update value when animal / year changes ─────────────
    @app.callback(
        Output('ap-update-value-input',    'value'),
        Input('ap-update-animal-dropdown', 'value'),
        Input('ap-year-dropdown',          'value'),
        State('ap-disease-stats-store',    'data'),
    )
    def prefill_update_value(animal, year, stats_records):
        if not animal or not stats_records or year is None:
            return 0
        stats_df = pd.DataFrame(stats_records)
        stats_df.columns = [c.strip().lower() for c in stats_df.columns]
        row = stats_df[stats_df['year'].astype(int) == int(year)]
        if row.empty or animal not in stats_df.columns:
            return 0
        val = row.iloc[0][animal]
        return int(val) if pd.notna(val) else 0

    # ── 11. Save disease stats ────────────────────────────────────────────
    #
    #  Removed the refresh_stores_after_write callback that was duplicating
    #  these outputs and causing Dash conflicts.
    #
    @app.callback(
        Output('ap-disease-stats-store', 'data',     allow_duplicate=True),
        Output('ap-flash',               'children',  allow_duplicate=True),
        Output('ap-flash',               'className', allow_duplicate=True),
        Input('ap-stats-save-btn',       'n_clicks'),
        State('ap-year-dropdown',            'value'),
        State('ap-update-animal-dropdown',   'value'),
        State('ap-update-value-input',       'value'),
        State('ap-disease-stats-store',      'data'),
        prevent_initial_call=True
    )
    def save_disease_stats(n, year, animal, new_value, stats_records):
        if not n or year is None or not animal:
            raise PreventUpdate

        stats_df = pd.DataFrame(stats_records or [])
        if not stats_df.empty:
            stats_df.columns = [c.strip().lower() for c in stats_df.columns]

        new_value = int(new_value) if new_value is not None else 0

        # Upsert row for this year
        if not stats_df.empty and 'year' in stats_df.columns:
            mask = stats_df['year'].astype(int) == int(year)
            if mask.any():
                stats_df.loc[mask, animal] = new_value
            else:
                new_row           = {col: 0 for col in stats_df.columns}
                new_row['year']   = int(year)
                new_row[animal]   = new_value
                stats_df = pd.concat([stats_df, pd.DataFrame([new_row])],
                                     ignore_index=True)
        else:
            # Empty df — create from scratch
            new_row = {'year': int(year), animal: new_value}
            stats_df = pd.DataFrame([new_row])

        # Build upload df with original capitalisation expected by the sheet
        # Year stays 'Year'; animal cols capitalised (Horse, Cattle, …)
        upload_df = stats_df.copy()
        upload_df.columns = [
            'Year' if c == 'year' else c.capitalize()
            for c in upload_df.columns
        ]

        try:
            success = update_disease_stats_worksheet(upload_df)
            if success:
                return (
                    stats_df.to_dict('records'),
                    f'✅ Stats for {year} updated.',
                    'ap-flash ap-flash-success',
                )
            else:
                return (
                    stats_records,
                    '❌ Failed to update stats.',
                    'ap-flash ap-flash-error',
                )
        except Exception as e:
            logger.error(f"save_disease_stats error: {e}")
            return stats_records, f'❌ Error: {e}', 'ap-flash ap-flash-error'

    # ── 12. Add new case ──────────────────────────────────────────────────
    @app.callback(
        Output('ap-database-store',   'data',     allow_duplicate=True),
        Output('ap-flash',            'children',  allow_duplicate=True),
        Output('ap-flash',            'className', allow_duplicate=True),
        Output('ap-case-location',    'value',     allow_duplicate=True),
        Output('ap-case-disease-code','value',     allow_duplicate=True),
        Output('ap-case-count',       'value',     allow_duplicate=True),
        Output('ap-case-notes',       'value',     allow_duplicate=True),
        Input('ap-case-submit-btn',   'n_clicks'),
        State('ap-case-location',     'value'),
        State('ap-case-disease-code', 'value'),
        State('ap-case-date',         'date'),
        State('ap-case-count',        'value'),
        State('ap-case-notes',        'value'),
        State('ap-database-store',    'data'),
        prevent_initial_call=True
    )
    def add_new_case(n, location, disease_code, reported_date,
                     cases, notes, db_records):
        if not n:
            raise PreventUpdate

        # Validation
        missing = not location or not disease_code or not reported_date or not cases
        if missing:
            return (
                db_records,
                '⚠️ Please fill in all required fields.',
                'ap-flash ap-flash-warning',
                location, disease_code, cases, notes,
            )

        db_df = pd.DataFrame(db_records) if db_records else pd.DataFrame(
            columns=['no', 'location', 'disease_code', 'reported_date', 'case']
        )

        # Determine next case number
        if 'no' in db_df.columns and not db_df.empty:
            try:
                next_no = int(pd.to_numeric(db_df['no'], errors='coerce').dropna().max()) + 1
            except (ValueError, TypeError):
                next_no = len(db_df) + 1
        else:
            next_no = 1

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
                updated_db = pd.concat(
                    [db_df, pd.DataFrame([new_case])], ignore_index=True
                )
                return (
                    updated_db.to_dict('records'),
                    f'✅ Case #{next_no} added successfully!',
                    'ap-flash ap-flash-success',
                    None, None, 1, '',
                )
            else:
                return (
                    db_records,
                    '❌ Failed to add case.',
                    'ap-flash ap-flash-error',
                    location, disease_code, cases, notes,
                )
        except Exception as e:
            logger.error(f"add_new_case error: {e}")
            return (
                db_records,
                f'❌ Error: {e}',
                'ap-flash ap-flash-error',
                location, disease_code, cases, notes,
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

    # ── 14. Flash auto-clear trigger ──────────────────────────────────────
    @app.callback(
        Output('ap-flash-trigger', 'data'),
        Input('ap-flash',          'children'),
        prevent_initial_call=True
    )
    def trigger_flash_timer(msg):
        if msg:
            return {'msg': str(msg), 'timestamp': datetime.now().isoformat()}
        raise PreventUpdate