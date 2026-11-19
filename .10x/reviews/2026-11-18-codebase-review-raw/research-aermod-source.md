# AERMOD source research: MODELOPT, NO2 methods, LOW_WIND, ADJ_U*, exit velocity, NO2STACK/NO2RATIO, SRCGROUP ALL

Read-only research. Nothing was edited or built.

## Versions read

| Version | Path | Evidence |
|---|---|---|
| 23132 | `a local copy of the v23132 source` | `modules.f` `DATA VERSN /'23132'/` |
| 24142 | `<repo>/aermod/` (the repo copy) | `modules.f:1472` `DATA VERSN /'24142'/ ! May 21, 2024` |
| 26135 | a local, unmodified copy of EPA's v26135 source | `DATA VERSN /'26135'/ ! May 15, 2026` |
| 22112 | No local source. Documentary evidence only (User's Guide v26135 text). | |


Documents (fetched, text extracted locally with pdftotext):
- AERMOD User's Guide v26135, EPA-454/B-26-001, 07-09-2026, https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/aermod_userguide.pdf (cited "UG §x p.y").
- Model Change Bulletin 19 (v26135), https://gaftp.epa.gov/Air/aqmg/SCRAM/models/preferred/aermod/aermod_mcb19.pdf.
- The SCRAM page lists only v26135 material. MCBs for 22112, 23132 and 24142 are not on the page. They may be inside `aermod_mcbs.zip`, which I did not download (downloads need the user's yes).

Line numbers: 24142 unless stated. 26135 is +36 lines in MODOPT (a BAREDGE branch and shifted code before it). Diffs of the MODOPT routine:
- 23132 vs 24142: differ only in the GRSM branch.
- 24142 vs 26135: differ only by an added BAREDGE branch.

---------------------------------------------------------------------------

## Q1. MODELOPT keywords (coset.f, SUBROUTINE MODOPT)

MODOPT starts at coset.f:1459 (23132, 24142) and coset.f:1495 (26135). Mechanics (24142 lines; 26135 = +36):
- **DFAULT pre-scan** (1586-1611): if DFAULT or DEFAULT is present, it sets DFAULT=T, ELEV=T, BETA=F, L_ALPHA=F, LOW_WIND=F, GRSM=F and L_NonDFAULT=F, and clears several other flags.
- **BETA/ALPHA pre-scan** (1651-1657): `IF (KOPT .EQ. 'BETA' .AND. .NOT.DFAULT)` sets BETA, and ALPHA likewise sets L_ALPHA. Keyword order therefore does not matter. Under DFAULT, L_ALPHA and BETA never become true in this scan.
- **Main loop** (1661-1998). The final `ELSE` is E203 (invalid parameter) at 1998.
- **Field count** (1527-1532): IFC<3 gives E200; IFC>14 gives only W202.
- E204 = "Regulatory DFAULT Conflicts with Non-DFAULT Option" (`modules.f:2120`). It is fatal: ERRHDL sets FATAL for any 'E' (`aermod.f:3860-3861`), and the run stops after setup.
- W206 = "Regulatory DFAULT Overrides Non-DFAULT Option For" (`modules.f:2128`). The option is dropped and the run continues.
- E198 = "Non-DFAULT ALPHA Option Required for use of" (`modules.f:2092`).
- E199 = "Non-DFAULT BETA Option Required" (`modules.f:2096`).

Table. "ok" = accepted with DFAULT and no message. Status is the same in 23132, 24142 and 26135 unless a column says otherwise.

| Keyword | Line (24142) | Status | With DFAULT |
|---|---|---|---|
| DFAULT / DEFAULT | 1589, 1663 | sets the regulatory default | n/a |
| CONC, DEPOS, DDEP, WDEP | 1665-1684 | output types, regulatory | ok |
| ELEV | 1685 | default terrain | ok (forced on by DFAULT) |
| FLAT | 1620, 1642-1646, 1685 | non-default | **W206, dropped** (FLAT stays F; the run is elevated). Not fatal. |
| DRYDPLT, WETDPLT, NODRYDPLT, NOWETDPLT | 1687-1727 | depletion switches. No ALPHA check and no DFAULT check. | ok. E149 only if DRYDPLT with NODRYDPLT (or WETDPLT with NOWETDPLT). |
| ROMBERG | 1702 | no checks | ok (no DFAULT test) |
| AREADPLT | 1705-1712 | non-default | **E204 fatal** |
| NOSTD | 1728-1735 | non-default | **W206, NOSTD=F** |
| NOWARN | 1736 | output control | ok |
| NOCHKD | 1738-1748 | non-default | **W206, NOCHKD=F**. E149 if used with WARNCHKD and not DFAULT. |
| WARNCHKD | 1749-1755 | | ok. E149 if NOCHKD is set. |
| SCREEN | 1756-1765 | non-default | **W206, SCREEN=F** |
| SCIM | 1766-1773 | non-default | **E204 fatal** |
| TOXICS | 1774-1792 | obsolete. W198 always (message says use FASTAREA). | **E204 fatal** |
| HBP | 1794-1805 | ALPHA | E198 without ALPHA. With DFAULT **E198 and E204**. |
| PVMRM | 1806 | regulatory Tier 3 | ok (no checks) |
| OLM | 1808 | regulatory Tier 3 | ok |
| ARM2 | 1829-1834 | regulatory Tier 2. Under DFAULT it fixes ARM2_Min=0.50 and ARM2_Max=0.90 (1831-1833). | ok |
| TTRM | 1810-1816 | ALPHA | E198 without ALPHA. Under DFAULT ALPHA cannot be set, so **E198 fatal**. There is no E204 for TTRM alone. |
| TTRM2 | 1817-1828 | ALPHA. Sets RUNTTRM2 and RUNTTRM. | E198 and **E204** under DFAULT |
| GRSM | 1835-1851 | **23132: BETA required (E199) and DFAULT conflict (E204). 24142 and 26135: no ALPHA/BETA/DFAULT check, branch only sets GRSM=T.** The old checks are commented out with the tag "CMGS D182_Remove_BETA_flag_GRSM_RLINE_COARE_WSP". | 23132: **E199 + E204 fatal**. 24142 and 26135: **ok**. |
| PSDCREDIT | 1852-1861 | ALPHA, and it needs PVMRM (E143, 2054) | E204 under DFAULT. E198 if not ALPHA and not DFAULT. |
| ALPHA | 1863-1873 | | **E204 fatal** with DFAULT |
| BETA | 1875-1885 | | **E204 fatal** with DFAULT |
| FASTAREA | 1887-1899 | non-default | **E204 fatal** |
| FASTALL | 1900-1916 | non-default. Implies FASTAREA and sets L_EFFSIGY. | **E204 fatal** |
| NOURBTRAN | 1917-1929 | non-default | **E204 fatal** |
| VECTORWS | 1932-1935 | no ALPHA check; W116 | ok (W116 only). UG §3.2.2 p.3-6: "can be used with the DFAULT keyword". |
| LOW_WIND | 1938-1947 | ALPHA. With ALPHA: LOW_WIND=T, W136, and `DFAULT = .FALSE.` (1943). | Not usable: L_ALPHA is false, so **E133** ("LOW_WIND Option requires ALPHA option on MODELOPT", `modules.f:1862`). |
| AREAMNDR | 1950-1968 | ALPHA, W134 and E139. The tail `IF (.NOT.DFAULT) W198 ELSE E204` is misplaced code. | **E139** (no ALPHA possible), and **E204** (1967) |
| RLINEFDH | 1978-1983 | ALPHA | **E198 fatal**. DFAULT is not tested, but ALPHA cannot be on. |
| NOMINO3 | 1986-1994 | allowed with DFAULT (UG p.3-6). E621 if no NO2 technique is set **before it in the card**. | ok. **Order-dependent quirk:** if NOMINO3 is written before OLM/PVMRM/GRSM/TTRM, E621 fires, because the flags are set in the same loop (1987-1994). ARM2 is not in the test, so ARM2 with NOMINO3 is always E621. |
| BAREDGE | **26135 only**, coset.f:2033-2036 | sets BAREDGE=T, nothing else. No ALPHA or DFAULT check at MODOPT. In 23132 and 24142 it is E203. UG lists it and says it needs RLINEXT and SBARRIER inputs. RLINEXT itself needs ALPHA. | ok at MODOPT |
| anything else (including LOWWIND1/2/3, ELEVATED, DEFAULT-typo) | 1996-1998 | | **E203 fatal** |

After the loop (2002-2056 in 24142):
- NO2-method conflicts raise E141 at 2008-2049. Pairs: OLM+PVMRM, OLM+ARM2, PVMRM+ARM2, any of them with GRSM, TTRM without TTRM2 with ARM2/OLM/PVMRM, TTRM(2)+GRSM, and TTRM2 with two other methods.
- E143 for PSDCREDIT without PVMRM (2054); E147 for PSDCREDIT with EVONLY (2059).
- `L_NonDFAULT` (24142:2078-2081) is set only when not DFAULT and any of FLAT, FLATSRCS, ARDPLETE, NOSTD, NOCHKD, SCREEN, SCIM, PSDCREDIT, BETA, FASTAREA, FASTALL, LOW_WIND, L_ALPHA, GRSM, L_PBal or no-UrbanTransition holds.
  - OLM, PVMRM, ARM2, TTRM and HBP are not in that list. The commented `C_OLD` list (2062-2070) shows that OLM, PVMRM and ARM2 were removed from it.
  - GRSM is still in the list, but the list applies only when DFAULT is absent.
  - So GRSM with DFAULT does not label the run non-default.

Related ALPHA gates outside MODOPT, 24142:
- `coset.f:924-928` (E198 and E204 for the ARCFTOPT/aircraft case).
- `coset.f:718-751` (E198 for GDSEASON, GASDEPDF, GDLANUSE, GASDEPVD).
- `aermod.f:6940-6990` (E198 for SWPOINT and RLINEXT).
- In 23132, RLINE needed BETA (`aermod.f:6967`, E199) and COARE met needed BETA (`meset.f:1857`, E199). Both were removed in 24142 (commented out, same D182 tag).

User's Guide cross-check:
- UG §3.2.2 pp.3-3 to 3-6 says PVMRM, OLM and ARM2 are "regulatory option, can be used simultaneously with DFAULT".
- It says TTRM, TTRM2, HBP, RLINEFDH, PSDCREDIT, FLAT, NOSTD, NOCHKD, SCREEN, SCIM, FASTAREA, FASTALL, AREADPLT, NOURBTRAN and ALPHA/BETA "cannot be used with the DFAULT keyword".
- It says VECTORWS and NOMINO3 "can be used with the DFAULT keyword".
- UG §3.2.2.3 p.3-9: "AERMOD version 26135 does not include any BETA options."

---------------------------------------------------------------------------

## Q2. NO2 methods with DFAULT

| Method | 23132 | 24142 | 26135 | Deciding lines |
|---|---|---|---|---|
| ARM2 | accepted | accepted | accepted | coset.f:1829-1834 (26135:1865-1870); no ALPHA/BETA/E204 test. Under DFAULT it sets ARM2_Min=0.5 and ARM2_Max=0.9. coset.f:652-660 does the same when ARMRATIO is absent. |
| OLM | accepted | accepted | accepted | coset.f:1808 (26135:1844) |
| PVMRM | accepted | accepted | accepted | coset.f:1806 (26135:1842) |
| GRSM | **refused: E199 (BETA needed) and E204 (DFAULT)** | **accepted with DFAULT, no BETA** | **accepted with DFAULT, no BETA** | 23132 coset.f:1839-1847. 24142 coset.f:1835-1851 (checks commented out). 26135 coset.f:1871-1887. |
| TTRM | refused (E198, ALPHA) | refused (E198) | refused (E198) | coset.f:1810-1816 (26135:1846-1852) |
| TTRM2 | refused (E198 and E204) | refused (E198 and E204) | refused (E198 and E204) | coset.f:1817-1828 (26135:1853-1864) |

- GRSM history (UG §3.2.5 p.3-30): ALPHA in 21112, BETA in 22112, "regulatory screening option beginning in version 24142".
- The code comment at 23132 coset.f:1837 says "GRSM in version 21112 updated from ALPHA to BETA", dated 4/1/2022. That is a loose label; the UG puts the BETA change in 22112.
- **The library's claim that GRSM is BETA in v24142 and "v26135 drops the BETA flag" is wrong.** BETA was dropped in 24142. The dropped flag is in the 24142 source itself.
- With GRSM and DFAULT, `L_NonDFAULT` stays false, so the header says DFAULT.

Other NO2 checks:
- MCB19 enhancement bug-fix 11 (v26135): negative emission with ARM2 now errors. In the source this is `soset.f:1856` (E338, tagged D227) in 26135. In 24142 the E338 check (`soset.f:1754`) covers OLM, PVMRM, GRSM and TTRM only.
- The O3 and NOx keyword gates (`coset.f:300-354`, 24142) accept OZONEVAL/O3VALUES/NO2STACK only with PVMRM, OLM, TTRM or GRSM. With ARM2 they are E600/E142.

---------------------------------------------------------------------------

## Q3. Low wind

**CO LOW_WIND keyword.**
- Dispatch: coset.f:374-386 (24142). A repeat is E135. `ELSE IF (L_ALPHA)` calls LOW_WND; otherwise **E133** (message "LOW_WIND option requires ALPHA option").
- The keyword needs ALPHA only. It does not need MODELOPT LOW_WIND.
- Locations:

| Version | Dispatch | LOW_WND routine |
|---|---|---|
| 23132 | coset.f:374 | coset.f:6775 |
| 24142 | coset.f:374 | coset.f:6779-7014 |
| 26135 | coset.f:379 (L_ALPHA test at 385) | coset.f:7248 |

- LOW_WND is identical in all three versions (diffed).
- Pre-pass `aermod.f:6035-6036` (24142; 26135 at 5652) sets LOW_WIND=T for any CO LOW_WIND card, and `aermod.f:6332-6375` assigns `MODOPS(22)='LOW_WIND'`.

Field count: IFC<=2 is E200; IFC>9 is E202. That allows 7 numbers.

Parameters in order, with defaults assigned in MODOPT (24142 lines) and ranges from LOW_WND (24142 lines):

| # | Parameter | Default | Allowed range | Out of range |
|---|---|---|---|---|
| 1 | SVmin (field 3, required) | 0.2 (coset.f:1539) | 0.01-1.001 (6837) | E380. Warning W111 when in range. |
| 2 | WSmin | 0.2828 (1546) | 0.01-1.001 | E380. Warning W112 when in range. |
| 3 | FRANmax | 1.0 (1557) | 0.0-1.0 | E380. Warning W113 when in range. |
| 4 | SWmin | 0.02 (1568) | 0.0-3.0 | E380. Warning W127 when in range. |
| 5 | BigT (hours) | 24.0 (1575) | 0.5-48.0 | E380. Warning W129 when in range. |
| 6 | FRANmin | 0.0 (1561) | 0.0-1.0 and <= FRANmax | E380 or **E426**. Warning W117. |
| 7 | PBAL (or PBALANCE) | off (L_PBal false) | literal text | any other text is E203. W128 when set. |

Any non-numeric field is E208.
- The UG documents the same parameters, ranges and defaults (UG §3.2.3 pp.3-22 to 3-24). Its range for SVmin and WSmin is "0.01 to 1.0"; the code accepts up to 1.001.
- **Library mismatch:** `ControlPathway.low_wind_option` writes `LOW_WIND LOWWIND3`, which is E208 in AERMOD (non-numeric).

**MODELOPT LOWWIND1/2/3:**
- These no longer exist in any of the three versions. grep for LOWWIND in all `*.f` finds only comments (`coset.f:1550-1554`, `modules.f:143-178`, `iblval.f:602`, `coset.f:2064-2068` "C_OLD").
- Comment at coset.f:1554 (24142): "LowWind2 has been removed as a BETA option" (1/29/2018).
- A deck with `MODELOPT LOWWIND3` falls to the final `ELSE`: **E203** (invalid parameter), fatal, in 23132 (coset.f:1992-1998), 24142 (1996-1998) and 26135 (2037-2040).
- UG §3.2.3 p.3-24: "The LOW_WIND keyword was previously implemented as a BETA option to supplement the former LOWWIND1, LOWWIND2, and LOWWIND3 BETA options. These options have since been removed from AERMOD."

**LOW_WIND with DFAULT:** no. DFAULT cannot coexist with ALPHA (E204 for ALPHA, MODOPT 1863-1873), and the CO card needs ALPHA (E133). MODELOPT LOW_WIND under DFAULT is also E133 (1938-1946).

---------------------------------------------------------------------------

## Q4. ADJ_U*

**How AERMOD learns it** (meset.f, SUBROUTINE MEOPEN):
- It reads the first record of the surface file into BUFFER and `IF (INDEX(BUFFER,'ADJ_U*') .NE. 0)` sets `L_AdjUstar = .TRUE.`, issues W187 ("ADJ_U* Option for Stable Low Winds used in AERMET", `modules.f:2049`) and sets `MODOPS(23)='ADJ_U*'`.
- Lines: meset.f:1815-1821 in 23132 and 24142; 1834-1840 in 26135.
- The comment at coset.f:941-944 (24142) says the non-DFAULT/BETA options of using ADJ_U* met data or MMIF are identified from flags in the surface-file header.

**Default or non-default?**
- ADJ_U* alone is not non-default. W187 is informational, and `L_NonDFAULT` is never set from `L_AdjUstar`.
- It is non-default only when site-specific turbulence data (sigma-A / sigma-W in the profile file) are present.
  - With DFAULT that is a **fatal E401** ("Use of turbulence data with ADJ_U* is NonDFAULT", `modules.f:2754`).
  - It is raised in metext.f SUBROUTINE METEXT at lines 622-648, and again in PFLCNV at 2719-2737.
  - Without DFAULT it is W401, `MODOPS(1)='NonDFAULT'` and W402 (metext.f:2738-2766).
- UG §3.2.3 p.3-24 says the same: regulatory with NWS data or with site data lacking turbulence; non-regulatory with turbulence data.
- Versions 23132, 24142 and 26135 are the same for these lines (26135 meset only shifted).

**Where AERMET takes it:**
- Card: `METHOD STABLEBL ADJ_U*`.
- Keyword tables: `aermet_source_code_24142/mod_main1.f90:158-165`. `items` includes 'STABLEBL' and `actions(7)='ADJ_U*'`.
- Flag set: `mod_pbl.f90:6905-6906`, `if (litems(3) .and. lactions(7)) adjustar=.true.`, inside `pbl_test` (starts at 6047).
- COARE disables it: `mod_pbl.f90:6908-6914`, "ADJUST U* NOT INVOKED".
- Header string: written in `sfc_header` (starts at 12380). `adjustarstr` is set at 12464-12465, and the string is written into the SFC header at 12489-12491.
- Reports: `mod_reports.f90:246-247`.
- I did not read an AERMET 26135 source. The `aermet-26135` output headers under `a local copy of EPA’s v26135 source show the same header layout.

---------------------------------------------------------------------------

## Q5. Stack exit velocity and temperature

**Vs, source types POINT, POINTCAP and POINTHOR** (soset.f, SUBROUTINE PPARM):

| Version | PPARM starts | Vs checks |
|---|---|---|
| 23132 | 2711 | 2782-2795 |
| 24142 | 2713 | 2784-2796 |
| 26135 | 2788 | 2859-2871 |

PPARM is identical in all three (diffed).

Code (24142, lines):
```
2784  IF (AVS(ISDX) .LT. 0.0D0) THEN
2786     CALL ERRHDL(PATH,MODNAM,'W','325',SRCID(ISDX))   ! warning
2788     AVS(ISDX) = 1.0D-5
2789  ELSE IF (AVS(ISDX) .LT. 1.0D-5) THEN
2791     AVS(ISDX) = 1.0D-5                                  ! silent
2792  ELSE IF (AVS(ISDX) .GT. 50.0D0) THEN
2794     CALL ERRHDL(PATH,MODNAM,'W','320',' VS ')
```
- **Vs < 0:** W325, "Negative Exit Velocity (Set=1.0E-5) for SRCID:" (`modules.f:2572`). Vs is set to 1.0E-5 and the run continues. This is a warning, not an error.
- **Vs = 0 (or 0 <= Vs < 1e-5):** no message. Vs is silently set to 1.0E-5.
- **Vs > 50:** W320.
- **Hourly emission file path** (aermod.f, HRQEXT, starts at 2699): lines 2872-2890 repeat it. Vs<0 gives W325 and Vs=1e-5. Vs=0 is silent. Vs>50 is an informational I320.

**Ts** (PPARM 2770-2783):
- Ts = 0: set to -1.0E-5. This is the "ambient release" mode, with no message.
- Ts > 2000: W320.
- 0 < Ts < 200: **E320, fatal**, and RUNERR=.TRUE.
- **Ts < 0 is valid and not touched.** `calc1.f:5967-5969` (SUBROUTINE FLUXES): "Check for Negative Stack Temperature, Used to Indicate Constant TS-TA", then `TS = TA + ABS(TS)`. UG p.3-71 also describes "a negative exit temperature" as TS-TA.
- In the hourly path (`aermod.f:2845-2870`), 0 < Ts < 200 is W320, or fatal E320 if Vs > 200.

**Implication for the validator:**
- Vs < 0 should be a **warning**, matching W325. It is not a fatal error in AERMOD.
- Vs = 0 is silent in AERMOD.
- Ts <= 0 must not be refused. Ts = 0 means ambient, and Ts < 0 means a constant temperature excess (-Ts).
- 0 < Ts < 200 is fatal in AERMOD for POINT sources.
- Other limits: Hs<0 is E209 (soset.f:2761) and Ds<0 is E209; Ds<1e-5 is set to 1e-5.
- Note also `soset.f` PPARM has an unreachable `ELSE IF (AHS > 3000)` after `> 600`.

---------------------------------------------------------------------------

## Q6. NO2STACK / NO2RATIO defaults

- `setup.f:1583` (24142; 23132 same; 26135 at 1596) sets `ANO2_RATIO(:) = -9.0D0` when `PVMRM .OR. OLM .OR. GRSM`. The subroutine is VARINI (starts 1125).
- TTRM: `coset.f:633-641` (26135:645) re-initialises to -9.0 when no NO2STACK was given (ICSTAT(28)==0).
- `coset.f` SUBROUTINE NO2STK (5760-5818) sets every source to NO2STACK (0.0-1.0, E380 outside).
- `soset.f` SUBROUTINE NO2RAT (6666-6770) sets per-source ratios, which override NO2STACK. Out of range is E336.
- The check (`soset.f:1757-1766` in 24142; 1761-1763 in 23132; 1828-1830 in 26135, in SRCQA, starts 957):
  `IF (ANO2_RATIO(I) .LT. 0.0D0) CALL ERRHDL(PATH,MODNAM,'E','336',SRCID(I))` for any source, under `OLM .OR. PVMRM .OR. RUNTTRM .OR. GRSM`. E336 is "NO2RATIO Missing/Invalid for OLM/PVMRM/GRSM. Src:" (`modules.f:2592`).
- The source comment above that check says "no default ratio has been determined for use with OLM, PVMRM or GRSM with the 1-hour NO2 NAAQS".
- **There is no default in-stack ratio in any version read (23132, 24142, 26135).** A run with OLM/PVMRM/GRSM/TTRM and neither NO2STACK nor a per-source NO2RATIO for every source is fatal E336.
- **Was 0.5 ever the default?** No evidence of it. UG §3.2.5.4 p.3-45 says AERMOD "no longer assumes a default in-stack ratio of **0.10**" for OLM and PVMRM (changed per the 2010 NO2 guidance). 0.5 appears in the source only as ARM2's minimum ratio (ARM2_Min=0.50, ARM2_Max=0.90; coset.f:1831-1833, comments at 5869 and 5925). That is not an in-stack ratio.
- UG p.3-46: NO2STACK is optional, but OLM, PVMRM, TTRM/TTRM2 and GRSM "require the user to specify an in-stack NO2/NOx ratio for each source".
- I did not read 22112 or older source, so "never in any version" is shown only for the three read plus the UG statement.

---------------------------------------------------------------------------

## Q7. SRCGROUP ALL and BACKGROUND

- Routine: soset.f SUBROUTINE SOGRP (identical in all three).

| Version | SOGRP starts | ALL branch | Comment line |
|---|---|---|---|
| 23132 | 5775 | 5860 | 5866 |
| 24142 | 5777 | 5862-5895 | 5868 |
| 26135 | 5852 | 5937 | 5943 |

- Comment (24142:5867-5868): "Include BACKGRND concentrations as specified by the user; Note the BACKGRND is NOT automatically included in source group ALL".
- Behaviour when BACKGRND data exist (`L_BACKGRND`):
  - `SRCGROUP ALL NOBACKGROUND` (or `NOBACKGRND`): GRP_BACK=F, and W298 (`modules.f:2481`, "Results reported for source group ALL include ...").
  - `SRCGROUP ALL BACKGROUND` (or `BACKGRND`): GRP_BACK=T, and W298.
  - `SRCGROUP ALL` with nothing after it: GRP_BACK=F, and W298 "NOBACKGROUND".
  - Any other 4th field: no message and GRP_BACK=F.
- Without a BACKGRND keyword: ALL BACKGROUND is **E323** (`modules.f:2564`). Any other extra field on ALL is E203.
- `setup.f:1513` (23132, 24142; 26135 at 1526) initialises `GRP_BACK(:)=.FALSE.`.
- For other groups, BACKGROUND (or BACKGRND) in the source list sets GRP_BACK=T (24142:5911).
- Group warnings (soset.f:1330-1357): W321 when BACKGROUND is given but in no source group (`modules.f:2556`), and W319 for an empty group.
- UG §3.3.6 p.3-117 confirms: "AERMOD will NOT automatically include background concentrations in source group ALL".
- **The prior verifier's report is confirmed**: background is excluded from ALL unless `SRCGROUP ALL BACKGROUND` is written. Omitting the keyword only warns (W298).
- A library writer should emit `ALL BACKGROUND` explicitly when it wants a cumulative total in ALL, and should not rely on a default.

---------------------------------------------------------------------------

## Library side (read-only), disagreements with source

Files: `<repo>/src/pyaermod/regulatory.py`, `validator.py`, `validator_advanced.py`, `pathways.py`.

1. **regulatory.py:208-226 and 231-235** say GRSM is BETA in v23132/v24142 and non-DFAULT, and `EPA_APPENDIX_W_2023.allow_chemistry_methods` is ("OLM","PVMRM"). The note at 222-225 says "v26135 drops the BETA flag for GRSM". Source: in 24142 GRSM is accepted with DFAULT and no BETA (coset.f:1835-1851), and the UG (§3.2.5 p.3-30) says it was promulgated in 24142. Only 23132 refuses it.
2. **regulatory.py:195, 216, 247** allowed chemistry tuples omit **ARM2**, which is accepted with DFAULT in all versions (coset.f:1829-1834) and is a regulatory Tier 2 option. `EPA_APPENDIX_W_2017` also omits ARM2, and OLM/PVMRM are said to be the only DFAULT options (regulatory.py:190). `SCREENING_PROFILE` (247) includes GRSM but not ARM2.
3. **regulatory.py:19, 65-66, 79, 189, 195, 216, 247** (LOWWIND3 and `allowed_low_wind`) and **pathways.py:677, 930-931** (`low_wind_option`, written as `LOW_WIND <value>`): LOWWIND1/2/3 do not exist as MODELOPT keywords (E203). A `LOW_WIND LOWWIND3` card is E208, and the card needs ALPHA (E133), which cannot coexist with DFAULT. A regulatory profile cannot allow any LOW_WIND. `allowed_low_wind` should be empty, and the writer should emit numeric parameters (SVmin, WSmin, FRANmax, SWmin, BigT, FRANmin, PBAL).
4. **regulatory.py:79-86 and validator_advanced.py:254-262** forbid flags `use_lowwind1/2/3`, `beta_options`, `use_nondefault`, `use_area_rural`, `flat_terrain`, `no_stack_tip_downwash`. None of these attributes exists on `ControlPathway` (grep of pathways.py finds none; pathways.py has `alpha`, `beta`, `psd_credit`, `terrain_type`, `low_wind_option`). The `getattr(..., None)` checks therefore never fire. The real flags are `alpha`, `beta`, `psd_credit`, `low_wind_option`, `terrain_type`, `chemistry.method`, `extra_model_options`.
5. **pathways.py:506** `ChemistryOptions.default_no2_ratio = 0.5` (documented at 493) and the writer at pathways.py:967-968 always writes `NO2STACK 0.5000` for OLM/PVMRM/GRSM/TTRM. AERMOD has no default ratio (soset.f:1757-1766 E336), and 0.5 is an invented regulatory value. UG p.3-45 says the pre-2010 default was 0.10. The ratio should be required (or None, with an error), not defaulted. `validator.py:1849-1852` checks only the 0-1 range.
6. **validator.py:937-941** treats `exit_velocity < 0` as an error ("must be >= 0"). AERMOD gives W325 and sets 1e-5 (soset.f:2784-2788). Vs = 0 is silent. This should be a warning for Vs < 0.
7. **validator.py:931-935** refuses `stack_temp <= 0`. AERMOD accepts Ts = 0 (ambient, soset.f:2770-2772) and Ts < 0 (constant TS-TA, calc1.f:5967-5969). The fatal case in AERMOD is 0 < Ts < 200 (E320, soset.f:2776-2782), which the validator does not check. `validator_advanced.py:74-92` is also off in its text ("AERMOD will model as neutral" for Vs = 0, with Ts above ambient; AERMOD sets Vs to 1e-5, so the plume is a weak buoyant plume, not neutral).
8. **validator.py** has no check for DFAULT combined with ALPHA, BETA, TTRM, TTRM2, PSDCREDIT, HBP, AREADPLT, SCIM, FASTAREA, FASTALL, NOURBTRAN, NOSTD, NOCHKD, SCREEN or LOW_WIND (grep for `regulatory_default` finds only lines 286, 623, 2471, with ALPHA-only gates at 622-692, 902, 1587, 2470-2525). `validator.py:277-296` handles only FLAT with DFAULT, and it is right (W206). The writer (`pathways.py:830-836`) emits both DFAULT and ALPHA/BETA together, which AERMOD refuses with E204 (`coset.f:1863-1885`).
9. **regulatory.py:65-66, 189** "permits LOWWIND3 and ADJ_U* only for documented cases"; regulatory.py:198-199 lists ADJ_U* as a BETA option requiring concurrence. ADJ_U* is a regulatory AERMET option (since AERMET 16216, UG p.3-24). AERMOD accepts it with DFAULT unless turbulence data are in the profile file (E401). It is a met-processing property read from the SFC header (meset.f:1815), not a MODELOPT flag, so a MODELOPT-level checker cannot see it.
10. `validator.py:2490-2493` (ARM2 ratios 0.5-0.9 under DFAULT) matches coset.f ARM2_Ratios; I did not verify the routine itself.
11. `pathways.py:146` `NO2STACK_METHODS` includes TTRM and TTRM2 and matches coset.f:343-354 and 5760.
12. SRCGROUP ALL and BACKGROUND (Q7) is not checked in the files I read. I did not search the writer for it.

Not verified: 22112 source; MCBs for 22112, 23132, 24142 (not on the SCRAM page; possibly in `aermod_mcbs.zip`, which needs the user's go-ahead to download); AERMET 26135 source.
