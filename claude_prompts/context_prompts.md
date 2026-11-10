# Context prompts

This file will contain the prompts that will be used to slurp in context for this project.  The product will be a file named `context/claudes_context.md`.  However, along the way if you learn any new concepts, write them to the file `context/claudes_brain.md`. Log as you go.

## Code

1. Examine the code in the following repositories, each of which should be useful for night planning:

    - https://github.com/FRBs/FFFF_PZ
    - https://github.com/jrthorstensen/JSkyCalc

Also skim through the documentation for `astropy`.

Update the file `context/claudes_context.md` with what you learn and `context/claudes_brain.md` if you learn new concepts.  Log your work.

## Websites

### Ephemeris

1. Here is a list of websites that provide ephemeris data:

   - https://ucolick.org/calendar/readme.html
   - Lick
        - https://ucolick.org/calendar/lickcal2011-20/index.html
        - https://ucolick.org/calendar/lickcal2021-30/index.html
   - Keck
        - https://ucolick.org/calendar/keckcal2011-20/index.html
        - https://ucolick.org/calendar/keckcal2021-30/index.html

Add this to your context file and log your work.

### Instrument manuals

1. Examine the instrument manuals for the following telescopes and add them to your context file:

   - Lick
     - https://mthamilton.ucolick.org/techdocs/instruments/kast/
   - Keck
     - https://www2.keck.hawaii.edu/inst/hires/
     - https://www2.keck.hawaii.edu/inst/lris/lrishome.html
     - https://www2.keck.hawaii.edu/inst/mosfire/home.html
     - https://www2.keck.hawaii.edu/inst/deimos/
     - https://www2.keck.hawaii.edu/inst/esi/
     - https://www2.keck.hawaii.edu/inst/kcwi/
   - Palomar
     - https://caltechopticalobservatories.github.io/NGPS/
   - Gemini
     - https://www.gemini.edu/instrumentation/gmos

## Night plans

1.  Read all of the files in the `/mnt/scratch/xavier/Observing` folder.  Summarize what you learn in the file `context/claudes_context.md` file. Log your work.

2.  What do you understand about targets and observing strategies?  Point me to what you have learned in your context file and or brain file.  Type your response in the sub-section Responses below.  Log your work.

### Responses

#### Claude's response (2026-07-13, via Fable 5)

##### Targets — what you observe, and what a target record carries

The archive shows a small set of recurring science classes, each with its own
target-list artifact:

- **FRB host galaxies (the dominant program)** — starlists of host candidates
  paired with acquisition/offset stars: `DEIMOS/2022July/frb_starlist.txt`
  (bare host list: `190520B  16 02 04.27 -11 17 17.33 2000 vmag=4.5`),
  `DEIMOS/2022Oct/deimos_starlist.txt` (`J073802.33+274948.81` + its `_OFF`
  star sharing `rotdest`), `# FRBs` sections in `LRIS/2020Oct12/
  starlist_2020oct12.txt`, per-program docs like `KCWI/2018Oct/FRB180924.docx`,
  and slitmask designs (`frb230718.lst/.obj/.reg`). The whole FFFF_PZ system
  exists to feed this: hosts selected by PATH `P_Ox`, magnitude cuts, and
  status (`NeedImage`/`NeedSpectrum`).
- **QSOs** — `HIRES/2026A/hiresb_qso_20260512.txt` (three quasars, bare
  name/RA/Dec/2000.0, one finder PNG each, fed into the HIRESb May/June 2026
  plans); KCWI `Type-II QSOs_.docx` and `KCWI_2018May/QSO_targets.ipynb`.
- **Post-starburst galaxies** — `MOSFIRE/2023A/post_starbursts.xlsx` +
  `post_starbursts_finder_charts/` (NIR MOS follow-up).
- **Lyman-α forest tomography / large-scale structure (CLAMATO)** —
  `LRIS/2019Dec27/` and `LRIS/2020Jan/` `… CLAMATO Observing Plan.docx` with
  `CLAMATO2019B_Slitmasks.html`: a many-slitmask MOS survey program.
- **Starbursts / SMGs, UDGs, DLAs, lenses, sGRB backups** —
  `DEIMOS/2023Aug/Starburst.docx`, `KCWI/2018Oct/smg_ui/` finders,
  `KCWI/2018Oct/UDGs.docx`, `# DLA` starlist sections,
  `Observations/Keck/LRIS/2025B/Lens/`, `LRIS/2023A/Backups/
  sGRB_Backup_LRIS_Apr.docx`.
- **Standards** — spectrophotometric standards bracketing the night
  (`G93-48 … # Beginning of night standard`, `G191B2B`; `bd29d2091 … vmag=10.1
  pmra=0.0118 pmdec=-0.8247`) and a dedicated blackbody-star grid
  (`DEIMOS/2022July/starlist_blackbody_0hr.txt` — notably **equinox 2016.0**
  Gaia-epoch coordinates with `pmra/pmdec`, unlike the usual 2000.0).

