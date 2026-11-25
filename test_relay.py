"""Test switching 2-channel HL-52S V1.0 relays one by one every 1 second."""

from machine import Pin
import time

# HL-52S V1.0 is active-LOW: 0=ON, 1=OFF.
RELAY_ON: int = 0
RELAY_OFF: int = 1
STEP_SECONDS: float = 1.0

RELAYS: tuple = (
    ("Relay 1 (D1/IN1)", 5),
    ("Relay 2 (D2/IN2)", 4),
)


def init_relays(specs: tuple) -> list:
    """Initialize relay pins in the OFF state."""
    relays: list = []
    for label, gpio in specs:
        if not isinstance(gpio, int) or gpio < 0:
            raise ValueError("GPIO tidak valid untuk {}: {}".format(label, gpio))
        pin: Pin = Pin(gpio, Pin.OUT, value=RELAY_OFF)
        relays.append((label, pin))
    return relays


def turn_off_all(relays: list) -> None:
    """Turn off all relay channels."""
    for _, pin in relays:
        pin.value(RELAY_OFF)


def run_test(relays: list, step_seconds: float) -> None:
    """Switch each relay ON for step_seconds, then OFF for step_seconds, one by one."""
    if step_seconds <= 0:
        raise ValueError("step_seconds harus > 0")

    while True:
        for label, pin in relays:
            turn_off_all(relays)
            pin.value(RELAY_ON)
            print(label, "-> ON")
            time.sleep(step_seconds)

            pin.value(RELAY_OFF)
            print(label, "-> OFF")
            time.sleep(step_seconds)


def main() -> None:
    """Initialize relays safely and run sequential 1-second switching loop."""
    relays: list = []
    try:
        relays = init_relays(RELAYS)
        run_test(relays, STEP_SECONDS)
    except KeyboardInterrupt:
        print("Tes relay dihentikan.")
    finally:
        if relays:
            turn_off_all(relays)


if __name__ == "__main__":
    main()
