import mido
import fluidsynth
import pyautogui as pgui
import threading
pgui.PAUSE = 0

import time

import config

fs = fluidsynth.Synth()
fs.start()

sfid = fs.sfload(config.SF_PATH)
for ch in range(16):
    fs.program_select(ch, sfid, 0, 0)

def is_black_key(note: int) -> bool:
    return note % 12 in {1, 3, 6, 8, 10}


def get_ports():
    print("Available MIDI input ports:")

    for name in mido.get_input_names():
        print(" -", name)

def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3

def start_mouse_move(dx, dy, duration=0.15):
    global mouse_anim
    with mouse_lock:
        mouse_anim = {
            "dx": dx,
            "dy": dy,
            "start": time.time(),
            "duration": duration,
            "last_x": 0,
            "last_y": 0,
        }

mouse_anim = None
mouse_lock = threading.Lock()
running = True

def mouse_worker():
    global mouse_anim

    FPS = 60
    FRAME_TIME = 1 / FPS

    while running:
        with mouse_lock:
            anim = mouse_anim

        if anim is not None:
            now = time.time()
            t = (now - anim["start"]) / anim["duration"]

            if t >= 1:
                dx = anim["dx"] - anim["last_x"]
                dy = anim["dy"] - anim["last_y"]
                pgui.moveRel(dx, dy)

                with mouse_lock:
                    mouse_anim = None
            else:
                eased = ease_out_cubic(t)
                x = anim["dx"] * eased
                y = anim["dy"] * eased

                pgui.moveRel(x - anim["last_x"], y - anim["last_y"])

                anim["last_x"] = x
                anim["last_y"] = y

        time.sleep(FRAME_TIME)

def echo():
    with mido.open_input(config.PORT_NAME) as inport:
        active_notes = set()

        for msg in inport:
            if msg.type == "note_on" and msg.velocity > 0:
                active_notes.add(msg.note)
                fs.noteon(0, msg.note, msg.velocity)
            elif msg.type in ["note_off", "note_on"] and msg.velocity == 0:
                active_notes.discard(msg.note)
                fs.noteoff(0, msg.note)

            if len(active_notes) > 0:
                print(active_notes)


def production():
    threading.Thread(target=mouse_worker, daemon=True).start()

    with mido.open_input(config.PORT_NAME) as inport:
        active_notes = set()
        pressed = set()

        mouse_last_note = None
        mouse_last_time = 0

        for msg in inport:
            now = time.time()

            if msg.type == "note_on" and msg.velocity > 0:
                active_notes.add(msg.note)
                fs.noteon(0, msg.note, msg.velocity)

            elif msg.type in ("note_off", "note_on") and msg.velocity == 0:
                active_notes.discard(msg.note)
                fs.noteoff(0, msg.note)

            keys_should_be_down = set()
            chord_notes_active = set()

            for chord_group, key in config.chords.items():
                for chord in chord_group:
                    if all(n in active_notes for n in chord):
                        keys_should_be_down.add(key)
                        chord_notes_active.update(chord)
                        break

            for key in keys_should_be_down:
                if key not in pressed:
                    if key == "m:left":
                        pgui.mouseDown(button="primary")
                    elif key == "m:right":
                        pgui.mouseDown(button="secondary")
                    else:
                        pgui.keyDown(key)

                    pressed.add(key)
                    print(f"Down:{key}")

            for key in pressed.copy():
                if key not in keys_should_be_down:
                    if key == "m:left":
                        pgui.mouseUp(button="primary")
                    elif key == "m:right":
                        pgui.mouseUp(button="secondary")
                    else:
                        pgui.keyUp(key)

                    pressed.remove(key)
                    print(f"Up:{key}")

            if (
                msg.type == "note_on"
                and msg.velocity > 0
                and msg.note >= config.MOUSE_CUTOFF
                and msg.note not in chord_notes_active
            ):
                if mouse_last_note is not None and (now - mouse_last_time) > config.MOUSE_RESET_TIME_SECONDS:
                    mouse_last_note = None

                if mouse_last_note is not None:
                    delta = msg.note - mouse_last_note

                    if is_black_key(msg.note):
                        start_mouse_move(0, -delta * config.MOUSE_MOVE_MULTIPLIER)
                    else:
                        start_mouse_move(delta * config.MOUSE_MOVE_MULTIPLIER, 0)

                mouse_last_note = msg.note
                mouse_last_time = now

if __name__ == "__main__":
    try:
        if config.MODE == 0:
            production()
        if config.MODE == 1:
            echo()
        if config.MODE == 2:
            get_ports()
    except KeyboardInterrupt:
        print("===============\nExiting")
        running = False
