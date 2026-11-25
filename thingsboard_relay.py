"""ThingsBoard MQTT controller for 2-channel HL-52S V1.0 relay (2 switches, 2 LEDs)."""

import json
import network
import time
from machine import Pin
from umqtt.simple import MQTTClient

# --- KONFIGURASI WIFI & THINGSBOARD ---
WIFI_SSID: str = "ISI_NAMA_WIFI"
WIFI_PASSWORD: str = "ISI_PASSWORD_WIFI"

THINGSBOARD_HOST: str = "thingsboard.cloud"  # atau "demo.thingsboard.io" / IP server
THINGSBOARD_PORT: int = 1883
ACCESS_TOKEN: str = "ISI_ACCESS_TOKEN_DEVICE"
CLIENT_ID: str = "esp8266_hl52s_01"

# --- PEMETAAN PIN HL-52S V1.0 (ACTIVE-LOW: 0=ON, 1=OFF) ---
RELAY_ON: int = 0
RELAY_OFF: int = 1

RELAY_PINS: dict = {
    1: Pin(5, Pin.OUT, value=RELAY_OFF),  # D1 (GPIO5) -> IN1 -> LED 1
    2: Pin(4, Pin.OUT, value=RELAY_OFF),  # D2 (GPIO4) -> IN2 -> LED 2
}

relay_states: dict = {1: False, 2: False}
mqtt_client = None


def parse_bool(value: object) -> bool:
    """Convert RPC/attribute parameter into a strict boolean."""
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


def set_relay(channel: int, enabled: bool) -> None:
    """Update physical HL-52S relay channel (active-LOW) and track state."""
    if channel not in RELAY_PINS:
        raise ValueError("Channel relay tidak dikenal: {}".format(channel))
    pin: Pin = RELAY_PINS[channel]
    pin.value(RELAY_ON if enabled else RELAY_OFF)
    relay_states[channel] = enabled
    print("Relay {} (IN{}) -> {}".format(channel, channel, "ON" if enabled else "OFF"))


def turn_off_all_relays() -> None:
    """Safely turn off both relay channels."""
    for channel in RELAY_PINS:
        set_relay(channel, False)


def connect_wifi(ssid: str, password: str, timeout_s: int = 20) -> None:
    """Connect ESP8266 to Wi-Fi station interface with timeout."""
    if not ssid or ssid == "ISI_NAMA_WIFI":
        raise ValueError("WIFI_SSID belum diisi.")

    wlan: network.WLAN = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return

    print("Menghubungkan ke WiFi {}...".format(ssid))
    wlan.connect(ssid, password)
    deadline: int = time.ticks_add(time.ticks_ms(), timeout_s * 1000)
    while not wlan.isconnected():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise RuntimeError("Timeout koneksi WiFi.")
        time.sleep(0.5)
    print("WiFi terhubung, IP:", wlan.ifconfig()[0])


def publish_telemetry(client: MQTTClient) -> None:
    """Publish LED/relay states to ThingsBoard telemetry for 2 LED widgets."""
    payload: str = json.dumps(
        {
            "led1": relay_states[1],
            "led2": relay_states[2],
            "relay1": relay_states[1],
            "relay2": relay_states[2],
        }
    )
    client.publish(b"v1/devices/me/telemetry", payload.encode("utf-8"))
    print("Telemetry terkirim:", payload)


def extract_request_id(topic: bytes) -> str:
    """Extract RPC request id from v1/devices/me/rpc/request/{id}."""
    topic_str: str = topic.decode("utf-8")
    parts: list = topic_str.split("/")
    return parts[-1] if parts else ""


def send_rpc_response(client: MQTTClient, req_id: str, value: object) -> None:
    """Reply to ThingsBoard two-way RPC request."""
    if not req_id:
        return
    resp_topic: bytes = "v1/devices/me/rpc/response/{}".format(req_id).encode("utf-8")
    client.publish(resp_topic, json.dumps(value).encode("utf-8"))


def handle_rpc(client: MQTTClient, topic: bytes, msg: bytes) -> None:
    """Handle ThingsBoard Server-Side RPC commands for Switch 1 and Switch 2."""
    req_id: str = extract_request_id(topic)
    data: dict = json.loads(msg.decode("utf-8"))
    method: str = str(data.get("method", ""))
    params = data.get("params")

    set_map: dict = {
        "setRelay1": 1,
        "setSwitch1": 1,
        "setLed1": 1,
        "setRelay2": 2,
        "setSwitch2": 2,
        "setLed2": 2,
    }
    get_map: dict = {
        "getRelay1": 1,
        "getSwitch1": 1,
        "getLed1": 1,
        "getRelay2": 2,
        "getSwitch2": 2,
        "getLed2": 2,
    }

    if method in set_map:
        channel: int = set_map[method]
        enabled: bool = parse_bool(params)
        set_relay(channel, enabled)
        send_rpc_response(client, req_id, enabled)
        publish_telemetry(client)
        return

    if method in get_map:
        channel = get_map[method]
        send_rpc_response(client, req_id, relay_states[channel])
        return

    if method == "setValue" and isinstance(params, dict):
        if "pin" in params and "enabled" in params:
            channel = int(params["pin"])
            enabled = parse_bool(params["enabled"])
            set_relay(channel, enabled)
            send_rpc_response(client, req_id, enabled)
            publish_telemetry(client)
            return

    print("RPC method tidak dikenal:", method, params)


def handle_shared_attributes(client: MQTTClient, msg: bytes) -> None:
    """Handle ThingsBoard shared attributes updates if switches use attributes."""
    data: dict = json.loads(msg.decode("utf-8"))
    changed: bool = False
    for key, channel in (("relay1", 1), ("led1", 1), ("relay2", 2), ("led2", 2)):
        if key in data:
            set_relay(channel, parse_bool(data[key]))
            changed = True
    if changed:
        publish_telemetry(client)


def mqtt_callback(topic: bytes, msg: bytes) -> None:
    """Route incoming MQTT messages from ThingsBoard."""
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


def connect_thingsboard() -> MQTTClient:
    """Connect to ThingsBoard MQTT broker and subscribe to RPC & attributes."""
    if not ACCESS_TOKEN or ACCESS_TOKEN == "ISI_ACCESS_TOKEN_DEVICE":
        raise ValueError("ACCESS_TOKEN ThingsBoard belum diisi.")

    client: MQTTClient = MQTTClient(
        CLIENT_ID,
        THINGSBOARD_HOST,
        port=THINGSBOARD_PORT,
        user=ACCESS_TOKEN,
        password="",
        keepalive=30,
    )
    client.set_callback(mqtt_callback)
    client.connect()
    client.subscribe(b"v1/devices/me/rpc/request/+")
    client.subscribe(b"v1/devices/me/attributes")
    print("Terhubung ke ThingsBoard:", THINGSBOARD_HOST)
    return client


def main() -> None:
    """Main loop: maintain WiFi/MQTT connection and process switch RPCs."""
    global mqtt_client
    turn_off_all_relays()
    last_ping_ms: int = time.ticks_ms()

    try:
        while True:
            try:
                connect_wifi(WIFI_SSID, WIFI_PASSWORD)
                if mqtt_client is None:
                    mqtt_client = connect_thingsboard()
                    publish_telemetry(mqtt_client)
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
        turn_off_all_relays()
        if mqtt_client is not None:
            try:
                mqtt_client.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    main()
