"""
Dash application for interactive exploration of Spotify track‑level audio features.

Launch with:
    python app.py

run these commands in the terminal:
    pip install -r requirements.txt

Then open http://127.0.0.1:8050/ in a browser.

The program will automatically shut down when you close the browser tab/window.
You can also end the program manually by pressing ctrl+c in the terminal.
"""
from __future__ import annotations
import pathlib
import threading
import time
import sys
import os

import dash
from dash import Dash, html, dcc, Input, Output, ClientsideFunction
import pandas as pd
import plotly.express as px

# -----------------------------------------------------------------------------
# Load data
# -----------------------------------------------------------------------------
THIS_DIR = pathlib.Path(__file__).resolve().parent
DATA_PATH = THIS_DIR / "data" / "dataset.csv"

df = pd.read_csv(DATA_PATH)

NUMERIC_COLS = [
    "danceability",
    "energy",
    "loudness",
    "speechiness",
    "acousticness",
    "instrumentalness",
    "liveness",
    "valence",
    "tempo",
    "duration_ms",
    "popularity",
]

metric_labels = {
    "danceability": "Danceability",
    "energy": "Energy",
    "loudness": "Loudness (dB)",
    "speechiness": "Speechiness",
    "acousticness": "Acousticness",
    "instrumentalness": "Instrumentalness",
    "liveness": "Liveness",
    "valence": "Valence",
    "tempo": "Tempo (BPM)",
    "duration_ms": "Duration (ms)",
    "popularity": "Popularity (0‑100)",
}

# -----------------------------------------------------------------------------
# Build Dash app
# -----------------------------------------------------------------------------
app: Dash = dash.Dash(__name__)
app.title = "Spotify Audio Explorer"

# Track active connections
active_connections = set()
connection_last_ping = {}  # Store the last ping time for each connection
connection_lock = threading.Lock()

# Function to monitor connections and shut down server when all are closed
def monitor_connections():
    # Give time for initial connection
    startup_time = time.time()
    startup_grace_period = 60  # seconds
    connection_timeout = 300  # seconds - how long to wait before considering a connection stale

    had_connections = False

    while True:
        time.sleep(2)  # Check every 2 seconds

        # Skip checking during startup grace period
        if time.time() - startup_time < startup_grace_period:
            continue

        current_time = time.time()

        with connection_lock:
            # Check for stale connections
            stale_connections = []
            for conn_id in active_connections:
                last_ping = connection_last_ping.get(conn_id, 0)
                if last_ping > 0 and current_time - last_ping > connection_timeout:
                    stale_connections.append(conn_id)

            # Remove stale connections
            for conn_id in stale_connections:
                active_connections.remove(conn_id)
                connection_last_ping.pop(conn_id, None)
                print(f"Removed stale connection: {conn_id}. Active connections: {len(active_connections)}")

            # Only shut down if we had connections before and now have none
            if active_connections:
                had_connections = True
            elif had_connections:
                print("All connections closed. Shutting down server...")
                os._exit(0)  # Force exit the process

# Start the monitoring thread
monitor_thread = threading.Thread(target=monitor_connections, daemon=True)
monitor_thread.start()

# Add client-side callback to detect page load/unload
app.clientside_callback(
    ClientsideFunction(
        namespace='clientside',
        function_name='updateConnectionStatus'
    ),
    Output('connection-status', 'data'),
    Input('connection-status', 'id')
)

