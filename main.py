"""Control Red (D0), Yellow (D1), and Green (D2) LEDs individually via 3 ThingsBoard switches."""

import json
import network
import time
from machine import Pin
from umqtt.simple import MQTTClient

# --- KONFIGURASI DEFAULT ---
DEFAULT_THINGSBOARD_HOST: str = "eu.thingsboard.cloud"
DEFAULT_THINGSBOARD_PORT: int = 1883
CLIENT_ID: str = "esp8266_ryg_01"
ENV_FILE: str = ".env"

# --- PEMETAAN PIN LED (AKTIF-HIGH: 1=ON, 0=OFF) ---
LED_ON: int = 1
LED_OFF: int = 0

LEDS: dict = {
    "red": ("Red (D0)", Pin(16, Pin.OUT, value=LED_OFF)),
    "yellow": ("Yellow (D1)", Pin(5, Pin.OUT, value=LED_OFF)),
    "green": ("Green (D2)", Pin(4, Pin.OUT, value=LED_OFF)),
}

GPIO_TO_CHANNEL: dict = {16: "red", 5: "yellow", 4: "green"}

SET_METHOD_TO_CHANNEL: dict = {
    "setred": "red",
    "setr": "red",
    "setledred": "red",
    "setredled": "red",
    "setled1": "red",
    "setswitch1": "red",
    "setd0": "red",
    "setyellow": "yellow",
    "sety": "yellow",
    "setledyellow": "yellow",
    "setyellowled": "yellow",
    "setled2": "yellow",
    "setswitch2": "yellow",
    "setd1": "yellow",
    "setgreen": "green",
    "setg": "green",
    "setledgreen": "green",
    "setgreenled": "green",
    "setled3": "green",
    "setswitch3": "green",
    "setd2": "green",
}

GET_METHOD_TO_CHANNEL: dict = {
    "getred": "red",
    "getr": "red",
    "getledred": "red",
    "getredled": "red",
    "getled1": "red",
    "getswitch1": "red",
    "getd0": "red",
    "checkred": "red",
    "checkr": "red",
    "checkled1": "red",
    "checkstatusred": "red",
    "checkstatus1": "red",
    "getyellow": "yellow",
    "gety": "yellow",
    "getledyellow": "yellow",
    "getyellowled": "yellow",
    "getled2": "yellow",
    "getswitch2": "yellow",
    "getd1": "yellow",
    "checkyellow": "yellow",
    "checky": "yellow",
    "checkled2": "yellow",
    "checkstatusyellow": "yellow",
    "checkstatus2": "yellow",
    "getgreen": "green",
    "getg": "green",
    "getledgreen": "green",
    "getgreenled": "green",
    "getled3": "green",
    "getswitch3": "green",
    "getd2": "green",
    "checkgreen": "green",
    "checkg": "green",
    "checkled3": "green",
    "checkstatusgreen": "green",
    "checkstatus3": "green",
}

SET_ALL_METHODS: tuple = (
    "setvalue",
    "setstate",
    "setstatus",
    "setled",
    "setswitch",
    "setpower",
    "setall",
)
GET_ALL_METHODS: tuple = (
    "getvalue",
    "checkstatus",
    "checkvalue",
    "checkstate",
    "getstate",
    "getstatus",
    "getled",
    "getswitch",
    "getpower",
    "getall",
)

ATTR_KEY_TO_CHANNEL: dict = {
    "red": "red",
    "r": "red",
    "ledred": "red",
    "led1": "red",
    "switch1": "red",
    "d0": "red",
    "yellow": "yellow",
    "y": "yellow",
    "ledyellow": "yellow",
    "led2": "yellow",
    "switch2": "yellow",
    "d1": "yellow",
    "green": "green",
    "g": "green",
    "ledgreen": "green",
    "led3": "green",
    "switch3": "green",
    "d2": "green",
}
GLOBAL_ATTR_KEYS: tuple = ("led", "status", "state", "value", "switch")

led_states: dict = {"red": False, "yellow": False, "green": False}
mqtt_client = None


def normalize_key(name: str) -> str:
    """Normalize method or attribute names for case- and separator-insensitive lookup."""
    return name.strip().replace("_", "").replace("-", "").lower()


