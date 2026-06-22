import numpy as np
import base64
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import folium
from folium.plugins import MarkerCluster
import matplotlib
# Enforce a non-interactive backend that does not use Tkinter
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde




COLORS = ["#0081a7", "#00afb9", "#f07167", "#e9c46a",
          "#264653", "#f4a261", "#e76f51", "#ef233c", "#fed9b7",
          "#f6bd60", "#84a59d", "#f95738", "#fdfcdc"]




def quick_overview_table(data: pd.DataFrame) -> go.Figure:
    """Toggle between table and chart view with button click."""

    # Return table view
    fig = go.Figure()

    # data = data.applymap(lambda x: f"{x}\n" if pd.notna(x) else x)

    # Format numbers with commas
    formatted_data = data.copy()
    for col in formatted_data.columns:
        if col != 'YEAR':
            formatted_data[col] = formatted_data[col].apply(lambda x: f"<br>{x:,.0f}<br>")

    headers = list(data.columns)
    cells = [formatted_data[col].tolist() for col in headers]

    fig.add_trace(go.Table(
        header=dict(
            values=[f"<b>{col}</b>" for col in headers],
            fill_color="#264653",
            font=dict(family="ubuntu", color="white", size=20, weight="bold"),
            align="center",
            height=50,
        ),
        cells=dict(
            values=cells,
            font=dict(family="ubuntu", size=18, weight="bold"),
            align="center",
            height=55,
            # padding=dict(top=15, bottom=15)  # Add padding for better spacing
        )
    ))

    fig.update_layout(
        title=dict(
            text="<b>Animal Statistics from 2020-2024</b>",
            font=dict(family="ubuntu", size=24, color="#1b263b"),
            x=0.5,
            xanchor="center"
        ),
        margin=dict(l=20, r=20, t=80, b=0),
        height=400,
    )
    return fig


def display_animal_stats(data: pd.DataFrame, animal: str) -> go.Figure:
    import numpy as np

    y_max = data[f"{animal}"].max()
    y_min = data[f"{animal}"].min()
    y_upper = y_max + y_min / 2

    tick_vals = np.linspace(0, y_upper, 6).tolist()
    tick_text = [format_currency_label(v) for v in tick_vals]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=data["YEAR"],
            y=data[f"{animal}"],
            name=f"{animal} Stats",
            marker_color="#264653",
            hovertemplate=(
                f"Year: %{{x}}<br>"
                f"{animal}: %{{y}}<br>"
                "<extra></extra>"
            ),
            text=data[f"{animal}"].apply(format_currency_label),
            textposition='outside',
            textfont=dict(size=16, family="ubuntu", color="#1b263b", weight="bold")
        )
    )
    fig.update_layout(
        height=350,
        showlegend=False,
        xaxis_title=dict(text="Year", font=dict(size=18, weight="bold", family="ubuntu")),
        yaxis_title=dict(text="Population Count", font=dict(size=18, weight="bold", family="ubuntu")),
        hovermode="x unified",
        xaxis=dict(
            tickfont=dict(size=16, family="ubuntu", weight="bold"),
            tickmode='array',
            tickvals=data["YEAR"].tolist(),
            gridcolor='lightgray',
            showline=True,
            linewidth=1,
            linecolor='lightgray'
        ),
        yaxis=dict(
            tickfont=dict(size=16, family="ubuntu", weight="bold"),
            tickvals=tick_vals,
            ticktext=tick_text,
            gridcolor='lightgray',
            showline=True,
            linewidth=1,
            linecolor='lightgray',
            range=[1, y_upper]
        ),
        hoverlabel=dict(
            bgcolor="white",
            font_color="black",
            font_size=16,
            font_family="Rockwell"
        ),
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(l=80, r=10, t=5, b=50)
    )
    return fig


def plot_disease_outbreak_overtime(data):
    data['reported_date'] = pd.to_datetime(
        data['reported_date'],
        format='%m/%d/%Y'
    )
    data = data.sort_values('reported_date')
    data = data.set_index('reported_date')['case'].resample('ME').sum().reset_index()

    fig = go.Figure()

    x_vals = data['reported_date'].tolist()
    y_vals = data['case'].tolist()

    fig.add_trace(go.Scatter(
        x=x_vals,
        y=y_vals,
        mode='markers+lines+text',
        textposition="top center",
        text=data['case'],
        fill="tozeroy",
        line=dict(color="#00afb9"),
        fillcolor="rgba(0, 175, 185, 0.4)",
        name='Number of Cases',
        hovertext=data['case'],
        hoverinfo='name+text',
    ))

    fig = format_hover_layout(fig)
    fig.update_layout(
        title=dict(
            text="<b>Number of Cases Reported overtime</b>",
            font=dict(family="ubuntu", size=24, color="#1b263b"),
            x=0.5,
            xanchor="center"
        ),
        xaxis_title=dict(text="Date", font=dict(size=16, weight="bold", family="ubuntu")),
        yaxis_title=dict(text="Number of Cases", font=dict(size=16, weight="bold", family="ubuntu")),
        xaxis=dict(
            showgrid=False
        ),
        yaxis=dict(
            showticklabels=False,
            showgrid=False,
            range=[0, max(y_vals)+2]
        ),
        legend=dict(orientation="h", xanchor='center', x=0.5, y=-0.25),
        height=300,
        margin=dict(t=60, l=10, r=10, b=10)

    )
    return fig


