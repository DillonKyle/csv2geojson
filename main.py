import pandas as pd
import pyproj
from pyproj import Transformer
import json
import plotly.express as px
import PySimpleGUI as sg
import os
import sys


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


# Take a CSV of polygon points, convert them into WGS84 coordinates and export as geojson


def create_geojson(file, epsg):
    # Setup variables
    file_name = file.split(".")[0]
    df = pd.read_csv(file)
    df.columns = ["X", "Y", "Z", "R", "G", "B"]
    transformer = Transformer.from_crs(epsg, 4326)
    cad_dict = {}
    trans_cad_dict = {}
    geojson = {"type": "FeatureCollection", "features": []}

    # parse CSV and make Dict object of CAD Polygons
    for i in range(0, len(df) - 1):
        if df.iloc[i].str.contains("# Object:").any():
            loop_id = df["X"].iloc[i].split("/")[-1]
            cad_dict[loop_id] = []
            geojson["features"].append(
                {
                    "type": "Feature",
                    "properties": {"id": loop_id},
                    "geometry": {"type": "Polygon", "coordinates": [[]]},
                }
            )
        else:
            cad_dict[loop_id].append([float(df["X"].iloc[i]), float(df["Y"].iloc[i])])

    # parse CAD Dict and convert coordinates to Lat Long
    for key, value in cad_dict.items():
        trans_cad_dict[key] = []
        for coord in value:
            lat, lng = transformer.transform(coord[0], coord[1])
            trans_cad_dict[key].append([lng, lat])

    # Close polygon by duplicating first coordinate at the end of list
    for key, value in trans_cad_dict.items():
        trans_cad_dict[key].append(trans_cad_dict[key][0])

    # Reverse list to follow right hand rule
    for key, value in trans_cad_dict.items():
        trans_cad_dict[key] = trans_cad_dict[key][::-1]

    # Add coordinates to geojson object
    for feature in geojson["features"]:
        key_id = feature["properties"]["id"]
        feature["geometry"]["coordinates"][0] = trans_cad_dict[key_id]

    # Write the geojson to a file
    with open(file_name + ".json", "w") as f:
        json.dump(geojson, f, indent=2)

    return geojson


# Display polygons over a satellite map to verify location


def show_map(geojson):
    # Zoom in point
    point = geojson["features"][0]["geometry"]["coordinates"][0][0]

    # Map server URL
    s = "https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v9/tiles/256/{z}/{x}/{y}@2x?access_token=pk.eyJ1Ijoia2VzcHJ5ZHJvbmVzIiwiYSI6ImZEVXNDVHMifQ.yOzxCocHxL7uQqVw3ghuPQ"

    # Create Map Plot
    fig = px.scatter_mapbox(lat=[point[1]], lon=[point[0]]).update_layout(
        # Set up map with satellite imagery and polygon layers
        mapbox={
            "style": "white-bg",
            "zoom": 16,
            "layers": [
                {
                    "below": "traces",
                    "sourcetype": "raster",
                    "sourceattribution": "Mapbox",
                    "source": [s],
                },
                {
                    "source": geojson,
                    "below": "traces",
                    "type": "line",
                    "color": "cyan",
                    "line": {"width": 2},
                },
            ],
        },
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
    )

    # Display map, opens browser tab
    fig.show()


sg.theme("DarkAmber")

epsg_file = resource_path("epsg-sp-nad83.csv")
epsg_codes = pd.read_csv(epsg_file)

file = [[sg.In(size=(30, 1), enable_events=True, key="CSV_FILE"), sg.FileBrowse()]]
status = [
    (""),
    ("Please select a file before converting."),
    ("Please input EPSG Code before converting."),
    ("GeoJSON file exported"),
    ("Map is displaying in browser window"),
]
epsg = [[sg.In(size=(25, 1), enable_events=True, key="_EPSG_")]]

layout = [
    [sg.Text("Points CSV File", size=(30, 1), font="Lucida", justification="left")],
    [
        sg.Text(
            "*files will be exported in the same folder as the input file.",
            size=(50, 1),
            font=("Lucida", 8),
            justification="left",
        )
    ],
    [sg.Column(file, element_justification="c")],
    [
        sg.Text(
            "EPSG Code For Input File",
            size=(30, 1),
            font="Lucida",
            justification="left",
        )
    ],
    [sg.Column(epsg, element_justification="c")],
    [sg.Checkbox("Show on map after conversion?", key="CB_MAP")],
    [
        sg.Text(
            text=status[0],
            size=(40, 1),
            text_color="white",
            key="INDICATOR",
            justification="c",
        )
    ],
    [sg.Button("Ok"), sg.Button("Cancel"), sg.Button("Reset")],
]
window = sg.Window("CSV to GeoJSON", layout, resizable=True)

while True:
    event, values = window.read()

    if event in (sg.WIN_CLOSED, "Exit"):
        break
    if event == "Cancel":
        raise SystemExit
    if event == "Reset":
        window["CSV_FILE"].Update(value="")
        window["_EPSG_"].Update(value="")

    if event == "Ok" and values["CSV_FILE"] == "":
        window["INDICATOR"].update(value=status[1])
    elif event == "Ok" and values["CSV_FILE"] and values["_EPSG_"] == "":
        window["INDICATOR"].update(value=status[2])
    elif (
        event == "Ok"
        and values["CSV_FILE"]
        and values["_EPSG_"]
        and values["CB_MAP"] == False
    ):
        window["INDICATOR"].update(value=status[0])
        try:
            create_geojson(values["CSV_FILE"], values["_EPSG_"])
            window["INDICATOR"].update(value=status[3])
        except pyproj.exceptions.CRSError:
            error = "Invalid/Unsupported EPSG Code"
            window["INDICATOR"].update(value=error)
    elif (
        event == "Ok"
        and values["CSV_FILE"]
        and values["_EPSG_"]
        and values["CB_MAP"] == True
    ):
        window["INDICATOR"].update(value=status[0])
        geojson = create_geojson(values["CSV_FILE"], values["_EPSG_"])
        show_map(geojson)
        window["INDICATOR"].update(value=status[4])
window.close()