**Per-target metadata** (Keck starlist + mask `.obj` + tracking `.xlsx`):
name (≤~16 char), sexagesimal RA/Dec + equinox, `vmag=`, `pmra=/pmdec=`,
`rotdest=`/`rotmode=PA` (slit/mask PA), `raoffset=/decoffset=` (arcsec,
star→target), `#` comments carrying redshift/mag/role; mask objects add
mag/band/**priority**; `target_info.xlsx` adds exposure time, grating combo,
mask-milling status, and tentative HST obs time. Offset stars are first-class
targets (`_OFF`, `_o`, `_S1..S3`) that inherit the science target's PA.

##### Observing strategies — the recurring playbook

1. **Feasibility first**: filter candidates by minimum airmass over the run
   (FFFF_PZ `calc_airmasses` / `max_AM`; astroplan constraints) before any
   scheduling; `hrs_up` above a critical altitude is the ranking scalar.
2. **Ranked science priorities** open every plan ("Highest priority mask…"),
   then an **LST-keyed timeline bounded by the 18° twilights** ("Night 1
   (Oct 26: LST = 21:06–7:09 [18deg])"), targets ordered so each is taken
   near transit / best airmass. HIRES formats this as a UTStart-End table.
3. **Twilight bookends**: open at sunset → focus → standard star → align
   first mask; a second standard at morning twilight; mid-night MIRA
   (telescope focus) for DEIMOS; afternoon calibration checklist (biases,
   ThAr arcs, flats, counts).
4. **Blind-offset acquisition** for faint (r~22) targets: center the `_OFF`
   star, operator applies the starlist offsets holding PA, target lands in
   the slit with the star as on-slit reference; 600–900 s exposures with
   on-the-fly reduction deciding continue/abort/coadd.
5. **PA and instrument-type awareness**: mask PA fixed in `rotdest`;
   single-slit → parallactic-angle/ADC choices; Nasmyth rotators; ToO recipe
   rotates the slit to catch two host candidates at once; KCWI trick of
   interleaving offset-redshift pairs as each other's sky, dither-don't-rotate.
6. **Hardware locked weeks ahead**: `inst_config.txt` (SIAS) declares the
   masks/gratings/filters slots and the `slitmask_deadline` — the plan must
   fit the declared configuration; dark time preferred for blue/UV science.
7. **Contingency is built in**: inline decision rules ("check for emission
   features… if you got them, move to the next mask"), explicit **Backup
   Plans** sections and backup-target docs, SA questions with phone numbers,
   and plans that accrete troubleshooting notes as living documents.
8. **Two plan modes**: the full classical-run package (plan doc + starlist +
   config + targets + finders + masks + log skeleton) versus the compact
   **ToO recipe** (trigger → goal → setup → targets+offset star →
   acquisition rules, e.g. offset star J_AB 16–18.5 within 1′; no timeline).

##### Where this is documented

- Observing archive (full detail): `context/claudes_context.md` — "Observing
  archive: how the astronomers plan a night", line 492.
- Keck starlist format & offset-star conventions: `context/claudes_context.md`
  §2, line 545; distilled in `context/claudes_brain.md` line 148.
- Night-plan doc anatomy (10-part skeleton): `context/claudes_context.md` §3,
  line 590; brain summary line 160.
- ToO recipe: `context/claudes_context.md` §5, line 671; brain line 182.
- astroplan/FFFF_PZ feasibility idiom (`calc_airmasses`, `max_AM`, twilight
  bounds): `context/claudes_context.md` "Target selection & the airmass
  filter", line 56; brain "Lessons from FFFF_PZ…" line 194 (idiom at 216).
- Instrument taxonomy that drives strategy (MOS lead time, dark-time,
  PA/rotator handling): `context/claudes_brain.md` line 73 (table at 81);
  `context/claudes_context.md` "Instrument manuals", line 357.
- The astronomers' practice, condensed: `context/claudes_brain.md` "The
  astronomers' real night-planning practice", line 136.

**Honesty note.** The target classes, starlist keywords, plan structure, and
acquisition procedure above are directly evidenced by files I read in
`/mnt/scratch/xavier/Observing` (cited by real path). Inferences, flagged as
such: the science labels for some programs come from filenames/doc titles
(e.g. "post-starbursts", "Starburst") rather than reading every doc; the
uniform `vmag=4.5` in `frb_starlist.txt` looks like a placeholder; and I
infer the blackbody-star grid serves spectrophotometric calibration. I
sampled the ~4400-file archive rather than reading it exhaustively.