def create_disease_map(data):
    data['reported_date'] = pd.to_datetime(
        data['reported_date'],
        format='%m/%d/%Y'
    )
    cutoff_date = datetime.today() - timedelta(days=10000)
    data = data[data['reported_date'] >= cutoff_date]

    province_disease = data.groupby(['province', 'disease_code'])['case'].sum().unstack().fillna(0)
    province_totals = province_disease.sum(axis=1)
    diseases = province_disease.columns
    disease_colors = {disease: COLORS[i % len(COLORS)] for i, disease in enumerate(diseases)}

    laos_coords = [18.0, 105.0]
    m = folium.Map(location=laos_coords, zoom_start=15, tiles='cartodbpositron')

    with open("data/laos.geojson", "r") as f:
        laos_geojson = json.load(f)

    folium.GeoJson(
        laos_geojson,
        style_function=lambda x: {
            'fillColor': '#3186cc',
            'color': '#3186cc',
            'weight': 0,
            'fillOpacity': 0.3
        },
        name='Laos Boundary'
    ).add_to(m)

    coordinates = laos_geojson['geometry']['coordinates'][0]
    m.fit_bounds([
        [min(y for x, y in coordinates), min(x for x, y in coordinates)],
        [max(y for x, y in coordinates), max(x for x, y in coordinates)]
    ])

    marker_cluster = MarkerCluster().add_to(m)

    province_centers = (
        data.groupby('province')
        .agg({'latitude': 'mean', 'longitude': 'mean'})
        .dropna()
        .to_dict('index')
    )

    max_total = province_totals.max()
    min_size = 80
    max_size = 120

    for province in province_disease.index:
        if province not in province_centers:
            continue

        lat = province_centers[province]['latitude']
        lon = province_centers[province]['longitude']
        total_cases = province_totals[province]
        size = min_size + (max_size - min_size) * (total_cases / max_total)
        values = province_disease.loc[province].values

        popup_content = f"""
        <div style='font-family: Arial, sans-serif; width: 200px;'>
            <h4 style='margin-bottom: 5px; color: #333;'>{province}</h4>
            <p style='margin: 5px 0; font-weight: bold; font-size:12px;'>Total cases: {total_cases}</p>
            <hr style='margin: 8px 0; border-color: #eee;'>
        """
        for disease, value in zip(diseases, values):
            if value > 0:
                popup_content += f"""
                <p style='margin: 3px 0;'>
                    <span style='color: {disease_colors[disease]}; font-size:12px; font-weight: bold;'>■</span>
                    <span style='font-weight: bold; font-size:12px; color: {disease_colors[disease]};'>{disease}</span>: {value}
                </p>
                """
        popup_content += "</div>"

        # ── Render pie to an in-memory buffer and encode as base64 ──────
        import io
        fig, ax = plt.subplots(figsize=(size / 10, size / 10))
        ax.pie(
            values,
            colors=[disease_colors[d] for d in diseases],
            wedgeprops={'linewidth': 0.5, 'edgecolor': 'white'}
        )
        ax.axis('equal')

        buf = io.BytesIO()
        plt.savefig(buf, format='png', transparent=True, dpi=100)
        plt.close()
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode('utf-8')
        buf.close()

        # ── Use data URI so the iframe can resolve the image ────────────
        icon_url = f"data:image/png;base64,{img_b64}"
        icon = folium.features.CustomIcon(icon_url, icon_size=(size, size))

        folium.Marker(
            location=[lat, lon],
            icon=icon,
            popup=folium.Popup(popup_content, max_width=250)
        ).add_to(marker_cluster)

    return m


# ----------------------------- key diseases page --------------------------------
def plot_key_disease_distribution(data):
    # Total cases per disease code
    summary = data.groupby("disease_code")["case"].sum().reset_index()

    # Plot the treemap
    fig = go.Figure(go.Treemap(
        labels=summary["disease_code"],
        values=summary["case"],
        parents=[""] * len(summary),  # single-level treemap
        marker=dict(
            colors=COLORS[:len(summary)],
            line=dict(color="#fff", width=2)
        ),
        textinfo="label+percent parent",
        hovertemplate="<b>%{label}</b><br>Cases: %{value}<extra></extra>"
    ))

    fig.update_layout(
        title=dict(
            text="<b>Distribution of Key Diseases</b>",
            font=dict(family="ubuntu", size=24, color="#1b263b"),
            x=0.5,
            xanchor="center"
        ),
        margin=dict(t=40, l=10, r=10, b=10),
        height=300,
    )

    fig = format_hover_layout(fig)

    return fig



def key_disease_reports_overtime(data):
    data['reported_date'] = pd.to_datetime(
        data['reported_date'],
        format='%m/%d/%Y'
    )
    data = data.sort_values('reported_date')

    pivot_df = (
        data.groupby(['reported_date', 'disease_code'])['case']
        .sum()
        .unstack(fill_value=0)
        .resample('ME')
        .sum()
        .reset_index()
    )
    pivot_df.columns.name = None
    disease_codes = pivot_df.columns[1:]  # exclude reported_date
        
    fig = go.Figure()

    cumulative_y = None  # tracks the running stack top

    for i, disease in enumerate(disease_codes):
        y_values = pivot_df[disease].values

        if cumulative_y is None:
            stacked_y = y_values
            fill_mode = 'tozeroy'
        else:
            stacked_y = cumulative_y + y_values
            fill_mode = 'tonexty'

        fig.add_trace(go.Scatter(
            x=pivot_df['reported_date'],
            y=stacked_y,
            mode='lines',
            name=disease,
            fill=fill_mode,
            line=dict(width=0),
            hoverinfo='x+name+text',
            text=y_values,   # show this disease's own contribution on hover
            fillcolor=COLORS[i % len(COLORS)]
        ))

        cumulative_y = stacked_y  # advance the stack baseline

    fig = format_hover_layout(fig)
    fig.update_layout(
        title=dict(
            text="<b>Stacked Disease Reports Over Time</b>",
            font=dict(family="ubuntu", size=24, color="#1b263b"),
            x=0.5,
            xanchor="center"
        ),
        xaxis_title=dict(text="Date", font=dict(size=16, weight="bold", family="ubuntu")),
        yaxis_title=dict(text="Number of Cases", font=dict(size=16, weight="bold", family="ubuntu")),
        legend=dict(orientation="h", xanchor='center', x=0.5, y=-0.25),
        yaxis=dict(showticklabels=True),
        height=300,
        margin=dict(l=50, r=5, t=50, b=20)
    )
    return fig


def key_disease_dist_overtime(data):
    data['reported_date'] = pd.to_datetime(
        data['reported_date'],
        format='%m/%d/%Y'
    )
    data['year'] = data['reported_date'].dt.year

    grouped = (
        data.groupby(['year', 'disease_code'])['case']
        .sum()
        .reset_index()
    )

    pivot_df = grouped.pivot(index='year', columns='disease_code', values='case').fillna(0)

    fig = go.Figure()

    for i, disease in enumerate(pivot_df.columns):
        x_values = pivot_df.index.astype(str).tolist()
        y_values = pivot_df[disease].tolist()

        fig.add_trace(go.Bar(
            x=x_values,
            y=y_values,
            name=disease,
            marker_color=COLORS[i % len(COLORS)],
            orientation='v'
        ))

    fig.update_layout(
        barmode='group',
        title=dict(
            text="<b>Yearly Distribution of Disease Cases</b>",
            font=dict(family="ubuntu", size=24, color="#1b263b"),
            x=0.5,
            xanchor="center"
        ),
        xaxis_title='Year',
        yaxis_title='Number of Cases',
        xaxis_type='category',
        yaxis=dict(tickformat=',d'),
        legend=dict(orientation="h", xanchor='center', x=0.5, y=-0.25),
        margin=dict(l=50, r=5, t=50, b=20)
    )

    fig = format_hover_layout(fig)
    return fig


def key_disease_kde_distribution(data):
    data['reported_date'] = pd.to_datetime(
        data['reported_date'],
        format='%m/%d/%Y'
    )
    disease_codes = data['disease_code'].unique()

    fig = go.Figure()

    for i, disease in enumerate(disease_codes):
        disease_data = data[data['disease_code'] == disease]['case']
        if len(disease_data) > 0:
            # Compute KDE
            kde = gaussian_kde(disease_data)
            x_vals = np.linspace(data['case'].min(), data['case'].max(), 200)
            y_vals = kde(x_vals)

            fig.add_trace(go.Scatter(
                x=x_vals.tolist(),
                y=y_vals.tolist(),
                mode='lines',
                name=disease,
                fill='tozeroy',
                line=dict(color=COLORS[i % len(COLORS)], width=2),
                opacity=0.6
            ))

    fig.update_layout(
        title=dict(
            text="<b>Probability Distribution of Key Diseases</b>",
            font=dict(family="ubuntu", size=24, color="#1b263b"),
            x=0.5,
            xanchor="center"
        ),
        xaxis_title=dict(text="Number of Cases per Report", font=dict(size=16, weight="bold", family="ubuntu")),
        yaxis_title=dict(text="Probability Density", font=dict(size=16, weight="bold", family="ubuntu")),
        legend_title='Disease',
        plot_bgcolor='white',
        hovermode='x unified',
        legend=dict(orientation="h", xanchor='center', x=0.5, y=-0.25),
        margin=dict(l=50, r=5, t=50, b=20),
        height=300
    )

    fig = format_hover_layout(fig)
    return fig


def key_disease_wrt_location(data):
    grouped = (
        data.groupby(['province', 'disease_code'])['case']
        .sum()
        .reset_index()
    )

    pivot_df = (
        grouped
        .pivot(index='province', columns='disease_code', values='case')
        .fillna(0)
    )

    fig = go.Figure()

    for i, disease in enumerate(pivot_df.columns):

        # 🔹 Skip diseases with TOTAL cases = 0
        if pivot_df[disease].sum() == 0:
            continue

        x_vals = pivot_df.index.tolist()

        # 🔹 Replace 0 with None → no bar, no hover
        y_vals = pivot_df[disease].replace(0, None).tolist()

        fig.add_trace(go.Bar(
            x=x_vals,
            y=y_vals,
            name=disease,
            marker_color=COLORS[i % len(COLORS)],
            hovertemplate=(
                f"<b>{disease}</b> "
                "Cases: %{y}<extra></extra>"
            )
        ))

    fig.update_layout(
        barmode='stack',
        title=dict(
            text="<b>Distribution of Disease Cases by Province</b>",
            font=dict(family="ubuntu", size=24, color="#1b263b"),
            x=0.5,
            xanchor="center"
        ),
        xaxis_title=dict(text="Province", font=dict(size=16, weight="bold", family="ubuntu")),
        yaxis_title=dict(text="Number of Cases", font=dict(size=16, weight="bold", family="ubuntu")),
        xaxis_type='category',
        legend=dict(orientation="h", xanchor='center', x=0.5, y=-0.25),
        height=400,
        plot_bgcolor='white',
        margin=dict(l=50, r=5, t=50, b=20)
    )

    fig = format_hover_layout(fig)
    return fig



