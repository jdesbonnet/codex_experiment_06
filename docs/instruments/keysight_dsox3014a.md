# Agilent/Keysight DSO-X 3014A

## Purpose

Digital oscilloscope available over USB or Ethernet for remote control, capture,
and waveform tooling.

## Local Documentation

- `datasheets/Keysight_DSOX3014A/README.md`
- `datasheets/Keysight_DSOX3014A/9018-03427_InfiniiVision_3000_X-Series_User_Guide.pdf`
- `datasheets/Keysight_DSOX3014A/9018-06894_InfiniiVision_3000_X-Series_Programmers_Guide.pdf`

## Linux Access

### USBTMC

The scope enumerates through the kernel `usbtmc` driver as `/dev/usbtmc0`.

Observed identification:

```text
AGILENT TECHNOLOGIES,DSO-X 3014A,MY51450646,02.31.2013040901
```

### udev rule

Repository copy:

- `tools/udev/99-keysight-usbtmc.rules`

Rule contents:

```udev
KERNEL=="usbtmc[0-9]*", SUBSYSTEM=="usbmisc", ATTRS{idVendor}=="0957", ATTRS{idProduct}=="17a8", MODE:="0660", GROUP:="plugdev", TAG+="uaccess"
```

Install on a fresh system:

```sh
sudo cp tools/udev/99-keysight-usbtmc.rules /etc/udev/rules.d/99-keysight-usbtmc.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usbmisc
```

Expected result:

```sh
ls -l /dev/usbtmc0
# crw-rw---- root plugdev ...
```

Verify access:

```sh
printf '*IDN?\n' > /dev/usbtmc0
timeout 2 dd if=/dev/usbtmc0 bs=256 count=1 status=none
```

### Ethernet / LAN

The scope also supports SCPI over Ethernet.

Observed working ports on this unit:

- raw SCPI socket: `5025`
- telnet-style console: `5024`

For this scope, Ethernet proved more reliable than USBTMC for waveform capture.
USBTMC control worked for simple commands such as `*IDN?`, but waveform and
screen-image transfers were flaky with the currently installed scope firmware
`02.31.2013040901`.

Basic raw-socket check:

```sh
python3 - <<'PY'
import socket
with socket.create_connection(("192.168.123.102", 5025), timeout=3.0) as s:
    s.sendall(b"*IDN?\n")
    print(s.recv(4096).decode().strip())
PY
```

## Helper Script

The repository now includes:

- `tools/keysight_scope.py`

Current commands:

- `idn`
- `query`
- `setup-blink`
- `measure`
- `waveform`
- `screenshot`

Example:

```sh
python3 tools/keysight_scope.py --device /dev/usbtmc0 idn
python3 tools/keysight_scope.py --device /dev/usbtmc0 waveform \
  --source CHANnel1 \
  --points-mode RAW \
  --points 1000 \
  --format BYTE \
  --output results/scope_trace.csv
```

## Notes

- The scope is documented for fresh-host USB setup and LAN operation.
- For this unit and firmware, prefer LAN for waveform transfers.
- Verified LAN capture path:
  - `*IDN?` over port `5025`
  - waveform preamble + waveform data for `CHANnel1`
  - exported trace artifacts such as:
    - `results/lpc824_ch1_trace_2026-03-14.csv`
    - `results/lpc824_ch1_trace_2026-03-14.png`
