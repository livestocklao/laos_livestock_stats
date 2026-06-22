# app.py
# ─────────────────────────────────────────────────────────────────────────────
# Two-page Dash app using dcc.Location for client-side routing:
#   /        → main dashboard  (tabs: Overview, Livestock, Disease, etc.)
#   /admin   → admin panel     (protected by auth-store)
#
# The header (logo, clock, Admin button, footer logos) renders on BOTH pages.
# The login modal also lives at top-level so it works from any page.
# ─────────────────────────────────────────────────────────────────────────────

import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()   # loads ADMIN_USERNAME / ADMIN_PASSWORD from .env

import dash
from dash import html, dcc, ctx
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

# ── Tab layout builders (dashboard page) ─────────────────────────────────────
from views.overview_layout        import build_overview_tab,        register_overview_callbacks
from views.livestock_stats_layout import build_livestock_stats_tab, register_livestock_stats_callbacks
from views.disease_stats_layout   import build_disease_stats_tab,   register_disease_stats_callbacks
from views.key_diseases_layout    import build_key_diseases_tab,    register_key_diseases_callbacks
from views.weather_info_layout    import build_weather_info_tab,    register_weather_info_callbacks
from views.global_health_news_layout import build_global_news_tab,  register_global_news_callbacks

# ── Admin panel (separate page) ───────────────────────────────────────────────
# from views.admin_panel_layout import build_admin_panel, register_admin_callbacks


from utils.data_loader import initialize_data


# ─────────────────────────────────────────────────────────────────────────────
# App init
# ─────────────────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    assets_folder='assets',
    suppress_callback_exceptions=True,   # needed because admin page mounts lazily
)

app.title = 'Livestock Disease Monitoring'

app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="stylesheet" href="/assets/style.css">
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''


# ─────────────────────────────────────────────────────────────────────────────
# Default store values
# ─────────────────────────────────────────────────────────────────────────────

_AUTH_STORE_DEFAULT = {
    'is_authenticated': False,
    'username': None,
    'role': 'guest',
}

_SETTINGS_STORE_DEFAULT = {
    'autorefresh_interval': 60,
    'timezone': 'PST',
    'key_diseases': ['HPAI-P', 'ND', 'IBD', 'MG'],
    'cache_expiry_seconds': 300,
    'show_notifications': True,
}


# ─────────────────────────────────────────────────────────────────────────────
# Shared header (renders on every page)
# ─────────────────────────────────────────────────────────────────────────────

def _build_header():
    return html.Div([
        html.Div([
            # ── Left: main logo ───────────────────────────────────────────
            html.Div([
                html.Img(
                    src='assets/logos/header.png',
                    style={'width': '100%', 'height': 'auto'}
                )
            ], className='container-1-header'),

            # ── Right: clock + admin btn + footer logos ───────────────────
            html.Div([
                # Parallel row: clock | admin button
                html.Div([
                    # Date/Time container
                    html.Div([
                        html.Div([
                            html.Span(
                                id='date-time-display',
                                children=[],
                                className='date-time-span'
                            )
                        ], className='date-time-wrapper')
                    ], className='sub-container-date-time'),

                    # Admin button — full container is clickable
                    html.Div(
                        id='admin-btn-container',
                        className='sub-container-empty admin-btn-container',
                        n_clicks=0,
                        children=[
                            html.Span(
                                id='admin-btn-label',
                                children='👤 Admin',
                                className='admin-btn-label'
                            )
                        ]
                    ),
                ], className='parallel-row'),

                # Footer logos row
                html.Div([
                    html.Div([
                        html.Img(src='assets/logos/logo-1.png', className='brand-logo')
                    ], className='logo-item') for _ in range(5)
                ], className='sub-container-logos'),

            ], className='container-2-header'),
        ], className='header-top-row'),
    ], className='header-section')


# ─────────────────────────────────────────────────────────────────────────────
# Login modal (top-level, always in DOM)
# ─────────────────────────────────────────────────────────────────────────────