def plot_disease_code_map(data):
    # Aggregate by location, disease_code, and coordinates
    grouped = (
        data.groupby(['location', 'disease_code', 'latitude', 'longitude'])['case']
        .sum()
        .reset_index()
    )

    fig = go.Figure()

    for i, disease in enumerate(grouped['disease_code'].unique()):
        df = grouped[grouped['disease_code'] == disease]

        fig.add_trace(go.Scattermapbox(
            lat=df['latitude'].tolist(),
            lon=df['longitude'].tolist(),
            mode='markers',
            marker=go.scattermapbox.Marker(
                size=(df['case'] / df['case'].max() * 40 + 5).tolist(),  # scaled sizes
                color=COLORS[i % len(COLORS)],
                opacity=0.7
            ),
            text=(df['location'] + "<br>Cases: " + df['case'].astype(int).astype(str)).tolist(),
            name=disease,
            hoverinfo="text"
        ))

    fig.update_layout(
        mapbox=dict(
            style="carto-positron",
            zoom=4.5,
            center=dict(
                lat=data['latitude'].mean(),
                lon=data['longitude'].mean()
            )
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        title=dict(
            text="<b>Disease Distribution Map</b>",
            font=dict(family="ubuntu", size=24, color="#1b263b"),
            x=0.5,
            xanchor="center"
        ),        
        legend=dict(orientation="h", x=0.5, xanchor='center', y=-0.1),
        height=400
    )

    fig = format_hover_layout(fig)
    return fig

# ----------------------------- WEATHER PAGE -------------------------------------
def create_weather_map(weather_data):
    """
    Create a map visualization of weather data with Laos polygon layer
    """
    if len(weather_data)==0:
        return go.Figure()

    # Load geojson for Laos boundary
    with open("data/laos.geojson", "r") as f:
        laos_geojson = json.load(f)

    # Prepare data for map
    regions = []
    temperatures = []
    humidity_values = []
    lats = []
    lons = []
    hover_texts = []

    for index, data in weather_data.iterrows():
        if data is not None:
            region = data['region']
            regions.append(data['region'])
            temperatures.append(data['temperature'])
            humidity_values.append(data['humidity'])
            lats.append(data['latitude'])
            lons.append(data['longitude'])

            hover_text = f"""
            <b>{region}</b><br>
            Temperature: {data['temperature']:.1f}°C<br>
            Feels like: {data['feels_like']:.1f}°C<br>
            Humidity: {data['humidity']}%<br>
            Description: {data['description']}<br>
            Wind: {data['wind_speed']:.1f} m/s
            """
            hover_texts.append(hover_text)

    # Create map
    fig = go.Figure()

    # Add Scattermapbox with darker colors
    fig.add_trace(go.Scattermapbox(
        lat=lats,
        lon=lons,
        mode='markers+text',
        marker=dict(
            size=[max(10, temp + 20) for temp in temperatures],
            color=temperatures,
            colorscale=[[0, '#3d0000'], [0.5, '#ff6b35'], [1, '#004e89']],  # Darker colorscale
            showscale=True,
            colorbar=dict(title="Temperature (°C)"),
            opacity=0.85
        ),
        text=[f"{temp:.1f}°C" for temp in temperatures],
        textposition="middle center",
        textfont=dict(size=10, color='white'),
        hovertemplate=['%{customdata}' for _ in hover_texts],
        customdata=hover_texts,
        hoverinfo='text',
        showlegend=False,
        name="City Weather"
    ))

    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=18.2052, lon=103.8950),
            zoom=5,
            layers=[
                dict(
                    source=laos_geojson,
                    type='fill',
                    color='rgba(100, 150, 200, 0.1)',
                    name='Laos Boundary'
                ),
                dict(
                    source=laos_geojson,
                    type='line',
                    color="#8bafcf",
                    line=dict(width=4),
                    name='Laos Border'
                )
            ]
        ),
        title=dict(
            text="<b>Weather Conditions Across Laos</b>",
            font=dict(family="ubuntu", size=24, color="#1b263b"),
            x=0.5,
            xanchor="center"
        ),
        height=500,
        margin=dict(l=0, r=0, t=40, b=0),
        showlegend=False
    )

    return fig


def create_weather_charts(weather_data):
    """
    Create temperature and humidity comparison charts using go.Figure
    """
    if len(weather_data)==0:
        return go.Figure(), go.Figure()

    regions = []
    temperatures = []
    humidity_values = []

    for index, data in weather_data.iterrows():
        if data is not None:
            region = data['region']
            regions.append(region)
            temperatures.append(data['temperature'])
            humidity_values.append(data['humidity'])

    # Normalize values for coloring
    temp_colors = np.interp(temperatures, (min(temperatures), max(temperatures)), (0, 1))
    humidity_colors = np.interp(humidity_values, (min(humidity_values), max(humidity_values)), (0, 1))

    # Temperature Figure
    temp_fig = go.Figure()
    temp_fig.add_trace(go.Bar(
        x=regions,
        y=temperatures,
        text=[f"{t:.1f}°C" for t in temperatures],
        textposition='outside',
        marker=dict(
            color=temperatures,
            colorscale='RdYlBu_r',
            colorbar=dict(title='Temp (°C)')
        ),
        hovertemplate='Region: %{x}<br>Temperature: %{y}°C<extra></extra>',
        name='Temperature'
    ))
    temp_fig.update_layout(
        title=dict(
            text="<b>Temperature by Region (°C)</b>",
            font=dict(family="ubuntu", size=24, color="#1b263b"),
            x=0.5,
            xanchor="center"
        ),
        xaxis_title=dict(text="Region", font=dict(size=16, weight="bold", family="ubuntu")),
        yaxis_title=dict(text="Temperature (°C)", font=dict(size=16, weight="bold", family="ubuntu")),
        xaxis_tickangle=-45,
        height=400,
        showlegend=False,
        plot_bgcolor='white',
        yaxis=dict(range=[0, max(temperatures) * 1.15]),
        margin=dict(l=50, r=40, t=80, b=20)
    )
    temp_fig = format_hover_layout(temp_fig)

    # Humidity Figure
    humidity_fig = go.Figure()
    humidity_fig.add_trace(go.Bar(
        x=regions,
        y=humidity_values,
        text=[f"{h:.0f}%" for h in humidity_values],
        textposition='outside',
        marker=dict(
            color=humidity_values,
            colorscale='Blues',
            colorbar=dict(title='Humidity (%)')
        ),
        hovertemplate='Region: %{x}<br>Humidity: %{y}%<extra></extra>',
        name='Humidity'
    ))
    humidity_fig.update_layout(
        title=dict(
            text="<b>Humidity by Region (%)</b>",
            font=dict(family="ubuntu", size=24, color="#1b263b"),
            x=0.5,
            xanchor="center"
        ),
        xaxis_title=dict(text="Region", font=dict(size=16, weight="bold", family="ubuntu")),
        yaxis_title=dict(text="Humidity (%)", font=dict(size=16, weight="bold", family="ubuntu")),
        xaxis_tickangle=-45,
        height=400,
        showlegend=False,
        plot_bgcolor='white',
        yaxis=dict(range=[0, 110]),
        margin=dict(l=50, r=40, t=80, b=20)
    )
    humidity_fig = format_hover_layout(humidity_fig)

    return temp_fig, humidity_fig




