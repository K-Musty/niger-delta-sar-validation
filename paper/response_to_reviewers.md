# Response to reviewers — paper V2

Point-by-point response to the 30 review comments. New analyses are in
`analysis/20_reviewer_response.py` (spatial nulls, equivalence, power,
overdispersion, truncation robustness) and `analysis/21_injection_sweep.py`
(amplitude sweep). Full outputs are in `data/output/reviewer_response.json` and
`data/output/injection_sweep.csv`. All three DOIs flagged by the reviewer
resolve to real papers (verified via DOI resolution and publisher records).

---

## A. Logical structure

### A1. What is the temporal signal, if not a spill signal? [Blocker]

**Reviewer concern.** The paper claims a real temporal signal (1.62×, p < 0.001)
and simultaneously that clusters do not sit near the coordinate. If both are
true, the temporal signal is unexplained; the terrestrial stratum's highest IRR
(2.45) suggests seasonal confounding.

**Response.** We accept the criticism and have rewritten the claim. Two new
results sharpen it. First, the temporal effect is not significant once
the data's overdispersion is modeled (see B9): the Poisson GLMM gives p < 0.001,
but the GEE with sandwich standard errors gives p = 0.057 and a negative-binomial
model gives p = 0.17. Second, we now state the attribution explicitly: the largest
cluster-rate ratio (2.45) sits in terrestrial habitat, where a marine slick
cannot form, so the temporal signal is at least partly, and likely mostly,
environmental change correlated with incident dates rather than oil. The
abstract, Results (§4.3, §4.5), Discussion, and Conclusion no longer present the
temporal signal as "real" or "usable" without qualification. We also ran the
decomposition the reviewer requested in the form of the habitat stratification
(Table 2), which shows the effect is largest where it cannot be oil.

### A2. If NOSDRA coordinates are useless for localization, why study them? [Blocker]

**Reviewer concern.** Distance-to-nearest-cluster is meaningless without a
random-point null.

**Response.** We added the random-point null. For each of the 32 incidents with a
post-incident cluster, we drew 500 uniform points in the 5 × 5 km AOI and
measured the distance to the nearest detected cluster. The reported coordinate is
1,438 m from the nearest cluster on average, which falls at the 43rd percentile
of the null distribution (median 1,674 m, 5th-95th percentile 270-4,411 m). The
coordinate is therefore within the range expected for a random point, and we do not
interpret it as carrying a usable spatial signal. It is reported in §3.7 and
§4.3. We note this null is not spatially matched (see F24, and the reviewer's
later comment), so we do not overstate the comparison.

### A3. Expected nearest-distance under complete spatial randomness. [Blocker]

**Reviewer concern.** Without an expected nearest-distance under a matched
spatial null, "1,972 m" has no reference point.

**Response.** We added two references. The analytic CSR expectation for an
incident with k clusters in the 25 km² AOI is
`sqrt(ln 2 / (π k / 25))` km, which gives a median of about 1,356 m across the
sample. The simulation-based random-point null gives 1,674 m. The observed
1,438 m (coordinate-to-nearest) sits between them. This is the 20-line
simulation the reviewer described, now in `analysis/20_reviewer_response.py` and
reported in §3.7 and §4.3.

### A4. The 0/63 visual inspection result is missing. [Blocker]

**Reviewer concern.** The brief and progress updates emphasized "0 visible spill
signatures across 63 incidents"; the v2 draft dropped it.

**Response.** Reinstated as §4.6. The single annotator's verdicts were 27
no-signal, 22 land-only, and 18 unclear across the 63 inspectable incidents; none
was judged a coherent spill signature. We state the single-annotator limitation
explicitly and frame the result as suggestive, consistent with the automated
distance result, and not the paper's primary evidence.

### A5. The synthetic injection tests a Gaussian blob at 8 dB, not a realistic slick. [Major]

**Reviewer concern.** 20/20 at 8 dB says nothing about near-threshold sensitivity.

**Response.** We re-ran the injection at six peak contrasts (5.0, 5.5, 6.0, 6.5,
7.0, 8.0 dB) using the same sites and pairs. Recovery is 20/20 at 8 dB, 19/20 at
7 dB, 17/20 at 6.5 dB, 13/20 at 6 dB, 6/20 at 5.5 dB, and 3/20 at 5 dB. So
detection probability falls to about 15 percent at the 5 dB threshold and 30
percent at 5.5 dB. This is now in §3.6, §4.2, §5, and Limitations, and it
replaces the single 8 dB point with a sensitivity curve.

