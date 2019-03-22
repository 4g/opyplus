import collections

import pandas as pd

from ..util import multi_mode_write, get_mono_line_copyright_message, to_buffer

WEEK_DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")

# "year",
# "month",
# "day",
# "hour",
# "minute",

WEATHER_SERIES_DEFAULTS = collections.OrderedDict((  # if None: mandatory field, else optional
    ("datasource", ""),
    ("drybulb", None),
    ("dewpoint", None),
    ("relhum", None),
    ("atmos_pressure", None),
    ("exthorrad", 9999),
    ("extdirrad", 9999),
    ("horirsky", 9999),
    ("glohorrad", None),
    ("dirnorrad", None),
    ("difhorrad", None),
    ("glohorillum", 999999),
    ("dirnorillum", 999999),
    ("difhorillum", 999999),
    ("zenlum", 9999),
    ("winddir", None),
    ("windspd", None),
    ("totskycvr", 99),
    ("opaqskycvr", 99),
    ("visibility", 9999),
    ("ceiling_hgt", 99999),
    ("presweathobs", 999),
    ("presweathcodes", 999),
    ("precip_wtr", 999),
    ("aerosol_opt_depth", 999),
    ("snowdepth", 999),
    ("days_last_snow", 99),
    ("Albedo", 999),
    ("liq_precip_depth", 999),
    ("liq_precip_rate", 99)
))

mandatory_columns = tuple(k for k, v in WEATHER_SERIES_DEFAULTS.items() if v is None)  # we use tuple for immutability


class WeatherData:
    def __init__(
            self,
            weather_series,  # dataframe
            latitude,
            longitude,
            timezone_offset,
            elevation,
            city=None,
            state_province_region=None,
            country=None,
            source=None,
            wmo=None,
            design_condition_source=None,
            design_conditions=None,  # list of design conditions
            typical_extreme_periods=None,  # list of typical/extreme periods
            ground_temperatures=None,  # list of ground temperatures
            leap_year_observed="no",
            daylight_savings_start_day=0,
            daylight_savings_end_day=0,
            holidays=None,  # [(name, day), ...]
            comments_1="",
            comments_2=""
    ):
        # todo: document two df mode (datetime index or not)
        self._weather_series = _check_and_sanitize_weather_series(weather_series)
        # todo: check headers
        self._headers = dict(
            # mandatory location
            latitude=latitude,
            longitude=longitude,
            timezone_offset=timezone_offset,
            elevation=elevation,
            # optional location
            city=city,
            state_province_region=state_province_region,
            country=country,
            source=source,
            wmo=wmo,
            # design conditions
            design_condition_source=design_condition_source,
            design_conditions=[] if design_conditions is None else design_conditions,
            # typical/extreme periods
            typical_extreme_periods=[] if typical_extreme_periods is None else typical_extreme_periods,
            # ground temperatures
            ground_temperatures=[] if ground_temperatures is None else ground_temperatures,
            # holidays/daylight savings
            leap_year_observed=leap_year_observed,
            daylight_savings_start_day=daylight_savings_start_day,
            daylight_savings_end_day=daylight_savings_end_day,
            holidays=[] if holidays is None else holidays,  # [(name, day), ...]
            # comments
            comments_1=comments_1,
            comments_2=comments_2
        )

    @classmethod
    def from_epw(cls, buffer_or_path, encoding=None):
        from .epw_parse import parse_epw
        _, buffer = to_buffer(buffer_or_path)
        with buffer as f:
            return parse_epw(f, encoding=encoding)

    @property
    def is_datetime_index_mode(self):
        return isinstance(self._weather_series.index, pd.DatetimeIndex)

    def _headers_to_epw(self):
        location = [
            "LOCATION",
            self._headers["city"],
            self._headers["state_province_region"],
            self._headers["country"],
            self._headers["source"],
            self._headers["wmo"],
            self._headers["latitude"],
            self._headers["longitude"],
            self._headers["timezone_offset"],
            self._headers["elevation"]
        ]

        # design conditions
        design_conditions = ["DESIGN CONDITIONS", len(self._headers["design_conditions"])]
        for dc in self._headers["design_conditions"]:
            design_conditions.extend([dc.name] + dc.values)

        # typical/extreme periods
        typical_extreme_periods = ["TYPICAL/EXTREME PERIODS", len(self._headers["typical_extreme_periods"])
                                   ]
        for tep in self._headers["typical_extreme_periods"]:
            typical_extreme_periods.extend([tep.name, tep.period_type, tep.start_day, tep.end_day])

        # ground temperatures
        ground_temperatures = ["GROUND TEMPERATURES", len(self._headers["ground_temperatures"])]
        for gt in self._headers["ground_temperatures"]:
            ground_temperatures.extend(
                [
                    gt.depth,
                    gt.soil_conductivity,
                    gt.soil_density,
                    gt.soil_specific_heat
                ] +
                gt.monthly_average_ground_temperatures
            )

        # holidays/daylight savings
        holidays_daylight_savings = [
            "HOLIDAYS/DAYLIGHT SAVINGS",
            self._headers["leap_year_observed"],
            self._headers["daylight_savings_start_day"],
            self._headers["daylight_savings_end_day"],
            len(self._headers["holidays"])
        ]
        for name, day in self._headers["holidays"]:
            holidays_daylight_savings.extend([name, day])

        # comments
        comments_1 = get_mono_line_copyright_message()
        if comments_1 not in self._headers["comments_1"]:
            comments_1 += self._headers["comments_1"]
        comments_1 = ["COMMENTS 1", comments_1]
        comments_2 = ["COMMENTS 2", self._headers["comments_2"]]

        # data periods
        if self.is_datetime_index_mode:
            start_timestamp = self._weather_series.index[0]
            end_timestamp = self._weather_series.index[-1]
            data_periods = [
                "DATA PERIODS",
                1,
                1,
                WEEK_DAYS[start_timestamp.weekday()],
                f"{start_timestamp.month}/{start_timestamp.day}",
                f"{end_timestamp.month}/{end_timestamp.day}"
            ]
        else:
            start_month, start_day = self._weather_series["month"].iloc[0], self._weather_series["day"].iloc[0]
            end_month, end_day = self._weather_series["month"].iloc[-1], self._weather_series["day"].iloc[-1]
            data_periods = [
                "DATA PERIODS",
                1,
                1,
                "Monday",  # todo: manage properly, should store this info while from_epw...
                f"{start_month}/{start_day}",
                f"{end_month}/{end_day}"
            ]

        return "\n".join([", ".join([str(cell) for cell in row]) for row in (
            location,
            design_conditions,
            typical_extreme_periods,
            holidays_daylight_savings,
            comments_1,
            comments_2,
            data_periods
        )])

    def to_epw(self, buffer_or_path=None):
        epw_content = self._headers_to_epw() + self._weather_series.to_csv(header=False, index=False)
        return multi_mode_write(
            lambda buffer: buffer.write(epw_content),
            lambda: epw_content,
            buffer_or_path=buffer_or_path
        )


