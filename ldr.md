# Photoresistor Power Sensor — Setup Guide

The piserver reads a photoresistor (LDR) aimed at the stereo's power LED to detect whether the stereo is on or off. Before sending the input-select IR command, it checks the sensor: if the stereo is off, it sends a power-on IR command first and waits for the stereo to boot, then sends input-select.

---

## Why a comparator is needed

The Raspberry Pi's GPIO pins are digital — they read HIGH or LOW based on voltage thresholds:

- **Guaranteed HIGH**: ≥ 2.31V (0.7 × 3.3V)
- **Guaranteed LOW**: ≤ 0.99V (0.3 × 3.3V)

A plain voltage divider (LDR + fixed resistor) produces an analog voltage that varies with light level. Whether that voltage lands cleanly in the guaranteed zones depends on how dramatically the LDR's resistance changes between lit and dark.

In testing with this stereo's power LED, the LDR measured:

| State   | LDR resistance |
| ------- | -------------- |
| LED on  | 40.1 kΩ        |
| LED off | 96.7 kΩ        |

That's only a 2.4× ratio. Solving the voltage divider equation for R_fixed:

- To guarantee HIGH when on: R_fixed ≥ 93.6 kΩ
- To guarantee LOW when off: R_fixed ≤ 41.4 kΩ

There is no single resistor value that satisfies both. The best achievable split (geometric mean, ~62 kΩ) puts both readings in the gray zone between 0.99V and 2.31V:

| State   | V at GPIO (62 kΩ fixed R) |
| ------- | ------------------------- |
| LED on  | 2.00V                     |
| LED off | 1.29V                     |

Both are indeterminate by spec. A comparator solves this by making the threshold decision itself and driving a clean 0V or 3.3V to the GPIO — no gray zone.

---

## How a comparator works

An LM393 comparator has two voltage inputs (IN+ and IN−) and one open-collector output:

- If IN+ > IN−: output transistor is **off** → pull-up resistor holds output **HIGH**
- If IN+ < IN−: output transistor is **on**, sinks to GND → output **LOW**

You wire the LDR divider to IN+ and a reference voltage to IN−. The comparator switches cleanly between rail voltages as the LDR crosses the threshold, regardless of how close the readings are.

---

## Parts

| Part             | Value                          | Notes                                                                                            |
| ---------------- | ------------------------------ | ------------------------------------------------------------------------------------------------ |
| LDR              | any 5mm photoresistor          | GL5528 or similar                                                                                |
| R1 (LDR divider) | 62 kΩ                          | Nearest standard to geometric mean of LDR values. 68 kΩ also works.                              |
| VR1 (reference)  | 10 kΩ potentiometer or trimmer | Adjustable threshold voltage (0–3.3V). Allows calibration after installation.                    |
| R4 (pull-up)     | 4.7 kΩ                         | Output pull-up to 3.3V                                                                           |
| R5 (hysteresis)  | 1 MΩ                           | Positive feedback from comparator output to input. Prevents chatter and improves noise immunity. |
| C1 (bypass)      | 100 nF ceramic                 | VCC decoupling, place close to LM393                                                             |
| Comparator       | LM393                          | DIP-8, dual comparator — only one half used                                                      |

---

## Circuit

Power the entire circuit from **3.3V** so the comparator output is directly safe for the Pi GPIO without any level shifting.

### LDR voltage divider (sense input)

```text
3.3V ──[LDR]──┬── V_sense
            [R1 62kΩ]
               │
              GND
```

Measured values:

- LED **on** (LDR ≈ 40 kΩ): V_sense ≈ 2.00V
- LED **off** (LDR ≈ 97 kΩ): V_sense ≈ 1.29V

### Adjustable reference voltage (threshold)

A comparator requires a reference voltage to decide whether the stereo LED is considered ON or OFF.

The original design used two fixed 10 kΩ resistors:

```text
3.3V ──[10kΩ]──┬── V_ref (1.65V)
             [10kΩ]
                 │
                GND
```

This produces a stable 1.65V reference, which sits midway between the measured sensor voltages:

| State   | V_sense |
| ------- | ------- |
| LED on  | ~2.00V  |
| LED off | ~1.29V  |

While this works well in theory, real-world installations vary:

- LDR positioning may not be perfect
- Ambient lighting may differ
- Different stereo LEDs can have different brightness levels
- Sensor alignment may change over time

To allow calibration after installation, the fixed divider was replaced with a 10 kΩ potentiometer:

```text
3.3V ─────────────┐
                  │
              [10kΩ pot]
                  │
                  ├── V_ref
                  │
GND ──────────────┘
```

Connections:

- Pot leg 1 → 3.3V
- Pot leg 3 → GND
- Pot wiper → LM393 IN1− (pin 2)

This allows V_ref to be adjusted anywhere between 0V and 3.3V.

During installation, adjust the potentiometer until the sensor reliably reports ON when the stereo LED is lit and OFF when it is dark.

### LM393 comparator

```text
        ┌──────┐
  OUT1 ─┤1    8├─ VCC ── 3.3V
  IN1− ─┤2    7├─ OUT2   (leave unconnected)
  IN1+ ─┤3    6├─ IN2−   (leave unconnected)
   GND ─┤4    5├─ IN2+   (leave unconnected)
        └──────┘

  IN1+ (pin 3) ── V_sense
  IN1− (pin 2) ── V_ref (potentiometer wiper)

  R5 1MΩ:
  OUT1 (pin 1) ──[1MΩ]── IN1+ (pin 3)

  VCC  (pin 8) ── 3.3V
  GND  (pin 4) ── GND

  C1 100nF between VCC and GND
```

