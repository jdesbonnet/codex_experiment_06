#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT_NAME = "stm32f103c8_sd_dev_board"
PROJECT_DIR = ROOT / "hardware" / PROJECT_NAME
SCHEMATIC_PATH = PROJECT_DIR / f"{PROJECT_NAME}.kicad_sch"
PROJECT_PATH = PROJECT_DIR / f"{PROJECT_NAME}.kicad_pro"
README_PATH = PROJECT_DIR / "README.md"
TEMPLATE_PRO = Path("/usr/share/kicad/template/Arduino_Micro/Arduino_Micro.kicad_pro")
SYMBOL_ROOT = Path("/usr/share/kicad/symbols")

SCHEMATIC_UUID = str(uuid.uuid4())
ROOT_UUID = str(uuid.uuid4())

SYMBOL_SPECS = [
    ("MCU_ST_STM32F1", "STM32F103C_8-B_Tx"),
    ("Connector", "Micro_SD_Card"),
    ("Connector_Generic", "Conn_01x02"),
    ("Connector_Generic", "Conn_01x03"),
    ("Connector_Generic", "Conn_01x04"),
    ("Connector_Generic", "Conn_01x06"),
    ("Connector_Generic", "Conn_02x06_Odd_Even"),
    ("Device", "Battery_Cell"),
    ("Device", "C_Small"),
    ("Device", "Crystal_GND24"),
    ("Device", "LED"),
    ("Device", "R_Small"),
    ("Switch", "SW_Push"),
    ("power", "+3.3V"),
    ("power", "GND"),
]


def quote(text: str) -> str:
    return json.dumps(text)


def extract_symbol_text(lib_path: Path, symbol_name: str) -> str:
    text = lib_path.read_text(encoding="utf-8")
    needle = f'(symbol {quote(symbol_name)})'
    start = text.find(needle)
    if start < 0:
        needle = f'(symbol {quote(symbol_name)}\n'
        start = text.find(needle)
    if start < 0:
        raise ValueError(f"Could not find symbol {symbol_name} in {lib_path}")
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    raise ValueError(f"Unbalanced symbol definition for {symbol_name}")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "()":
            tokens.append(ch)
            i += 1
            continue
        if ch == '"':
            buf = ['"']
            i += 1
            escape = False
            while i < len(text):
                c = text[i]
                buf.append(c)
                i += 1
                if escape:
                    escape = False
                    continue
                if c == "\\":
                    escape = True
                    continue
                if c == '"':
                    break
            tokens.append("".join(buf))
            continue
        start = i
        while i < len(text) and not text[i].isspace() and text[i] not in "()":
            i += 1
        tokens.append(text[start:i])
    return tokens


def parse_expr(tokens: list[str]):
    if not tokens or tokens.pop(0) != '(':
        raise ValueError("Expected '('")
    out = []
    while tokens:
        tok = tokens.pop(0)
        if tok == ')':
            return out
        if tok == '(':
            tokens.insert(0, tok)
            out.append(parse_expr(tokens))
            continue
        if tok.startswith('"'):
            out.append(json.loads(tok))
        else:
            out.append(tok)
    raise ValueError("Unbalanced expression")


def parse_symbol(symbol_text: str):
    tokens = tokenize(symbol_text)
    return parse_expr(tokens)


def symbol_units(parsed) -> dict[int, dict[str, dict[str, float | str]]]:
    units: dict[int, dict[str, dict[str, float | str]]] = {}
    for child in parsed[2:]:
        if not isinstance(child, list) or len(child) < 2 or child[0] != "symbol":
            continue
        unit_name = child[1]
        pins = {}
        for item in child[2:]:
            if not isinstance(item, list) or not item or item[0] != "pin":
                continue
            number = None
            name = None
            at = None
            for part in item[3:]:
                if not isinstance(part, list) or not part:
                    continue
                if part[0] == "number":
                    number = part[1]
                elif part[0] == "name":
                    name = part[1]
                elif part[0] == "at":
                    at = (float(part[1]), float(part[2]), int(part[3]))
            if number is None or at is None:
                continue
            pins[number] = {"name": name or number, "x": at[0], "y": at[1], "rot": at[2]}
        if not pins:
            continue
        parts = unit_name.rsplit("_", 2)
        unit = int(parts[-1])
        units.setdefault(unit, {}).update(pins)
    return units