def _check_and_sanitize_weather_series(df):
    # check dataframe
    if not isinstance(df, pd.DataFrame):
        raise TypeError("Weather series must be a pandas DataFrame.")

    # check data columns
    given_columns = set(df.columns)
    diff = set(mandatory_columns).difference(given_columns)
    if len(diff) != 0:
        raise ValueError(f"Missing mandatory columns: {diff}.")

    # prepare data container
    data = collections.OrderedDict()

    # check index info
    is_datetime_index = False
    if isinstance(df.index, pd.DatetimeIndex):  # datetime index mode
        is_datetime_index = True

        # check frequency
        if df.index.freq != "H":
            raise ValueError("Weather series must have an hourly frequence.")

        # check first minute is 0
        if df.index[0].minute != 0:
            raise ValueError("Minutes must be 0.")

        # prepare instant columns
        data.update((
            ("year", df.index.year),
            ("month", df.index.month),
            ("day", df.index.day),
            ("hour", df.index.hour + 1),
            ("minute", 0)
        ))
    else:
        # check instant columns
        diff = {"year", "month", "day", "hour", "minute"}.difference(given_columns)
        if len(diff) != 0:
            raise ValueError(f"Missing mandatory columns: {diff}.")

        # prepare instant columns
        data.update((k, df[k]) for k in ("year", "month", "day", "hour", "minute"))

    # add data columns
    data.update(collections.OrderedDict(
            (k, df[k] if k in given_columns else v) for k, v in WEATHER_SERIES_DEFAULTS.items())
    )

    # create
    sanitized_df = pd.DataFrame(data, index=df.index if is_datetime_index else None)

    # check no empty values
    nan_columns = set(sanitized_df.columns[sanitized_df.isnull().sum() > 0])
    if len(nan_columns) > 0:
        raise ValueError(f"Some columns contain null values: {tuple(sorted(nan_columns))}")

    # prepare
    return sanitized_df