def _build_login_modal():
    return html.Div(
        id='admin-modal-overlay',
        className='modal-overlay modal-hidden',
        children=[
            html.Div(
                className='modal-box',
                children=[
                    # Header row
                    html.Div([
                        html.H3('Admin Login', className='modal-title'),
                        html.Button(
                            '✕',
                            id='modal-close-btn',
                            className='modal-close-btn',
                            n_clicks=0
                        ),
                    ], className='modal-header'),

                    html.P(
                        'Enter your credentials to access the admin panel.',
                        className='modal-subtitle'
                    ),

                    # Username field
                    html.Div([
                        html.Label('Username', className='modal-label'),
                        dcc.Input(
                            id='modal-username',
                            type='text',
                            placeholder='Username',
                            className='modal-input',
                            debounce=False,
                            n_submit=0
                        ),
                    ], className='modal-field'),

                    # Password field
                    html.Div([
                        html.Label('Password', className='modal-label'),
                        dcc.Input(
                            id='modal-password',
                            type='password',
                            placeholder='Password',
                            className='modal-input',
                            debounce=False,
                            n_submit=0
                        ),
                    ], className='modal-field'),

                    # Error message
                    html.Div(id='modal-error-msg', className='modal-error'),

                    # Action buttons
                    html.Div([
                        html.Button(
                            'Login',
                            id='modal-login-btn',
                            className='modal-btn modal-btn-primary',
                            n_clicks=0
                        ),
                        html.Button(
                            'Cancel',
                            id='modal-cancel-btn',
                            className='modal-btn modal-btn-secondary',
                            n_clicks=0
                        ),
                    ], className='modal-actions'),
                ]
            )
        ]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard page layout  (rendered at  /  )
# ─────────────────────────────────────────────────────────────────────────────

def _build_dashboard_page():
    return html.Div([
        dcc.Tabs(
            id='main-tabs',
            value='livestock-statistics',
            className='custom-tabs-container',
            children=[
                dcc.Tab(
                    label='Overview',
                    value='overview',
                    className='custom-tab',
                    selected_className='tab--selected',
                    children=build_overview_tab(),
                ),
                dcc.Tab(
                    label='Livestock Statistics',
                    value='livestock-statistics',
                    className='custom-tab',
                    selected_className='tab--selected',
                    children=build_livestock_stats_tab(),
                ),
                dcc.Tab(
                    label='Disease Statistics',
                    value='disease-statistics',
                    className='custom-tab',
                    selected_className='tab--selected',
                    children=build_disease_stats_tab(),
                ),
                dcc.Tab(
                    label='Key Diseases',
                    value='key-diseases',
                    className='custom-tab',
                    selected_className='tab--selected',
                    children=build_key_diseases_tab(),
                ),
                dcc.Tab(
                    label='Weather Information',
                    value='weather-information',
                    className='custom-tab',
                    selected_className='tab--selected',
                    children=build_weather_info_tab(),
                ),
                dcc.Tab(
                    label='Global Health News',
                    value='global-health-news',
                    className='custom-tab',
                    selected_className='tab--selected',
                    children=build_global_news_tab(),
                ),
            ]
        )
    ], className='main-body')


# ─────────────────────────────────────────────────────────────────────────────
# Root layout  —  header + modal are always present;
#                 page content swaps via dcc.Location
# ─────────────────────────────────────────────────────────────────────────────

app.layout = html.Div([

    # ── Client-side URL tracker ───────────────────────────────────────────
    dcc.Location(id='url', refresh=False),

    # ── Persistent stores (survive page refresh within the same browser tab)
    dcc.Store(id='auth-store',         storage_type='session', data=_AUTH_STORE_DEFAULT),
    dcc.Store(id='app-settings-store', storage_type='session', data=_SETTINGS_STORE_DEFAULT),

    # ── Login modal (always in DOM, hidden by default) ────────────────────
    _build_login_modal(),

    # ── Header (always visible on every page) ─────────────────────────────
    _build_header(),

    # ── Page content container (swapped by routing callback below) ────────
    html.Div(id='page-content'),

    # ── Clock interval ────────────────────────────────────────────────────
    dcc.Interval(id='date-time-interval', interval=1000, n_intervals=0),

], className='app-container')


# ─────────────────────────────────────────────────────────────────────────────
# Routing callback  —  swaps page-content based on URL pathname
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    Output('page-content', 'children'),
    Input('url', 'pathname'),
)
def route(pathname):
    """
    /        → dashboard (tabs)
    /admin   → admin panel
    anything else → redirect to dashboard
    """
    if pathname == '/admin':
        return _build_dashboard_page()
        # return build_admin_panel()
    return _build_dashboard_page()


