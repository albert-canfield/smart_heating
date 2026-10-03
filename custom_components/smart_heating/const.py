"""Constants for Smart Heating."""
DOMAIN = "smart_heating"
VERSION = "0.10.1"  # keep in sync with manifest.json (cache-busts the card)
PLATFORMS = ["sensor", "binary_sensor", "select", "switch", "number"]

SUBENTRY_ROOM = "room"

# House (config entry data)
CONF_BOILER = "boiler_switch"
CONF_BOILER_ON = "boiler_on_sensor"
CONF_HW_CALLING = "hw_calling"
CONF_OUTDOOR_MEAN = "outdoor_mean"
CONF_OUTDOOR_TEMP = "outdoor_temperature"
CONF_WEATHER = "weather"
CONF_NIGHT_SCHEDULE = "night_schedule"
CONF_GAS_METER = "gas_meter"
CONF_GAS_RATE = "gas_rate"
CONF_ENERGY_SOURCE = "energy_source"
SOURCE_METER, SOURCE_ESTIMATE = "smart_meter", "estimate"
CONF_START_MODE = "start_mode"
START_HEAT, START_WATCH = "heat_now", "watch_first"
START_MODES = [START_HEAT, START_WATCH]
ENERGY_SOURCES = [SOURCE_METER, SOURCE_ESTIMATE]
CONF_ALARM = "alarm_panel"
CONF_HEATING_TYPE = "heating_type"
TYPE_TANK, TYPE_COMBI, TYPE_ELECTRIC, TYPE_HYBRID = "boiler_tank", "combi", "electric", "hybrid"
HEATING_TYPES = [TYPE_TANK, TYPE_COMBI, TYPE_ELECTRIC, TYPE_HYBRID]
CONF_HW_SYSTEM = "hot_water_system"
HW_TANK, HW_COMBI, HW_NONE = "tank", "combi", "none"
HW_SYSTEMS = [HW_TANK, HW_COMBI, HW_NONE]
HW_S_PLAN, HW_Y_PLAN = "s_plan", "y_plan"  # older entries: both mean a tank
CONF_HW_PRIORITY = "hot_water_priority"
CONF_THERMOSTAT_STYLE = "thermostat_style"
STYLE_RELAY, STYLE_SETPOINT = "relay", "setpoint"
ALARM_AWAY_STATES = ("armed_away", "armed_vacation")

FORECAST_REFRESH_MIN = 30
FORECAST_RETRY_MIN = 5  # after a failed or empty fetch (e.g. the weather entity still starting)

# Room (subentry data)
CONF_NAME = "name"
CONF_AREA = "area_id"
CONF_FLOOR = "floor"
CONF_PRIORITY = "priority"
CONF_COMFORT = "comfort"
CONF_TEMP = "temperature_sensor"
CONF_HUMIDITY = "humidity_sensor"
CONF_TRVS = "trvs"
CONF_PRESENCE = "presence"
CONF_MEDIA = "media"
CONF_LIGHTS = "lights"
CONF_SCHEDULE = "schedule"
CONF_HEATERS = "heaters"
CONF_HEATER_W = "heater_power_w"
CONF_HEATER_ECO_W = "heater_eco_power_w"
CONF_RADIATOR = "radiator"
DEFAULT_HEATER_W = 2000.0

# Options (tuning)
OPT_KEYS = [
    "baseline_day",
    "baseline_night",
    "safety",
    "season_gate",
    "hysteresis",
    "min_run_min",
    "min_off_min",
    "coast_rate",
    "coast_horizon_min",
    "stack_max_wait_min",
    "hw_max_pause_min",
    "trv_open_offset",
    "trv_closed",
]
OPT_OVERRIDE_HOURS = "override_hours"
OPT_GAS_PRICE = "gas_price"
OPT_BOILER_KW = "boiler_input_kw"
OPT_NOTIFY = "notify_service"
OPT_NIGHT_START = "night_start"
OPT_NIGHT_END = "night_end"
DEFAULT_NIGHT_START = "22:00:00"
DEFAULT_NIGHT_END = "07:00:00"
DEFAULT_GAS_PRICE = 0.06
DEFAULT_BOILER_KW = 15.0
OPT_ELEC_PRICE = "electricity_price"
DEFAULT_ELEC_PRICE = 0.25
CALIBRATED_SHARE = 0.8  # share of rooms that must be calibrated
STORE_VERSION = 1
SAVE_DELAY_S = 600
DEFAULT_OVERRIDE_HOURS = 2.0

UPDATE_INTERVAL_S = 60
TRV_STAGGER_S = 3

EVENT_DECISION = "smart_heating_decision"
LOG_SIZE = 200

# Setpoints
SETPOINT_MIN = 10.0
SETPOINT_MAX = 25.0
SETPOINT_STEP = 0.5

# Heat test (speeds up calibration)
HEAT_TEST_MIN = 135  # maximum duration: 10 min warm-up + 2 h of heating samples
HEAT_TEST_CAP = 21.5  # a room never goes above this during the test
HEAT_TEST_RISE = 1.0  # a room stops once it is this much warmer than at the start
SERVICE_HEAT_TEST = "heat_test"
SERVICE_RELEARN = "relearn"
STARTUP_GRACE_MIN = 2  # sensors may still be coming up after a restart
BOILER_SILENT_MIN = 20  # heating called this long without the boiler running sensor turning on
SERVICE_START_CONTROL = "start_control"

# Boiler protection (applies to every command, whatever asked for it)
BOILER_GUARD_S = 120  # never switch the boiler again within this of its last change
BOILER_FLAP_WINDOW_MIN = 30
BOILER_FLAP_MAX = 6  # more switches than this in the window locks boiler control
BOILER_LOCK_MIN = 30
EXTERNAL_HOLD_MIN = 15  # after something else switched the boiler, don't switch it back on for this long