def format_hover_layout(fig):
    fig = fig.update_layout(
        height=400,
        hovermode="x unified",
        hoverlabel=dict(bgcolor="white", font_color="black",
                        font_size=12, font_family="Rockwell"))
    return fig


def format_currency_label(value):
    """
    Format a numerical value as a currency label.

    :param value: The numerical value to format.
    :return: Formatted currency label string.
    """
    if value >= 1e9:  # Billion
        return f'{value / 1e9:.1f} bn'
    elif value >= 1e6:  # Million
        return f'{value / 1e6:.1f} M'
    elif value >= 1e3:  # Thousand
        return f'{value / 1e3:.1f} K'
    else:
        return f'{value}'


def calculate_disease_metrics(
        database: pd.DataFrame
) -> dict:
    """
    Calculate disease metrics for display.

    Args:
        database: Disease database DataFrame

    Returns:
        Dictionary of calculated metrics
    """
    filtered_data = database

    metrics = {
        'total_cases': int(filtered_data['case'].sum()) if 'case' in filtered_data.columns else 0,
        # 'total_deaths': int(filtered_data['deaths'].sum()) if 'deaths' in filtered_data.columns else 0,
        'most_affected': filtered_data.groupby('location')['case'].sum().idxmax(),
        'most_viral': filtered_data.groupby('disease_code')['case'].sum().idxmax(),
    }

    return metrics


# =====================livestock stats =============================

def create_livestock_year_chart(df_2024, df_2025):
    """
    Create a bar chart comparing livestock counts between 2024 and 2025.
    
    Parameters:
    -----------
    df_2024 : pandas.DataFrame
        DataFrame containing 2024 livestock data
    df_2025 : pandas.DataFrame
        DataFrame containing 2025 livestock data
    
    Returns:
    --------
    plotly.graph_objects.Figure
        Bar chart figure comparing livestock by year
    """
    cols = [c for c in df_2024.columns if c != 'Province']
    
    # Sum by species
    species_2024 = df_2024[cols].sum()
    species_2025 = df_2025[cols].sum()
    
    # Apply currency formatting to text values
    text_2024 = [format_currency_label(val) for val in species_2024.values]
    text_2025 = [format_currency_label(val) for val in species_2025.values]
    
    fig = go.Figure(data=[
        go.Bar(
            x=species_2024.index, 
            y=species_2024.values, 
            name="2024",
            marker_color="#219451",
            text=text_2024,
            textposition="outside",
            textfont=dict(size=14, family="ubuntu", color="#1b263b", weight="bold")
        ),
        go.Bar(
            x=species_2025.index, 
            y=species_2025.values, 
            name="2025",
            marker_color="#279599",
            text=text_2025,
            textposition="outside",
            textfont=dict(size=14, family="ubuntu", color="#1b263b", weight="bold")
        ),
    ])
    
    fig.update_layout(
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font={"size": 11, "color": "#555"},
        title=dict(
            text="<b>Total Livestock by Year</b>",
            font=dict(family="ubuntu", size=18, color="#1b263b"),
            x=0.5,
            xanchor="center"
        ),
        xaxis_title=dict(
            text="Livestock Type", 
            font=dict(size=12, weight="bold", family="ubuntu")
        ),
        yaxis_title=dict(
            text="Count", 
            font=dict(size=12, weight="bold", family="ubuntu")
        ),
        xaxis=dict(
            tickfont=dict(size=14, family="ubuntu", weight="bold"),
            tickmode='array',
            gridcolor='lightgray',
            showline=True,
            linewidth=1,
            linecolor='lightgray'
        ),
        yaxis=dict(
            tickfont=dict(size=14, family="ubuntu", weight="bold"),
            gridcolor='lightgray',
            showline=True,
            linewidth=1,
            linecolor='lightgray'
        ),
        margin=dict(t=45, l=40, r=20, b=30),
        legend=dict(
            orientation="h", 
            xanchor='center', 
            x=0.5, 
            y=-0.15,
            font=dict(size=11)
        ),
        height=None,  # Allow auto-sizing
        bargap=0.3,
    )
    
    return fig


def create_livestock_composition_chart(df, year="2024"):
    cols = [c for c in df.columns if c != 'Province']
    species_totals = df[cols].sum()
    # species_totals = species_totals.sort_index()
    
    # Color palette for the donut chart
    colors = [
        "#2ecc71", "#3498db", "#e74c3c", "#f39c12",
        "#9b59b6", "#1abc9c", "#34495e", "#e67e22",
        "#95a5a6", "#16a085"
    ]
    
    fig = go.Figure(data=[
        go.Pie(
            labels=species_totals.index,
            values=species_totals.values,
            hole=0.4,  # Donut chart
            marker={"colors": COLORS[:len(species_totals)]},
            textinfo="label+percent",
            textposition="outside",
            textfont=dict(size=14, family="ubuntu", color="#1b263b", weight="bold"),
            hoverinfo="label+value+percent",
            pull=[0.02] * len(species_totals),  # Slight pull for all slices
        )
    ])
    
    # Add year in center
    fig.add_annotation(
        text=f"<b>{year}</b>",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(
            size=28,
            family="ubuntu",
            color="#1b263b"
        ),
        xanchor="center",
        yanchor="middle"
    )
    
    fig.update_layout(
        hovermode="closest",
        margin={"l": 20, "r": 20, "t": 45, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"size": 11, "color": "#555"},
        title=dict(
            # text=f"<b>Livestock Composition {year}</b>",
            font=dict(family="ubuntu", size=18, color="#1b263b"),
            # x=0.5,
            # xanchor="center"
        ),
        height=None,  # Allow auto-sizing
        legend=dict(
            orientation="v", 
            x=1.05, 
            y=0.5,
            font=dict(size=11)
        ),
        showlegend=True,
    )
    
    return fig