# ─────────────────────────────────────────────────────────────────────────────
# Admin button: navigate to /admin  OR  logout if already authenticated
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    Output('admin-modal-overlay', 'className'),
    Output('modal-username',      'value'),
    Output('modal-password',      'value'),
    Output('modal-error-msg',     'children'),
    Output('auth-store',          'data'),
    Output('url',                 'pathname'),       # ← navigate to /admin after login
    Input('admin-btn-container',  'n_clicks'),
    Input('modal-close-btn',      'n_clicks'),
    Input('modal-cancel-btn',     'n_clicks'),
    Input('modal-login-btn',      'n_clicks'),
    State('modal-username',       'value'),
    State('modal-password',       'value'),
    State('auth-store',           'data'),
    State('url',                  'pathname'),
    prevent_initial_call=True,
)
def handle_admin_modal(
    admin_clicks, close_clicks, cancel_clicks, login_clicks,
    username, password, auth_data, current_path
):
    """
    Admin container clicked:
      - If authenticated  → logout and stay on current page
      - If not            → open login modal

    Login button:
      - Valid creds       → close modal, store auth, redirect to /admin
      - Invalid           → show error, stay on modal

    Close / Cancel        → close modal, clear fields
    """
    triggered = ctx.triggered_id

    # ── Admin button clicked ──────────────────────────────────────────────
    if triggered == 'admin-btn-container':
        if auth_data and auth_data.get('is_authenticated'):
            # Already logged in → logout, go back to dashboard
            new_auth = {'is_authenticated': False, 'username': None, 'role': 'guest'}
            return 'modal-overlay modal-hidden', '', '', '', new_auth, '/'
        else:
            # Not logged in → open modal, stay on current page
            return 'modal-overlay modal-visible', '', '', '', auth_data, current_path

    # ── Close or Cancel ───────────────────────────────────────────────────
    if triggered in ('modal-close-btn', 'modal-cancel-btn'):
        return 'modal-overlay modal-hidden', '', '', '', auth_data, current_path

    # ── Login attempt ─────────────────────────────────────────────────────
    if triggered == 'modal-login-btn':
        username = (username or '').strip()
        password = (password or '').strip()

        if not username or not password:
            return (
                'modal-overlay modal-visible', username, password,
                'Please enter both username and password.',
                auth_data, current_path
            )

        valid_username = os.environ.get('ADMIN_USERNAME', '')
        valid_password = os.environ.get('ADMIN_PASSWORD', '')

        if not valid_username:
            return (
                'modal-overlay modal-visible', username, password,
                'Admin credentials not configured on the server.',
                auth_data, current_path
            )

        if username == valid_username and password == valid_password:
            new_auth = {'is_authenticated': True, 'username': username, 'role': 'admin'}
            # Close modal + navigate to /admin
            return 'modal-overlay modal-hidden', '', '', '', new_auth, '/admin'
        else:
            return (
                'modal-overlay modal-visible', username, '',
                'Invalid username or password.',
                auth_data, current_path
            )

    raise PreventUpdate


# ─────────────────────────────────────────────────────────────────────────────
# Admin button label  (shows "Admin"  or  "Logout (username)")
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    Output('admin-btn-label', 'children'),
    Input('auth-store', 'data'),
)
def update_admin_label(auth_data):
    if auth_data and auth_data.get('is_authenticated'):
        return f"Logout ({auth_data.get('username', 'Admin')})"
    return 'Admin'


# ─────────────────────────────────────────────────────────────────────────────
# Clock
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Clock
# ─────────────────────────────────────────────────────────────────────────────

@app.callback(
    Output('date-time-display', 'children'),
    Input('date-time-interval', 'n_intervals'),
)
def update_clock(n):
    now = datetime.now()
    # Return HTML that combines time and date in one line with icons
    return html.Div([
        html.Span([
            html.Span("🕐", className="time-icon"),
            html.Span(now.strftime('%I:%M:%S %p'), className="time-text"),
            html.Span("  ", style={"margin": "0 8px", "color": "#4a6a8a"}),
            html.Span("📅", className="date-icon"),
            html.Span(now.strftime('%a, %b %d, %Y'), className="date-text"),
        ], className="date-time-span")
    ], className="date-time-wrapper")
    


# ─────────────────────────────────────────────────────────────────────────────
# Register all callbacks
# ─────────────────────────────────────────────────────────────────────────────

initialize_data()

register_overview_callbacks(app)
register_livestock_stats_callbacks(app)
register_disease_stats_callbacks(app)
register_key_diseases_callbacks(app)
register_weather_info_callbacks(app)
register_global_news_callbacks(app)
# register_admin_callbacks(app)


# ─────────────────────────────────────────────────────────────────────────────
# Timed flash-message clear  (clientside, targets the trigger store)
# Writing to ap-flash-trigger (a Store) avoids any Output conflict with
# the ap-flash div, whose sole owner is render_flash() in admin_panel_layout.
# ─────────────────────────────────────────────────────────────────────────────

app.clientside_callback(
    """
    function(trigger) {
        if (!trigger || !trigger.msg) return window.dash_clientside.no_update;
        setTimeout(function() {
            var el = document.getElementById('ap-flash');
            if (el) { el.textContent = ''; el.className = 'ap-flash'; }
        }, 4000);
        return window.dash_clientside.no_update;
    }
    """,
    Output('ap-flash-trigger', 'data', allow_duplicate=True),
    Input('ap-flash-trigger',  'data'),
    prevent_initial_call=True,
)


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True, port=8030)