def fmt_num(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def project_instance(project_name: str, ref: str, unit: int) -> str:
    return (
        f'\t\t(instances\n'
        f'\t\t\t(project {quote(project_name)}\n'
        f'\t\t\t\t(path {quote("/" + ROOT_UUID)}\n'
        f'\t\t\t\t\t(reference {quote(ref)})\n'
        f'\t\t\t\t\t(unit {unit})\n'
        f'\t\t\t\t)\n'
        f'\t\t\t)\n'
        f'\t\t)\n'
    )


def make_symbol(lib_id: str, ref: str, value: str, footprint: str, at: tuple[float, float, int], unit: int = 1, in_bom: str = "yes") -> str:
    x, y, rot = at
    ref_y = y + 7.62
    val_y = y - 7.62
    uuid_text = str(uuid.uuid4())
    pins = pin_maps[lib_id][unit]
    pin_entries = "".join(
        f'\t\t(pin {quote(number)}\n\t\t\t(uuid {quote(str(uuid.uuid4()))})\n\t\t)\n'
        for number in sorted(pins.keys(), key=lambda n: (int(n) if n.isdigit() else n))
    )
    return (
        f'\t(symbol\n'
        f'\t\t(lib_id {quote(lib_id)})\n'
        f'\t\t(at {fmt_num(x)} {fmt_num(y)} {rot})\n'
        f'\t\t(unit {unit})\n'
        f'\t\t(exclude_from_sim no)\n'
        f'\t\t(in_bom {in_bom})\n'
        f'\t\t(on_board yes)\n'
        f'\t\t(dnp no)\n'
        f'\t\t(uuid {quote(uuid_text)})\n'
        f'\t\t(property {quote("Reference")} {quote(ref)}\n'
        f'\t\t\t(at {fmt_num(x - 7.62)} {fmt_num(ref_y)} 0)\n'
        f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n'
        f'\t\t)\n'
        f'\t\t(property {quote("Value")} {quote(value)}\n'
        f'\t\t\t(at {fmt_num(x + 7.62)} {fmt_num(val_y)} 0)\n'
        f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n'
        f'\t\t)\n'
        f'\t\t(property {quote("Footprint")} {quote(footprint)}\n'
        f'\t\t\t(at {fmt_num(x)} {fmt_num(y)} 0)\n'
        f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(hide yes)\n\t\t\t)\n'
        f'\t\t)\n'
        f'\t\t(property {quote("Datasheet")} {quote("~")}\n'
        f'\t\t\t(at {fmt_num(x)} {fmt_num(y)} 0)\n'
        f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(hide yes)\n\t\t\t)\n'
        f'\t\t)\n'
        f'\t\t(property {quote("Description")} {quote(value)}\n'
        f'\t\t\t(at {fmt_num(x)} {fmt_num(y)} 0)\n'
        f'\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(hide yes)\n\t\t\t)\n'
        f'\t\t)\n'
        f'{pin_entries}'
        f'{project_instance(PROJECT_NAME, ref, unit)}'
        f'\t)\n'
    )


def pin_xy(inst: dict, pin_number: str) -> tuple[float, float, int]:
    pin = pin_maps[inst["lib_id"]][inst["unit"]][pin_number]
    x = inst["at"][0] + float(pin["x"])
    y = inst["at"][1] + float(pin["y"])
    rot = int(pin["rot"])
    return x, y, rot


def make_label(text: str, x: float, y: float, rot: int | None = None) -> str:
    if rot is None:
        rot = 0
    justify = "left bottom" if rot in (0, 90, 270) else "right bottom"
    return (
        f'\t(label {quote(text)}\n'
        f'\t\t(at {fmt_num(x)} {fmt_num(y)} {rot})\n'
        f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify {justify})\n\t\t)\n'
        f'\t\t(uuid {quote(str(uuid.uuid4()))})\n'
        f'\t)\n'
    )


def make_no_connect(x: float, y: float) -> str:
    return f'\t(no_connect\n\t\t(at {fmt_num(x)} {fmt_num(y)})\n\t\t(uuid {quote(str(uuid.uuid4()))})\n\t)\n'


PROJECT_DIR.mkdir(parents=True, exist_ok=True)

symbol_defs: list[str] = []
pin_maps: dict[str, dict[int, dict[str, dict[str, float | str]]]] = {}
for lib, sym in SYMBOL_SPECS:
    lib_path = SYMBOL_ROOT / f"{lib}.kicad_sym"
    symbol_text = extract_symbol_text(lib_path, sym)
    symbol_defs.append(symbol_text)
    pin_maps[f"{lib}:{sym}"] = symbol_units(parse_symbol(symbol_text))

