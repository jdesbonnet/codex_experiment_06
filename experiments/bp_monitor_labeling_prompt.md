# Blood Pressure Monitor Labeling Prompt

Use this prompt for future manual or AI-assisted transcription of these monitor
photos.

## Prompt

You are reading a photograph of a Sanitas blood pressure monitor LCD.

Read only what is visibly present on the LCD. Do not infer hidden digits. If a
field is not legible, return an empty string for that field.

Return exactly one JSON object with these fields:

```json
{
  "filename": "",
  "systolic_mmhg": "",
  "diastolic_mmhg": "",
  "pulse_bpm": "",
  "lcd_time": "",
  "lcd_day": "",
  "lcd_month": "",
  "user_number": "",
  "blue_backlight_on": ""
}
```

## Field Definitions

- `filename`
  - image filename only
- `systolic_mmhg`
  - the large top numeric reading next to `SYS mmHg`
- `diastolic_mmhg`
  - the large middle numeric reading next to `DIA mmHg`
- `pulse_bpm`
  - the smaller bottom-right numeric reading next to `PUL./min`
- `lcd_time`
  - the time shown in the top-left corner of the LCD, formatted as `H:MM` or
    `HH:MM`
- `lcd_day`
  - the day number shown on the second line in the top-left area
- `lcd_month`
  - the month number shown on the second line in the top-left area
- `user_number`
  - the number shown inside the person icon
- `blue_backlight_on`
  - `true` if the LCD background is visibly blue-lit
  - `false` if the LCD is reflective gray/green without the blue backlight

## Interpretation Rules

- Rotate mentally if needed so the display is upright before reading.
- Read the display itself, not the camera filename or EXIF timestamp.
- If only part of the time is visible, leave `lcd_time` empty.
- If the date line is visible as `DD/MM`, split it into:
  - `lcd_day`
  - `lcd_month`
- If the user icon is visible but the number is not readable, leave
  `user_number` empty.
- Use digits only for numeric fields.
- Use lowercase JSON booleans for `blue_backlight_on`.

## Example

```json
{
  "filename": "20260324_200920.jpg",
  "systolic_mmhg": "127",
  "diastolic_mmhg": "80",
  "pulse_bpm": "69",
  "lcd_time": "2:41",
  "lcd_day": "30",
  "lcd_month": "1",
  "user_number": "1",
  "blue_backlight_on": false
}
```

## Notes

- `experiments/bp_monitor_ground_truth.csv` contains the current benchmark
  labels.
- Blank fields in that CSV mean the field was not confidently readable from the
  available image.
