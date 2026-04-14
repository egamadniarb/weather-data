from datetime import datetime, timedelta, timezone
from math import isnan, nan

from helper_functions import query_acis_data
from meteostat import Daily, Hourly


class StationData:
    def __init__(
        self,
        data_source: str,
        station_metadata: dict,
        start: datetime,
        end: datetime,
    ) -> None:
        def degree_convert(deg):
            m, s = divmod(abs(deg) * 3600, 60)
            d, m = divmod(m, 60)
            if deg < 0:
                d = -d
            d, m = int(d), int(m)
            return d, m, s

        deg, min, sec = degree_convert(station_metadata["latitude"])
        if deg > 0.0:
            hem = "N"
        else:
            hem = "S"
        latitude = "{}º {}' {}\" {}".format(abs(deg), min, round(sec, 4), hem)
        deg, min, sec = degree_convert(station_metadata["longitude"])
        if deg > 0.0:
            hem = "E"
        else:
            hem = "W"
        longitude = "{}º {}' {}\" {}".format(abs(deg), min, round(sec, 4), hem)

        self.metadata = {
            "Source": data_source,
            "Name": station_metadata["name"],
            "Country": station_metadata["country"],
            "Region": station_metadata["state"],
            "ID": station_metadata["id"],
            "WMO_ID": station_metadata["wmo"],
            "ICAO_ID": station_metadata["icao"],
            "Location": {"Latitude": latitude, "Longitude": longitude},
            "Elevation": {
                "Metric": station_metadata["elevation"],
                "Imperial": round(station_metadata["elevation"] * 1.8 + 32, 2),
            },
            "Timezone": station_metadata["timezone"],
        }

        if "distance" in station_metadata:
            self.metadata["Distance"] = {
                "Metric": station_metadata["distance"],
                "Imperial": round(station_metadata["distance"] * 3.280839895, 2),
            }

        self.start = start
        self.end = end
        self.hourly_data = {}
        self.hourly_for_averaging = {}
        self.daily_data = {}
        self.computed_daily_data = {}
        self.custom_date_ranges_data = {}

    def get_hourly_data(self):
        self.hourly_for_averaging = self.hourly_data
        temp_list = []
        for row in self.hourly_data["data"]:
            test_date = datetime(
                row["dtindex"].year, row["dtindex"].month, row["dtindex"].day
            )
            if test_date < self.start or test_date > self.end:
                pass
            else:
                newrow = {}
                newrow["timestamp"] = row["timestamp"]
                newrow["readings"] = row["readings"]
                temp_list.append(newrow)
        self.hourly_data = {
            "headers": self.hourly_for_averaging["headers"],
            "data": temp_list,
        }

        self.hourly_data["metadata"] = self.metadata
        return self.hourly_data

    def get_daily_data(self):
        self.daily_data["metadata"] = self.metadata
        return self.daily_data

    def custom_date_ranges(self, ranges):
        if not self.daily_data:
            return
        range_data = []
        for range in ranges:
            if range["start"] < self.start or range["start"] > self.end:
                return
            if range["end"] < self.start or range["end"] > self.end:
                return
            if range["start"] >= range["end"]:
                return
            range_sum = 0
            range_counter = 0

            for day in self.daily_data["data"]:
                ts = datetime(
                    day["timestamp"]["Year"],
                    day["timestamp"]["Month"],
                    day["timestamp"]["Day"],
                )
                if ts >= range["start"] and ts <= range["end"]:
                    if not isnan(day["readings"]["Metric"]["tavg"]):
                        range_sum += day["readings"]["Metric"]["tavg"]
                        range_counter += 1
            range_avg = round(range_sum / range_counter, 2)
            range_data.append(
                {
                    "timestamp": {},
                    "readings": {
                        "Metric": {
                            "start": range["start"].strftime("%Y-%m-%d"),
                            "end": range["end"].strftime("%Y-%m-%d"),
                            "tavg": range_avg,
                        },
                        "Imperial": {
                            "start": range["start"].strftime("%Y-%m-%d"),
                            "end": range["end"].strftime("%Y-%m-%d"),
                            "tavg": round(range_avg * 1.8 + 32, 2),
                        },
                    },
                }
            )
        self.custom_date_ranges_data = {
            "headers": {
                "Metric": [
                    "Start Date",
                    "End Date",
                    "Average Temperature ºC",
                ],
                "Imperial": [
                    "Start Date",
                    "End Date",
                    "Average Temperature ºF",
                ],
            },
            "data": range_data,
        }

        self.custom_date_ranges_data["metadata"] = self.metadata
        return self.custom_date_ranges_data

    def compute_daily_averages(self, end_hour):
        if not self.hourly_for_averaging:
            return

        hours_back = timedelta(hours=23)
        target_dt = datetime(
            self.start.year, self.start.month, self.start.day, end_hour, 0
        )
        avg_list = []
        temp_list = []
        for row in self.hourly_for_averaging["data"]:
            if row["dtindex"].replace(tzinfo=None) >= target_dt - hours_back:
                if not isnan(row["readings"]["Metric"]["temp"]):
                    temp_list.append(row["readings"]["Metric"]["temp"])
                if row["dtindex"].replace(tzinfo=None) == target_dt:
                    if end_hour == 0:
                        correct_date = row["dtindex"] - timedelta(days=1)
                        year = correct_date.year
                        month = correct_date.month
                        day = correct_date.day
                    else:
                        year = row["dtindex"].year
                        month = row["dtindex"].month
                        day = row["dtindex"].day
                    avg_list.append(
                        {
                            "timestamp": {
                                "Year": year,
                                "Month": month,
                                "Day": day,
                            },
                            "readings": {
                                "Metric": {
                                    "tavg": round(sum(temp_list) / len(temp_list), 2),
                                    "tmin": min(temp_list),
                                    "tmax": max(temp_list),
                                },
                                "Imperial": {
                                    "tavg": round(
                                        (sum(temp_list) / len(temp_list)) * 1.8 + 32,
                                        2,
                                    ),
                                    "tmin": round(min(temp_list) * 1.8 + 32, 2),
                                    "tmax": round(max(temp_list) * 1.8 + 32, 2),
                                },
                            },
                        }
                    )
                    temp_list = []
                    target_dt = target_dt + timedelta(days=1)
                if end_hour == 0:
                    if target_dt > self.end + timedelta(days=1):
                        break
                else:
                    if target_dt > self.end:
                        break

        if end_hour == 0:
            temp_list = []
            for row in avg_list:
                if (
                    datetime(
                        row["timestamp"]["Year"],
                        row["timestamp"]["Month"],
                        row["timestamp"]["Day"],
                    )
                    >= self.start
                ):
                    temp_list.append(row)

            avg_list = temp_list

        self.computed_daily_data = {
            "headers": {
                "Metric": [
                    "Average Temperature ºC",
                    "Minimum Temperature ºC",
                    "Maximum Temperature ºC",
                ],
                "Imperial": [
                    "Average Temperature ºF",
                    "Minimum Temperature ºF",
                    "Maximum Temperature ºF",
                ],
            },
            "data": avg_list,
        }

        self.computed_daily_data["metadata"] = self.metadata
        return self.computed_daily_data


