# Recorded AERMOD runs for every set of output types

`tests/test_postfile_types.py` reads these files to pin how
`pyaermod.postfile` labels the value columns of a POSTFILE or PLOTFILE
from a run with one, two, three or four output types on MODELOPT. None of
the files in a case directory is hand-edited; `regenerate.sh` writes the
decks and re-records every case.

- **Program:** AERMOD v26135, built from EPA's source archive
  `aermod_source.zip` (top-level directory `aermod_source_v26135`) with
  GNU Fortran 15.2.0 (Homebrew GCC 15.2.0_1).
- **Recorded:** 2026-09-29 (`noheader_*/` and `year_2005/` on
  2026-09-30), on macOS arm64.
- **Meteorology:** `HOUSTON_0228.SFC` and `HOUSTON_0228.PFL` are the header
  line and hours 11 to 14 of 28 February 1996 cut from the `HOUSTON.SFC`
  and `HOUSTON.PFL` that AERMET v24142 wrote for EPA's AERMET example EX04
  (Houston, surface station 12960, upper-air station 3937). The lines are
  copied unchanged; only the other hours of the year are left out.
  `PVD_0101.SFC` and `PVD_0101.PFL`, used only by `year_2005/`, are the
  header line and hours 11 to 14 of 1 January 2005 cut the same way from
  the `PVD_2005_NO1MIN-ASOS_NOADJ.SFC` and `.PFL` of EPA's AERMET v24142
  default test cases (Providence, surface station 14765, upper-air
  station 14684).

## The deck

Every case runs the same deck (see `regenerate.sh`), differing only in the
output types on MODELOPT: one 10 m point source (`STK1`) emitting
particles in three size bins, so that dry and wet deposition are both
non-zero; three discrete receptors downwind; four hours of meteorology;
`AVERTIME 1 PERIOD`. The source is in two source groups, `ALL` and `STK`,
which therefore hold the same values, and each group is written in one
format:

| File | OU keyword | What it is |
|---|---|---|
| `post_1h.pst` | `POSTFILE 1 ALL PLOT` | Text POSTFILE of the 1-hour values, 12 rows |
| `post_1h.bin` | `POSTFILE 1 STK UNFORM` | Binary POSTFILE of the same values, 4 records |
| `high_1h.plt` | `PLOTFILE 1 ALL FIRST` | Text PLOTFILE of the highest 1-hour value per receptor |
| `post_per.pst` | `POSTFILE PERIOD ALL PLOT` | Text POSTFILE of the period values, 3 rows |
| `post_per.bin` | `POSTFILE PERIOD STK UNFORM` | Binary POSTFILE of the period values, 1 record |

AERMOD finishes successfully in every case, with no warnings except
W496 in `year_2005/` (the four Providence hours have no precipitation, so
wet deposition is zero).

## Cases

One directory per non-empty set of CONC, DEPOS, DDEP and WDEP (15), plus
`wdep_ddep_conc_keyword_order/`, whose MODELOPT line reads
`WDEP DDEP CONC`. The directory name gives the MODELOPT keywords in the
order written.

Three more cases each change one thing in the deck:

- `noheader_conc/` and `noheader_conc_ddep/` add `NOHEADER ALL` to the OU
  pathway (CONC, and CONC DDEP). Their 1-hour POSTFILE and PLOTFILE have
  no header at all, so the files begin with a data row rather than `*`
  and nothing names the value columns. The PERIOD POSTFILEs keep their
  header: `PSTANN` in `output.f` writes it without checking `L_NoHeader`,
  while `OUPOST` (`ouset.f`, which writes a 1-hour POSTFILE's header) and
  `PLOTFL` (`output.f`) check it.
- `year_2005/` (CONC DDEP) runs the Providence hours, with the receptors
  moved downwind of their north-westerly winds, so the dates have a year
  below 10.

## What the recordings show

- A row holds one value per output type, always in the order CONC, DEPOS,
  DDEP, WDEP, whatever the keyword order on MODELOPT (`MODOPT` in
  `coset.f` numbers the types in that order; `POSTFL` in `calc2.f` and
  `PSTANN` and `PLOTFL` in `output.f` loop over them in that order).
- The text header names each value column: `AVERAGE CONC`, `TOTAL DEPO`,
  `DRY DEPO`, `WET DEPO` (from `CHIDEP` in `coset.f`), and the FORMAT line
  has NUMTYP+2 wide float fields, for example `6(1X,F13.5)` with four
  types.
- A binary record is `KURDAT, IANHRS, GRPID` followed by NUMREC values of
  the first type, then NUMREC of the second, and so on: a payload of
  16 + 8 x NUMREC x NUMTYP bytes between two 4-byte length markers. Nothing
  in the file names the types, so a reader needs the run's MODELOPT line.
  With three receptors a record is 48, 72, 96 or 120 bytes on disk for one
  to four types, and 12 values can be four types at three receptors or
  three types at four.
- DEPOS is the sum of DDEP and WDEP to the printed precision.
- A PLOTFILE of high values prints one date, `DATE(CONC)`, that of the
  first type's high value, even where another type's high came in a
  different hour (`conc_wdep/`).
- A PLOTFILE writes its date as `I8` (the FORMAT line ends `2X,I8`), a
  POSTFILE as `I8.8`, so for 2005 the PLOTFILE has `5010112` where the
  POSTFILE has `05010112` (`year_2005/`).
- The period POSTFILE has the number of hours (`00000004`) where a 1-hour
  file has the date; a period concentration is the mean of the hourly
  ones and a period deposition their sum.