def create_livestock_animal_type_charts(data_farm, data_amount):
    cols = [c for c in data_farm.columns if c != 'Province']
    
    # Aggregate totals across all provinces
    farm_totals = data_farm[cols].sum()
    amount_totals = data_amount[cols].sum()
    
    # farm_totals = farm_totals.sort_index()
    # amount_totals = amount_totals.sort_index()
    
    # Color palette for the donut charts
    colors = [
        "#2ecc71", "#3498db", "#e74c3c", "#f39c12",
        "#9b59b6", "#1abc9c", "#34495e", "#e67e22",
        "#95a5a6", "#16a085"
    ]
    
    # Chart 1: Farm Count Distribution
    fig_farm = go.Figure(data=[
        go.Pie(
            labels=farm_totals.index,
            values=farm_totals.values,
            hole=0.4,
            marker={"colors": COLORS[:len(farm_totals)]},
            textinfo="label+percent",
            textposition="outside",
            textfont=dict(size=12, family="ubuntu", color="#1b263b", weight="bold"),
            hoverinfo="label+value+percent",
            pull=[0.02] * len(farm_totals),
        )
    ])
    
    fig_farm.update_layout(
        hovermode="closest",
        margin={"l": 20, "r": 20, "t": 45, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"size": 11, "color": "#555"},
        title=dict(
            text="<b>Farm Count</b>",
            font=dict(family="ubuntu", size=16, color="#1b263b"),
        ),
        legend=dict(
            orientation="v", 
            x=1.05, 
            y=0.5,
            font=dict(size=10)
        ),
        showlegend=True,
        height=400,
    )
    
    # Chart 2: Total Amount Distribution
    fig_amount = go.Figure(data=[
        go.Pie(
            labels=amount_totals.index,
            values=amount_totals.values,
            hole=0.4,
            marker={"colors": COLORS[:len(amount_totals)]},
            textinfo="label+percent",
            textposition="outside",
            textfont=dict(size=12, family="ubuntu", color="#1b263b", weight="bold"),
            hoverinfo="label+value+percent",
            pull=[0.02] * len(amount_totals),
        )
    ])
    
    fig_amount.update_layout(
        hovermode="closest",
        margin={"l": 20, "r": 20, "t": 45, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"size": 11, "color": "#555"},
        title=dict(
            text="<b>Total Amount</b>",
            font=dict(family="ubuntu", size=16, color="#1b263b"),
        ),
        legend=dict(
            orientation="v", 
            x=1.05, 
            y=0.5,
            font=dict(size=10)
        ),
        showlegend=True,
        height=400,
    )
    
    return fig_farm, fig_amount