class StationDataMeteostat(StationData):
    id = "Meteostat"

    def __init__(self, station_metadata: dict, start: datetime, end: datetime) -> None:
        super().__init__("Meteostat", station_metadata, start, end)

    def get_hourly_data(self) -> bool:
        one_day = timedelta(days=1)
        data = Hourly(
            loc=self.metadata["ID"],
            start=self.start - one_day,
            end=self.end + one_day,
            timezone=self.metadata["Timezone"],
            model="False",
        )
        if data.count() == 0:
            return False
        data = data.normalize()
        data = data.fetch()
        hourly_dict = data.to_dict("index")
        result_list = []
        headers = {
            "Metric": [
                "Temperature ºC",
                "Relative Humidity",
            ],
            "Imperial": [
                "Temperature ºF",
                "Relative Humidity",
            ],
        }
        for reading in hourly_dict:
            dt = reading.to_pydatetime()
            offset = reading.utcoffset().total_seconds() / 3600
            timestamp = {
                "Year": reading.year,
                "Month": reading.month,
                "Day": reading.day,
                "Hour": "{} UTC {}{}".format(
                    reading.hour, "+" if offset >= 0 else "", offset
                ),
            }
            readings = {
                "Metric": {
                    "temp": hourly_dict[reading]["temp"],
                    "rhum": hourly_dict[reading]["rhum"],
                },
                "Imperial": {
                    "temp": round(hourly_dict[reading]["temp"] * 1.8 + 32, 2),
                    "rhum": hourly_dict[reading]["rhum"],
                },
            }
            result_list.append(
                {
                    "dtindex": dt,
                    "timestamp": timestamp,
                    "readings": readings,
                }
            )
        self.hourly_data = {"headers": headers, "data": result_list}
        return super().get_hourly_data()

    def get_daily_data(self) -> bool:
        data = Daily(
            loc=self.metadata["ID"],
            start=self.start,
            end=self.end,
            model="False",
        )
        if data.count() == 0:
            return False
        data = data.normalize()
        data = data.fetch()
        daily_dict = data.to_dict("index")
        result_list = []
        headers = {
            "Metric": [
                "Average Temperature ºC",
                "Minimum Temperature ºC",
                "Maximum Temperature ºC",
            ],
            "Imperial": [
                "Average Temperature ºF",
                "Minimum Temperature ºF",
                "Maximum Temperature ºF",
            ],
        }
        for day in daily_dict:
            timestamp = {
                "Year": day.year,
                "Month": day.month,
                "Day": day.day,
            }
            readings = {
                "Metric": {
                    "tavg": daily_dict[day]["tavg"],
                    "tmin": daily_dict[day]["tmin"],
                    "tmax": daily_dict[day]["tmax"],
                },
                "Imperial": {
                    "tavg": (
                        daily_dict[day]["tavg"]
                        if isnan(daily_dict[day]["tavg"])
                        else round(daily_dict[day]["tavg"] * 1.8 + 32, 2)
                    ),
                    "tmin": (
                        daily_dict[day]["tmin"]
                        if isnan(daily_dict[day]["tmin"])
                        else round(daily_dict[day]["tmin"] * 1.8 + 32, 2)
                    ),
                    "tmax": (
                        daily_dict[day]["tmax"]
                        if isnan(daily_dict[day]["tmax"])
                        else round(daily_dict[day]["tmax"] * 1.8 + 32, 2)
                    ),
                },
            }
            result_list.append({"timestamp": timestamp, "readings": readings})
        self.daily_data = {"headers": headers, "data": result_list}
        return super().get_daily_data()