## B. Statistical and inferential

### B6. p = 0.495 is failure to reject, not equivalence. [Blocker]

**Reviewer concern.** "Indistinguishable" is an overclaim; report the median
difference, its CI, and a formal equivalence test.

**Response.** Replaced "indistinguishable" with "did not differ detectably"
throughout. We now report the median difference (+125 m, bootstrap 95% CI −96 to
+476 m) and a two one-sided equivalence test: the median difference is equivalent at
a 500 m bound but not at 300 m. Power for a 500 m shift is 99.8 percent at the
full-sample level, so the aggregate null is informative (contrary to the
reviewer's concern). §3.7 and §4.3 updated.

### B7. Why does accounting for clustering increase the point estimate? [Major]

**Reviewer concern.** GLMM (1.62) > naive (1.31) is unusual; explain.

**Response.** We measured the mechanism directly. Acquisition frequency and
cluster propensity are positively correlated (Pearson r = 0.21, Spearman ρ = 0.32
across the 57 incidents), so incidents that contribute more acquisitions also
contribute more clusters. The GLMM estimates a within-incident (conditional)
quantity and removes incident-level baseline differences, which is why it exceeds
the acquisition-weighted naive ratio. We state this in §5 rather than asserting
the ratio "needs" the mixed model without explaining the direction.

### B8. The stratified p ≥ 0.161 minimum is not a null. [Major]

**Reviewer concern.** The terrestrial stratum's distance null (p = 0.568) rests on
11 control clusters; no power.

**Response.** We now report power per stratum. The aggregate test has 99.8 percent
power to detect a 500 m shift; the terrestrial stratum has 21 percent. We label
the terrestrial and swamp distance comparisons "descriptive only, insufficient n
for inferential test" in Table 2's note and in §4.3, and we no longer treat the
terrestrial distance p as informative.

### B9. The GLMM p < 0.001 uses a Wald test; check the model and overdispersion. [Major]

**Reviewer concern.** Check overdispersion; the Poisson GLMM may be misspecified.

**Response.** This is the most consequential correction. The cluster counts are
strongly overdispersed (variance-to-mean ratio 9.4; Pearson dispersion 9.3 from a
Poisson GLM). The GLMM's random intercept absorbs between-incident heterogeneity
but not within-incident overdispersion, so its Wald p < 0.001 is optimistic. We
added three dispersion-robust estimators: a Poisson GEE with sandwich errors
(IRR 1.54, p = 0.057), a negative-binomial GEE (1.52, p = 0.063), and a
negative-binomial model with incident fixed effects (1.44, p = 0.17). The point
estimates are stable and all exceed 1, but significance is estimator-dependent.
We therefore demote the temporal claim from "significant" to "directionally
consistent, marginal under the most defensible estimator." Reported in §3.7,
§4.3, §5, and the abstract. Python's statsmodels does not implement a
negative-binomial mixed model. The negative-binomial GEE (1.52, p = 0.063) and
the negative-binomial model with incident fixed effects (1.44, p = 0.17) bracket
the answer from either side; both are reported.

### B10. Why is the GEE the cross-check, not a co-equal test? [Major]

**Reviewer concern.** The GEE may be the better estimator here; its interval
includes 1.

**Response.** We agree and now present the GLMM, GEE, and negative-binomial
models as co-equal estimators (§3.7, §4.3), with the dispersion-robust GEE given
equal weight. Because the GEE interval includes 1, the temporal claim is stated
as marginal, not significant. We kept the GLMM as a listed estimator but no
longer as the sole source of the p-value.

### B11. No correction for multiple comparisons across the 15-setting grid. [Moderate]

**Reviewer concern.** Apply a Bonferroni threshold to the sensitivity grid.

**Response.** Added. No Mann-Whitney comparison reaches p < 0.05 (range 0.082 to
0.956), so no setting clears the conventional threshold, let alone the
Bonferroni-corrected 0.0033. We state this explicitly in §4.4, which strengthens
the spatial-stability claim.

## C. Measurement and design

### C12. The 14-day window produces mostly post-dispersal images. [Blocker]

**Reviewer concern.** Median post-incident gap is 6 days; slicks disperse in 1–3
days, so the window biases toward "no signal."

**Response.** We now address this head-on. We (a) state in §3.4 that the 14-day
window biases the spatial comparison toward no signal, (b) add a first-three-day
restriction as a sensitivity analysis (§4.5), and (c) keep the wide window as the
primary for comparability with prior work. The first-three-day subset raises the
temporal point estimate (IRR 2.05) but leaves the spatial null unchanged (median
1,861 m, p = 0.97), which is what a coordinate-level mismatch looks like even
before the oil has had time to disperse.

### C13. Is the 8–14 day baseline enough for a "clean" baseline? [Major]

**Reviewer concern.** The baseline may contain earlier spills or seasonal change.

**Response.** We justify the choice in §3.4: with a 12-day repeat cycle and a
14-day search window, a 20–30 day baseline is available only by skipping a closer
acquisition, trading a cleaner seasonal control for a weaker temporal one. We
acknowledge in Limitations that the baseline is not a seasonal control and may
contain earlier unrelated spills. We did not run a 20–30 day baseline because it
would discard the nearest pre-incident image; we state this rather than imply a
robustness check we did not perform.

### C14. AOI shape and truncation. [Major]

**Reviewer concern.** The paper says "radius" but max distance is 3,354 m, implying
a square.

**Response.** Correct. The AOI is a 5 km × 5 km square (2.5 km half-width, 3.5 km
at the corners); the observed maximum distance is 3,354 m, consistent with the
square geometry. We fixed "radius" to "half-width" throughout (§3.2, §3.4, §5,
§7, and the workflow in §5) and stated the censoring correctly.

### C15. The single-analyst visual inspection. [Major]

**Reviewer concern.** If the 0/63 result returns, address inter-rater reliability.

**Response.** We reinstated the result (§4.6) and state explicitly that a second
analyst was not available, that the inspection was blind to hypothesis, and that
the automated distance metric is the primary evidence. The limitation (previously
orphaned) now refers to the reinstated result.

## D. Data and sampling

### D16. Why do terrestrial incidents contribute more acquisitions? [Major]

**Reviewer concern.** Terrestrial acquisitions are overrepresented, weighting the
aggregate signal toward terrestrial.

**Response.** We checked. The apparent overrepresentation is an artifact of the
classification, not of acquisition frequency: a terrestrial acquisition is always
classed "unobservable terrestrial" regardless of wind, whereas open-water
acquisitions are split into observable or low-wind. Per-incident acquisition
counts are comparable (3.6 terrestrial over 29 incidents, 3.7 open water over 29, 3.6 swamp over 7). We state this
in §3.3 and confirm that the terrestrial stratum's high IRR is driven by 11
control clusters, which we now flag as low-power and descriptive only.

### D17. Volume ≥ 50 bbl is a NOSDRA-reported quantity. [Major]

**Reviewer concern.** Filtering on NOSDRA volume may select higher-profile
incidents with more accurate coordinates.

**Response.** We state this explicitly in §3.1: the 50-barrel filter uses
NOSDRA's own reported volume and therefore selects toward higher-volume,
higher-profile incidents most likely to have received careful JIV attention, so
the failure we document likely understates the coordinate error in the full
database. This turns the selection bias into a strength of the argument.

### D18. Why are 5 incidents classified UNKNOWN_HABITAT? [Moderate]

**Reviewer concern.** Explain the 5 unknown-habitat rows.

**Response.** Corrected and explained. At incident level there are 2 unknown-habitat
records, not 5: incident 32687 (early-2015, no SAR data) and 282326 (raw record
lacks a habitat field). The 5 unknown-habitat acquisitions in Table 1 all belong
to 282326. We fixed the incident-level habitat counts in §3.1 and Figure 1 (open
water 29, swamp 7, terrestrial 29, unknown 2) and explained the 5 acquisition rows
in §4.1.

### D19. State representation. [Moderate]

**Reviewer concern.** Which seven states; is one dominant?

**Response.** Stated in §3.1: Rivers 13, Bayelsa 13, Delta 11, Abia 11, Imo 10,
Edo 6, Akwa Ibom 3. Ondo and Cross River, which the NDDC also lists, contributed
no qualifying records; Akwa Ibom is thin (3). The result is effectively a
Bayelsa–Rivers–Delta–Abia–Imo study, and we say so.

## E. Positioning against prior work

### E20. Where does "2–4× more anomalies" come from? [Blocker]

**Reviewer concern.** The specific multiplier is uncited.

**Response.** The manuscript does not contain a "2–4×" figure; it says "a gap
between what the regulator records and what the surface shows," which we have
kept unquantified. We adopted the reviewer's stronger framing in the Introduction:
prior studies overstate their case because the comparison is invalid, and our
contribution is to show that and measure how it fails.

### E21. Is Oseni et al. (2026) real? [Blocker]

**Reviewer concern.** Verify the DOI; if real, engage it directly.

**Response.** Verified real (checked 2026-11-18 against publisher and index
records — Scopus, UWC Scholar). Oseni, Omosanya, Mosuro, Saka, Oludipe, and
Oshomoji, "Mapping persistent oil spill risk in the Niger Delta using Sentinel-1
SAR and environmental exposure indicators," Marine Pollution Bulletin 229, 119674
(2026), DOI 10.1016/j.marpolbul.2026.119674. We now engage it directly in Related
Work (§2): it maps persistent risk in the target journal and reports that
exposure extends beyond reported locations, and it inherits the
coordinate-accuracy assumption we test. We also verified Adebangbe et al. (2025b)
(Int. J. Digital Earth 18(1), 2448218; accepted 24 Dec 2024, published online
6 Jan 2025, so the DOI carries 2024 and the citation year 2025 is the publication
year) and O'Farrell et al. (2025) (Remote Sensing 17(3), 358). All three resolve
correctly.

### E22. What does "weak supervision" concretely mean here? [Major]

**Reviewer concern.** Is weak supervision proven for Niger Delta SAR?

**Response.** Added the caveat the reviewer requested (§2): weak supervision has
not, to our knowledge, been applied to Niger Delta SAR, so our recommendation is
a proposed framework, not a demonstrated improvement.

### E23. NOSDRA is unusable as masks — what is usable? [Major]

**Reviewer concern.** What replaces NOSDRA as pixel-level ground truth?

**Response.** Added a paragraph in §5 naming the alternatives: field-verified
slick polygons (scarce), industry-confirmed locations (not public), hand-annotated
optical slicks (cloud-limited), and independent operational products such as
SkyTruth's Cerulean (thin field validation in the delta). Until a field-verified
reference exists, the field has a measurement problem beyond NOSDRA, and the
correct posture is to report localization uncertainty rather than assume a
coordinate is a pixel.

## F. Minor academic points

### F24. Expected nearest-distance under uniform placement. [Moderate]

**Response.** Computed and reported (§4.3): the CSR median nearest distance is
about 1,356 m for the observed cluster densities, close to the reviewer's
~1.25 km. The observed coordinate-to-nearest (1,438 m) is comparable, and the
random-point null (1,674 m) is the relevant comparison for a non-uniform cluster
field.

### F25. State the polarization. [Moderate]

**Response.** Stated in §3.2: change detection used the VV band; VH co-polarization
was present in every acquisition (all 262 are VV,VH) but not used.

### F26. Report incidence-angle range. [Moderate]

**Response.** Reported in §3.2: scene-center incidence 39.0° for all acquisitions;
the IW swath spans roughly 29° to 46° across the image. The STAC metadata records
only the scene-center angle, so the swath range is nominal.

### F27. Is the 142357 example representative? [Moderate]

**Response.** Stated in §4.3: Incident 142357 (1,751 barrels) is near the upper
end of the sample (median 105 barrels) in the modal open-water habitat, and it is
representative of the majority of incidents that returned no signal near the
coordinate.

### F28. Remove "actually" and quantify "far more". [Cosmetic]

**Response.** "Actually" does not appear in the current draft. "Far more" is
replaced with "a gap between what the regulator records and what the surface
shows." The offset description "far larger than detector error" is retained where
it is literally supported (1,972 m vs 11.9 m).

### F29. Truncate to the first 3 days post-incident. [Moderate]

**Response.** Run and reported in §4.5: the first-three-day subset raises the
temporal point estimate (IRR 2.05) and leaves the spatial null unchanged (median
1,861 m, p = 0.97). The temporal signal is, if anything, concentrated near the
incident date, yet carries no localization.

### F30. Require ≥ 2 post-incident acquisitions per incident. [Moderate]

**Response.** Run and reported in §4.5: restricting to 45 incidents with at least
two post-incident acquisitions leaves the temporal estimate at IRR 1.52 and the
distance comparison unchanged (p = 0.43). The temporal signal is not an artifact
of single-acquisition incidents.
