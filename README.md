
<div style="text-align:center">
<img src="SciQLop/resources/icons/SciQLop.png" alt="sciqlop_logo" style="width: 200px;"/>
<br /><br />
<img src="pictures/sciqlop_screenshot.png" alt="sciqlop_logo" style="width: 80%;"/>
</div>



# Overview

**SciQLOP** (**SCI**entific **Q**t application for **L**earning from **O**bservations of **P**lasmas) is a powerful and user-friendly tool designed for the visualization and analysis of in-situ space plasma data. The software has been developed to address the technical challenges that arise from the high time resolution required by modern plasma measurements. It is capable of plotting millions of data points without compromising on interactivity, ensuring that users can scroll, zoom, move, and export plots with ease.

One of the key features of SciQLOP is its ability to abstract the manipulation of physics data, making it accessible to users with different levels of expertise. The software also provides contextual features such as coordinate transforms and physical quantity extraction from data.

Keeping SciQLOP lightweight and intuitive has been a top priority during the software's development, making it both usable and competitive. By balancing advanced graphical features with a simple and streamlined GUI, SciQLOP delivers an exceptional user experience that sets it apart from other software tools in the field.

If you are looking for a reliable and powerful tool for analyzing space plasma data, SciQLOP is an excellent choice. With its intuitive interface and advanced features, it offers a seamless workflow that can save you time and effort. Download SciQLOP today and experience the benefits for yourself!


## How to install SciQLop

Since SciQLop depends on specific versions of PySide6 you should use a dedicated virtualenv for SciQLop to avoid any conflict
with any other Python package already installed in your system.

- Using releases from PyPi
```Bash
python -m pip install sciqlop
```
- Using the latest code from GitHub
```Bash
python -m pip install git+https://github.com/SciQLop/SciQLop
```

Once installed the sciqlop launcher should be in your PATH and you should be able to start SciQLop from your terminal.

## Experimental Python API Examples:

The following API examples are for early adopters and will likely change a bit in the future!

- Creating plot panels:
```python
from SciQLop.backend import TimeRange
from datetime import datetime

# all plots are stacked
p = main_window.new_plot_panel()
p.time_range = TimeRange(datetime(2015,10,22,6,4,30).timestamp(), datetime(2015,10,22,6,6,0).timestamp())
p.plot("speasy/cda/MMS/MMS1/FGM/MMS1_FGM_BRST_L2/mms1_fgm_b_gsm_brst_l2")
p.plot("speasy/cda/MMS/MMS1/DIS/MMS1_FPI_BRST_L2_DIS_MOMS/mms1_dis_bulkv_gse_brst")
p.plot("speasy/cda/MMS/MMS1/DIS/MMS1_FPI_BRST_L2_DIS_MOMS/mms1_dis_energyspectr_omni_brst")

# tha_peif_sc_pot and tha_peif_en_eflux will share the same plot 
p2 = main_window.new_plot_panel()
p2.plot("speasy/cda/THEMIS/THA/L2/THA_L2_ESA/tha_peif_en_eflux")
p2.plots[0].plot("speasy/cda/THEMIS/THA/L2/THA_L2_ESA/tha_peif_sc_pot")
p2.plot("speasy/cda/THEMIS/THA/L2/THA_L2_ESA/tha_peif_velocity_dsl")
```
> **_NOTE:_**  An easy way to get product paths, is to drag a product from Products  Tree to any text zone or even your Python terminal.

- Custom products:

```python
from datetime import datetime

import numpy as np

from SciQLop.backend.pipelines_model.easy_provider import EasyVector, EasyScalar


# The following functions can do anything from loading data from a file to any complex computation, they should not 
# block the GUI since they will be run in background.

def my_vect(start: datetime, stop: datetime) -> (np.ndarray, np.ndarray):
    x = np.arange(start.timestamp(), stop.timestamp(), 0.1) * 1.
    y = np.empty((len(x), 3))
    y[:, 0] = np.cos(x / 100.) * 10.
    y[:, 1] = np.cos((x + 100) / 100.) * 10.
    y[:, 2] = np.cos((x + 200) / 100.) * 10.
    return x, y


def my_scalar(start: datetime, stop: datetime) -> (np.ndarray, np.ndarray):
    x = np.arange(start.timestamp(), stop.timestamp(), 0.1) * 1.
    y = np.empty((len(x), 1))
    y[:, 0] = np.cos(x / 100.) * 10.
    return x, y


my_vector_provider = EasyVector(path='some_root_folder/my_hello_world_vector', get_data_callback=my_vect,
                                components_names=["x", "y", "z"], metadata={})
my_scalar_provider = EasyScalar(path='some_other_root_folder/my_hello_world_scalar', get_data_callback=my_scalar,
                                component_name="x", metadata={})
```

## How to contribute

Contact sciqlop@lpp.polytechnique.fr