def create_district_stats_bar_chart(df_province, animal_col):
    df_sorted = df_province.sort_values(by=animal_col, ascending=True)
    fig = go.Figure(
        go.Bar(
            x=df_sorted[animal_col],
            y=df_sorted["Province"],
            orientation="h",
            marker=dict(
                color=df_sorted[animal_col],
                colorscale=[
                    [0, "#fdd0a2"],   # Your light orange
                    [1, "#fb8d3d"]    # Darker orange
                ],
                showscale=False,  # Hide colorbar
                line=dict(
                    color="#fdae6b",
                    width=1
                )
            ),
            text=df_sorted[animal_col].apply(lambda v: f"{v:,.0f}"),
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>" + animal_col + ": %{x:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        # title=dict(text=f"<b>{animal_col} by Province</b>", font=dict(family="ubuntu", size=24, color="#1b263b"), x=0.5, xanchor="center"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=10, r=40, t=30, b=30),
        font=dict(family="ubuntu"),
        xaxis=dict(
            title=animal_col, 
            showgrid=True, 
            gridcolor="#eee",
            tickfont=dict(size=16, family="ubuntu", weight="bold"),
            tickmode='array',
            linewidth=1,
            linecolor='lightgray'
        ),
        yaxis=dict(
            title="", 
            automargin=True,
            tickfont=dict(size=16, family="ubuntu", weight="bold")
        ),
    )
    return fig



# Oranges (ColorBrewer) sequential palette — used to keep every layer in
# the same family, from lightest (background) to the full gradient (data).
_ORANGES_LIGHTEST = "#fff5eb"   # national boundary fill
_ORANGES_LIGHT     = "#fee6ce"  # "no data" province fill
_ORANGES_LIGHT_LINE = "#fdae6b" # "no data" province outline
_ORANGES_BG_LINE    = "#fdd0a2" # national boundary outline
 
 
# def _detect_name_key(properties: dict, candidates=("NAME_1", "shapeName", "name", "Province", "province",
#                                                      "NAME", "ADM0_NAME", "COUNTRY", "admin")):
#     """Pick the most likely property key holding a place name."""
#     return next((k for k in candidates if k in properties), None)
 
 
# def _add_country_background(fig: go.Figure, country_geojson_path: str) -> None:
#     """Bottom layer: national Laos boundary, light fill, drawn first so
#     every other trace renders on top of it."""
#     try:
#         with open(country_geojson_path, "r", encoding="utf-8") as f:
#             country_geo = json.load(f)
#     except FileNotFoundError:
#         return  # optional layer — skip quietly if the file isn't there
 
#     if country_geo.get("type") == "Feature":
#         features = [country_geo]
#         country_geo = {"type": "FeatureCollection", "features": features}
#     else:
#         features = country_geo.get("features", [])
 
#     if not features:
#         return
 
#     props = features[0].get("properties") or {}
#     name_key = _detect_name_key(props)
 
#     if name_key:
#         fig.add_trace(go.Choropleth(
#             geojson=country_geo,
#             locations=[props[name_key]],
#             z=[1],
#             featureidkey=f"properties.{name_key}",
#             colorscale=[[0, _ORANGES_LIGHTEST], [1, _ORANGES_LIGHTEST]],
#             showscale=False,
#             marker_line_color=_ORANGES_BG_LINE,
#             marker_line_width=1.5,
#             hoverinfo="skip",
#         ))
#     else:
#         # No usable properties field — fall back to the feature's top-level
#         # "id" (Plotly's default match target when featureidkey is omitted).
#         feat_id = features[0].get("id", "laos")
#         fig.add_trace(go.Choropleth(
#             geojson=country_geo,
#             locations=[feat_id],
#             z=[1],
#             colorscale=[[0, _ORANGES_LIGHTEST], [1, _ORANGES_LIGHTEST]],
#             showscale=False,
#             marker_line_color=_ORANGES_BG_LINE,
#             marker_line_width=1.5,
#             hoverinfo="skip",
#         ))
 
 
# def _add_remaining_provinces_background(fig: go.Figure, geojson: dict, name_key: str, present_names) -> None:
#     """Middle layer: every province boundary, light fill — guarantees the
#     full set of provinces is always visible even where data is missing."""
#     present = set(present_names)
#     all_names = [feat["properties"].get(name_key) for feat in geojson["features"]]
#     remaining = [n for n in all_names if n is not None and n not in present]
 
#     if not remaining:
#         return
 
#     fig.add_trace(go.Choropleth(
#         geojson=geojson,
#         locations=remaining,
#         z=[1] * len(remaining),
#         featureidkey=f"properties.{name_key}",
#         colorscale=[[0, _ORANGES_LIGHT], [1, _ORANGES_LIGHT]],
#         showscale=False,
#         marker_line_color=_ORANGES_LIGHT_LINE,
#         marker_line_width=1,
#         hovertemplate="<b>%{location}</b><br>No data<extra></extra>",
#     ))
 
 
# def create_livestock_province_map(
#     df,
#     animal_col: str,
#     province_col: str = "Province",
#     geojson_path: str = "assets/geo/laos_provinces.geojson",
#     country_geojson_path: str = "assets/geo/laos.geojson",
# ):
#     """
#     Build a province-boundary choropleth of Laos coloured by livestock count,
#     layered over a national outline and a "no data" province background so
#     the full country shape is always visible.
 
#     Parameters
#     ----------
#     df : pd.DataFrame
#         One row per province, with a `province_col` column and at least
#         one numeric column to visualise (e.g. 'Buffalo', or a precomputed
#         'Total' column).
#     animal_col : str
#         Name of the column in `df` to use as the colour value.
#     province_col : str
#         Name of the province column in `df`. Default "Province".
#     geojson_path : str
#         Path to a GeoJSON file with one feature per province.
#     country_geojson_path : str
#         Path to a GeoJSON file with the national Laos boundary. Optional —
#         if missing, that background layer is simply skipped.
 
#     Returns
#     -------
#     plotly.graph_objects.Figure
#     """
#     try:
#         with open(geojson_path, "r", encoding="utf-8") as f:
#             geojson = json.load(f)
#     except FileNotFoundError:
#         fig = go.Figure()
#         fig.add_annotation(
#             text=f"Province boundary file not found.<br>Expected at: {geojson_path}",
#             xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
#             font=dict(size=14, color="#888"),
#         )
#         fig.update_layout(
#             plot_bgcolor="white", paper_bgcolor="white",
#             xaxis=dict(visible=False), yaxis=dict(visible=False),
#             margin=dict(l=10, r=10, t=10, b=10),
#         )
#         return fig
 
#     sample_props = geojson["features"][0]["properties"]
#     name_key = _detect_name_key(sample_props) or list(sample_props.keys())[0]
 
#     fig = go.Figure()
 
#     # Layer 1 (bottom / "z -100"): national outline ------------------------
#     _add_country_background(fig, country_geojson_path)
 
#     # Layer 2 (middle): full province set, light fill -----------------------
#     _add_remaining_provinces_background(fig, geojson, name_key, df[province_col])
 
#     # Layer 3 (top): actual data choropleth ----------------------------------
#     fig.add_trace(go.Choropleth(
#         geojson=geojson,
#         locations=df[province_col],
#         z=df[animal_col],
#         featureidkey=f"properties.{name_key}",
#         colorscale="Oranges",
#         marker_line_color="white",
#         marker_line_width=1,
#         colorbar=dict(title=animal_col, thickness=14, len=0.75),
#         hovertemplate="<b>%{location}</b><br>" + animal_col + ": %{z:,.0f}<extra></extra>",
#     ))
 
#     fig.update_geos(
#         fitbounds="locations",
#         visible=False,
#         bgcolor="rgba(0,0,0,0)",
#         # projection_scale=1.5,
#     )
#     fig.update_layout(
#         paper_bgcolor="white",
#         plot_bgcolor="white",
#         margin=dict(l=0, r=0, t=0, b=0),
#         geo=dict(bgcolor="rgba(0,0,0,0)"),
#         showlegend=False,
#         height=600,
#         # mapbox=dict(
#         #     zoom=6.5
#         # ),
#     )
#     return fig


def _detect_name_key(properties: dict, candidates=("NAME_1", "shapeName", "name", "Province", "province",
                                                     "NAME", "ADM0_NAME", "COUNTRY", "admin")):
    """Pick the most likely property key holding a place name."""
    return next((k for k in candidates if k in properties), None)


def _add_country_background(fmap: folium.Map, country_geojson_path: str) -> None:
    """Bottom layer: national Laos boundary, light fill, drawn first so
    every other layer renders on top of it."""
    try:
        with open(country_geojson_path, "r", encoding="utf-8") as f:
            country_geo = json.load(f)
    except FileNotFoundError:
        return  # optional layer — skip quietly if the file isn't there

    if country_geo.get("type") == "Feature":
        country_geo = {"type": "FeatureCollection", "features": [country_geo]}

    if not country_geo.get("features"):
        return

    folium.GeoJson(
        country_geo,
        name="Country outline",
        style_function=lambda feature: {
            "fillColor": _ORANGES_LIGHTEST,
            "color": _ORANGES_BG_LINE,
            "weight": 1.5,
            "fillOpacity": 1,
        },
        highlight_function=lambda feature: {"fillOpacity": 1},
        control=False,
    ).add_to(fmap)


def _add_remaining_provinces_background(fmap: folium.Map, geojson: dict, name_key: str, present_names) -> None:
    """Middle layer: every province boundary, light fill — guarantees the
    full set of provinces is always visible even where data is missing."""
    present = set(present_names)
    remaining_features = [
        feat for feat in geojson["features"]
        if feat["properties"].get(name_key) is not None
        and feat["properties"].get(name_key) not in present
    ]

    if not remaining_features:
        return

    remaining_geo = {"type": "FeatureCollection", "features": remaining_features}

    folium.GeoJson(
        remaining_geo,
        name="No data provinces",
        style_function=lambda feature: {
            "fillColor": _ORANGES_LIGHT,
            "color": _ORANGES_LIGHT_LINE,
            "weight": 1,
            "fillOpacity": 1,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[name_key],
            aliases=[""],
            labels=True,
            sticky=True,
            style="background-color: white; color: #333; font-size: 12px; padding: 4px;",
        ),
        highlight_function=lambda feature: {"fillOpacity": 0.8},
        control=False,
    ).add_to(fmap)

def create_livestock_province_map(
    df,
    animal_col: str,
    province_col: str = "Province",
    geojson_path: str = "assets/geo/laos_provinces.geojson",
    country_geojson_path: str = "assets/geo/laos.geojson",
):
    """
    Build a province-boundary choropleth of Laos coloured by livestock count,
    layered over a national outline and a "no data" province background so
    the full country shape is always visible.

    Parameters
    ----------
    df : pd.DataFrame
        One row per province, with a `province_col` column and at least
        one numeric column to visualise (e.g. 'Buffalo', or a precomputed
        'Total' column).
    animal_col : str
        Name of the column in `df` to use as the colour value.
    province_col : str
        Name of the province column in `df`. Default "Province".
    geojson_path : str
        Path to a GeoJSON file with one feature per province.
    country_geojson_path : str
        Path to a GeoJSON file with the national Laos boundary. Optional —
        if missing, that background layer is simply skipped.

    Returns
    -------
    folium.Map
    """
    try:
        with open(geojson_path, "r", encoding="utf-8") as f:
            geojson = json.load(f)
    except FileNotFoundError:
        fmap = folium.Map(location=[18.0, 105.0], zoom_start=16, tiles=None)
        folium.Marker(
            [18.0, 105.0],
            icon=folium.DivIcon(html=f"""
                <div style="font-size:14px; color:#888; text-align:center; white-space:nowrap;">
                    Province boundary file not found.<br>Expected at: {geojson_path}
                </div>"""),
        ).add_to(fmap)
        return fmap

    sample_props = geojson["features"][0]["properties"]
    name_key = _detect_name_key(sample_props) or list(sample_props.keys())[0]

    fmap = folium.Map(
        location=[18.0, 105.0],
        zoom_start=20,
        tiles=None,
        # control_scale=True,
    )

    # Layer 1 (bottom): national outline -------------------------------------
    _add_country_background(fmap, country_geojson_path)

    # Layer 2 (middle): full province set, light fill ------------------------
    _add_remaining_provinces_background(fmap, geojson, name_key, df[province_col])

    # Layer 3 (top): actual data choropleth -----------------------------------
    data_lookup = dict(zip(df[province_col], df[animal_col]))
    data_features = [
        feat for feat in geojson["features"]
        if feat["properties"].get(name_key) in data_lookup
    ]
    data_geo = {"type": "FeatureCollection", "features": data_features}

    # Stash the value on each feature so the tooltip layer can read it.
    for feat in data_geo["features"]:
        feat["properties"]["_value"] = data_lookup.get(feat["properties"].get(name_key))

    folium.Choropleth(
        geo_data=data_geo,
        data=df,
        columns=[province_col, animal_col],
        key_on=f"feature.properties.{name_key}",
        fill_color="Oranges",
        fill_opacity=0.9,
        line_color="white",
        line_weight=1,
        legend_name=animal_col,
        name="Livestock data",
        highlight=True,
    ).add_to(fmap)

    # Transparent overlay purely for rich hover tooltips (name + value),
    # since folium.Choropleth itself doesn't support custom hovertemplates.
    folium.GeoJson(
        data_geo,
        name="Livestock tooltips",
        style_function=lambda feature: {"fillOpacity": 0, "color": "transparent", "weight": 0},
        tooltip=folium.GeoJsonTooltip(
            fields=[name_key, "_value"],
            aliases=["Province:", f"{animal_col}:"],
            labels=True,
            sticky=True,
            localize=True,
            style="background-color: white; color: #333; font-size: 12px; padding: 4px;",
        ),
        control=False,
    ).add_to(fmap)

    with open("data/laos.geojson", "r") as f:
        laos_geojson = json.load(f)

    coordinates = laos_geojson['geometry']['coordinates'][0]
    fmap.fit_bounds([
        [min(y for x, y in coordinates), min(x for x, y in coordinates)],
        [max(y for x, y in coordinates), max(x for x, y in coordinates)]
    ])

    # folium.LayerControl(collapsed=True).add_to(fmap)

    return fmap