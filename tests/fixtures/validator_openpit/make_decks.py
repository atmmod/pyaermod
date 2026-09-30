"""Oracle decks for WP-D2: every rule the validator gains, run through AERMOD v26135."""
import sys
from pathlib import Path

OUT = Path(sys.argv[1])

TAIL = """RE STARTING
{re}
RE FINISHED

ME STARTING
   SURFFILE  AERMET2.SFC
   PROFFILE  AERMET2.PFL
   SURFDATA  14735  1988
   UAIRDATA  14735  1988
   PROFBASE  0.0  METERS
ME FINISHED

OU STARTING
   RECTABLE  ALLAVE  FIRST
OU FINISHED
"""

def deck(name, modelopt, so, re="   DISCCART  1000.0  1000.0", pollut="PM10", title=None):
    txt = f"""CO STARTING
   TITLEONE  {title or name}
   MODELOPT  {modelopt}
   AVERTIME  1 PERIOD
   POLLUTID  {pollut}
   RUNORNOT  RUN
CO FINISHED

SO STARTING
{so}
   SRCGROUP  ALL
SO FINISHED

""" + TAIL.format(re=re)
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "aermod.inp").write_text(txt)

PM = """   PARTDIAM  {s}  1  2.5  5  10  20
   MASSFRAX  {s}  0.2  0.2  0.2  0.2  0.2
   PARTDENS  {s}  2.65  2.65  2.65  2.65  2.65"""

# 1. OPENPIT SRCPARAM limits (soset.f OPARM 3530-3595)
so = "\n".join([
    # QS = 0 -> W320 QS
    "   LOCATION  PQ0  OPENPIT  0.0 0.0 0.0",
    "   SRCPARAM  PQ0  0.0  0.0  100.0 100.0 1.0E6",
    # HS > 200 in a deep pit -> W320 HS (no E322: depth 300 m)
    "   LOCATION  PHS  OPENPIT  5000.0 0.0 0.0",
    "   SRCPARAM  PHS  1.0E-5  210.0  100.0 100.0 3.0E6",
    # XINIT > 2000 -> W320 XINIT (aspect 2100/300 = 7, no W392)
    "   LOCATION  PXL  OPENPIT  10000.0 0.0 0.0",
    "   SRCPARAM  PXL  1.0E-5  0.0  2100.0 300.0 6.3E7",
    # YINIT > 2000 -> W320 YINIT
    "   LOCATION  PYL  OPENPIT  20000.0 0.0 0.0",
    "   SRCPARAM  PYL  1.0E-5  0.0  300.0 2100.0 6.3E7",
    # |ANGLE| > 180 -> W320 ANGLE
    "   LOCATION  PAN  OPENPIT  30000.0 0.0 0.0",
    "   SRCPARAM  PAN  1.0E-5  0.0  100.0 100.0 1.0E6  190.0",
    # aspect ratio 12 -> W392
    "   LOCATION  PAR  OPENPIT  40000.0 0.0 0.0",
    "   SRCPARAM  PAR  1.0E-5  0.0  1200.0 100.0 1.2E7",
    # XINIT = 0 -> W320 XINIT (reset to 1E-5) and W392 (aspect)
    "   LOCATION  PX0  OPENPIT  50000.0 0.0 0.0",
    "   SRCPARAM  PX0  1.0E-5  0.0  0.0 100.0 1.0E6",
])
for s in ("PQ0", "PHS", "PXL", "PYL", "PAN", "PAR", "PX0"):
    so += "\n" + PM.format(s=s)
deck("openpit_limits", "CONC DDEP", so)

# 1b. negative XINIT / HS -> E209 ; HS > Deff -> E322
so = "\n".join([
    "   LOCATION  PNX  OPENPIT  0.0 0.0 0.0",
    "   SRCPARAM  PNX  1.0E-5  0.0  -100.0 100.0 1.0E6",
    "   LOCATION  PNH  OPENPIT  5000.0 0.0 0.0",
    "   SRCPARAM  PNH  1.0E-5  -1.0  100.0 100.0 1.0E6",
    "   LOCATION  PDP  OPENPIT  10000.0 0.0 0.0",
    "   SRCPARAM  PDP  1.0E-5  100.1  100.0 100.0 1.0E6",
    "   LOCATION  PEQ  OPENPIT  20000.0 0.0 0.0",
    "   SRCPARAM  PEQ  1.0E-5  100.0  100.0 100.0 1.0E6",
])
for s in ("PNX", "PNH", "PDP", "PEQ"):
    so += "\n" + PM.format(s=s)
deck("openpit_errors", "CONC DDEP", so)

# 1c. XINIT between 0 and 1e-5 m: OPARM raises it to 1e-5 m (W320) before
# computing Deff, so Deff = 1e-3 / (1e-5 * 100) = 1 m and Hs = 1.5 m is
# E322; the raw 5e-6 m would give Deff = 2 m and no E322. The 1e7:1 aspect
# ratio draws W392.
so = "\n".join([
    "   LOCATION  PSM  OPENPIT  0.0 0.0 0.0",
    "   SRCPARAM  PSM  1.0E-5  1.5  5.0E-6 100.0 1.0E-3",
]) + "\n" + PM.format(s="PSM")
deck("openpit_tiny_dimension", "CONC DDEP", so)

