# Zemax reference output: twinkle_excitation

From the TWINKLE authors' repository (https://github.com/BrainCOGS/Microscope/tree/b9e40b9a5b3840203f54d78f5532f09e14fbfb07/zemax), exported with OpticStudio 22.2.1. Ground truth: do not edit. The `.svg` files are as supplied; each `.png` is a render of the SVG for the page.

| File | What it is |
|---|---|
| `FieldCurvatureAndFWHM_vs_angle.svg/png` | Axial focus offset, radial FWHM and axial FWHM of the two-photon PSF against galvo angle, -10 to +10 degrees in 0.5 degree steps |
| `PSF_xz_slices_vs_angle.svg/png` | xz PSF slices at 21 galvo angles |
| `PSF_onaxis_xy_xz.svg/png`, `PSF_onaxis_xy_7um_above_focus.svg/png` | On-axis PSF slices |
| `PSF_3D_isosurfaces.svg/png` | 3D isosurfaces of the on-axis PSF |
| `3DLayout_angle.png` | Zemax 3D layout close to the sample at several galvo angles |
| `plot_zmax.m`, `MATLABStandaloneApplication.m` | The authors' MATLAB scripts. The second drives the Zemax API: for each angle and each 0.1 µm step in z it sets the galvo tilt (and its opposite on the return break), moves the image plane and saves a Huygens PSF |
| `zemax_digitised.json` | The three scan curves read from the vertices of the first SVG. **Digitised, not Zemax numeric output** (calibration to about 0.01 µm) |

Notes: the PSF is the Huygens PSF squared (two-photon). The Zemax file stores the galvo angle as multi-configuration data (22 configurations).
