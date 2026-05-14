import subprocess


def gentle_beep():
    try:
        subprocess.run(
            ["osascript", "-e", "beep 1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception:
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass