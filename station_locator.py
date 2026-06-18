from datetime import datetime

import pycountry
from meteostat import Station

from helper_functions import (
    acis_make_list,
    calculate_spherical_distance,
    meteostat_make_list,
    neighboring,
    query_acis_data,
)


class StationLocator:
    @classmethod
    def get_coverage(cls):
        coverage = {}
        sources = {c.id: c for c in cls.__subclasses__()}
        names = list(sources.keys())
        for name in names:
            result = sources[name].report_coverage()
            coverage[name] = result
        return coverage

    def __init__(self, data_source: str) -> None:
        self.data_source = data_source
        self.lookup_radius = 50000
        self.stations_list = None

    def set_lookup_radius(self, distance: int = 50000) -> bool:
        self.lookup_radius = distance
        return True

    def stations_by_state(self, country: str, state: str) -> list:
        pass

    def stations_by_location(
        self, latitude: float, longitude: float, state: str
    ) -> list:
        pass

    def filter_by_hourly(self, start: datetime, end: datetime) -> list:
        pass

    def filter_by_daily(self, start: datetime, end: datetime) -> list:
        pass


class StationLocatorMeteostat(StationLocator):
    id = "Meteostat"

    @classmethod
    def report_coverage(cls):
        coverage = {}
        countries = {
            country.name: country.alpha_2 for country in pycountry.countries
        }
        country_names = list(countries.keys())
        for name in country_names:
            regions = {
                region.name: region.code[3:][:2]
                for region in pycountry.subdivisions.get(
                    country_code=countries[name]
                )
            }
            coverage[name] = [countries[name], regions]
        return coverage

    def __init__(self) -> None:
        self.stations_obj = Station()
        self.stations = None
        super().__init__("Meteostat")

    def stations_by_state(self, country: str, state: str):
        self.stations = None
        self.stations = self.stations_obj.region(country, state)
        stations_data = self.stations.fetch()
        stations_dict = stations_data.to_dict("index")
        self.stations_list = meteostat_make_list(stations_dict)
        self.stations_list.sort(key=lambda station: station.get("name"))
        return self.stations_list

    def stations_by_location(
        self, latitude: float, longitude: float, state: str
    ):
        self.stations = None

        if latitude and longitude:
            self.stations = self.stations_obj.nearby(
                latitude, longitude, self.lookup_radius
            )
            stations_data = self.stations.fetch()
            stations_dict = stations_data.to_dict("index")
            self.stations_list = meteostat_make_list(stations_dict)
            self.stations_list.sort(key=lambda station: station.get("distance"))

        return self.stations_list

    def filter_by_hourly(self, start: datetime, end: datetime):
        if self.stations is not None:
            self.stations = self.stations.inventory("hourly", (start, end))
            stations_data = self.stations.fetch()
            stations_dict = stations_data.to_dict("index")

            self.stations_list = meteostat_make_list(stations_dict)

        return self.stations_list

    def filter_by_daily(self, start: datetime, end: datetime):
        if self.stations is not None:
            self.stations = self.stations.inventory("daily", (start, end))
            stations_data = self.stations.fetch()
            stations_dict = stations_data.to_dict("index")

            self.stations_list = meteostat_make_list(stations_dict)

        return self.stations_list


