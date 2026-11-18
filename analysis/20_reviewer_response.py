#!/usr/bin/env python3
"""
Reviewer-response analyses for paper V2.

Computes the quantitative answers to the reviewer points that require new
statistics, all from existing interim CSVs (no TIF re-processing):

  A2   random-point null        : NOSDRA-coordinate distance vs uniform-random
                                  point distance to nearest cluster
  A3/F24 matched spatial null   : expected nearest-cluster distance under
                                  complete spatial randomness (CSR), analytic
                                  and simulated
  B6   bootstrap CI + TOST      : median difference and equivalence bounds
  B7   GLMM-vs-naive mechanism  : cluster count vs acquisition count per incident
  B8   per-stratum power        : sample sizes + simulated power for the MW test
  B9   overdispersion           : variance-to-mean, Pearson dispersion
  C14  AOI geometry             : square vs circle, observed max distance
  D16  acquisitions per habitat : per-incident and per-acquisition
  D17/D18/D19/F25/F26           : volume, states, unknown habitat, polarization,
                                  incidence angle
  F29  first-3-day truncation   : rate ratio + distance under tight window
  F30  >=2 post acq restriction : rate ratio + distance under incident filter
  A4   visual inspection        : 0/63 verdict + n_patches distribution

Every headline number in the paper is re-derived here as a regression guard.
Output: data/output/reviewer_response.json + a printed summary.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402

CAND_CSV = config.DATA_INTERIM / "anomaly_candidates.csv"
INSP_CSV = config.DATA_INTERIM / "inspection_done.csv"
OBS_CSV  = config.DATA_INTERIM / "observability_classes.csv"
DIFF_CSV = config.DATA_INTERIM / "per_acquisition_diff.csv"
META_CSV = config.DATA_INTERIM / "acquisition_metadata.csv"
SCORED_CSV = config.DATA_INTERIM / "scored_candidates.csv"
NOS_CSV  = config.DATA_INTERIM / "nosdra_original_subset.csv"
OUT_JSON = config.DATA_OUTPUT / "reviewer_response.json"

RNG = np.random.default_rng(42)

# AOI geometry (config.AOI_BUFFER_DEG = 0.0225 deg ~ 2.5 km half-width square).
M_PER_DEG_LAT = 111_320.0
HALF_WIDTH_M = 2500.0
AREA_KM2 = 25.0


def load():
    cand = pd.read_csv(CAND_CSV)
    insp = pd.read_csv(INSP_CSV)
    obs = pd.read_csv(OBS_CSV)
    diff = pd.read_csv(DIFF_CSV)
    meta = pd.read_csv(META_CSV)
    scored = pd.read_csv(SCORED_CSV)
    return cand, insp, obs, diff, meta, scored


def local_m_per_deg(lat):
    return M_PER_DEG_LAT * np.cos(np.radians(lat))


def nearest_cluster_dist_from_points(points_xy, clusters_xy):
    """Euclidean distance (m) from each point to nearest cluster. xy in meters."""
    if clusters_xy.shape[0] == 0:
        return np.full(points_xy.shape[0], np.nan)
    # small matrices; brute force is fine
    d = np.hypot(points_xy[:, 0][:, None] - clusters_xy[0][None, :],
                 points_xy[:, 1][:, None] - clusters_xy[1][None, :])
    return d.min(axis=1)


def to_xy(lat, lon, lat0, lon0):
    x = (lon - lon0) * local_m_per_deg(lat0)
    y = (lat - lat0) * M_PER_DEG_LAT
    return x, y


def csr_median_nearest(k, area_km2=AREA_KM2):
    """Median distance from a random point to nearest of k points under CSR."""
    if k <= 0:
        return np.nan
    lam = k / area_km2  # points per km^2
    # P(distance <= r) = 1 - exp(-pi * lam * r^2), r in km -> *1000 to meters
    r_km = np.sqrt(np.log(2.0) / (np.pi * lam))
    return r_km * 1000.0


def bootstrap_median_diff(post, ctrl, n_boot=20_000):
    """Bootstrap 95% CI for (post median - ctrl median)."""
    post = np.asarray(post); ctrl = np.asarray(ctrl)
    med = np.median(post) - np.median(ctrl)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        b = np.median(RNG.choice(post, size=post.size, replace=True)) \
            - np.median(RNG.choice(ctrl, size=ctrl.size, replace=True))
        boots[i] = b
    return med, float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def tost_medians(post, ctrl, bounds_m=(300, 500, 1000), n_boot=20_000):
    """Equivalence (TOST) on the median shift via bootstrap confidence bounds.

    Returns, per bound, whether the 90% CI of the median difference lies
    entirely inside (-bound, +bound). A 90% CI is used so that two one-sided
    tests at alpha=0.05 correspond to a 90% central interval.
    """
    post = np.asarray(post); ctrl = np.asarray(ctrl)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        boots[i] = (np.median(RNG.choice(post, size=post.size, replace=True))
                    - np.median(RNG.choice(ctrl, size=ctrl.size, replace=True)))
    out = {}
    for b in bounds_m:
        lo = float(np.percentile(boots, 5.0))
        hi = float(np.percentile(boots, 95.0))
        out[f"bound_{b}m"] = {
            "ci90_lower": round(lo, 1),
            "ci90_upper": round(hi, 1),
            "equivalent": bool(lo > -b and hi < b),
        }
    return out


def mw_power_sim(ctrl_dist, post_n, ctrl_n, shift_m=500.0, n_sim=2000):
    """Approximate power of a Mann-Whitney test to detect a `shift_m` location
    shift, using the empirical control distance distribution as the shape.

    Under the alternative, post distances are drawn from (control + shift_m);
    under the null both are drawn from control. Rejection at alpha=0.05 across
    `n_sim` replicates is the power.
    """
    ctrl_dist = np.asarray(ctrl_dist)
    ctrl_n = int(ctrl_n)
    post_n = int(post_n)
    rej = 0
    for _ in range(n_sim):
        a = RNG.choice(ctrl_dist, size=post_n, replace=True) + shift_m
        b = RNG.choice(ctrl_dist, size=ctrl_n, replace=True)
        p = sp_stats.mannwhitneyu(a, b, alternative="two-sided").pvalue
        rej += (p < 0.05)
    return rej / n_sim


def fit_glmm_irr(df):
    """Minimal Poisson GLMM (random intercept per incident); returns dict."""
    from statsmodels.genmod.bayes_mixed_glm import PoissonBayesMixedGLM
    d = df[["incident_id", "post", "n_clusters"]].dropna().copy()
    d["incident_id"] = d["incident_id"].astype(str)
    if d["incident_id"].nunique() < 3 or len(d) < 5:
        return None
    try:
        model = PoissonBayesMixedGLM.from_formula(
            "n_clusters ~ post", {"incident": "0 + C(incident_id)"}, d)
        res = model.fit_map()
    except Exception:
        return None
    fe = np.asarray(res.fe_mean).ravel()
    sd = np.asarray(res.fe_sd).ravel()
    coef, se = float(fe[1]), float(sd[1])
    return {
        "IRR": round(float(np.exp(coef)), 3),
        "CI_lower": round(float(np.exp(coef - 1.96 * se)), 3),
        "CI_upper": round(float(np.exp(coef + 1.96 * se)), 3),
        "p": round(float(2 * sp_stats.norm.sf(abs(coef / se))), 4),
        "n": int(len(d)),
        "n_incidents": int(d["incident_id"].nunique()),
    }


def build_acq_level(cand, obs, diff):
    diff2 = diff.merge(
        obs[["incident_id", "sar_date", "observability", "habitat_group"]],
        left_on=["incident_id", "target_date"],
        right_on=["incident_id", "sar_date"], how="left")
    diff2["observability"] = diff2["observability"].fillna("UNKNOWN_HABITAT")
    diff2["habitat_group"] = diff2["habitat_group"].fillna("unknown")
    cc = (cand.groupby(["incident_id", "target_date", "pre_incident"])
          .size().reset_index(name="n_clusters"))
    acq = diff2.merge(cc, on=["incident_id", "target_date", "pre_incident"],
                      how="left")
    acq["n_clusters"] = acq["n_clusters"].fillna(0).astype(int)
    acq["post"] = (~acq["pre_incident"]).astype(int)
    return acq


def main():
    cand, insp, obs, diff, meta, scored = load()

    R = {}  # results

    # ------------------------------------------------------------------ guard
    post = cand[~cand["pre_incident"]]
    ctrl = cand[cand["pre_incident"]]
    R["guard"] = {
        "n_clusters": int(len(cand)),
        "n_post_clusters": int(len(post)),
        "n_ctrl_clusters": int(len(ctrl)),
        "post_median_distance_m": round(float(post["distance_from_reported_m"].median()), 1),
        "ctrl_median_distance_m": round(float(ctrl["distance_from_reported_m"].median()), 1),
        "mann_whitney_p": round(float(sp_stats.mannwhitneyu(
            post["distance_from_reported_m"], ctrl["distance_from_reported_m"],
            alternative="two-sided").pvalue), 4),
        "max_observed_distance_m": round(float(cand["distance_from_reported_m"].max()), 1),
    }

    # ------------------------------------------------------- C14 AOI geometry
    R["aoi_geometry"] = {
        "half_width_m": HALF_WIDTH_M,
        "area_km2": AREA_KM2,
        "corner_distance_m": round(HALF_WIDTH_M * np.sqrt(2.0), 1),
        "max_observed_distance_m": round(float(cand["distance_from_reported_m"].max()), 1),
        "note": "AOI is a 5x5 km square (2.5 km half-width); paper says 'radius'",
    }

    # -------------------------------------------------- A2 random-point null
    # Observed: per-incident nearest-cluster distance to the reported coord.
    coord_lookup = {int(r["incident_id"]): (float(r["lat"]), float(r["lon"]))
                    for _, r in insp.iterrows()}
    post_groups = {iid: g for iid, g in post.groupby("incident_id")}

    obs_nearest = []      # distance from reported coord to nearest cluster, per incident
    obs_percluster = []   # per-cluster distance (paper's actual metric)
    null_nearest = []     # distance from random point to nearest cluster, per incident
    csr_analytic = []     # CSR median nearest per incident
    n_rand_per_inc = 500

    for iid, g in post_groups.items():
        if iid not in coord_lookup:
            continue
        lat0, lon0 = coord_lookup[iid]
        cx, cy = to_xy(g["centroid_lat"].to_numpy(), g["centroid_lon"].to_numpy(),
                       lat0, lon0)
        clusters_xy = np.vstack([cx, cy])
        # observed: nearest cluster to the reported coordinate (origin)
        obs_nearest.append(float(np.hypot(cx, cy).min()))
        obs_percluster.extend(np.hypot(cx, cy).tolist())
        csr_analytic.append(csr_median_nearest(len(g)))
        # null: random points uniform in the square
        rx = RNG.uniform(-HALF_WIDTH_M, HALF_WIDTH_M, n_rand_per_inc)
        ry = RNG.uniform(-HALF_WIDTH_M, HALF_WIDTH_M, n_rand_per_inc)
        d = nearest_cluster_dist_from_points(
            np.column_stack([rx, ry]), clusters_xy)
        null_nearest.extend(d[~np.isnan(d)].tolist())

    obs_nearest = np.array(obs_nearest)
    null_nearest = np.array(null_nearest)
    csr_analytic = np.array(csr_analytic)

    R["A2_random_point_null"] = {
        "obs_nearest_median_m": round(float(np.median(obs_nearest)), 1),
        "obs_nearest_n": int(obs_nearest.size),
        "null_nearest_median_m": round(float(np.median(null_nearest)), 1),
        "null_nearest_p05_m": round(float(np.percentile(null_nearest, 5)), 1),
        "null_nearest_p95_m": round(float(np.percentile(null_nearest, 95)), 1),
        "obs_percluster_median_m": round(float(np.median(obs_percluster)), 1),
        "note": "obs_nearest = reported coord -> nearest cluster per incident; "
                "null = random point -> nearest cluster; obs_percluster is the "
                "paper's actual per-cluster metric",
    }

    R["A3_CSR_expected_nearest"] = {
        "csr_median_nearest_median_m": round(float(np.median(csr_analytic)), 1),
        "csr_median_nearest_mean_m": round(float(np.mean(csr_analytic)), 1),
        "csr_median_nearest_range_m": [round(float(np.min(csr_analytic)), 1),
                                       round(float(np.max(csr_analytic)), 1)],
        "formula": "median r = sqrt(ln2 / (pi * k / 25 km^2)) * 1000 m",
    }

    # -------------------------------------------------------- B6 bootstrap + TOST
    pd_post = post["distance_from_reported_m"].to_numpy()
    pd_ctrl = ctrl["distance_from_reported_m"].to_numpy()
    med, lo, hi = bootstrap_median_diff(pd_post, pd_ctrl)
    R["B6_median_difference"] = {
        "point_estimate_m": round(float(med), 1),
        "bootstrap_ci95_lower_m": round(lo, 1),
        "bootstrap_ci95_upper_m": round(hi, 1),
    }
    R["B6_tost_medians"] = tost_medians(pd_post, pd_ctrl)

    # --------------------------------------------------------- B8 power per stratum
    strata_power = {}
    for name, df in {
        "All QC-passing": None,
    }.items():
        pass  # strata handled below from observability join

    # per-stratum cluster counts + power (using cluster-level distance medians)
    power_rows = {}
    power_rows["All QC-passing"] = {
        "post_n": int(len(pd_post)), "ctrl_n": int(len(pd_ctrl)),
        "post_median_m": round(float(np.median(pd_post)), 1),
        "ctrl_median_m": round(float(np.median(pd_ctrl)), 1),
    }
    # stratum definitions from observability classes
    acq = build_acq_level(cand, obs, diff)
    stratum_obs = {
        "Observable (OW+Swamp)": ["OBSERVABLE_OPEN_WATER", "OBSERVABLE_SWAMP"],
        "Open water only": ["OBSERVABLE_OPEN_WATER"],
        "Terrestrial": ["UNOBSERVABLE_TERRESTRIAL"],
        "Other": ["UNOBSERVABLE_LOW_WIND", "UNOBSERVABLE_RAIN", "UNKNOWN_HABITAT"],
    }
    cand_obs = cand.merge(
        obs[["incident_id", "sar_date", "observability"]],
        left_on=["incident_id", "target_date"], right_on=["incident_id", "sar_date"],
        how="left")
    cand_obs["observability"] = cand_obs["observability"].fillna("UNKNOWN_HABITAT")

    for name, classes in stratum_obs.items():
        sub = cand_obs[cand_obs["observability"].isin(classes)]
        p = sub[~sub["pre_incident"]]["distance_from_reported_m"]
        c = sub[sub["pre_incident"]]["distance_from_reported_m"]
        power_rows[name] = {
            "post_n": int(p.size), "ctrl_n": int(c.size),
            "post_median_m": round(float(p.median()), 1) if p.size else None,
            "ctrl_median_m": round(float(c.median()), 1) if c.size else None,
        }
    R["B8_stratum_sample_sizes"] = power_rows

    # power to detect a 500 m location shift (empirical control shape)
    R["B8_power"] = {
        "power_500m_shift_all": round(
            mw_power_sim(pd_ctrl, len(pd_post), len(pd_ctrl), shift_m=500.0), 3),
        "power_500m_shift_terrestrial": round(
            mw_power_sim(cand_obs[(cand_obs["observability"] == "UNOBSERVABLE_TERRESTRIAL")
                                  & (cand_obs["pre_incident"])]["distance_from_reported_m"],
                         power_rows["Terrestrial"]["post_n"],
                         power_rows["Terrestrial"]["ctrl_n"], shift_m=500.0), 3),
        "note": "power to reject the null of equal distance distributions when "
                "post is a 500 m location shift of control (empirical shape)",
    }

    # ------------------------------------------- B7 GLMM-vs-naive mechanism
    per_inc = acq.groupby("incident_id").agg(
        n_acq=("n_clusters", "size"),
        n_clusters=("n_clusters", "sum"),
        n_post=("post", "sum"),
    )
    R["B7_mechanism"] = {
        "corr_acq_vs_clusters": round(float(
            per_inc["n_acq"].corr(per_inc["n_clusters"])), 3),
        "spearman_acq_vs_clusters": round(float(
            per_inc["n_acq"].corr(per_inc["n_clusters"], method="spearman")), 3),
        "n_incidents": int(len(per_inc)),
        "note": "if positive, incidents with more acquisitions contribute more "
                "clusters, biasing the naive per-acquisition ratio downward",
    }

    # ------------------------------------------------------- B9 overdispersion
    vmr = float(acq["n_clusters"].var() / acq["n_clusters"].mean())
    # Pearson dispersion from a Poisson GLM (no random effect)
    try:
        from statsmodels.genmod.generalized_linear_model import GLM
        from statsmodels.genmod.families import Poisson, NegativeBinomial
        import statsmodels.api as sm
        glm = GLM(acq["n_clusters"], sm.add_constant(acq["post"]),
                  family=Poisson()).fit()
        pearson = float(glm.pearson_chi2 / glm.df_resid)
        # Negative binomial as an overdispersion-robust cross-check
        nb = GLM(acq["n_clusters"], sm.add_constant(acq["post"]),
                 family=NegativeBinomial()).fit()
        nb_coef = float(nb.params["post"])
        nb_se = float(nb.bse["post"])
        R["B9_overdispersion"] = {
            "variance_to_mean_ratio": round(vmr, 3),
            "poisson_glm_pearson_dispersion": round(pearson, 3),
            "negbin_irr": round(float(np.exp(nb_coef)), 3),
            "negbin_ci_lower": round(float(np.exp(nb_coef - 1.96 * nb_se)), 3),
            "negbin_ci_upper": round(float(np.exp(nb_coef + 1.96 * nb_se)), 3),
            "negbin_p": round(float(2 * sp_stats.norm.sf(abs(nb_coef / nb_se))), 4),
            "note": "dispersion > 1 indicates overdispersion; negative binomial "
                    "cross-check relaxes the Poisson mean=variance assumption",
        }
    except Exception as e:
        R["B9_overdispersion"] = {"error": str(e), "variance_to_mean_ratio": round(vmr, 3)}

    # ------------------------------------------------- D16 acquisitions per habitat
    insp_hab = insp[["incident_id", "habitat_group"]].dropna(subset=["habitat_group"])
    hab_map = dict(zip(insp_hab["incident_id"], insp_hab["habitat_group"]))
    diff["habitat_group"] = diff["incident_id"].map(hab_map).fillna("unknown")
    d16 = diff.groupby("habitat_group").agg(
        n_incidents=("incident_id", "nunique"),
        n_acquisitions=("incident_id", "size"),
    )
    d16["acq_per_incident"] = (d16["n_acquisitions"] / d16["n_incidents"]).round(2)
    R["D16_acquisitions_per_habitat"] = d16.reset_index().to_dict(orient="records")

    # ----------------------------------------------------- D17/D18/D19 states
    R["D19_states"] = insp["final_state"].value_counts().to_dict()
    R["D17_volume"] = {
        "n": int(insp["volume"].notna().sum()),
        "min_bbl": float(insp["volume"].min()),
        "median_bbl": float(insp["volume"].median()),
        "max_bbl": float(insp["volume"].max()),
        "note": "volume is the NOSDRA-reported quantity used to filter >=50 bbl",
    }
    unk = insp[insp["habitat_group"] == "unknown"]
    R["D18_unknown_habitat"] = {
        "n_incidents": int(len(unk)),
        "incident_ids": unk["incident_id"].astype(str).tolist(),
    }
    R["habitat_incident_level"] = insp["habitat_group"].fillna("unknown").value_counts().to_dict()

    # --------------------------------------------------------- F25 / F26
    R["F25_polarization"] = meta["polarization"].value_counts().to_dict()
    R["F26_incidence_angle"] = {
        "center_angle_deg": round(float(meta["incidence_angle"].mean()), 2),
        "range_deg": [round(float(meta["incidence_angle"].min()), 2),
                      round(float(meta["incidence_angle"].max()), 2)],
        "note": "STAC view:incidence_angle is the scene-center angle; the IW "
                "swath spans ~29-46 deg",
    }

    # --------------------------------------------------- F29 first-3-day truncation
    post3 = cand[(~cand["pre_incident"]) & (cand["days_after_incident"] <= 3)]
    ctrl_all = cand[cand["pre_incident"]]
    R["F29_first3days"] = {
        "n_post_clusters": int(len(post3)),
        "n_post_images": int(post3.groupby(["incident_id", "target_date"]).ngroups),
        "post_median_distance_m": round(float(post3["distance_from_reported_m"].median()), 1),
        "ctrl_median_distance_m": round(float(ctrl_all["distance_from_reported_m"].median()), 1),
        "mann_whitney_p": round(float(sp_stats.mannwhitneyu(
            post3["distance_from_reported_m"], ctrl_all["distance_from_reported_m"],
            alternative="two-sided").pvalue), 4),
    }
    # GLMM IRR on the <=3-day subset (acquisition level)
    idate = insp.set_index("incident_id")["date"].to_dict()
    acq["days_after"] = (pd.to_datetime(acq["target_date"])
                         - acq["incident_id"].map(idate).apply(pd.to_datetime)).dt.days
    acq3 = acq[(acq["post"] == 0) | (acq["days_after"] <= 3)].copy()
    R["F29_first3days"]["glmm_irr"] = fit_glmm_irr(acq3)

    # --------------------------------------------------- F30 >=2 post acq restriction
    post_per_inc = acq.groupby("incident_id")["post"].sum()
    eligible = post_per_inc[post_per_inc >= 2].index
    acq2 = acq[acq["incident_id"].isin(eligible)].copy()
    R["F30_min2post"] = {
        "n_incidents_eligible": int(len(eligible)),
        "n_acquisitions": int(len(acq2)),
        "glmm_irr": fit_glmm_irr(acq2),
    }
    c2 = cand[cand["incident_id"].isin(eligible)]
    p2 = c2[~c2["pre_incident"]]["distance_from_reported_m"]
    cc2 = c2[c2["pre_incident"]]["distance_from_reported_m"]
    if p2.size and cc2.size:
        R["F30_min2post"]["post_median_distance_m"] = round(float(p2.median()), 1)
        R["F30_min2post"]["ctrl_median_distance_m"] = round(float(cc2.median()), 1)
        R["F30_min2post"]["mann_whitney_p"] = round(float(sp_stats.mannwhitneyu(
            p2, cc2, alternative="two-sided").pvalue), 4)

    # -------------------------------------------------------- A4 visual inspection
    R["A4_visual_inspection"] = {
        "n_incidents": int(len(insp)),
        "n_with_verdict_spill": int(insp["verdict"].notna().sum()),
        "n_no_spill": int(insp["verdict"].isna().sum()),
        "n_patches_distribution": insp["n_patches"].value_counts().sort_index().to_dict(),
        "n_incidents_with_0_patches": int((insp["n_patches"] == 0).sum()),
        "note": "verdict empty for all -> 0 coherent spill signatures; n_patches "
                "counts incidental dark patches (channels etc.), not spills",
    }

    # ------------------------------------------------------------- write out
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(R, f, indent=2, default=str)

    print(json.dumps(R, indent=2, default=str))
    print(f"\nSaved to {OUT_JSON}")


if __name__ == "__main__":
    main()
