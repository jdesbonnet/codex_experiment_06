# Experiment Ideas

## Best Picks
1. `LED electro-optical transfer curve`
Measure `I-V`, optical intensity, and spectrum versus current for red/green/blue LEDs. Use `Rigol DP832` for drive, `SDM3064` for spot checks, `C12880MA` for spectrum, and a `photodiode + DSO` for fast optical output. You can extract wavelength shift, FWHM, and efficiency droop.

2. `LED as photodiode`
Use one LED as emitter and another as detector. Measure detector current/voltage versus emitter color and current. This is surprisingly instructive because LEDs are narrow-band detectors and you get a crude spectral selectivity experiment with very simple hardware.

3. `Incandescent bulb dynamics`
Sweep current slowly for static `I-V` and spectrum, then pulse it and watch warm-up/cool-down on the scope through a photodiode. You will see cold resistance, thermal time constant, and color-temperature shift very clearly.

4. `BJT output-characteristic curves`
Generate `I_C-V_CE` families for a few base currents, then extract `beta`, saturation behavior, and approximate Early voltage. This is a very good “first-principles transistor lab” and only needs the PSU, DMM, and a few resistors.

5. `Diode and transistor temperature coefficients`
Hold a diode or `V_BE` junction at constant current and measure voltage while heating it gently. You should get a clean negative tempco in `mV/°C`. That is a useful calibration experiment and good sanity check of your bench accuracy.

## Very Good Optical Experiments
6. `Spectrometer calibration and validation`
Use known sources such as green LED, red LED, blue LED, laser pointers if available, and possibly spectral lines from lamps. Fit a corrected wavelength calibration and quantify residual error. Given the earlier blue/green confusion, this is worth doing properly.

7. `Free-space optical link`
Use one MCU plus transistor to modulate an LED, receive with a photodiode or LED, and view the recovered waveform on the scope. Then push bitrate until the link fails. This gives you emitter bandwidth, detector bandwidth, ambient-light sensitivity, and modulation tradeoffs.

8. `Relative photodiode responsivity`
Illuminate a photodiode with different LEDs at controlled current and distance. Use the spectrometer to characterize source spectra and the DMM/scope to measure photocurrent. That gives you a relative responsivity curve without needing calibrated optical power.

9. `LED heating and spectral drift`
Run an LED at fixed current for minutes and log its spectrum over time. Watch the peak wavelength move and output intensity drift. That is a compact experiment in self-heating and semiconductor bandgap shift.

## Best RF / Mixed-Signal Experiments
10. `Near-field EMI sniffing with HackRF`
Make a small loop probe from wire and map emissions from MCU clocks, LED PWM circuits, switch edges, USB cables, and the DP832. Correlate what you see on the `HackRF` with what you see on the `DSO`.

11. `Power rail noise versus load step`
Use a transistor load switched by an MCU to create load steps on the DP832 output. Watch recovery, overshoot, and noise with the scope. Then compare with DMM readings and with any radiated signature seen on the HackRF.

12. `Optical flicker and PWM artifacts`
Drive LEDs with PWM at different frequencies and duty cycles. Measure the photodiode waveform on the scope and the average/current on the DMM. Then inspect whether the spectrometer’s integrated reading changes with PWM conditions.

## Most Interesting / Slightly Unusual
13. `LED reciprocity matrix`
Take several LED colors and measure every emitter/detector pair. Build a matrix of coupling strength. This is a very compact way to visualize semiconductor bandgap selectivity.

14. `Photodiode dark current and reverse bias`
Measure dark current versus reverse bias and then illuminated current versus bias. If you add a simple transimpedance stage, you can also explore shot noise and bandwidth.

15. `Semiconductor junction capacitance`
Use a fast edge, resistor, and scope to estimate diode or transistor junction capacitance versus reverse bias. It is a nice bridge between device physics and circuit behavior.

## Top 5 For This Bench
1. `LED electro-optical family`
2. `Spectrometer calibration`
3. `Incandescent bulb dynamics`
4. `BJT curves`
5. `HackRF EMI sniffing`

## Additional Ideas From Expanded Instrument Set
16. `Ultrasonic transducer characterization`
Drive the `40 kHz` transducers, map frequency response, ringing, beam width, and distance sensitivity. Use the scope and mic or a receive transducer. This is a very good mixed analog/mechanical experiment.

17. `UV fluorescence spectroscopy`
Illuminate materials with `UV LEDs` and capture emitted spectra with the `C12880MA`. Paper, plastics, phosphors, detergents, and optical brighteners are all useful targets.

18. `Bridge-wire thermal runaway / fusing`
Sweep current into bridge wire and record temperature rise, optical emission, and failure threshold. This needs careful current limiting and shielding, but it is a very strong thermal-electrical experiment.

19. `Thermal camera calibration and emissivity study`
Compare `MLX90640`, `DS18B20`, and the DMM under controlled heating and cooling. Then compare shiny metal, painted surfaces, tape, and LEDs under load to show emissivity effects.

20. `Smoke detector source and sensor study`
Use the microscope, spectrometer, thermal tools, and gamma spectrometer to investigate optical and ionization smoke alarms. This could be very interesting, but needs care and restraint around radioactive parts and high voltage sections.

21. `Gamma spectrometer source discrimination`
Use the `Radiocode` unit with common benign sources and shielding materials to compare count rate and spectral shape. This is a good data-analysis project.

22. `Acoustic impulse / ultrasonic-to-audio aliasing study`
Use the `192 kHz mic` to look at audible and ultrasonic content, ringing, harmonics, and environmental reflections.

23. `LED die inspection`
Use the `USB microscope` to inspect different LED packages, phosphor coatings, damage after overstress, and construction differences by color.

## Higher-Risk Categories
- `high voltage sparky thing`
- `bridge wire`
- `smoke alarm ionization source`
- anything combining `UV`, `HV`, or combustion products`

## Laser Experiments
24. `Spectrometer wavelength calibration`
Use known laser wavelengths such as `405 nm`, `450 nm`, `520/532 nm`, and `650 nm` to fit or verify the wavelength polynomial. This is probably the single most valuable addition.

25. `Spectral resolution measurement`
Use a laser line to estimate the spectrometer instrument response and `FWHM` versus wavelength.

26. `Beam profiling`
Use the `USB microscope`, thermal targets, or a translation fixture to estimate spot size, divergence, and focus.

27. `Free-space optical receiver tests`
Use lasers as transmitters and photodiodes or LEDs as receivers. This gives much cleaner modulation experiments than broad LED emitters.

28. `Scattering and diffusion`
Compare how paper, frosted plastic, tape, smoke, or dust scatter different wavelengths.

29. `Filter characterization`
Measure how colored plastics, sunglasses, microscope slides, or other materials attenuate different laser lines.

30. `Photoelectric response mapping`
Measure photodiode or LED detector sensitivity at several discrete wavelengths.

31. `Fluorescence excitation`
Use `UV` and visible lasers to excite fluorescence and capture the emission spectrum.

## Laser Safety Notes
- no eye-level beams
- beam stop behind target
- avoid specular reflections
- no microscope viewing into an active beam path
- wavelength-appropriate eye protection if alignment becomes non-trivial
