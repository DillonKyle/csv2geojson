# CSV parser imports
import pandas as pd

# Coordinate transformation imports
import pyproj
from pyproj import Transformer

# GUI imports
import plotly.express as px
import PySimpleGUI as sg

# DXF parser imports
import ezdxf
from ezdxf.addons import geo
from ezdxf.math import Vec3

# system imports
import sys
import json

# Take a CSV of polygon points, convert them into WGS84 coordinates and export as geojson


def csv_to_geojson(csv_file, epsg):
    # Setup variables
    file_name = csv_file.split(".csv")[0]
    df = pd.read_csv(csv_file)
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


# Take a DXF of polygons, convert them into WGS84 coordinates and export as geojson


def dxf_to_geojson(dxf_file, epsg):
    file_name = dxf_file.split(".dxf")[0]
    
    print(file_name)
    geojson = {"type": "FeatureCollection", "features": []}

    # Verify DXF validity
    try:
        doc = ezdxf.readfile(dxf_file)
    except IOError:
        print(f"Not a DXF file or a generic I/O error.")
        sys.exit(1)
    except ezdxf.DXFStructureError:
        print(f"Invalid or corrupted DXF file.")
        sys.exit(2)

    # Enter DXF Modelspace
    msp = doc.modelspace()

    # Iterate polylines in DXF
    for polyline in msp.query("POLYLINE"):
        geo_proxy = geo.proxy(polyline)

        # Grab the polyline IDs
        id = str(polyline.dxf.layer).split("%%")[1]

        # Convert from input CRS to WGS84
        ct = Transformer.from_crs(epsg, 4326, always_xy=True)

        # Apply the coordinate transformation
        geo_proxy.apply(lambda v: Vec3(ct.transform(v.x, v.y)))

        # Add polygon geojson to FeatureCollection
        geojson["features"].append(
            {
                "type": "Feature",
                "properties": {"id": id},
                "geometry": geo_proxy.__geo_interface__,
            }
        )

    # Write full geojson to file
    with open(file_name + ".json", "w") as f:
        json.dump(geojson, f, indent=2)

    return geojson


# Display polygons over a satellite map to verify location


def show_map(geojson):
    # Zoom in point
    point = geojson["features"][0]["geometry"]["coordinates"][0][0]

    # Map server URL
    s = "GET FROM ENV"

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


# GUI Code ***********************************************************************

sg.theme("DarkAmber")

file = [[sg.In(size=(30, 1), enable_events=True, key="FILE"), sg.FileBrowse()]]
status = [
    (""),
    ("Please select a file before converting."),
    ("Please input EPSG Code before converting."),
    ("GeoJSON file exported"),
    ("Map is displaying in browser window"),
    ("Incorrect File Format."),
]
epsg = [[sg.In(size=(25, 1), enable_events=True, key="_EPSG_")]]

layout = [
    [
        sg.Text(
            "Points CSV or DXF File", size=(30, 1), font="Lucida", justification="left"
        )
    ],
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
window = sg.Window("Convert to GeoJSON", layout, resizable=True)

while True:
    event, values = window.read()

    if event in (sg.WIN_CLOSED, "Exit"):
        break
    if event == "Cancel":
        raise SystemExit
    if event == "Reset":
        window["FILE"].Update(value="")
        window["_EPSG_"].Update(value="")
        window["INDICATOR"].update(value=status[0])

    if event == "Ok" and values["FILE"] == "":
        window["INDICATOR"].update(value=status[1])
    elif event == "Ok" and values["FILE"] and values["_EPSG_"] == "":
        window["INDICATOR"].update(value=status[2])
    elif (
        event == "Ok"
        and values["FILE"]
        and values["_EPSG_"]
        and values["CB_MAP"] == False
    ):
        window["INDICATOR"].update(value=status[0])
        try:
            if values["FILE"].endswith(".csv"):
                csv_to_geojson(values["FILE"], values["_EPSG_"])
                window["INDICATOR"].update(value=status[3])
            elif values["FILE"].endswith(".dxf"):
                dxf_to_geojson(values["FILE"], values["_EPSG_"])
                window["INDICATOR"].update(value=status[3])
            else:
                window["INDICATOR"].update(value=status[5])
        except pyproj.exceptions.CRSError:
            error = "Invalid/Unsupported EPSG Code"
            window["INDICATOR"].update(value=error)
    elif (
        event == "Ok"
        and values["FILE"]
        and values["_EPSG_"]
        and values["CB_MAP"] == True
    ):
        window["INDICATOR"].update(value=status[0])
        try:
            if values["FILE"].endswith(".csv"):
                geojson = csv_to_geojson(values["FILE"], values["_EPSG_"])
                show_map(geojson)
                window["INDICATOR"].update(value=status[4])
            elif values["FILE"].endswith(".dxf"):
                geojson = dxf_to_geojson(values["FILE"], values["_EPSG_"])
                show_map(geojson)
                window["INDICATOR"].update(value=status[4])
            else:
                window["INDICATOR"].update(value=status[5])
        except pyproj.exceptions.CRSError:
            error = "Invalid/Unsupported EPSG Code"
            window["INDICATOR"].update(value=error)
window.close()
