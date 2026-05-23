import contextlib
import json
from datetime import datetime
from math import acos, cos, radians

import pandas
import pandas._libs.missing
import requests
from requests.exceptions import RequestException


# Used for Meteostat implementation
def meteostat_make_list(stations_dict: dict) -> list:
    stations_list = []
    for index in stations_dict:
        keys = list(stations_dict[index].keys())
        for key in keys:
            if isinstance(
                stations_dict[index][key], pandas._libs.missing.NAType
            ):
                stations_dict[index][key] = "N/A"
        t_dict = {
            "name": stations_dict[index]["name"],
            "country": stations_dict[index]["country"],
            "state": stations_dict[index]["region"],
            "id": index,
            "wmo": stations_dict[index]["wmo"],
            "icao": stations_dict[index]["icao"],
            "latitude": stations_dict[index]["latitude"],
            "longitude": stations_dict[index]["longitude"],
            "elevation": stations_dict[index]["elevation"],
            "timezone": stations_dict[index]["timezone"],
        }
        if "distance" in stations_dict[index]:
            t_dict["distance"] = stations_dict[index]["distance"]
        stations_list.append(t_dict)
    return stations_list


# Used for ACIS implementation


def calculate_spherical_distance(lat1, lon1, lat2, lon2, r=6371):
    coordinates = lat1, lon1, lat2, lon2
    phi1, lambda1, phi2, lambda2 = [radians(c) for c in coordinates]
    d = r * acos(
        cos(phi2 - phi1) - cos(phi1) * cos(phi2) * (1 - cos(lambda2 - lambda1))
    )
    return d * 1000.0


def neighboring(code: str):
    neighboring_regions = {
        # Canada
        "AB": ["ID", "MT", "BC", "SK", "NT"],
        "MB": ["ME", "NS", "PE", "QC"],
        "NL": ["QC"],
        "NT": ["YT", "BC", "AB", "SK", "MB", "NU"],
        "ON": ["MB", "QC", "MN", "WI", "MI", "NY"],
        "QC": ["VT", "NH", "ME", "NY", "NB", "NL", "ON"],
        "YT": ["AK", "NT", "BC"],
        "NB": ["NS", "PE", "QC", "ME"],
        "BC": ["WA", "ID", "MT", "AB", "NT", "YT"],
        "NS": ["PE", "NL", "NB"],
        "NU": ["MB", "NT", "SK"],
        "PE": ["NS", "NL", "NB", "QC"],
        "SK": ["MT", "ND", "AB", "MB", "NT"],
        # US territories
        "PR": [],
        "AS": [],
        "MP": [],
        "VI": [],
        "GU": [],
        "UM": [],
        # USA
        "AK": ["YT", "BC"],
        "AL": ["FL", "GA", "MS", "TN"],
        "AR": ["LA", "MO", "MS", "OK", "TN", "TX"],
        "AZ": ["CA", "CO", "NM", "NV", "UT"],
        "CA": ["AZ", "HI", "NV", "OR"],
        "CO": ["AZ", "KS", "NE", "NM", "OK", "UT", "WY"],
        "CT": ["MA", "NY", "RI"],
        "DC": ["MD", "VA"],
        "DE": ["MD", "NJ", "PA"],
        "FL": ["AL", "GA"],
        "GA": ["AL", "FL", "NC", "SC", "TN"],
        "HI": [],
        "IA": ["IL", "MN", "MO", "NE", "SD", "WI"],
        "ID": ["MT", "NV", "OR", "UT", "WA", "WY", "BC", "AB"],
        "IL": ["IA", "IN", "KY", "MO", "WI"],
        "IN": ["IL", "KY", "MO", "WI"],
        "KS": ["CO", "MO", "NE", "OK"],
        "KY": ["IL", "IN", "MO", "OH", "TN", "VA", "WV"],
        "LA": ["AR", "MS", "TX"],
        "MA": ["CT", "NH", "NY", "RI", "VT"],
        "MD": ["DC", "DE", "PA", "VA", "WV"],
        "ME": ["NH", "QC", "NB", "NS"],
        "MI": ["IN", "OH", "WI", "ON"],
        "MN": ["IA", "ND", "SD", "WI", "MB", "ON"],
        "MO": ["AR", "IA", "IL", "KS", "KY", "NE", "OK", "TN"],
        "MS": ["AL", "AR", "LA", "TN"],
        "MT": ["ID", "ND", "SD", "WY", "BC", "AB", "SK"],
        "NC": ["GA", "SC", "TN", "VA"],
        "ND": ["MN", "MT", "SD", "SK", "MB"],
        "NE": ["CO", "IA", "KS", "MO", "SD", "WY"],
        "NH": ["MA", "ME", "VT", "QC"],
        "NJ": ["DE", "NY", "PA"],
        "NM": ["AZ", "CO", "OK", "TX", "UT"],
        "NV": ["AZ", "CA", "ID", "OR", "UT"],
        "NY": ["CT", "MA", "NJ", "PA", "VT", "ON", "QC"],
        "OH": ["IN", "KY", "MI", "PA", "WV", "ON"],
        "OK": ["AR", "CO", "KS", "MO", "NM", "TX"],
        "OR": ["CA", "ID", "NV", "WA"],
        "PA": ["DE", "MD", "NJ", "NY", "OH", "WV", "ON"],
        "RI": ["CT", "MA"],
        "SC": ["GA", "NC"],
        "SD": ["IA", "MN", "MT", "ND", "NE", "WY"],
        "TN": ["AL", "AR", "GA", "KY", "MO", "MS", "NC", "VA"],
        "TX": ["AR", "LA", "NM", "OK"],
        "UT": ["AZ", "CO", "ID", "NM", "NV", "WY"],
        "VA": ["DC", "KY", "MD", "NC", "TN", "WV"],
        "VT": ["MA", "NH", "NY", "QC"],
        "WA": ["AK", "ID", "OR", "BC"],
        "WI": ["IA", "IL", "MI", "MN"],
        "WV": ["KY", "MD", "OH", "PA", "VA"],
        "WY": ["CO", "ID", "MT", "NE", "SD", "UT"],
    }

    return neighboring_regions[code]