# Create the client-side JavaScript function
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <script>
            window.dash_clientside = Object.assign({}, window.dash_clientside, {
                clientside: {
                    updateConnectionStatus: function(id) {
                        // Generate a unique ID for this connection
                        if (!window.connectionId) {
                            window.connectionId = Date.now().toString() + Math.random().toString(36).substr(2, 9);

                            // Set up ping interval to keep connection alive
                            window.pingInterval = setInterval(function() {
                                fetch('/_dash-update-component', {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                    },
                                    body: JSON.stringify({
                                        output: {
                                            id: 'connection-status',
                                            property: 'data'
                                        },
                                        inputs: [{"id": "connection-status", "property": "id", "value": "connection-status"}],
                                        changedPropIds: ['connection-status.id'],
                                        value: {'status': 'ping', 'id': window.connectionId}
                                    })
                                }).catch(function(error) {
                                    console.log('Ping error:', error);
                                });
                            }, 10000); // Ping every 10 seconds
                        }

                        // Set up the unload handler - try multiple approaches
                        window.addEventListener('beforeunload', function(e) {
                            // Clear the ping interval
                            if (window.pingInterval) {
                                clearInterval(window.pingInterval);
                            }

                            // Method 1: Use sendBeacon (most reliable for page unload)
                            const payload = JSON.stringify({
                                output: {
                                    id: 'connection-status',
                                    property: 'data'
                                },
                                inputs: [{"id": "connection-status", "property": "id", "value": "connection-status"}],
                                changedPropIds: ['connection-status.id'],
                                value: {'status': 'disconnected', 'id': window.connectionId}
                            });

                            navigator.sendBeacon('/_dash-update-component', payload);

                            // Method 2: Try a synchronous XHR as fallback
                            try {
                                const xhr = new XMLHttpRequest();
                                xhr.open('POST', '/_dash-update-component', false); // false makes it synchronous
                                xhr.setRequestHeader('Content-Type', 'application/json');
                                xhr.send(payload);
                            } catch (e) {
                                console.log('Sync XHR fallback failed:', e);
                            }
                        });

                        // Also handle page visibility changes as another fallback
                        document.addEventListener('visibilitychange', function() {
                            if (document.visibilityState === 'hidden') {
                                fetch('/_dash-update-component', {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                    },
                                    body: JSON.stringify({
                                        output: {
                                            id: 'connection-status',
                                            property: 'data'
                                        },
                                        inputs: [{"id": "connection-status", "property": "id", "value": "connection-status"}],
                                        changedPropIds: ['connection-status.id'],
                                        value: {'status': 'hidden', 'id': window.connectionId}
                                    })
                                }).catch(function(error) {
                                    console.log('Visibility change error:', error);
                                });
                            }
                        });

                        // Return connected status
                        return {'status': 'connected', 'id': window.connectionId};
                    }
                }
            });
        </script>
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

app.layout = html.Div(
    [
        # Hidden div to store connection status
        dcc.Store(id='connection-status', storage_type='memory'),

        html.H1("Spotify Audio Feature Explorer", style={"textAlign": "center"}),
        dcc.Markdown(
            """
            Filter tracks by genre, popularity and explicitness, then explore relationships
            between audio features. Hover on points or bars for exact values.
            """,
            style={"maxWidth": "900px", "margin": "0 auto"},
        ),
        html.Br(),
        html.Div(
            [
                # ─── Controls column ───────────────────────────────────────────
                html.Div(
                    [
                        html.H4("Controls"),
                        html.Label("Genre(s)"),
                        dcc.Dropdown(
                            id="genreDropdown",
                            options=[{"label": g.capitalize(), "value": g} for g in sorted(df.track_genre.unique())],
                            value=["pop", "rock"] if "pop" in df.track_genre.values else sorted(df.track_genre.unique())[:3],
                            multi=True,
                        ),
                        html.Br(),
                        html.Label("Popularity range"),
                        dcc.RangeSlider(
                            id="popSlider",
                            min=0,
                            max=100,
                            step=1,
                            value=[20, 80],
                            marks={0: "0", 50: "50", 100: "100"},
                        ),
                        html.Br(),
                        html.Label("Explicit?"),
                        dcc.RadioItems(
                            id="explicitRadio",
                            options=[
                                {"label": "All", "value": "all"},
                                {"label": "Non‑explicit", "value": "non"},
                                {"label": "Explicit only", "value": "explicit"},
                            ],
                            value="all",
                        ),
                        html.Br(),
                        html.Label("X‑axis metric"),
                        dcc.Dropdown(
                            id="xMetric",
                            options=[{"label": metric_labels[c], "value": c} for c in NUMERIC_COLS],
                            value="danceability",
                            clearable=False,
                        ),
                        html.Br(),
                        html.Label("Y‑axis metric"),
                        dcc.Dropdown(
                            id="yMetric",
                            options=[{"label": metric_labels[c], "value": c} for c in NUMERIC_COLS],
                            value="energy",
                            clearable=False,
                        ),
                    ],
                    style={"width": "24%", "display": "inline-block", "verticalAlign": "top", "padding": "0 16px"},
                ),

                # ─── Graphs column ────────────────────────────────────────────
                html.Div(
                    [
                        dcc.Graph(id="scatterPlot"),
                        dcc.Graph(id="boxPlot"),
                        dcc.Graph(id="barPlot"),
                    ],
                    style={"width": "74%", "display": "inline-block"},
                ),
            ]
        ),
    ],
    style={"fontFamily": "Arial, sans-serif", "margin": "0 32px"},
)