class StationDataACIS(StationData):
    id = "ACIS"

    def __init__(self, station_metadata: dict, start: datetime, end: datetime) -> None:
        super().__init__("ACIS", station_metadata, start, end)

    def get_hourly_data(self) -> bool:
        one_day = timedelta(days=1)
        extra_day = self.start - one_day

        extra_day2 = self.start + one_day

        parameter_string = {
            "sid": self.metadata["ID"],
            "sdate": extra_day.strftime("%Y-%m-%d"),
            "edate": extra_day2.strftime("%Y-%m-%d"),
            "elems": [{"vX": 23, "prec": 2}, {"vX": 24}],
            "meta": "tzo",
        }
        raw_result = query_acis_data("HourlyData", parameter_string)
        if raw_result:
            if raw_result.status_code == 200:
                json_data = raw_result.json()
                tzoffset = float(nan)
                if "meta" in json_data:
                    if "tzo" in json_data["meta"]:
                        tzoffset = float(json_data["meta"]["tzo"])
                if "data" in json_data:
                    headers = {
                        "Metric": [
                            "Temperature ºC",
                            "Relative Humidity",
                        ],
                        "Imperial": [
                            "Temperature ºF",
                            "Relative Humidity",
                        ],
                    }
                    response_data = json_data["data"]
                    result_list = []
                    for day in response_data:
                        dt = datetime.strptime(day[0], "%Y-%m-%d")
                        ryear = dt.year
                        rmonth = dt.month
                        rday = dt.day
                        measure_time = datetime.strptime("00:00", "%H:%M")
                        for idx in range(len(day[1])):
                            temp = day[1][idx]
                            if temp == "M":
                                temp = float(nan)
                                mtemp = temp
                            else:
                                mtemp = round((float(temp) - 32.0) / 1.8, 2)
                            rhum = day[2][idx]
                            if rhum == "M":
                                rhum = float(nan)
                            else:
                                rhum = int(rhum)

                            timestamp = {
                                "Year": ryear,
                                "Month": rmonth,
                                "Day": rday,
                                "Hour": "{} UTC {}{}".format(
                                    measure_time.hour,
                                    "+" if tzoffset >= 0 else "",
                                    tzoffset,
                                ),
                            }
                            reading = {
                                "Metric": {"temp": mtemp, "rhum": rhum},
                                "Imperial": {"temp": temp, "rhum": rhum},
                            }
                            dtindex = datetime(
                                dt.year,
                                dt.month,
                                dt.day,
                                hour=measure_time.hour,
                                minute=0,
                                tzinfo=timezone(timedelta(hours=tzoffset)),
                            )
                            result_list.append(
                                {
                                    "dtindex": dtindex,
                                    "timestamp": timestamp,
                                    "readings": reading,
                                }
                            )
                            measure_time = measure_time + timedelta(hours=1)
                    self.hourly_data = {
                        "headers": headers,
                        "data": result_list,
                    }
        return super().get_hourly_data()

    def get_daily_data(self) -> bool:
        parameter_string = {
            "sid": self.metadata["ID"],
            "sdate": self.start.strftime("%Y-%m-%d"),
            "edate": self.end.strftime("%Y-%m-%d"),
            "elems": [
                {"name": "avgt", "prec": 2},
                {"name": "mint", "prec": 2},
                {"name": "maxt", "prec": 2},
            ],
            "meta": "tzo",
        }
        raw_result = query_acis_data("DailyData", parameter_string)
        if raw_result:
            if raw_result.status_code == 200:
                json_data = raw_result.json()
                # tzoffset = float(nan)
                if "meta" in json_data:
                    if "tzo" in json_data["meta"]:
                        pass
                        # tzoffset = float(json_data["meta"]["tzo"])
                if "data" in json_data:
                    response_data = json_data["data"]
                    headers = {
                        "Metric": [
                            "Average Temperature ºC",
                            "Minimum Temperature ºC",
                            "Maximum Temperature ºC",
                        ],
                        "Imperial": [
                            "Average Temperature ºF",
                            "Minimum Temperature ºF",
                            "Maximum Temperature ºF",
                        ],
                    }
                    result_list = []
                    for day in response_data:
                        t_date = datetime.strptime(day[0], "%Y-%m-%d")
                        timestamp = {
                            "Year": t_date.year,
                            "Month": t_date.month,
                            "Day": t_date.day,
                        }
                        if day[1] == "M":
                            day_temp = float(nan)
                            day_temp1 = float(nan)
                        else:
                            day_temp1 = float(day[1])
                            day_temp = round((day_temp1 - 32.0) / 1.8, 2)
                        if day[2] == "M":
                            day_min = float(nan)
                            day_min1 = float(nan)
                        else:
                            day_min1 = float(day[2])
                            day_min = round((day_min1 - 32.0) / 1.8, 2)
                        if day[3] == "M":
                            day_max = float(nan)
                            day_max1 = float(nan)
                        else:
                            day_max1 = float(day[3])
                            day_max = round((day_max1 - 32.0) / 1.8, 2)
                        result_list.append(
                            {
                                "timestamp": timestamp,
                                "readings": {
                                    "Metric": {
                                        "tavg": day_temp,
                                        "tmin": day_min,
                                        "tmax": day_max,
                                    },
                                    "Imperial": {
                                        "tavg": day_temp1,
                                        "tmin": day_min1,
                                        "tmax": day_max1,
                                    },
                                },
                            }
                        )
                    self.daily_data = {"headers": headers, "data": result_list}
            return super().get_daily_data()