def parse_bool(value: object) -> bool:
    """Convert RPC or attribute parameter into a strict boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized: str = value.strip().lower()
        if normalized in ("true", "1", "on", "yes"):
            return True
        if normalized in ("false", "0", "off", "no"):
            return False
    raise ValueError("Nilai boolean tidak valid: {}".format(value))


def set_led(channel: str, enabled: bool) -> None:
    """Turn a single LED channel (red, yellow, or green) ON or OFF."""
    if channel not in LEDS:
        raise ValueError("Channel LED tidak dikenal: {}".format(channel))
    label, pin = LEDS[channel]
    pin.value(LED_ON if enabled else LED_OFF)
    led_states[channel] = enabled
    print(label, "->", "ON" if enabled else "OFF")


def set_all_leds(enabled: bool) -> None:
    """Turn all three LEDs (Red, Yellow, Green) ON or OFF together."""
    for channel in LEDS:
        set_led(channel, enabled)


def load_env(path: str = ENV_FILE) -> dict:
    """Load KEY=VALUE pairs from a .env file on ESP8266 flash."""
    env: dict = {}
    try:
        with open(path, "r") as handle:
            for raw_line in handle:
                line: str = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if len(val) >= 2 and (
                    (val[0] == '"' and val[-1] == '"')
                    or (val[0] == "'" and val[-1] == "'")
                ):
                    val = val[1:-1]
                if key:
                    env[key] = val
    except OSError as exc:
        raise RuntimeError("File {} tidak ditemukan di ESP8266: {}".format(path, exc))
    return env


def connect_wifi(ssid: str, password: str, timeout_s: int = 20) -> None:
    """Connect ESP8266 to Wi-Fi station interface with timeout."""
    if not ssid:
        raise ValueError("WIFI_SSID belum diisi di .env.")

    wlan: network.WLAN = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return

    print("Menghubungkan ke WiFi {}...".format(ssid))
    wlan.connect(ssid, password)
    deadline: int = time.ticks_add(time.ticks_ms(), timeout_s * 1000)
    while not wlan.isconnected():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            status: int = wlan.status()
            wlan.disconnect()
            raise RuntimeError("Timeout koneksi WiFi (status={}).".format(status))
        time.sleep(0.5)
    print("WiFi terhubung, IP:", wlan.ifconfig()[0])


def publish_led_status(client: MQTTClient) -> None:
    """Publish per-LED and aggregate states to ThingsBoard telemetry and attributes."""
    any_on: bool = any(led_states.values())
    payload: bytes = json.dumps(
        {
            "red": led_states["red"],
            "yellow": led_states["yellow"],
            "green": led_states["green"],
            "r": led_states["red"],
            "y": led_states["yellow"],
            "g": led_states["green"],
            "led1": led_states["red"],
            "led2": led_states["yellow"],
            "led3": led_states["green"],
            "led": any_on,
            "status": any_on,
        }
    ).encode("utf-8")
    client.publish(b"v1/devices/me/telemetry", payload)
    client.publish(b"v1/devices/me/attributes", payload)
    print("Status terkirim ke ThingsBoard:", payload.decode("utf-8"))


def extract_request_id(topic: bytes) -> str:
    """Extract RPC request id from v1/devices/me/rpc/request/{id}."""
    parts: list = topic.decode("utf-8").split("/")
    return parts[-1] if parts else ""


def send_rpc_response(client: MQTTClient, req_id: str, value: object) -> None:
    """Reply to ThingsBoard two-way RPC request."""
    if not req_id:
        return
    resp_topic: bytes = "v1/devices/me/rpc/response/{}".format(req_id).encode("utf-8")
    client.publish(resp_topic, json.dumps(value).encode("utf-8"))


def apply_dict_params(params: dict) -> bool:
    """Apply channel updates from dict-style RPC params or shared attributes."""
    changed: bool = False

    if "pin" in params and "enabled" in params:
        gpio: int = int(params["pin"])
        if gpio in GPIO_TO_CHANNEL:
            set_led(GPIO_TO_CHANNEL[gpio], parse_bool(params["enabled"]))
            return True

    for raw_key, raw_val in params.items():
        norm_key: str = normalize_key(str(raw_key))
        if norm_key in ATTR_KEY_TO_CHANNEL:
            set_led(ATTR_KEY_TO_CHANNEL[norm_key], parse_bool(raw_val))
            changed = True
        elif norm_key in GLOBAL_ATTR_KEYS:
            set_all_leds(parse_bool(raw_val))
            changed = True
    return changed


def handle_rpc(client: MQTTClient, topic: bytes, msg: bytes) -> None:
    """Handle ThingsBoard Server-Side RPC requests for Red, Yellow, and Green switches."""
    req_id: str = extract_request_id(topic)
    data: dict = json.loads(msg.decode("utf-8"))
    method: str = str(data.get("method", ""))
    norm_method: str = normalize_key(method)
    params = data.get("params")

    if norm_method in SET_METHOD_TO_CHANNEL:
        channel: str = SET_METHOD_TO_CHANNEL[norm_method]
        enabled: bool = parse_bool(params)
        set_led(channel, enabled)
        send_rpc_response(client, req_id, led_states[channel])
        publish_led_status(client)
        return

    if norm_method in GET_METHOD_TO_CHANNEL:
        channel = GET_METHOD_TO_CHANNEL[norm_method]
        state: bool = led_states[channel]
        send_rpc_response(client, req_id, state)
        print("RPC status ({} -> {}) -> {}".format(method, channel, state))
        return

    if norm_method in SET_ALL_METHODS:
        if isinstance(params, dict):
            if apply_dict_params(params):
                send_rpc_response(client, req_id, any(led_states.values()))
                publish_led_status(client)
                return
        else:
            enabled = parse_bool(params)
            set_all_leds(enabled)
            send_rpc_response(client, req_id, enabled)
            publish_led_status(client)
            return

    if norm_method in GET_ALL_METHODS:
        any_on: bool = any(led_states.values())
        send_rpc_response(client, req_id, any_on)
        print("RPC status ({}) -> {}".format(method, any_on))
        return

    print("RPC method tidak dikenal:", method, params)


def handle_shared_attributes(client: MQTTClient, msg: bytes) -> None:
    """Handle ThingsBoard shared attribute updates for individual or all LEDs."""
    data: dict = json.loads(msg.decode("utf-8"))
    if isinstance(data, dict) and apply_dict_params(data):
        publish_led_status(client)


def mqtt_callback(topic: bytes, msg: bytes) -> None:
    """Route incoming ThingsBoard MQTT messages."""
    global mqtt_client
    if mqtt_client is None:
        return
    try:
        if topic.startswith(b"v1/devices/me/rpc/request/"):
            handle_rpc(mqtt_client, topic, msg)
        elif topic == b"v1/devices/me/attributes":
            handle_shared_attributes(mqtt_client, msg)
    except Exception as exc:
        print("Error memproses pesan MQTT:", exc)


def connect_thingsboard(host: str, port: int, access_token: str) -> MQTTClient:
    """Connect to ThingsBoard MQTT broker using device Access Token."""
    if not access_token:
        raise ValueError("ACCESS_TOKEN belum diisi di .env.")

    client: MQTTClient = MQTTClient(
        CLIENT_ID,
        host,
        port=port,
        user=access_token,
        password="",
        keepalive=30,
    )
    client.set_callback(mqtt_callback)
    client.connect()
    client.subscribe(b"v1/devices/me/rpc/request/+")
    client.subscribe(b"v1/devices/me/attributes")
    print("Terhubung ke ThingsBoard:", host)
    return client


def main() -> None:
    """Load .env config, maintain Wi-Fi/MQTT connection, and process switch events."""
    global mqtt_client
    env: dict = load_env(ENV_FILE)
    wifi_ssid: str = env.get("WIFI_SSID", "")
    wifi_password: str = env.get("WIFI_PASSWORD", "")
    tb_host: str = env.get("THINGSBOARD_HOST", DEFAULT_THINGSBOARD_HOST) or DEFAULT_THINGSBOARD_HOST
    tb_port: int = int(env.get("THINGSBOARD_PORT", str(DEFAULT_THINGSBOARD_PORT)) or DEFAULT_THINGSBOARD_PORT)
    access_token: str = env.get("ACCESS_TOKEN", "")

    set_all_leds(False)
    last_ping_ms: int = time.ticks_ms()

    try:
        while True:
            try:
                connect_wifi(wifi_ssid, wifi_password)
                if mqtt_client is None:
                    mqtt_client = connect_thingsboard(tb_host, tb_port, access_token)
                    publish_led_status(mqtt_client)
                    last_ping_ms = time.ticks_ms()

                mqtt_client.check_msg()

                now_ms: int = time.ticks_ms()
                if time.ticks_diff(now_ms, last_ping_ms) >= 20000:
                    mqtt_client.ping()
                    last_ping_ms = now_ms

                time.sleep(0.1)
            except (OSError, RuntimeError) as exc:
                print("Koneksi terputus, mencoba ulang dalam 5 detik:", exc)
                mqtt_client = None
                time.sleep(5)
    except KeyboardInterrupt:
        print("Program dihentikan.")
    finally:
        set_all_leds(False)
        if mqtt_client is not None:
            try:
                mqtt_client.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    main()