# 2. Method 1 particle arrays (soset.f 1222-1231, INPPDM/INPPHI/INPPDN)
so = "\n".join([
    "   LOCATION  S1  VOLUME  0.0 0.0 0.0",
    "   SRCPARAM  S1  1.0  10.0  5.0  5.0",
    # E335 at 0.001 and 1001 ; 1000 and 0.0011 accepted. (1001, not
    # 1000.5: pyaermod writes PARTDIAM to 4 significant figures, so a
    # read-back 1000.5 is written, and validated, as 1000.)
    "   PARTDIAM  S1  0.001  0.0011  1000.0  1001.0",
    "   MASSFRAX  S1  0.25  0.25  0.25  0.25",
    "   PARTDENS  S1  2.65  2.65  2.65  2.65",
    "   LOCATION  S2  VOLUME  100.0 0.0 0.0",
    "   SRCPARAM  S2  1.0  10.0  5.0  5.0",
    # E332 for 1.1 and -0.1 (sum = 1.0)
    "   PARTDIAM  S2  1  2  3",
    "   MASSFRAX  S2  1.1  -0.1  0.0",
    "   PARTDENS  S2  2.65  2.65  2.65",
    "   LOCATION  S3  VOLUME  200.0 0.0 0.0",
    "   SRCPARAM  S3  1.0  10.0  5.0  5.0",
    # sum 0.98 exactly: no W330
    "   PARTDIAM  S3  1  2",
    "   MASSFRAX  S3  0.49  0.49",
    "   PARTDENS  S3  2.65  2.65",
    "   LOCATION  S4  VOLUME  300.0 0.0 0.0",
    "   SRCPARAM  S4  1.0  10.0  5.0  5.0",
    # sum 0.975: W330
    "   PARTDIAM  S4  1  2",
    "   MASSFRAX  S4  0.475  0.5",
    "   PARTDENS  S4  2.65  2.65",
    "   LOCATION  S5  VOLUME  400.0 0.0 0.0",
    "   SRCPARAM  S5  1.0  10.0  5.0  5.0",
    # sum 1.021: W330
    "   PARTDIAM  S5  1  2",
    "   MASSFRAX  S5  0.521  0.5",
    "   PARTDENS  S5  2.65  2.65",
    "   LOCATION  S6  VOLUME  500.0 0.0 0.0",
    "   SRCPARAM  S6  1.0  10.0  5.0  5.0",
    # density 0.1 -> W334 ; 0.0 -> E334 ; 0.11 fine
    "   PARTDIAM  S6  1  2  3",
    "   MASSFRAX  S6  0.4  0.3  0.3",
    "   PARTDENS  S6  0.1  0.0  0.11",
    "   LOCATION  S7  VOLUME  600.0 0.0 0.0",
    "   SRCPARAM  S7  1.0  10.0  5.0  5.0",
    # mismatched counts -> E240
    "   PARTDIAM  S7  1  2  3",
    "   MASSFRAX  S7  0.5  0.5",
    "   PARTDENS  S7  2.65  2.65  2.65",
])
deck("method1", "CONC DDEP", so)

# 3. receptors inside, on the edge of, and outside the pit (calc1.f 4859-4892)
so = "   LOCATION  PIT  OPENPIT  -300.0 -200.0 0.0\n" \
     "   SRCPARAM  PIT  1.0E-5  0.0  600.0 400.0 2.4E7\n" + PM.format(s="PIT")
re = "\n".join([
    "   DISCCART     0.0     0.0",    # centre: inside
    "   DISCCART   299.0   199.0",    # inside, near NE corner
    "   DISCCART   300.0     0.0",    # on the east edge
    "   DISCCART   301.0     0.0",    # just outside
    "   DISCCART   500.0   500.0",    # outside
    "   DISCCART  -300.0  -200.0",    # SW vertex
])
deck("inpit", "CONC", so, re=re)

# 3b. rotated pit: 30 degrees
so = "   LOCATION  PIT  OPENPIT  0.0 0.0 0.0\n" \
     "   SRCPARAM  PIT  1.0E-5  0.0  600.0 400.0 2.4E7  30.0\n" + PM.format(s="PIT")
re = "\n".join([
    "   DISCCART   400.0   100.0",    # inside the rotated pit
    "   DISCCART   500.0   -200.0",   # inside, near the SE corner
    "   DISCCART   -50.0   300.0",    # outside, west of the NW side
])
deck("inpit_rotated", "CONC", so, re=re)

# 4. DFAULT with FLAT -> W206 (coset.f 1674-1683)
so = "   LOCATION  S1  VOLUME  0.0 0.0 0.0\n   SRCPARAM  S1  1.0  10.0  5.0  5.0"
deck("dfault_flat", "CONC FLAT DFAULT", so, pollut="OTHER")
deck("dfault_flatsrcs", "CONC FLAT ELEV DFAULT", so, pollut="OTHER")
deck("dfault_elev", "CONC ELEV DFAULT", so, pollut="OTHER")

# 5. 25 particle categories on one OPENPIT: no category limit (NPDMAX is
# allocated to the deck's own count)
diam = [0.5 + i for i in range(25)]
so = ("   LOCATION  PIT  OPENPIT  -300.0 -200.0 0.0\n"
      "   SRCPARAM  PIT  1.0E-5  0.0  600.0 400.0 2.4E7\n"
      "   PARTDIAM  PIT  " + "  ".join(f"{d:g}" for d in diam) + "\n"
      "   MASSFRAX  PIT  " + "  ".join(["0.04"] * 25) + "\n"
      "   PARTDENS  PIT  " + "  ".join(["2.65"] * 25))
re = "\n".join(["   DISCCART   500.0   0.0", "   DISCCART  1000.0   0.0", "   DISCCART     0.0 1000.0"])
deck("bins25", "CONC DDEP", so, re=re)