if __name__ == "__main__":
    start = datetime(2022, 1, 1, 0, 0)
    end = datetime(2022, 6, 1, 23, 59)

    billing_cycle = [
        {"start": datetime(2022, 1, 1), "end": datetime(2022, 1, 15)},
        {"start": datetime(2022, 1, 16), "end": datetime(2022, 2, 14)},
        {"start": datetime(2022, 2, 15), "end": datetime(2022, 3, 12)},
        {"start": datetime(2022, 3, 13), "end": datetime(2022, 4, 12)},
        {"start": datetime(2022, 4, 13), "end": datetime(2022, 5, 15)},
        {"start": datetime(2022, 5, 16), "end": datetime(2022, 5, 30)},
    ]

    # station_data = StationDataMeteostat(
    #     {
    #         "name": "Detroit Metropolitan",
    #         "country": "US",
    #         "state": "MI",
    #         "id": "72537",
    #         "wmo": "72537",
    #         "icao": "KDTW",
    #         "latitude": 42.2333,
    #         "longitude": -83.0,
    #         "elevation": 195.0,
    #         "timezone": "America/Detroit",
    #         "distance": 14322.271197538386,
    #     },
    #     start,
    #     end,
    # )

    station_data = StationDataACIS(
        {
            "name": "DETROIT METRO AIRPORT",
            "country": "US",
            "state": "MI",
            "id": "DTW",
            "wmo": "72537",
            "icao": "KDTW",
            "latitude": 42.23113,
            "longitude": -83.33121,
            "elevation": 192.03,
            "timezone": -5.0,
            "daily_start": "",
            "daily_end": "",
            "hourly_start": "",
            "hourly_end": "",
            "distance": 32211.91457777178,
        },
        start,
        end,
    )

    # daily_data = station_data.get_daily_data()
    # if daily_data:
    #     # print(list(daily_data.keys()))
    #     # print(list(daily_data["data"][0].keys()))
    #     # print(daily_data["metadata"])
    #     # print(daily_data["metadata"]["Location"]["Latitude"])
    #     # print(daily_data["metadata"]["Location"]["Longitude"])
    #     # print(daily_data["headers"])
    #     # print(list(daily_data["data"][0]["readings"]["Metric"].keys()))

    #     print(daily_data)
    #     # print(daily_data["headers"])
    #     # for row in daily_data["data"]:
    #     #     print(row)

    hourly_data = station_data.get_hourly_data()
    if hourly_data:
        print(list(hourly_data.keys()))
        print(list(hourly_data["data"][0].keys()))
        print(hourly_data["headers"])
        print(list(hourly_data["data"][0]["readings"]["Metric"].keys()))
        print(hourly_data["data"][0])
        print(hourly_data["headers"])
        for row in hourly_data["data"]:
            print(row)
        # print(hourly_data)

    # computed_data = station_data.compute_daily_averages(10)
    # if computed_data:
    #     print(computed_data)
    #     # print(list(computed_data.keys()))
    #     # print(list(computed_data["data"][0].keys()))
    #     # print(computed_data["headers"])
    #     # print(list(computed_data["data"][0]["readings"]["Metric"].keys()))
    # #     print(computed_data)
    # #     print(computed_data["headers"])
    # #     for row in computed_data["data"]:
    # #         print(row)

    # range_data = station_data.custom_date_ranges(billing_cycle)
    # if range_data:
    #     print("")
    #     print(range_data)
    #     # print(list(range_data.keys()))
    #     # print(list(range_data["data"][0].keys()))
    #     # print(range_data["headers"])
    #     # print(list(range_data["data"][0]["readings"]["Metric"].keys()))
    # #     print(range_data)
    # #     print(range_data["headers"])
    # #     for row in range_data["data"]:
    # #         print(row)