def query_acis_data(query_type: str, data: str) -> None | requests.Response:
    if query_type == "Station":
        query_url = "https://data.nrcc.rcc-acis.org/StnMeta"
    elif query_type == "DailyData" or query_type == "HourlyData":
        query_url = "https://data.nrcc.rcc-acis.org/StnData"
    else:
        return None

    headers = {"content-type": "application/json"}

    jdata = json.dumps(data)

    try:
        reply = requests.post(query_url, jdata, headers=headers)

    except RequestException:
        return None

    return reply


def parse_out_station_ids(sids: list[str]):
    # wmo: looking for type 4 (last character of sid string)
    # icao: looking for type 5 (last character of sid string)
    # id: prefer faa (3), then icao (5), then wmo (4), then ghcn (6),
    # then just use the fist one
    wmo = "N/A"
    icao = "N/A"
    faa = "N/A"
    ghcn = "N/A"

    for sid in sids:
        parts = sid.split(" ")
        if parts[1] == "5":
            icao = parts[0]
        if parts[1] == "4":
            wmo = parts[0]
        if parts[1] == "3":
            faa = parts[0]
        if parts[1] == "6":
            ghcn = parts[0]

    if faa != "N/A":
        id = faa
    elif icao != "N/A":
        id = icao
    elif wmo != "N/A":
        id = wmo
    elif ghcn != "N/A":
        id = ghcn
    else:
        id = sids[0].split(" ")[0]

    return (id, wmo, icao)


def acis_make_list(stations: list) -> list:
    stations_list = []
    for station in stations:
        # if there's no name skip the record
        if "name" in station:
            name = station["name"]
        else:
            continue
        state = ""
        if "state" in station:
            state = station["state"]
        # if there are no sids, skip the record
        if ("sids" not in station) or (not station["sids"]):
            continue
        id, wmo, icao = parse_out_station_ids(station["sids"])

        # set lat long to N/A if "ll" values are malformed or missing
        latitude = "N/A"
        longitude = "N/A"
        if "ll" in station and len(station["ll"]) == 2:
            latitude = float(station["ll"][1])
            longitude = float(station["ll"][0])

        # set elevation to N/A if elev is malformed or missing
        elevation = "N/A"
        if "elev" in station:
            elevation = station["elev"]
            # ACIS returns Imperial values, convert feet to meters
            with contextlib.suppress(ValueError, TypeError):
                elevation = round(float(elevation) / 3.2808, 2)
        # time zone is offset from GMT/UTC
        time_zone = 0
        if "tzo" in station:
            time_zone = station["tzo"]

        # if the date range is not properly formed, skip the station
        if "valid_daterange" in station:
            if len(station["valid_daterange"]) == 2:
                daily_dates = station["valid_daterange"][0]
                hourly_dates = station["valid_daterange"][1]
                if len(daily_dates) == 2:
                    daily_start = datetime.strptime(daily_dates[0], "%Y-%m-%d")
                    daily_end = datetime.strptime(daily_dates[1], "%Y-%m-%d")
                else:
                    continue
                if len(hourly_dates) == 2:
                    hourly_start = datetime.strptime(
                        hourly_dates[0], "%Y-%m-%d"
                    )
                    hourly_end = datetime.strptime(hourly_dates[1], "%Y-%m-%d")
                else:
                    hourly_start = "N/A"
                    hourly_end = "N/A"
            else:
                continue
        else:
            continue

        t_dict = {
            "name": name,
            "country": (
                "CA"
                if state
                in ["AB", "BC", "MB", "NB", "NL", "NS", "ON", "PE", "QC", "SK"]
                else "US"
            ),
            "state": state,
            "id": id,
            "wmo": wmo,
            "icao": icao,
            "latitude": latitude,
            "longitude": longitude,
            "elevation": elevation,
            "timezone": time_zone,
            "daily_start": daily_start,
            "daily_end": daily_end,
            "hourly_start": hourly_start,
            "hourly_end": hourly_end,
        }
        stations_list.append(t_dict)

    return stations_list


if __name__ == "__main__":
    pass