instances: list[dict] = []
power_symbol_counters = {"+3.3V": 1000, "GND": 2000}

def add_instance(lib_id: str, ref: str, value: str, footprint: str, x: float, y: float, rot: int = 0, unit: int = 1, in_bom: str = "yes") -> dict:
    inst = {
        "lib_id": lib_id,
        "ref": ref,
        "value": value,
        "footprint": footprint,
        "at": (x, y, rot),
        "unit": unit,
        "in_bom": in_bom,
    }
    instances.append(inst)
    return inst


def add_power_symbol(net_name: str, x: float, y: float) -> dict:
    if net_name not in power_symbol_counters:
        raise ValueError(f"Unsupported power symbol net {net_name}")
    power_symbol_counters[net_name] += 1
    ref = f"#PWR{power_symbol_counters[net_name]:04d}"
    lib_id = "power:+3.3V" if net_name == "+3.3V" else "power:GND"
    return add_instance(lib_id, ref, net_name, "", x, y, in_bom="no")

U1 = add_instance("MCU_ST_STM32F1:STM32F103C_8-B_Tx", "U1", "STM32F103C8T6", "Package_QFP:LQFP-48_7x7mm_P0.5mm", 140, 105)
J_PWR = add_instance("Connector_Generic:Conn_01x02", "J1", "3V3_IN", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", 25, 35)
J_SWD = add_instance("Connector_Generic:Conn_01x06", "J2", "SWD", "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical", 25, 75)
J_UART = add_instance("Connector_Generic:Conn_01x04", "J3", "USART1", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", 25, 115)
J_GPIO = add_instance("Connector_Generic:Conn_02x06_Odd_Even", "J4", "GPIO", "Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Vertical", 260, 115)
J_SD = add_instance("Connector:Micro_SD_Card", "J5", "microSD", "Connector_Card:microSD_HC_Hirose_DM3AT-SF-PEJM5", 245, 55)
Y1 = add_instance("Device:Crystal_GND24", "Y1", "8MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", 78, 65)
C1 = add_instance("Device:C_Small", "C1", "100n", "Capacitor_SMD:C_0603_1608Metric", 110, 45)
C2 = add_instance("Device:C_Small", "C2", "100n", "Capacitor_SMD:C_0603_1608Metric", 118, 45)
C3 = add_instance("Device:C_Small", "C3", "4.7u", "Capacitor_SMD:C_0603_1608Metric", 126, 45)
C4 = add_instance("Device:C_Small", "C4", "100n", "Capacitor_SMD:C_0603_1608Metric", 134, 45)
C5 = add_instance("Device:C_Small", "C5", "1u", "Capacitor_SMD:C_0603_1608Metric", 142, 45)
C6 = add_instance("Device:C_Small", "C6", "18p", "Capacitor_SMD:C_0603_1608Metric", 64, 55)
C7 = add_instance("Device:C_Small", "C7", "18p", "Capacitor_SMD:C_0603_1608Metric", 64, 75)
C8 = add_instance("Device:C_Small", "C8", "100n", "Capacitor_SMD:C_0603_1608Metric", 215, 35)
BT1 = add_instance("Device:Battery_Cell", "BT1", "CR2032", "Battery:BatteryHolder_Keystone_106_1x20mm", 30, 165)
SW1 = add_instance("Switch:SW_Push", "SW1", "RESET", "Button_Switch_THT:SW_PUSH_6mm_H5mm", 85, 150)
R1 = add_instance("Device:R_Small", "R1", "10k", "Resistor_SMD:R_0603_1608Metric", 70, 150)
R2 = add_instance("Device:R_Small", "R2", "10k", "Resistor_SMD:R_0603_1608Metric", 205, 65)
R3 = add_instance("Device:R_Small", "R3", "100k", "Resistor_SMD:R_0603_1608Metric", 80, 185)
R4 = add_instance("Device:R_Small", "R4", "100k", "Resistor_SMD:R_0603_1608Metric", 80, 200)
R5 = add_instance("Device:R_Small", "R5", "1k", "Resistor_SMD:R_0603_1608Metric", 210, 160)
R6 = add_instance("Device:R_Small", "R6", "1k", "Resistor_SMD:R_0603_1608Metric", 210, 180)
D1 = add_instance("Device:LED", "D1", "PWR", "LED_SMD:LED_0603_1608Metric", 225, 160)
D2 = add_instance("Device:LED", "D2", "USER", "LED_SMD:LED_0603_1608Metric", 225, 180)
J_BOOT0 = add_instance("Connector_Generic:Conn_01x03", "J6", "BOOT0_SEL", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", 95, 185)
J_BOOT1 = add_instance("Connector_Generic:Conn_01x03", "J7", "BOOT1_SEL", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", 95, 200)

labels: list[str] = []
no_connects: list[str] = []


def label_pin(inst: dict, pin: str, net: str, rot: int | None = None):
    x, y, pin_rot = pin_xy(inst, pin)
    labels.append(make_label(net, x, y, pin_rot if rot is None else rot))


def nc_pin(inst: dict, pin: str):
    x, y, _ = pin_xy(inst, pin)
    no_connects.append(make_no_connect(x, y))


def power_pin(inst: dict, pin: str, net_name: str):
    x, y, _ = pin_xy(inst, pin)
    add_power_symbol(net_name, x, y)

# Power entry and flags.
for inst, pin in ((J_PWR, "1"), (U1, "24"), (U1, "36"), (U1, "48"), (U1, "9"), (J_SWD, "1"), (J_UART, "1"), (J_BOOT0, "3"), (J_BOOT1, "3"), (R1, "1"), (R2, "2"), (R5, "1"), (R6, "1"), (J_SD, "4"), (C1, "1"), (C2, "1"), (C3, "1"), (C4, "1"), (C5, "1"), (C8, "1")):
    power_pin(inst, pin, "+3.3V")
for inst, pin in ((J_PWR, "2"), (U1, "23"), (U1, "35"), (U1, "47"), (U1, "8"), (J_SWD, "5"), (J_UART, "2"), (J_BOOT0, "1"), (J_BOOT1, "1"), (SW1, "2"), (R3, "2"), (R4, "2"), (D1, "2"), (J_SD, "6"), (J_SD, "9"), (C1, "2"), (C2, "2"), (C3, "2"), (C4, "2"), (C5, "2"), (C6, "2"), (C7, "2"), (C8, "2"), (BT1, "2"), (Y1, "2"), (Y1, "4")):
    power_pin(inst, pin, "GND")
label_pin(BT1, "1", "VBAT")
label_pin(U1, "1", "VBAT")

# Core nets.
label_pin(U1, "7", "NRST")
label_pin(J_SWD, "4", "NRST")
label_pin(R1, "2", "NRST")
label_pin(SW1, "1", "NRST")

label_pin(U1, "44", "BOOT0")
label_pin(J_BOOT0, "2", "BOOT0")
label_pin(R3, "1", "BOOT0")

label_pin(U1, "20", "BOOT1_PB2")
label_pin(J_BOOT1, "2", "BOOT1_PB2")
label_pin(R4, "1", "BOOT1_PB2")

label_pin(U1, "5", "HSE_IN")
label_pin(U1, "6", "HSE_OUT")
label_pin(Y1, "1", "HSE_IN")
label_pin(Y1, "3", "HSE_OUT")
label_pin(C6, "1", "HSE_IN")
label_pin(C7, "1", "HSE_OUT")

label_pin(U1, "14", "SD_CS")
label_pin(U1, "15", "SD_SCK")
label_pin(U1, "16", "SD_MISO")
label_pin(U1, "17", "SD_MOSI")
label_pin(J_SD, "2", "SD_CS")
label_pin(J_SD, "5", "SD_SCK")
label_pin(J_SD, "7", "SD_MISO")
label_pin(J_SD, "3", "SD_MOSI")
label_pin(R2, "1", "SD_CS")

label_pin(U1, "30", "USART1_TX")
label_pin(U1, "31", "USART1_RX")
label_pin(J_UART, "3", "USART1_TX")
label_pin(J_UART, "4", "USART1_RX")

label_pin(U1, "34", "SWDIO")
label_pin(U1, "37", "SWCLK")
label_pin(U1, "39", "SWO")
label_pin(J_SWD, "2", "SWDIO")
label_pin(J_SWD, "3", "SWCLK")
label_pin(J_SWD, "6", "SWO")

# Selected GPIO breakout subset.
for pin_num, hdr_pin, net in [
    ("10", "1", "PA0"),
    ("11", "2", "PA1"),
    ("12", "3", "PA2"),
    ("13", "4", "PA3"),
    ("18", "5", "PB0"),
    ("19", "6", "PB1"),
    ("21", "7", "PB10"),
    ("22", "8", "PB11"),
    ("25", "9", "PB12"),
    ("26", "10", "PB13"),
    ("27", "11", "PB14"),
    ("28", "12", "PB15"),
]:
    label_pin(U1, pin_num, net)
    label_pin(J_GPIO, hdr_pin, net)

# LEDs.
label_pin(R5, "2", "PWR_LED_A")
label_pin(D1, "1", "PWR_LED_A")
label_pin(R6, "2", "USER_LED_A")
label_pin(D2, "1", "USER_LED_A")
label_pin(D2, "2", "USER_LED_N")
label_pin(U1, "2", "USER_LED_N")

# Unused pins.
for inst, pin in ((J_SD, "1"), (J_SD, "8"), (U1, "3"), (U1, "4"), (U1, "29"), (U1, "32"), (U1, "33"), (U1, "38"), (U1, "40"), (U1, "41"), (U1, "42"), (U1, "43"), (U1, "45"), (U1, "46")):
    nc_pin(inst, pin)

symbol_blocks = [make_symbol(inst["lib_id"], inst["ref"], inst["value"], inst["footprint"], inst["at"], inst["unit"], inst["in_bom"]) for inst in instances]

sch_text = (
    '(kicad_sch\n'
    '\t(version 20250114)\n'
    '\t(generator "eeschema")\n'
    '\t(generator_version "9.0")\n'
    f'\t(uuid {quote(SCHEMATIC_UUID)})\n'
    '\t(paper "A3")\n'
    '\t(lib_symbols\n'
    + ''.join('\t\t' + block.replace('\n', '\n\t\t').rstrip('\t') + '\n' for block in symbol_defs)
    + '\t)\n'
    + ''.join(symbol_blocks)
    + ''.join(labels)
    + ''.join(no_connects)
    + '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n'
    '\t(embedded_fonts no)\n'
    ')\n'
)

sample_project = json.loads(TEMPLATE_PRO.read_text(encoding="utf-8"))
sample_project["meta"]["filename"] = f"{PROJECT_NAME}.kicad_pro"
PROJECT_PATH.write_text(json.dumps(sample_project, indent=2) + "\n", encoding="utf-8")
SCHEMATIC_PATH.write_text(sch_text, encoding="utf-8")
README_PATH.write_text(
    "# STM32F103C8 SD Dev Board\n\n"
    "Initial KiCad 9 schematic for a small STM32F103C8T6 board.\n\n"
    "## Assumptions\n"
    "- Main system power is supplied externally at `3.3V`. No regulator stage is included yet.\n"
    "- `CR2032` holder feeds `VBAT` only. It is not intended to power the whole board.\n"
    "- `microSD` is wired in `SPI` mode.\n"
    "- `USART1` is broken out on a dedicated header.\n"
    "- `SWD` header is a simple 1x6 pin header carrying `3.3V`, `SWDIO`, `SWCLK`, `NRST`, `GND`, `SWO`.\n"
    "\n"
    "## GPIO breakout subset\n"
    "The dedicated GPIO header exports:\n"
    "- `PA0`, `PA1`, `PA2`, `PA3`\n"
    "- `PB0`, `PB1`\n"
    "- `PB10`, `PB11`, `PB12`, `PB13`, `PB14`, `PB15`\n"
    "\n"
    "## Board-specific fixed assignments\n"
    "- `PA4` `SD_CS`\n"
    "- `PA5` `SD_SCK`\n"
    "- `PA6` `SD_MISO`\n"
    "- `PA7` `SD_MOSI`\n"
    "- `PA9` `USART1_TX`\n"
    "- `PA10` `USART1_RX`\n"
    "- `PA13` `SWDIO`\n"
    "- `PA14` `SWCLK`\n"
    "- `PB3` `SWO`\n"
    "- `PC13` user LED, active low\n"
    "- `PD0` and `PD1` `8MHz` crystal\n"
    "\n"
    "## Notes\n"
    "- `BOOT0` and `PB2/BOOT1` each have a 1x3 selector header plus a default pulldown.\n"
    "- The schematic uses stock KiCad 9 symbols and footprints. Footprints are first-pass choices and should be reviewed before layout.\n",
    encoding="utf-8",
)
print(f"Wrote {PROJECT_PATH}")
print(f"Wrote {SCHEMATIC_PATH}")
print(f"Wrote {README_PATH}")
