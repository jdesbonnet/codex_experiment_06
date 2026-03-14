# Siglent SDM3065X-SC

## Purpose

Bench digital multimeter used for current measurements, including sleep/awake current logging.

## Local Documentation

- `datasheets/Siglent_SDM3065X/SDM3065X_DataSheet_E03A.pdf`
- `datasheets/Siglent_SDM3065X/SDM3065X_Remote_Manual_RC06036-E01A.pdf`
- `datasheets/Siglent_SDM3065X/SDM3065X_Usermanual_E02B.pdf`
- `datasheets/Siglent_SDM3065X/SDM_Series_Programming_Guide_EN02A.pdf`

## Linux Access

The meter appears as a `USBTMC` instrument, typically at `/dev/usbtmc0` or `/dev/usbtmc1`.

Recommended `udev` rule:

```udev
SUBSYSTEM=="usbmisc", KERNEL=="usbtmc*", ATTRS{idVendor}=="f4ec", ATTRS{idProduct}=="1208", MODE="0666", TAG+="uaccess"
```

Install on a fresh system:

```sh
sudo tee /etc/udev/rules.d/99-sdm3065x-usbtmc.rules >/dev/null <<'EOF'
SUBSYSTEM=="usbmisc", KERNEL=="usbtmc*", ATTRS{idVendor}=="f4ec", ATTRS{idProduct}=="1208", MODE="0666", TAG+="uaccess"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Repo Tools

- `tools/sdm3065x_current.sh`
- `tools/sdm3065x_event_log.sh`
- `tools/sdm3065x_idn.sh`
- `tools/sdm3065x_usbtmc_list.sh`
- `tools/measure_sleep_wake_current.sh`

## Notes

- Existing repository scripts assume the instrument is reachable through `/dev/usbtmc*`.
- Check `README.md` for the historical sleep-current measurement workflow.