### Hysteresis (noise and flicker prevention)

Comparators can become unstable when the input voltage sits very close to the switching threshold.

For example, if V_ref is adjusted to a value near the measured LDR voltage, small fluctuations caused by:

- ambient light changes
- electrical noise
- sensor movement
- stereo LED brightness variation

can cause the output to rapidly switch between HIGH and LOW.

To prevent this, a 1 MΩ feedback resistor is added:

```text
LM393 pin 1 (OUT1)
          │
        [1MΩ]
          │
LM393 pin 3 (IN1+ / V_sense)
```

This creates **positive feedback**, also known as **hysteresis**.

When the output is HIGH, the feedback resistor slightly boosts V_sense.

When the output is LOW, the feedback resistor slightly lowers V_sense.

As a result, the comparator develops two different switching thresholds:

```text
LOW → HIGH threshold  = slightly above V_ref
HIGH → LOW threshold  = slightly below V_ref
```

The exact values depend on component tolerances and potentiometer position.

The effect is similar to a thermostat:

- heater turns ON below one temperature
- heater turns OFF above a different temperature

This prevents rapid toggling when the signal hovers near the threshold and makes the detector more tolerant of ambient light changes and electrical noise.

### Output to GPIO

```text
3.3V ──[R4 4.7kΩ]──┬── OUT1 (LM393 pin 1)
                   └── GPIO 17 (Pi Pin 11)
                        (open-collector pulls to GND when output fires)
```

### Complete wiring to Pi header

| Signal  | Pi Pin | Notes                                                     |
| ------- | ------ | --------------------------------------------------------- |
| 3.3V    | Pin 1  | Powers LDR divider, potentiometer, LM393 VCC, and pull-up |
| GND     | Pin 9  | Common ground                                             |
| GPIO 17 | Pin 11 | Comparator output (via 4.7 kΩ pull-up)                    |

---

## Full circuit diagram

```text
3.3V (Pin 1) ───┬─────────────────────────────── VCC (LM393 pin 8)
                │                                  │
              [LDR]                            [C1 100nF]
                │                                  │
                ├── V_sense ────────────────┐      │
              [R1 62kΩ]                     │      │
                │                           │      │
GND (Pin 9) ────┴───────────────────────────┴──────┴── GND (LM393 pin 4)


3.3V ─────────────┐
                  │
              [VR1 10kΩ]
                  │
                  ├── V_ref ───────────── IN1− (pin 2)
                  │
GND ──────────────┘


V_sense ───────────────────────── IN1+ (pin 3)

                           LM393
                      ┌─────────────┐
                      │             │
                      │    OUT1     │
                      │   (pin 1)   │
                      └──────┬──────┘
                             │
             3.3V ──[4.7kΩ]──┤
                             │
                             ├──────── GPIO17 (Pin 11)
                             │
                           [1MΩ]
                             │
                             └──────── V_sense
```

---

## Logic

| Stereo state | LDR resistance | V_sense | vs V_ref        | Comparator output              | GPIO |
| ------------ | -------------- | ------- | --------------- | ------------------------------ | ---- |
| ON (LED lit) | ~40 kΩ         | ~2.00V  | above threshold | transistor off, pull-up active | HIGH |
| OFF (dark)   | ~97 kΩ         | ~1.29V  | below threshold | transistor on, sinks to GND    | LOW  |

---

## Verification

Once wired, confirm the circuit is reading correctly before enabling it in the server:

1. Run the sensor monitor:

   ```bash
   make ldr
   ```

2. Turn the stereo **off**.
3. Adjust the potentiometer until the sensor reports `OFF`.
4. Turn the stereo **on**.
5. Confirm the sensor reports `ON`.
6. Toggle several times and fine-tune the potentiometer if needed.
7. Verify the reading remains stable and does not flicker when ambient room lighting changes.

---

## LDR placement tips

- The LDR should be aimed directly at the power LED, as close as possible.
- The narrower the angle and the closer the LDR, the more dramatic the resistance swing and the more reliable the reading.
- A short piece of heat-shrink tubing over the LDR can dramatically improve reliability by limiting its field of view.
- If the stereo is near a window or bright room lighting, shielding the LDR becomes even more important.
- The added hysteresis resistor helps reject small ambient-light fluctuations, but proper sensor placement remains the most important factor.

---

## Configuration

Once the hardware is in place, enable the sensor in `piserver.json`:

```json
{
  "use_sensor": true,
  "ir": {
    "power": {
      "sirc": { "address": "0x10", "command": "0x2E" },
      "repeat": 3,
      "switch_delay_s": 3.0
    },
    "input": {
      "sirc": { "address": "0x10", "command": "0x12" },
      "repeat": 3,
      "switch_delay_s": 0.5
    }
  }
}
```

- **`use_sensor: true`** — enables the sensor check before sending `input`. Without this the sensor is ignored and the power command is never sent automatically.
- **`switch_delay_s`** on `power` — how long to wait after powering on before sending `input`. Set long enough for the stereo to finish booting (typically 2–4 seconds for a Sony receiver).

If `piserver.json` is absent or `use_sensor` is `false`, IR blasting continues normally — the power command is simply never sent automatically.