# -----------------------------------------------------------------------------
# Callbacks
# -----------------------------------------------------------------------------

@app.callback(
    Output('connection-status', 'data', allow_duplicate=True),
    Input('connection-status', 'data'),
    prevent_initial_call=True
)
def handle_connection_status(data):
    """Track connection status and update the active_connections set."""
    if not data:
        print("Warning: Received empty data in handle_connection_status")
        return dash.no_update

    connection_id = data.get('id')
    status = data.get('status')

    print(f"Connection status update received: {status} - {connection_id}")

    current_time = time.time()

    with connection_lock:
        if status == 'connected' and connection_id:
            active_connections.add(connection_id)
            connection_last_ping[connection_id] = current_time
            print(f"New connection: {connection_id}. Active connections: {len(active_connections)}")
        elif status == 'disconnected' and connection_id in active_connections:
            active_connections.remove(connection_id)
            connection_last_ping.pop(connection_id, None)
            print(f"Connection closed: {connection_id}. Active connections: {len(active_connections)}")
        elif status == 'ping' and connection_id:
            # Update the last ping time for this connection
            connection_last_ping[connection_id] = current_time
            # This is just a heartbeat to keep the connection alive
            if connection_id not in active_connections:
                active_connections.add(connection_id)
                print(f"Reconnected via ping: {connection_id}. Active connections: {len(active_connections)}")
            # Otherwise, connection is already tracked, no need to log
        elif status == 'hidden' and connection_id:
            # Page is hidden but not necessarily closed
            # We'll keep the connection active but log it
            connection_last_ping[connection_id] = current_time
            if connection_id not in active_connections:
                active_connections.add(connection_id)
            print(f"Connection hidden: {connection_id}. Active connections: {len(active_connections)}")
        else:
            print(f"Unhandled connection status: {status} for ID: {connection_id}")

    return dash.no_update

@app.callback(
    Output("scatterPlot", "figure"),
    Output("boxPlot", "figure"),
    Output("barPlot", "figure"),
    Input("genreDropdown", "value"),
    Input("popSlider", "value"),
    Input("explicitRadio", "value"),
    Input("xMetric", "value"),
    Input("yMetric", "value"),
)
def update_figures(genres: list[str], pop_range: list[int], explicit_filter: str, x_col: str, y_col: str):
    """Return three Plotly figures based on current filters."""
    # Filter dataframe -----------------------------------------------------
    dff = df[df.track_genre.isin(genres) & (df.popularity.between(pop_range[0], pop_range[1]))]
    if explicit_filter == "non":
        dff = dff[~dff["explicit"]]
    elif explicit_filter == "explicit":
        dff = dff[dff["explicit"]]

    # Scatter plot ---------------------------------------------------------
    scatter = px.scatter(
        dff,
        x=x_col,
        y=y_col,
        color="track_genre",
        hover_data=["track_name", "artists", "popularity"],
        labels={x_col: metric_labels[x_col], y_col: metric_labels[y_col], "track_genre": "Genre"},
        title=f"{metric_labels[x_col]} vs {metric_labels[y_col]} ({len(dff)} tracks)",
    )

    # Box plot -------------------------------------------------------------
    box = px.box(
        dff,
        x="track_genre",
        y=y_col,
        points="all",
        labels={"track_genre": "Genre", y_col: metric_labels[y_col]},
        title=f"Distribution of {metric_labels[y_col]} by Genre",
    )

    # Bar chart ------------------------------------------------------------
    # Drop duplicates to ensure each song appears only once
    unique_tracks = dff.drop_duplicates(subset=["track_name", "artists"])
    bar_df = unique_tracks.nlargest(10, "popularity").sort_values("popularity", ascending=True)
    bar = px.bar(
        bar_df,
        x="popularity",
        y="track_name",
        orientation="h",
        hover_data=["artists", "track_genre"],
        labels={"popularity": "Popularity", "track_name": "Track"},
        title="Top 10 Most Popular Tracks (filtered)",
    )

    return scatter, box, bar


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)
