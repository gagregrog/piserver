# Photoresistor Power Sensor — Setup Guide

The piserver reads a photoresistor (LDR) aimed at the stereo's power LED to detect whether the stereo is on or off. Before sending the input-select IR command, it checks the sensor: if the stereo is off, it sends a power-on IR command first and waits for the stereo to boot, then sends input-select.

---

## Why a comparator is needed

The Raspberry Pi's GPIO pins are digital — they read HIGH or LOW based on voltage thresholds:

- **Guaranteed HIGH**: ≥ 2.31V (0.7 × 3.3V)
- **Guaranteed LOW**: ≤ 0.99V (0.3 × 3.3V)

A plain voltage divider (LDR + fixed resistor) produces an analog voltage that varies with light level. Whether that voltage lands cleanly in the guaranteed zones depends on how dramatically the LDR's resistance changes between lit and dark.

In testing with this stereo's power LED, the LDR measured:

| State | LDR resistance |
|-------|---------------|
| LED on | 40.1 kΩ |
| LED off | 96.7 kΩ |

That's only a 2.4× ratio. Solving the voltage divider equation for R_fixed:

- To guarantee HIGH when on: R_fixed ≥ 93.6 kΩ
- To guarantee LOW when off: R_fixed ≤ 41.4 kΩ

There is no single resistor value that satisfies both. The best achievable split (geometric mean, ~62 kΩ) puts both readings in the gray zone between 0.99V and 2.31V:

| State | V at GPIO (62 kΩ fixed R) |
|-------|--------------------------|
| LED on | 2.00V |
| LED off | 1.29V |

Both are indeterminate by spec. A comparator solves this by making the threshold decision itself and driving a clean 0V or 3.3V to the GPIO — no gray zone.

---

## How a comparator works

An LM393 comparator has two voltage inputs (IN+ and IN−) and one open-collector output:

- If IN+ > IN−: output transistor is **off** → pull-up resistor holds output **HIGH**
- If IN+ < IN−: output transistor is **on**, sinks to GND → output **LOW**

You wire the LDR divider to IN+ and a stable reference voltage (set between your two LDR readings) to IN−. The comparator switches cleanly between rail voltages as the LDR crosses the threshold, regardless of how close the readings are.

---

## Parts

| Part | Value | Notes |
|------|-------|-------|
| LDR | any 5mm photoresistor | GL5528 or similar |
| R1 (LDR divider) | 62 kΩ | Nearest standard to geometric mean of LDR values. 68 kΩ also works. |
| R2, R3 (reference) | 10 kΩ each | Equal values → 1.65V reference, midpoint between 1.29V and 2.00V. |
| R4 (pull-up) | 4.7 kΩ | Output pull-up to 3.3V |
| C1 (bypass) | 100 nF ceramic | VCC decoupling, place close to LM393 |
| Comparator | LM393 | DIP-8, dual comparator — only one half used |


---

## Circuit

Power the entire circuit from **3.3V** so the comparator output is directly safe for the Pi GPIO without any level shifting.

### LDR voltage divider (sense input)

```
3.3V ──[LDR]──┬── V_sense
            [R1 62kΩ]
               │
              GND
```

- LED **on** (LDR ≈ 40 kΩ): V_sense ≈ 2.00V
- LED **off** (LDR ≈ 97 kΩ): V_sense ≈ 1.29V

### Reference voltage divider (threshold)

```
3.3V ──[R2 10kΩ]──┬── V_ref (≈ 1.65V)
               [R3 10kΩ]
                   │
                  GND
```

Sets the switching threshold at 1.65V — midway between the two sense voltages.

### LM393 comparator

```
        ┌──────┐
  OUT1 ─┤1    8├─ VCC ── 3.3V
  IN1− ─┤2    7├─ OUT2   (leave unconnected)
  IN1+ ─┤3    6├─ IN2−   (leave unconnected)
   GND ─┤4    5├─ IN2+   (leave unconnected)
        └──────┘

  IN1+ (pin 3) ── V_sense  (LDR divider output)
  IN1− (pin 2) ── V_ref    (reference divider output)
  VCC  (pin 8) ── 3.3V
  GND  (pin 4) ── GND
  C1 100nF between VCC and GND, placed close to the IC
```

### Output to GPIO

```
3.3V ──[R4 4.7kΩ]──┬── OUT1 (LM393 pin 1)
                   └── GPIO 17 (Pi Pin 11)
                        (open-collector pulls to GND when output fires)
```

### Complete wiring to Pi header

| Signal | Pi Pin | Notes |
|--------|--------|-------|
| 3.3V | Pin 1 | Powers LDR divider, reference divider, LM393 VCC, and pull-up |
| GND | Pin 9 | Common ground |
| GPIO 17 | Pin 11 | Comparator output (via 4.7 kΩ pull-up) |

---

## Full circuit diagram

```
3.3V (Pin 1) ───┬──────────────┬──────────────── VCC (LM393 pin 8)
                │              │                   │
              [LDR]          [R2 10kΩ]          [C1 100nF]
                │              │                   │
                ├─ V_sense    ├─ V_ref             │
              [R1 62kΩ]      [R3 10kΩ]            │
                │              │                   │
GND  (Pin 9) ───┴──────────────┴──────────────── GND (LM393 pin 4)

V_sense ── IN1+ (LM393 pin 3)
V_ref   ── IN1− (LM393 pin 2)

3.3V ──[R4 4.7kΩ]──┬── OUT1 (LM393 pin 1)
                   └── GPIO 17 (Pi Pin 11)
```

---

## Logic

| Stereo state | LDR resistance | V_sense | vs V_ref (1.65V) | Comparator output | GPIO |
|---|---|---|---|---|---|
| ON (LED lit) | ~40 kΩ | ~2.00V | above | transistor off, pull-up active | HIGH |
| OFF (dark) | ~97 kΩ | ~1.29V | below | transistor on, sinks to GND | LOW |

---

## Verification

Once wired, confirm the circuit is reading correctly before enabling it in the server:

1. Run the sensor monitor:
   ```bash
   make ldr
   ```
2. Turn the stereo **on**. Confirm the output reads `ON`.
3. Turn the stereo **off**. Confirm the output reads `OFF`.
4. Toggle a few times and confirm the reading tracks reliably.

---

## LDR placement tips

- The LDR should be aimed directly at the power LED, as close as possible.
- The narrower the angle and the closer the LDR, the more dramatic the resistance swing and the more reliable the reading.
- If the stereo is near a window, ambient light changes throughout the day can shift the LDR reading. Shielding the LDR (a short piece of heat-shrink tubing works well) limits its field of view to the LED only.
- If the LED is very dim or the LDR can't get close, a comparator is essential — a plain voltage divider will not give reliable readings when the resistance swing is small.

---

## Configuration

Once the hardware is in place, enable the sensor in `piserver.json`:

```json
{
  "use_sensor": true,
  "ir": {
    "power": {
      "sirc": {"address": "0x10", "command": "0x2E"},
      "repeat": 3,
      "switch_delay_s": 3.0
    },
    "input": {
      "sirc": {"address": "0x10", "command": "0x12"},
      "repeat": 3,
      "switch_delay_s": 0.5
    }
  }
}
```

- **`use_sensor: true`** — enables the sensor check before sending `input`. Without this the sensor is ignored and the power command is never sent automatically.
- **`switch_delay_s`** on `power` — how long to wait after powering on before sending `input`. Set long enough for the stereo to finish booting (typically 2–4 seconds for a Sony receiver).

If `piserver.json` is absent or `use_sensor` is `false`, IR blasting continues normally — the power command is simply never sent automatically.
