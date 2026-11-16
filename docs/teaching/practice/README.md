# Practice deck: a small aggregate plant

`practice_quarry.inp` is an AERMOD input file for practicing with the
[browser app](https://atmmod.github.io/pyaermod/app/). Nothing needs to be installed.
The plant is made up and the emission rates are invented, so the results mean nothing
outside this exercise.

The plant emits PM10 from four sources:

| Source | AERMOD type | What it stands for |
|---|---|---|
| `DRYER` | POINT | A 30 m dryer stack, hot and fast exhaust |
| `CRUSHER` | VOLUME | Dust from a crusher building, released at 5 m |
| `PILE` | AREA | An 80 m by 50 m storage pile |
| `ROAD` | LINE | A 400 m haul road |

Two source groups split them: `STACKS` (the dryer) and `FUGITIVE` (the other three).
The receptors are a 2 km by 2 km grid at 100 m spacing and two discrete receptors (a
house at 450, 300 and a school at -600, -350). The meteorology is four days of hourly
data from Albany, NY (1-4 March 1988), one of the app's built-in samples.

## Load it

1. Open the app and click **Import deck...** on the Project step. Pick
   `practice_quarry.inp`.
2. The app says `AERMET2.SFC` and `AERMET2.PFL` are still to upload. Go to the
   Meteorology step and click **Use Albany, NY, 1-4 March 1988** under Sample
   meteorology. That loads both files.
3. Go to **Review & Run**. The checklist should be empty. Click **Run AERMOD**. It takes a few
   seconds.

AERMOD gives one warning, W403 ("Turbulence data is being used w/o ADJ_U* option"). It
comes from the sample met file, which has measured turbulence, and does not affect this
exercise.

## Things to try

Write down the answer to each question before you change anything, then check it.

1. **Where is the maximum?** On the Results step, find the highest 1-hour, 24-hour and
   period values. Which source group causes each one? How far is each from the dryer
   stack at 0, 0?
2. **Stack or fugitive?** The dryer emits more PM10 (2.5 g/s) than the other three
   sources together. Why are its concentrations so much lower? Compare the
   `pm10_period_stacks.plt` and `pm10_period_fugitive.plt` maps.
3. **Taller stack.** Raise the dryer stack from 30 m to 50 m and run again. What happens
   to the `STACKS` maximum? To the `ALL` maximum?
4. **Control the dust.** Watering the haul road can cut its emissions by about 70 %.
   Multiply the `ROAD` emission rate by 0.3 and run again. Which maxima change, and by
   how much?
5. **The neighbors.** Find the concentrations at the house and the school (the discrete
   receptors) in the `.out` file. Which source matters most at each one? Use the wind
   directions in the met data to explain why.
6. **Compare with the standard.** The Results step compares the highest 24-hour value
   with the PM10 NAAQS (150 µg/m³). Why is four days of met data not enough to say
   whether the plant meets it?

Save the project (**Save** on the Project step) before each change, so you can go back.
