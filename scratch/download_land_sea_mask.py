import cdsapi
c = cdsapi.Client()
c.retrieve(
    "reanalysis-era5-single-levels",
    {
        "product_type": ["reanalysis"],
        "variable": ["land_sea_mask"],
        "year": ["2020"], "month": ["01"], "day": ["01"],
        "time": ["00:00"],
        "area": [8.5, 3.5, 4.0, 9.5],
        "data_format": "netcdf",
    },
    "data/raw/era5_land_sea_mask.nc",
)
print("Saved data/raw/era5_land_sea_mask.nc")