class StationLocatorACIS(StationLocator):
    id = "ACIS"

    @classmethod
    def report_coverage(cls):
        us_regions = {
            region.name: region.code[3:][:2]
            for region in pycountry.subdivisions.get(country_code="US")
        }
        ca_regions = {
            region.name: region.code[3:][:2]
            for region in pycountry.subdivisions.get(country_code="CA")
        }
        return {
            "United States": ["US", us_regions],
            "Canada": ["CA", ca_regions],
        }

    def __init__(self) -> None:
        self.stations = []
        self.state = ""
        super().__init__("ACIS")

    def stations_by_state(self, country: str, state: str):
        self.state = state
        self.stations = []
        self.stations_list = []
        parameter_string = {
            "meta": "name,state,sids,ll,elev,tzo,valid_daterange",
            "elems": "avgt,23",
            "state": state,
        }
        raw_result = query_acis_data("Station", parameter_string)
        if raw_result and raw_result.status_code == 200:
            json_data = raw_result.json()
            if "meta" in json_data:
                self.stations = json_data["meta"]
                self.stations_list = acis_make_list(self.stations)
                self.stations_list.sort(key=lambda station: station.get("name"))
        return self.stations_list

    def stations_by_location(
        self, latitude: float, longitude: float, state: str
    ) -> list:
        self.stations_list = []

        if not state:
            return self.stations_list

        state_list = [state]
        state_list.extend(neighboring(state))

        for each_state in state_list:
            parameter_string = {
                "meta": "name,state,sids,ll,elev,tzo,valid_daterange",
                "elems": "avgt,23",
                "state": each_state,
            }
            raw_result = query_acis_data("Station", parameter_string)
            if raw_result and raw_result.status_code == 200:
                json_data = raw_result.json()
                if "meta" in json_data:
                    self.stations = json_data["meta"]
                    raw_stations_list = acis_make_list(self.stations)
                    temp_list = []
                    for station in raw_stations_list:
                        if (
                            station["latitude"] != "N/A"
                            and station["longitude"] != "N/A"
                        ):
                            distance = calculate_spherical_distance(
                                latitude,
                                longitude,
                                station["latitude"],
                                station["longitude"],
                            )
                            if distance <= self.lookup_radius:
                                station["distance"] = distance
                                temp_list.append(station)
                    if len(temp_list) > 0:
                        self.stations_list.extend(temp_list)

        self.stations_list.sort(key=lambda station: station.get("distance"))
        return self.stations_list

    def filter_by_hourly(self, start: datetime, end: datetime) -> list:
        temp_list = []
        for station in self.stations_list:
            if (
                station["hourly_start"] != "N/A"
                and station["hourly_end"] != "N/A"
            ) and (
                start >= station["hourly_start"]
                and end <= station["hourly_end"]
            ):
                temp_list.append(station)
        self.stations_list = temp_list
        return self.stations_list

    def filter_by_daily(self, start: datetime, end: datetime) -> list:
        temp_list = []
        for station in self.stations_list:
            if start >= station["daily_start"] and end <= station["daily_end"]:
                temp_list.append(station)
        self.stations_list = temp_list
        return self.stations_list


if __name__ == "__main__":
    # Coverage data available from the class StationLocator

    coverage = StationLocator.get_coverage()
    print(f"StationLocator has {len(coverage.keys())} data sources")
    datasources = list(coverage.keys())
    for datasource in datasources:
        print(f"Data Source: {datasource} : ")
        countries = list(coverage[datasource].keys())
        for country in countries:
            print(
                f"Country Name: {country}, Country Code {coverage[datasource][country][0]}"
            )
            regions = coverage[datasource][country][1]
            region_names = list(regions.keys())
            for region_name in region_names:
                region_code = regions[region_name]
                if (
                    coverage[datasource][country][0] in ["US", "CA"]
                    and datasource == "ACIS"
                ):
                    print(
                        f"\tCountry: {country}, Region Name: {region_name}, Region Code: {region_code}, \
                        Neighboring: {neighboring(region_code)}"
                    )
                else:
                    print(
                        f"\tCountry: {country}, Region Names: {region_name}, \
                            Region Code: {region_code}"
                    )

#     lat = 42.3508285
#     long = -82.9994093
#     state = "MI"
#     start_date = datetime(2020, 1, 1, 0, 0, 0)
#     end_date = datetime(2020, 12, 31, 23, 59, 59)
#     search_radius = 500000

#     ds = {cls.id: cls for cls in StationLocator.__subclasses__()}
#     print(ds)

#     for source in list(ds.keys()):
#         locator = ds[source]()
#         print(locator.id)
#         success = locator.set_lookup_radius(search_radius)
#         station_list = locator.stations_by_location(lat, long, state)
#         station_list = locator.filter_by_hourly(start_date, end_date)
#         station_list = locator.filter_by_daily(start_date, end_date)
#         for station in station_list:
#             print(
#                 "Station Name: {} Country: {} State: {} Distance: {} \
# WMO {} ICAO {}".format(
#                     station["name"],
#                     station["country"],
#                     station["state"],
#                     round(station["distance"], 2),
#                     station["wmo"],
#                     station["icao"],
#                 )
#             )
#         print(len(station_list))
